from types import SimpleNamespace
import pandas as pd
import numpy as np

from optimizer.workflow import WorkflowManager


class DummyLogger:
    def info(self, *a, **k):
        pass
    def debug(self, *a, **k):
        pass
    def warning(self, *a, **k):
        pass
    def exception(self, *a, **k):
        pass


def make_price(n=200):
    rng = np.random.default_rng(1)
    r = rng.normal(0, 0.001, size=n)
    p = 100 * np.exp(np.cumsum(r))
    return pd.Series(p, index=pd.date_range("2020-01-01", periods=n))


def test_workflow_monte_integration():
    cfg = SimpleNamespace(
        optimizer={"monte_carlo": {"enabled": True, "simulations": 10}, "weights": {"sharpe": 0.35, "profit": 0.2, "drawdown": 0.2, "robustness": 0.25}, "seed": 42, "engine": "optuna"},
        backtest={"initial_balance": 100000, "leverage": 10},
        reporting={"output_dir": "reports_test"},
        pine_script={},
        data={},
    )
    wm = WorkflowManager(cfg, DummyLogger())
    price = make_price(150)
    params = {"momentum_window": 5, "threshold": 0.001}
    metrics, equity, trades, mc = wm._evaluate_candidate_with_result(price, params, allow_oos=False)
    assert metrics is not None
    assert mc is not None and "robustness_score" in mc
