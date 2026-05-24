from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Union


class PineScriptParseError(Exception):
    """Raised when Pine Script parsing or parameter extraction fails."""


@dataclass
class PineParameter:
    id: str
    name: str
    type: str
    default: Any
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    step: Optional[float] = None
    category: Optional[str] = None
    options: Optional[List[Any]] = None
    description: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "default": self.default,
            "min_value": self.min_value,
            "max_value": self.max_value,
            "step": self.step,
            "category": self.category,
            "options": self.options,
            "description": self.description,
        }


class PineParameterManager:
    def __init__(self, parameters: List[PineParameter], source: str) -> None:
        self.parameters = parameters
        self.source = source
        self.by_id = {param.id: param for param in parameters}

    def generate_search_space(self) -> Dict[str, List[Any]]:
        search_space: Dict[str, List[Any]] = {}
        for param in self.parameters:
            if param.options:
                search_space[param.id] = param.options
                continue

            if param.type == "bool":
                search_space[param.id] = [True, False]
                continue

            if param.type in {"int", "float"}:
                if param.min_value is not None and param.max_value is not None:
                    step = param.step if param.step is not None else 1 if param.type == "int" else 0.01
                    if param.type == "int":
                        values = list(range(int(param.min_value), int(param.max_value) + 1, max(1, int(step))))
                    else:
                        count = int(max(1, round((param.max_value - param.min_value) / float(step)))) + 1
                        values = [round(param.min_value + i * float(step), 10) for i in range(count)]
                    search_space[param.id] = values
                    continue

            search_space[param.id] = [param.default]
        return search_space

    def replace_parameters(self, values: Dict[str, Any]) -> str:
        output = self.source
        for param in self.parameters:
            if param.id not in values:
                continue
            output = self._replace_parameter(output, param, values[param.id])
        return output

    def save_version(self, values: Dict[str, Any], output_dir: str, prefix: Optional[str] = None) -> str:
        output_dir_path = Path(output_dir)
        output_dir_path.mkdir(parents=True, exist_ok=True)
        replaced_source = self.replace_parameters(values)
        suffix = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        report_prefix = prefix or "pine_strategy"
        file_name = f"{report_prefix}_{suffix}.pine"
        file_path = output_dir_path / file_name
        file_path.write_text(replaced_source, encoding="utf-8")
        return str(file_path)

    def _replace_parameter(self, source: str, parameter: PineParameter, new_value: Any) -> str:
        import re

        input_pattern = re.compile(
            rf"(?P<var>{re.escape(parameter.id)})\s*=\s*input\.{parameter.type}\s*\(",
            re.DOTALL,
        )

        match = input_pattern.search(source)
        if not match:
            return source

        start = match.end()
        args_text, end_index = self._extract_call_arguments(source, start)
        args = self._split_args(args_text)
        updated_args = []
        found_defval = False
        for arg in args:
            if arg.strip().startswith("defval"):
                updated_args.append(f"defval={self._format_value(new_value, parameter.type)}")
                found_defval = True
            else:
                updated_args.append(arg)

        if not found_defval:
            updated_args.append(f"defval={self._format_value(new_value, parameter.type)}")

        joined_args = ", ".join(updated_args)
        replacement = f"{parameter.id} = input.{parameter.type}({joined_args})"
        return source[:match.start()] + replacement + source[end_index:]

    def _extract_call_arguments(self, source: str, start_index: int) -> tuple[str, int]:
        depth = 1
        in_string = False
        quote_char = ""
        escaped = False
        chars: List[str] = []
        for index in range(start_index, len(source)):
            char = source[index]
            if escaped:
                chars.append(char)
                escaped = False
                continue

            if char == "\\" and in_string:
                chars.append(char)
                escaped = True
                continue

            if char in {'"', "'"}:
                chars.append(char)
                if not in_string:
                    in_string = True
                    quote_char = char
                elif quote_char == char:
                    in_string = False
                continue

            if in_string:
                chars.append(char)
                continue

            if char == "(":
                depth += 1
                chars.append(char)
                continue

            if char == ")":
                depth -= 1
                if depth == 0:
                    return "".join(chars), index + 1
                chars.append(char)
                continue

            chars.append(char)

        raise PineScriptParseError("Unbalanced parentheses in Pine Script input declaration.")

    @staticmethod
    def _format_value(value: Any, input_type: str) -> str:
        if input_type == "string":
            return f'"{value}"'
        if input_type == "bool":
            return "true" if bool(value) else "false"
        return str(value)

    @staticmethod
    def _split_args(arg_text: str) -> List[str]:
        args: List[str] = []
        current = []
        depth = 0
        in_string = False
        quote_char = ""
        for char in arg_text:
            if char in {'"', "'"}:
                if not in_string:
                    in_string = True
                    quote_char = char
                elif quote_char == char:
                    in_string = False
                current.append(char)
                continue
            if in_string:
                current.append(char)
                continue
            if char in "([{":
                depth += 1
            elif char in ")]}":
                depth = max(0, depth - 1)
            if char == "," and depth == 0:
                args.append("".join(current).strip())
                current = []
                continue
            current.append(char)
        if current:
            args.append("".join(current).strip())
        return args
