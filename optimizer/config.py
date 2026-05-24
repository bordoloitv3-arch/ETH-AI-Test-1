import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import yaml


@dataclass(frozen=True)
class Config:
    logging: Dict[str, Any]
    backtest: Dict[str, Any]
    optimizer: Dict[str, Any]
    reporting: Dict[str, Any]
    pine_script: Dict[str, Any]
    data: Dict[str, Any]


class ConfigManager:
    def __init__(self, path: str) -> None:
        self.path = Path(path)

    def load(self) -> Config:
        if not self.path.exists():
            raise FileNotFoundError(f"Configuration file not found: {self.path}")

        with self.path.open("r", encoding="utf-8") as stream:
            data = yaml.safe_load(stream)

        if not isinstance(data, dict):
            raise ValueError("Config file must contain a YAML mapping at the top level.")

        config = Config(
            logging=data.get("logging", {}),
            backtest=data.get("backtest", {}),
            optimizer=data.get("optimizer", {}),
            reporting=data.get("reporting", {}),
            pine_script=data.get("pine_script", {}),
            data=data.get("data", {}),
        )
        return config

    def dump(self, config: Config, output_path: Optional[str] = None) -> None:
        target = Path(output_path or self.path)
        with target.open("w", encoding="utf-8") as stream:
            yaml.safe_dump(json.loads(json.dumps(config.__dict__)), stream)
