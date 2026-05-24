from optimizer.config import ConfigManager


def test_load_config() -> None:
    config = ConfigManager("configs/config.yaml").load()
    assert config.backtest["initial_balance"] == 100000
    assert config.optimizer["engine"] in {"optuna", "genetic", "rl"}
