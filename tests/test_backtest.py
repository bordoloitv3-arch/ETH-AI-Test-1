import pandas as pd

from backtester.engine import FuturesBacktester


def test_futures_backtester_runs_without_error() -> None:
    prices = pd.Series([100.0, 102.0, 101.0, 103.0, 104.0])
    signals = pd.Series([1, 0, 0, -1, 0])
    backtester = FuturesBacktester(
        price_series=prices,
        initial_balance=10000.0,
        leverage=5.0,
        fee_rate=0.0005,
        slippage_pct=0.0002,
        stop_loss_pct=0.01,
        take_profit_pct=0.02,
    )
    result = backtester.run(signals)
    assert len(result.equity_curve) == len(prices)
    assert isinstance(result.stats["final_balance"], float)
