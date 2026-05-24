import pandas as pd

from optimizer.metrics import performance_metrics
from utils.types import TradeRecord


def test_performance_metrics_calculates_values() -> None:
    equity = pd.Series([100000.0, 101000.0, 100500.0, 102000.0])
    trades = [
        TradeRecord(entry_index=0, exit_index=2, direction=1, entry_price=100.0, exit_price=102.0, size=1000.0, pnl=2000.0, return_pct=0.02, exit_reason="take_profit"),
        TradeRecord(entry_index=2, exit_index=3, direction=-1, entry_price=102.0, exit_price=100.5, size=1000.0, pnl=1500.0, return_pct=0.015, exit_reason="take_profit"),
    ]
    metrics = performance_metrics(equity, trades)
    assert metrics["net_profit"] == 2000.0
    assert metrics["trade_count"] == 2.0
    assert metrics["win_rate"] == 1.0
