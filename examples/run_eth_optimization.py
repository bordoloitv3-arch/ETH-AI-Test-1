from optimizer.config import ConfigManager
from optimizer.logger import get_logger
from optimizer.workflow import WorkflowManager


def main() -> None:
    config = ConfigManager("configs/config.yaml").load()
    logger = get_logger(config.logging.get("level", "INFO"), config.logging.get("path", "logs/optimizer_example.log"))
    manager = WorkflowManager(config=config, logger=logger)

    result = manager.run()
    print("Optimization completed.")
    for key, value in result["report_path"].items():
        print(f"{key}: {value}")
    print("Best parameters:", result["best_parameters"])


if __name__ == "__main__":
    main()
