from pathlib import Path
from typing import Any, Dict, List, Optional

from .parser import PineScriptParser
from .parameters import PineParameter, PineParameterManager


class PineStrategyManager:
    def __init__(self, path: str, output_dir: Optional[str] = None) -> None:
        self.path = Path(path)
        if not self.path.exists():
            raise FileNotFoundError(f"Pine Script strategy file not found: {self.path}")
        self.source = self.path.read_text(encoding="utf-8")
        self.parser = PineScriptParser(self.source)
        self.parameters: List[PineParameter] = self.parser.parse()
        self.parameter_manager = PineParameterManager(self.parameters, self.source)
        self.output_dir = Path(output_dir or self.path.parent / "strategy_versions")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_search_space(self) -> Dict[str, List[Any]]:
        return self.parameter_manager.generate_search_space()

    def save_version(self, values: Dict[str, Any], output_dir: Optional[str] = None, prefix: Optional[str] = None) -> str:
        target_dir = output_dir or str(self.output_dir)
        return self.parameter_manager.save_version(values, target_dir, prefix=prefix or self.path.stem)

    def get_parameter_report(self) -> Dict[str, Any]:
        return {param.id: param.to_dict() for param in self.parameters}

    def validate(self) -> None:
        if not self.parameters:
            raise ValueError(f"No Pine Script parameters extracted from {self.path}")
