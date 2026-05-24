import logging

import pandas as pd

from optimizer.config import ConfigManager
from optimizer.logger import get_logger
from optimizer.workflow import WorkflowManager


def test_workflow_evaluate_candidate_runs() -> None:
    config = ConfigManager("configs/config.yaml").load()
    logger = get_logger("INFO", "logs/test_workflow.log")
    workflow = WorkflowManager(config=config, logger=logger)

    metrics = workflow.evaluate_candidate(
        price_series=workflow.generate_sample_price(50),
        params={
            "momentum_window": 5,
            "threshold": 0.005,
            "stop_loss_pct": 0.02,
            "take_profit_pct": 0.04,
        },
    )

    assert "net_profit" in metrics
    assert "sharpe_ratio" in metrics


def test_walk_forward_splits_create_valid_windows() -> None:
    config = ConfigManager("configs/config.yaml").load()
    config.optimizer["walk_forward"]["enabled"] = True
    config.optimizer["walk_forward"]["windows"] = 2
    config.optimizer["walk_forward"]["train_pct"] = 0.5
    config.optimizer["walk_forward"]["test_pct"] = 0.5

    logger = get_logger("INFO", "logs/test_walk_forward.log")
    workflow = WorkflowManager(config=config, logger=logger)

    data = pd.DataFrame(
        {
            "open": [i + 1.0 for i in range(20)],
            "high": [i + 2.0 for i in range(20)],
            "low": [i * 1.0 for i in range(20)],
            "close": [i + 1.5 for i in range(20)],
        }
    )

    splits = workflow._create_walk_forward_splits(data)
    assert len(splits) == 2
    assert splits[0]["train"].shape[0] > 0
    assert splits[0]["test"].shape[0] > 0
    assert splits[1]["train"].shape[0] > 0
    assert splits[1]["test"].shape[0] > 0
    assert splits[0]["window_index"] == 0
    assert splits[1]["window_index"] == 1
