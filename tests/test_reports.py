import json
from pathlib import Path

import pandas as pd

from memory.sqlite_memory import SQLOptimizationMemory
from optimizer.reporting import ReportGenerator
from utils.types import TradeRecord


def test_sql_memory_persists_oos_and_robustness() -> None:
    db_path = Path("memory/test_optimizer_memory.db")
    if db_path.exists():
        db_path.unlink()

    memory = SQLOptimizationMemory(str(db_path))
    parameters = {"momentum_window": 5, "threshold": 0.01}
    metrics = {"sharpe_ratio": 1.2, "drawdown": -0.05, "net_profit": 500.0}
    validation_metrics = {"sharpe_ratio": 1.1}
    oos_metrics = {"sharpe_ratio": 0.9}
    walk_forward_metrics = {"score": 0.8}
    rejected = [{"momentum_window": 10, "threshold": 0.02}]
    history = [{"params": parameters, "value": 1.2}, {"params": rejected[0], "value": 1.0}]

    run_id = memory.save_run(
        engine="optuna",
        parameters=parameters,
        metrics=metrics,
        report_path="reports/test_report.json",
        validation_metrics=validation_metrics,
        oos_metrics=oos_metrics,
        walk_forward_metrics=walk_forward_metrics,
        overfitting_score=0.15,
        robustness_rank=0.82,
        rejected_parameters=rejected,
        optimization_history=history,
    )

    assert isinstance(run_id, int) and run_id > 0
    runs = memory.get_runs(limit=1)
    assert len(runs) == 1
    run = runs[0]
    assert run["engine"] == "optuna"
    assert run["parameters"] == parameters
    assert run["metrics"]["net_profit"] == 500.0
    assert run["validation_metrics"]["sharpe_ratio"] == 1.1
    assert run["oos_metrics"]["sharpe_ratio"] == 0.9
    assert run["walk_forward_metrics"]["score"] == 0.8
    assert run["overfitting_score"] == 0.15
    assert run["robustness_rank"] == 0.82
    assert run["rejected_parameters"] == rejected
    assert run["optimization_history"] == history

    memory.close()


def test_report_generator_outputs_summary_files(tmp_path: Path) -> None:
    output_dir = tmp_path / "reports"
    generator = ReportGenerator(str(output_dir))
    trades = [
        TradeRecord(entry_index=0, exit_index=1, direction=1, entry_price=100.0, exit_price=105.0, size=1.0, pnl=5.0, return_pct=0.05, exit_reason="take_profit"),
    ]
    metrics = {"sharpe_ratio": 1.5, "drawdown": -0.02, "net_profit": 500.0}
    dataset_metrics = {"validation": {"sharpe_ratio": 1.4, "drawdown": -0.03, "net_profit": 450.0}, "test": {"sharpe_ratio": 1.1, "drawdown": -0.06, "net_profit": 200.0}}
    history = [
        {"params": {"momentum_window": 5, "threshold": 0.005}, "value": 1.5},
        {"params": {"momentum_window": 10, "threshold": 0.01}, "value": 1.2},
    ]
    report_name = "test_run"

    output = generator.build_report(
        trades=trades,
        metrics=metrics,
        equity_curve=pd.Series([1000.0, 1005.0, 1010.0]),
        report_prefix=report_name,
        formats=["csv", "json", "plot"],
        search_history=history,
        dataset_metrics=dataset_metrics,
        dataset_equity={"validation": pd.Series([1000.0, 1020.0]), "test": pd.Series([1000.0, 1010.0])},
        best_parameters=history[0]["params"],
        oos_metrics=dataset_metrics["test"],
    )

    assert Path(output["csv"]).exists()
    assert Path(output["json"]).exists()
    assert Path(output["dataset_metrics_csv"]).exists()
    assert Path(output["parameter_metrics_csv"]).exists()
    assert Path(output["plot"]).exists()
    assert Path(output["drawdown_plot"]).exists()
    assert Path(output["oos_comparison_plot"]).exists()
    if "walk_forward_plot" in output:
        assert Path(output["walk_forward_plot"]).exists()
    assert Path(output["convergence_plot"]).exists()
    assert Path(output["robustness_plot"]).exists()
    assert Path(output["heatmap"]).exists()

    with Path(output["json"]).open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    assert payload["metrics"]["sharpe_ratio"] == 1.5
    assert payload["dataset_metrics"]["test"]["net_profit"] == 200.0
    assert payload["best_parameters"] == history[0]["params"]
