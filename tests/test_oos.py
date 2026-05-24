import pytest
import numpy as np
import pandas as pd

from data.market_data import MarketDataEngine, MarketDataSplit
from optimizer.config import ConfigManager
from optimizer.logger import get_logger
from optimizer.metrics import robustness_rank
from optimizer.workflow import WorkflowManager


def make_price_df(length: int = 100) -> pd.DataFrame:
    prices = pd.Series(np.linspace(100.0, 200.0, length))
    return pd.DataFrame({"open": prices, "high": prices * 1.01, "low": prices * 0.99, "close": prices})


def test_oos_protection_blocks_access() -> None:
    config = ConfigManager("configs/config.yaml").load()
    logger = get_logger("INFO", "logs/test_oos.log")
    workflow = WorkflowManager(config=config, logger=logger)

    df = make_price_df(60)
    engine = MarketDataEngine()
    split = engine.split_data(df, train_pct=0.6, validation_pct=0.2, test_pct=0.2)
    # attach split to workflow as market_data
    workflow.market_data = split

    params = {"momentum_window": 5, "threshold": 0.005}
    # calling the public evaluation on the reserved final test set must be forbidden
    with pytest.raises(ValueError):
        workflow.evaluate_candidate_with_result(workflow.market_data.test, params)


def test_train_validation_oos_separation() -> None:
    df = make_price_df(100)
    engine = MarketDataEngine()
    split = engine.split_data(df, train_pct=0.5, validation_pct=0.25, test_pct=0.25)

    assert split.train.index.max() < split.validation.index.min()
    assert split.validation.index.max() < split.test.index.min()
    assert len(split.train) + len(split.validation) + len(split.test) == len(split.full)


def test_walk_forward_windows_non_overlapping() -> None:
    config = ConfigManager("configs/config.yaml").load()
    config.optimizer["walk_forward"]["enabled"] = True
    config.optimizer["walk_forward"]["windows"] = 3
    logger = get_logger("INFO", "logs/test_walk_forward_oos.log")
    workflow = WorkflowManager(config=config, logger=logger)

    df = make_price_df(90)
    splits = workflow._create_walk_forward_splits(df)
    assert len(splits) == 3
    for w in splits:
        train = w["train"]
        test = w["test"]
        assert train.index.max() < test.index.min()


def test_robustness_rank_penalizes_overfitting() -> None:
    # create contrived metrics: strong train, weak oos
    train_metrics = {"sharpe_ratio": 3.0, "return_pct": 50.0, "equity_stability": 0.8}
    val_metrics = {"sharpe_ratio": 2.5, "return_pct": 40.0, "equity_stability": 0.7}
    oos_good = {"sharpe_ratio": 2.8, "return_pct": 45.0, "equity_stability": 0.75}
    oos_bad = {"sharpe_ratio": 0.5, "return_pct": -10.0, "equity_stability": 0.2}

    rank_good = robustness_rank(train_metrics, val_metrics, oos_good)
    rank_bad = robustness_rank(train_metrics, val_metrics, oos_bad)
    assert rank_good > rank_bad
