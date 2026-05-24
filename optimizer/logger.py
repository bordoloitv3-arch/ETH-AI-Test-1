import json
import logging
from logging import Logger
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional, Dict, Any


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: Dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def get_logger(
    level: str = "INFO",
    path: str = "logs/optimizer.log",
    structured: bool = False,
    max_bytes: int = 10 * 1024 * 1024,
    backup_count: int = 5,
) -> Logger:
    log_level = getattr(logging, level.upper(), logging.INFO)
    logger = logging.getLogger("eth_ai_optimizer")
    logger.setLevel(log_level)

    if not logger.handlers:
        formatter = JsonFormatter() if structured else logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

        console_handler = logging.StreamHandler()
        console_handler.setLevel(log_level)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        log_path = Path(path)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(log_path, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8")
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger
