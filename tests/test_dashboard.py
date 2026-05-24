import json
from pathlib import Path

import pandas as pd

from dashboard.utils import (
    build_history_table,
    build_run_table,
    generate_pdf_report_bytes,
    load_report_payload,
)


def test_build_history_table():
    history = [
        {"params": {"momentum_window": 5, "threshold": 0.005}, "value": 1.23, "sharpe_ratio": 1.5},
        {"params": {"momentum_window": 10, "threshold": 0.01}, "value": 1.0, "sharpe_ratio": 1.2},
    ]
    df = build_history_table(history)
    assert not df.empty
    assert list(df.columns) >= ["objective", "momentum_window", "threshold", "sharpe_ratio"]
    assert df.loc[0, "objective"] == 1.23


def test_build_run_table():
    runs = [
        {
            "id": 1,
            "engine": "optuna",
            "created_at": "2026-05-24T12:00:00Z",
            "metrics": {"sharpe_ratio": 1.5, "net_profit": 500.0, "drawdown": -0.05},
            "oos_metrics": {"sharpe_ratio": 1.2},
            "rejected_parameters": [],
            "report_path": "reports/test_run.json",
        }
    ]
    df = build_run_table(runs)
    assert not df.empty
    assert df.loc[0, "id"] == 1
    assert df.loc[0, "engine"] == "optuna"
    assert df.loc[0, "sharpe_ratio"] == 1.5


def test_load_report_payload(tmp_path: Path):
    payload = {"metrics": {"sharpe_ratio": 1.8}, "trades": []}
    report_path = tmp_path / "dashboard_report.json"
    report_path.write_text(json.dumps(payload), encoding="utf-8")
    loaded = load_report_payload(str(report_path))
    assert loaded["metrics"]["sharpe_ratio"] == 1.8


def test_generate_pdf_report_bytes():
    run = {"id": 1, "engine": "optuna", "created_at": "2026-05-24T12:00:00Z"}
    report_data = {"metrics": {"sharpe_ratio": 1.5, "net_profit": 300.0}, "oos_metrics": {"sharpe_ratio": 1.2}, "monte_carlo": {"probability_of_ruin": 0.05}}
    pdf_bytes = generate_pdf_report_bytes("Test Report", run, report_data)
    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes[:4] == b"%PDF"
