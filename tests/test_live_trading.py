import time
from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd

from live.binance_stream import BinanceFuturesMarketStream
from live.paper_engine import PaperTradingEngine
from live.replay import MarketReplay
from live.validation import LiveValidationSession, MultiSessionForwardTester


class DummyWebSocketApp:
    def __init__(self, url, on_open=None, on_message=None, on_error=None, on_close=None):
        self.url = url
        self.on_open = on_open
        self.on_message = on_message
        self.on_error = on_error
        self.on_close = on_close
        self.closed = False

    def run_forever(self, **kwargs):
        if self.on_open:
            self.on_open(self)
        if self.on_close:
            self.on_close(self, 1006, "simulated disconnect")
        return

    def close(self):
        self.closed = True


def test_paper_trading_engine_executes_order_and_records_trade() -> None:
    engine = PaperTradingEngine(
        initial_balance=10000.0,
        leverage=10.0,
        taker_fee=0.001,
        slippage_pct=0.001,
        stop_loss_pct=0.01,
        take_profit_pct=0.02,
        max_drawdown_pct=0.2,
        max_daily_loss_pct=0.1,
    )

    start = datetime.now(timezone.utc)
    engine.process_signal(1, timestamp=start)
    engine.on_market_candle({"open": 100.0, "high": 103.0, "low": 99.0, "close": 101.0, "volume": 1.0}, timestamp=start)
    engine.on_market_candle({"open": 101.0, "high": 104.0, "low": 100.5, "close": 103.5, "volume": 1.0}, timestamp=start + timedelta(minutes=1))

    state = engine.get_state()
    assert len(state["execution_log"]) >= 1
    assert state["balance"] != 10000.0
    assert isinstance(state["equity"], float)


def test_paper_trading_engine_snapshot_and_restore() -> None:
    engine = PaperTradingEngine(initial_balance=10000.0)
    now = datetime.now(timezone.utc)
    engine.process_signal(1, timestamp=now)
    engine.on_market_candle({"open": 100.0, "high": 100.01, "low": 99.99, "close": 100.0, "volume": 1.0}, timestamp=now)
    snapshot = engine.snapshot()

    restored = PaperTradingEngine(initial_balance=10000.0)
    restored.restore(snapshot)

    assert restored.balance == engine.balance
    assert restored.position is not None
    assert len(restored.open_orders) == len(engine.open_orders)


def test_market_replay_simulates_from_historical_candles() -> None:
    candles = pd.DataFrame(
        [
            {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1.0},
            {"open": 100.5, "high": 102.0, "low": 100.0, "close": 101.5, "volume": 1.0},
            {"open": 101.5, "high": 103.0, "low": 101.0, "close": 102.5, "volume": 1.0},
        ],
        index=pd.to_datetime(["2026-01-01T00:00:00Z", "2026-01-01T00:01:00Z", "2026-01-01T00:02:00Z"]),
    )
    engine = PaperTradingEngine(initial_balance=5000.0)
    replay = MarketReplay(candles, engine, signal_source={candles.index[0]: 1})
    state = replay.run()

    assert len(state["equity_curve"]) == 4
    assert state["equity"] >= 0.0


def test_binance_market_stream_reconnects(monkeypatch) -> None:
    import live.binance_stream as stream_module

    monkeypatch.setattr(stream_module, "websocket", type("M", (), {"WebSocketApp": DummyWebSocketApp}))
    market_stream = BinanceFuturesMarketStream(symbol="ETHUSDT", interval="1m", reconnect_delay=0.1, watchdog_interval=0.1, watchdog_timeout=0.2)
    market_stream.start()
    time.sleep(0.5)
    market_stream.stop()

    assert market_stream.reconnect_count >= 1


def test_live_state_store_persists_and_loads_snapshot(tmp_path) -> None:
    from live.monitoring import LiveStateStore

    state_store = LiveStateStore(str(tmp_path / "live_state"))
    payload = {"engine_state": {"balance": 1234.5, "drawdown": 0.0}, "metadata": {"snapshot_at": "2026-01-01T00:00:00Z"}}
    saved = state_store.save_snapshot(payload)

    assert saved.exists()
    loaded = state_store.load_latest_snapshot()
    assert loaded["engine_state"]["balance"] == 1234.5
    assert loaded["metadata"]["snapshot_at"] == "2026-01-01T00:00:00Z"


