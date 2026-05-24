from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from live.monitoring import LiveDriftDetector, LiveHealthScorer, LiveMetricsCollector, LiveStateStore
from live.paper_engine import PaperTradingEngine
from webhook.models import TradingViewAlertPayload
from webhook.storage import WebhookStorage


class WebhookTradingCoordinator:
    def __init__(
        self,
        db_path: str = "memory/webhook/webhook.db",
        report_dir: str = "reports/webhook",
        log_dir: str = "logs/webhook",
        state_dir: str = "memory/webhook_state",
        max_age_seconds: int = 300,
        secret_token: Optional[str] = None,
        logger: Any = None,
    ) -> None:
        self.logger = logger
        self.secret_token = secret_token
        self.max_age_seconds = int(max_age_seconds)
        self.storage = WebhookStorage(db_path=db_path, alert_csv=f"{log_dir}/alerts.csv", error_csv=f"{log_dir}/errors.csv", report_dir=report_dir)
        self.engine = PaperTradingEngine(logger=logger)
        self.metrics = LiveMetricsCollector(logger=logger)
        self.health = LiveHealthScorer(logger=logger)
        self.drift = LiveDriftDetector()
        self.state_store = LiveStateStore(state_dir, logger=logger)
        self.last_alert_time: Optional[datetime] = None
        self.last_alert_hash: Optional[str] = None
        self._recover_from_snapshot()

    def _recover_from_snapshot(self) -> None:
        snapshot = self.state_store.load_latest_snapshot()
        if not snapshot:
            return
        engine_state = snapshot.get("engine_state")
        if engine_state is not None:
            try:
                self.engine.restore(engine_state)
                self.logger and self.logger.info("Recovered webhook engine state from snapshot.")
            except Exception:
                self.logger and self.logger.exception("Failed to restore webhook engine state from snapshot.")

    def _validate_age(self, alert: TradingViewAlertPayload) -> None:
        age = datetime.now(timezone.utc) - alert.timestamp.astimezone(timezone.utc)
        if age > timedelta(seconds=self.max_age_seconds):
            raise ValueError(f"Alert is too old: {age.total_seconds():.0f} seconds")
        if age < -timedelta(days=1):
            raise ValueError("Alert timestamp is more than one day in the future.")

    def _compute_alert_hash(self, alert: TradingViewAlertPayload) -> str:
        canonical = {
            "symbol": alert.symbol,
            "timeframe": alert.timeframe,
            "signal": alert.signal,
            "strategy_name": alert.strategy_name,
            "timestamp": alert.timestamp.isoformat(),
            "price": alert.price,
            "strategy_parameters": alert.strategy_parameters,
            "risk_settings": alert.risk_settings.dict() if alert.risk_settings else {},
        }
        payload_text = json.dumps(canonical, sort_keys=True, default=str)
        return hashlib.sha256(payload_text.encode("utf-8")).hexdigest()

    def _map_alert_to_signal(self, alert: TradingViewAlertPayload) -> Dict[str, Any]:
        signal = alert.signal
        if signal == "LONG":
            return {
                "side": 1,
                "order_type": alert.order_type or "market",
                "limit_price": alert.limit_price,
                "stop_price": alert.stop_price,
                "size_override": alert.strategy_parameters.get("size_override"),
            }
        if signal == "SHORT":
            return {
                "side": -1,
                "order_type": alert.order_type or "market",
                "limit_price": alert.limit_price,
                "stop_price": alert.stop_price,
                "size_override": alert.strategy_parameters.get("size_override"),
            }
        if signal == "CLOSE":
            return {
                "side": 0,
                "order_type": "market",
                "size_override": None,
            }
        if signal == "STOP":
            direction = 1
            if self.engine.position is not None:
                direction = self.engine.position.direction
            if alert.direction == "SHORT":
                direction = -1
            return {
                "side": direction,
                "order_type": "stop",
                "stop_price": alert.stop_price or alert.price,
                "size_override": None,
            }
        raise ValueError(f"Unsupported signal: {signal}")

    def process_alert(self, alert: TradingViewAlertPayload) -> Dict[str, Any]:
        self._validate_age(alert)
        alert_hash = self._compute_alert_hash(alert)
        if self.storage.is_duplicate_alert(alert_hash):
            raise ValueError("Duplicate alert detected")

        if self.last_alert_hash == alert_hash:
            raise ValueError("Duplicate replay attempt detected")

        if self.last_alert_time and alert.timestamp <= self.last_alert_time:
            raise ValueError("Alert timestamp must be newer than the last received alert")

        alert_payload = alert.dict(by_alias=True)
        alert_payload["timestamp"] = alert.timestamp.isoformat()
        alert_id = self.storage.insert_alert(alert_payload, alert_hash)
        self.last_alert_time = alert.timestamp
        self.last_alert_hash = alert_hash

        if alert.strategy_parameters:
            self.engine.strategy_parameters.update(alert.strategy_parameters)
            self.engine._bind_strategy_parameters()
        if alert.risk_settings:
            self.engine.risk_management.update(alert.risk_settings.dict(exclude_none=True))

        signal_payload = self._map_alert_to_signal(alert)
        order = self.engine.process_signal(signal_payload, timestamp=alert.timestamp)

        candle = {
            "timestamp": alert.timestamp,
            "open": alert.price,
            "high": alert.price,
            "low": alert.price,
            "close": alert.price,
            "volume": 0.0,
        }
        self.engine.on_market_candle(candle, latency_ms=0.0, timestamp=alert.timestamp)

        if order is not None:
            self.metrics.record_order()
            self.storage.insert_execution(alert_id, "order_created", order.to_dict())

        self.metrics.record_signal()
        self.metrics.record_execution()

        self.checkpoint()

        return {
            "alert_id": alert_id,
            "alert_hash": alert_hash,
            "order_created": order is not None,
            "balance": float(self.engine.balance),
            "equity": float(self.engine.equity_curve[-1]) if self.engine.equity_curve else float(self.engine.balance),
        }

    def checkpoint(self) -> None:
        snapshot = {
            "engine_state": self.engine.snapshot(),
            "metadata": {
                "snapshot_at": datetime.now(timezone.utc).isoformat(),
            },
        }
        self.state_store.save_snapshot(snapshot)
        metrics_summary = self.metrics.export_summary()
        self.state_store.save_metrics(metrics_summary)
        health_summary = self.health.compute_score(self.engine.get_state(), metrics_summary)
        self.state_store.save_health(health_summary)
        self.storage.insert_metrics(metrics_summary)
        self.storage.dump_json_report("webhook_state", {
            "engine_state": self.engine.get_state(),
            "metrics": metrics_summary,
            "health": health_summary,
            "last_alert_time": self.last_alert_time.isoformat() if self.last_alert_time else None,
        })
        self.drift.update_baseline({
            "latency": metrics_summary.get("latency", {}),
            "drawdown": self.engine.open_drawdown,
            "executions": metrics_summary.get("executions", 0),
        })

    def get_health(self) -> Dict[str, Any]:
        metrics_summary = self.metrics.export_summary()
        return self.health.compute_score(self.engine.get_state(), metrics_summary)

    def get_metrics(self) -> Dict[str, Any]:
        return self.metrics.export_summary()

    def get_status(self) -> Dict[str, Any]:
        return {
            "engine_state": self.engine.get_state(),
            "metrics": self.get_metrics(),
            "health": self.get_health(),
            "last_alert_time": self.last_alert_time.isoformat() if self.last_alert_time else None,
        }
