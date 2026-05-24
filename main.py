import argparse

from optimizer.config import ConfigManager
from optimizer.logger import get_logger
from optimizer.workflow import WorkflowManager


def main() -> None:
    parser = argparse.ArgumentParser(description="Run ETH futures optimization workflow.")
    parser.add_argument(
        "--config",
        type=str,
        default="configs/config.yaml",
        help="Path to the YAML configuration file.",
    )
    args = parser.parse_args()

    config = ConfigManager(args.config).load()
    logger = get_logger(config.logging.get("level", "INFO"), config.logging.get("path", "logs/optimizer.log"))
    manager = WorkflowManager(config=config, logger=logger)

    logger.info("Starting ETH futures optimization workflow.")
    try:
        result = manager.run()
        logger.info("Optimization workflow completed successfully.")
        logger.info(f"Best run saved to: {result['report_path']}")
    except Exception as exc:
        logger.exception("Workflow failed with an unhandled exception.")
        raise exc


if __name__ == "__main__":
    main()