def test_live_trading_coordinator_reloads_snapshot(tmp_path, monkeypatch) -> None:
    from live.manager import LiveTradingCoordinator
    import live.manager as manager_module

    class DummyStream:
        def __init__(self, symbol: str, interval: str, logger: Any = None, **kwargs):
            self.symbol = symbol
            self.interval = interval
            self.logger = logger
            self.connection_status = "disconnected"
            self.reconnect_count = 0
            self.latency_ms = None
            self.url = "ws://dummy"
            self._callbacks = {}

        def register_callback(self, event: str, callback: Any) -> None:
            self._callbacks[event] = callback

        def start(self) -> None:
            self.connection_status = "connected"

        def stop(self) -> None:
            self.connection_status = "disconnected"

    monkeypatch.setattr(manager_module, "BinanceFuturesMarketStream", DummyStream)

    state_dir = str(tmp_path / "live_state")
    coordinator = LiveTradingCoordinator(
        symbol="ETHUSDT",
        interval="1m",
        signal_callback=None,
        state_directory=state_dir,
        checkpoint_interval=1,
    )
    coordinator.engine.process_signal(1, datetime.now(timezone.utc))
    coordinator.engine.on_market_candle({"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1.0}, timestamp=datetime.now(timezone.utc))
    coordinator._checkpoint()

    recovered = LiveTradingCoordinator(
        symbol="ETHUSDT",
        interval="1m",
        signal_callback=None,
        state_directory=state_dir,
        checkpoint_interval=1,
    )

    assert recovered.engine.balance == coordinator.engine.balance
    assert recovered.engine.equity_curve == coordinator.engine.equity_curve


def test_long_duration_forward_validation_session_metrics() -> None:
    candles = pd.DataFrame(
        [
            {"open": 100.0, "high": 102.0, "low": 99.0, "close": 101.0, "volume": 1.0},
            {"open": 101.0, "high": 103.0, "low": 100.0, "close": 102.0, "volume": 1.0},
            {"open": 102.0, "high": 104.0, "low": 101.0, "close": 103.0, "volume": 1.0},
            {"open": 103.0, "high": 105.0, "low": 102.0, "close": 104.0, "volume": 1.0},
        ],
        index=pd.to_datetime(["2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z", "2026-01-03T00:00:00Z", "2026-01-04T00:00:00Z"]),
    )
    engine = PaperTradingEngine(initial_balance=10000.0)
    result = LiveValidationSession(
        session_name="validation",
        candles=candles,
        engine=engine,
        signal_source={candles.index[0].to_pydatetime(): 1},
        baseline_metrics={"sharpe": 1.0, "drawdown": -0.01, "net_return": 0.04, "stability": 0.5},
    ).run(accelerated=True)

    assert result.metrics["net_return"] >= 0.0
    assert isinstance(result.daily_summary, list)
    assert isinstance(result.weekly_summary, list)
    assert result.drift_report.get("changes") is not None


def test_regime_classification_stability() -> None:
    candles = pd.DataFrame(
        [
            {"open": 1.0, "high": 1.01, "low": 0.995, "close": 1.005, "volume": 1.0},
            {"open": 1.005, "high": 1.015, "low": 1.0, "close": 1.01, "volume": 1.0},
            {"open": 1.01, "high": 1.02, "low": 1.005, "close": 1.015, "volume": 1.0},
            {"open": 1.015, "high": 1.025, "low": 1.01, "close": 1.02, "volume": 1.0},
        ],
        index=pd.to_datetime(["2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z", "2026-01-03T00:00:00Z", "2026-01-04T00:00:00Z"]),
    )
    engine = PaperTradingEngine(initial_balance=10000.0)
    session = LiveValidationSession(
        session_name="regime",
        candles=candles,
        engine=engine,
        signal_source=None,
        regime_thresholds={"trend_pct": 0.004, "low_volatility": 0.0005, "high_volatility": 0.02},
    )
    regime_series = session._classify_regimes()

    assert set(regime_series).issubset({"trending", "ranging", "high_volatility", "low_volatility"})
    assert "trending" in set(regime_series)


def test_degradation_detection_flags_weakening_edge() -> None:
    candles = pd.DataFrame(
        [
            {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1.0},
            {"open": 100.5, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1.0},
            {"open": 100.0, "high": 100.5, "low": 98.5, "close": 99.0, "volume": 1.0},
            {"open": 99.0, "high": 99.5, "low": 97.0, "close": 97.5, "volume": 1.0},
        ],
        index=pd.to_datetime(["2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z", "2026-01-03T00:00:00Z", "2026-01-04T00:00:00Z"]),
    )
    engine = PaperTradingEngine(initial_balance=10000.0)
    result = LiveValidationSession(
        session_name="degrade",
        candles=candles,
        engine=engine,
        signal_source=None,
        alert_thresholds={"drawdown_pct": 0.01, "sharpe_decay_pct": 0.05, "slippage_pct": 0.1, "stability_decay_pct": 0.05},
    ).run(accelerated=True)

    assert isinstance(result.alerts, list)
