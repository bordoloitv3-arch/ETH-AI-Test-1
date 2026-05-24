from types import SimpleNamespace
import pandas as pd

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


def test_assess_candidate_rejection():
    cfg = SimpleNamespace(
        optimizer={
            "monte_carlo": {"enabled": True, "simulations": 10},
            "weights": {"sharpe": 0.35, "profit": 0.2, "drawdown": 0.2, "robustness": 0.25},
            "rejection": {"max_drawdown": 0.3, "min_robustness_score": 0.6, "max_probability_of_ruin": 0.15, "min_oos_sharpe": 1.0},
            "seed": 42,
        },
        backtest={"initial_balance": 100000, "leverage": 10},
        reporting={"output_dir": "reports_test"},
        pine_script={},
        data={},
    )
    wm = WorkflowManager(cfg, DummyLogger())
    # craft fake metrics to trigger rejection
    train_metrics = {"sharpe_ratio": 2.0, "return_pct": 50.0, "drawdown": -0.1}
    validation_metrics = None
    oos_metrics = {"sharpe_ratio": 0.5, "return_pct": -10.0, "drawdown": -0.25}
    monte_carlo_stats = {
        "probability_of_ruin": 0.2,
        "robustness_score": 0.4,
        "average_cvar95": -0.25,
        "equity_stability_score": 0.2,
    }
    assessment = wm._assess_candidate(train_metrics, validation_metrics, oos_metrics, monte_carlo_stats, walk_forward_results=None)
    assert assessment["rejected"] is True
    assert "high_probability_of_ruin" in assessment["rejection_reasons"]
    assert "low_robustness_score" in assessment["rejection_reasons"]


def test_ranking_prefers_robust():
    cfg = SimpleNamespace(
        optimizer={
            "weights": {"sharpe": 0.35, "profit": 0.2, "drawdown": 0.2, "robustness": 0.25},
            "rejection": {"max_drawdown": 0.5, "min_robustness_score": 0.1, "max_probability_of_ruin": 0.5, "min_oos_sharpe": 0.0},
            "seed": 42,
        },
        backtest={"initial_balance": 100000, "leverage": 10},
        reporting={"output_dir": "reports_test"},
        pine_script={},
        data={},
    )
    wm = WorkflowManager(cfg, DummyLogger())
    # candidate A: high profit but low robustness
    a_train = {"sharpe_ratio": 3.0, "return_pct": 200.0, "drawdown": -0.4}
    a_mc = {"robustness_score": 0.2, "probability_of_ruin": 0.1, "average_cvar95": -0.2, "equity_stability_score": 0.2}
    a = wm._assess_candidate(a_train, None, None, a_mc, None)
    # candidate B: lower profit but high robustness
    b_train = {"sharpe_ratio": 1.5, "return_pct": 50.0, "drawdown": -0.15}
    b_mc = {"robustness_score": 0.9, "probability_of_ruin": 0.01, "average_cvar95": -0.02, "equity_stability_score": 0.8}
    b = wm._assess_candidate(b_train, None, None, b_mc, None)
    assert b["final_ranking_score"] > a["final_ranking_score"]
