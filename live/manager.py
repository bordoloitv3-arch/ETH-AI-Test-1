from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock
from typing import Any, Callable, Dict, Optional

from live.binance_stream import BinanceFuturesMarketStream
from live.monitoring import (
    LiveDriftDetector,
    LiveHealthScorer,
    LiveMetricsCollector,
    LiveStateStore,
)
from live.paper_engine import PaperTradingEngine


SignalCallback = Callable[[Dict[str, Any], PaperTradingEngine], Any]


class LiveTradingCoordinator:
    def __init__(
        self,
        symbol: str = "ETHUSDT",
        interval: str = "1m",
        strategy_parameters: Optional[Dict[str, Any]] = None,
        pine_config: Optional[Dict[str, Any]] = None,
        risk_management: Optional[Dict[str, Any]] = None,
        signal_callback: Optional[SignalCallback] = None,
        logger: Any = None,
        state_directory: str = "memory/live_state",
        checkpoint_interval: int = 1,
        enable_prometheus: bool = False,
        prometheus_port: int = 8000,
        baseline_metrics: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.logger = logger
        self.stream = BinanceFuturesMarketStream(symbol=symbol, interval=interval, logger=logger)
        self.engine = PaperTradingEngine(
            strategy_parameters=strategy_parameters,
            pine_config=pine_config,
            risk_management=risk_management,
            logger=logger,
        )
        self.signal_callback = signal_callback
        self.state_store = LiveStateStore(state_directory, logger=logger)
        self.metrics = LiveMetricsCollector(logger=logger, enable_prometheus=enable_prometheus, prometheus_port=prometheus_port)
        self.health = LiveHealthScorer(logger=logger)
        self.drift = LiveDriftDetector(baseline_metrics=baseline_metrics)
        self.checkpoint_interval = max(int(checkpoint_interval), 1)
        self.checkpoint_counter = 0
        self._lock = Lock()
        self._bind_stream_callbacks()
        self._recover_from_snapshot()

    def _bind_stream_callbacks(self) -> None:
        self.stream.register_callback("kline", self._on_kline)
        self.stream.register_callback("trade", self._on_trade)
        self.stream.register_callback("depth", self._on_depth)
        self.stream.register_callback("watchdog_timeout", self._on_watchdog_timeout)
        self.stream.register_callback("reconnect", self._on_reconnect)

    def start(self) -> None:
        self.stream.start()

    def stop(self) -> None:
        self.stream.stop()

    def _on_kline(self, data: Dict[str, Any]) -> None:
        with self._lock:
            self.metrics.record_event("kline")
            if self.signal_callback is not None:
                try:
                    signal = self.signal_callback(data, self.engine)
                    if signal is not None:
                        order = self.engine.process_signal(signal, data.get("start_time") or datetime.now(timezone.utc))
                        if order is not None:
                            self.metrics.record_signal()
                            self.metrics.record_order()
                except Exception:
                    if self.logger:
                        self.logger.exception("Live signal callback failed.")
            self.engine.on_market_candle(
                {
                    "start_time": data.get("start_time"),
                    "open": data.get("open"),
                    "high": data.get("high"),
                    "low": data.get("low"),
                    "close": data.get("close"),
                    "volume": data.get("volume"),
                },
                latency_ms=data.get("latency_ms"),
                timestamp=data.get("start_time"),
            )
            self.metrics.record_latency(data.get("latency_ms"))
            self._checkpoint()

    def _on_trade(self, data: Dict[str, Any]) -> None:
        event = {
            "timestamp": data.get("trade_time").isoformat() if data.get("trade_time") else datetime.now(timezone.utc).isoformat(),
            "event": "trade_tick",
            "price": data.get("price"),
            "quantity": data.get("quantity"),
            "buyer_is_maker": data.get("buyer_is_maker"),
        }
        self.engine.execution_log.append(event)
        self.metrics.record_event("trade")

    def _on_depth(self, data: Dict[str, Any]) -> None:
        event = {
            "timestamp": data.get("received_at").isoformat() if data.get("received_at") else datetime.now(timezone.utc).isoformat(),
            "event": "order_book",
            "bids": data.get("bids"),
            "asks": data.get("asks"),
        }
        self.engine.execution_log.append(event)
        self.metrics.record_event("depth")

    def _on_watchdog_timeout(self, data: Dict[str, Any]) -> None:
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": "watchdog_timeout",
            "details": data,
        }
        self.engine.execution_log.append(event)
        self.metrics.record_event("watchdog_timeout")

    def _on_reconnect(self, data: Dict[str, Any]) -> None:
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": "reconnect",
            "details": data,
        }
        self.engine.execution_log.append(event)
        self.metrics.record_event("reconnect")

    def _recover_from_snapshot(self) -> None:
        snapshot = self.state_store.load_latest_snapshot()
        if snapshot is None:
            return
        engine_snapshot = snapshot.get("engine_state") if isinstance(snapshot, dict) else None
        if engine_snapshot:
            try:
                self.engine.restore(engine_snapshot)
                self.logger and self.logger.info("Recovered live engine state from snapshot.")
                self.recovery_loaded = True
            except Exception:
                if self.logger:
                    self.logger.exception("Failed to restore live engine state from snapshot.")

    def _build_live_snapshot(self) -> Dict[str, Any]:
        return {
            "engine_state": self.engine.snapshot(),
            "stream_state": {
                "connection_status": self.stream.connection_status,
                "reconnect_count": self.stream.reconnect_count,
                "latency_ms": self.stream.latency_ms,
                "url": self.stream.url,
            },
            "metadata": {
                "snapshot_at": datetime.now(timezone.utc).isoformat(),
                "symbol": self.stream.symbol,
                "interval": self.stream.interval,
            },
        }

    def _checkpoint(self) -> None:
        self.checkpoint_counter += 1
        if self.checkpoint_interval <= 0 or self.checkpoint_counter % self.checkpoint_interval != 0:
            return
        try:
            snapshot = self._build_live_snapshot()
            self.state_store.save_snapshot(snapshot)
            self.metrics.mark_snapshot()
            metrics_summary = self.metrics.export_summary()
            self.state_store.save_metrics(metrics_summary)
            health_summary = self.health.compute_score(self.engine.get_state(), metrics_summary)
            self.state_store.save_health(health_summary)
            self.drift.update_baseline({
                "latency": metrics_summary.get("latency", {}),
                "drawdown": self.engine.open_drawdown,
                "executions": metrics_summary.get("executions", 0),
            })
        except Exception:
            if self.logger:
                self.logger.exception("Failed to checkpoint live trading state.")

    def get_live_report(self) -> Dict[str, Any]:
        state = self.engine.get_state()
        metrics_summary = self.metrics.export_summary()
        health_summary = self.health.compute_score(state, metrics_summary)
        drift_report = self.drift.evaluate(state, metrics_summary)
        return {
            "connection_status": self.stream.connection_status,
            "stream_url": self.stream.url,
            "reconnect_count": self.stream.reconnect_count,
            "latency_ms": self.stream.latency_ms,
            "engine_state": state,
            "metrics_summary": metrics_summary,
            "health_summary": health_summary,
            "drift_report": drift_report,
            "persistence": {
                "snapshot_path": str(self.state_store.snapshot_path),
                "metrics_path": str(self.state_store.metrics_path),
                "health_path": str(self.state_store.health_path),
            },
        }
