import re
from typing import Any, Dict, List, Optional

from .parameters import PineParameter, PineScriptParseError


class PineScriptParser:
    INPUT_CALL_START_REGEX = re.compile(
        r"(?P<var>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*input\.(?P<type>int|float|bool|string)\s*\(",
        re.DOTALL,
    )

    POSITIONAL_KEYS = {
        "int": ["defval", "title", "minval", "maxval", "step", "inline", "group", "tooltip"],
        "float": ["defval", "title", "minval", "maxval", "step", "inline", "group", "tooltip"],
        "bool": ["defval", "title", "inline", "group", "tooltip"],
        "string": ["defval", "title", "options", "inline", "group", "tooltip"],
    }

    def __init__(self, source: str) -> None:
        self.source = source

    @classmethod
    def parse_file(cls, path: str) -> List[PineParameter]:
        with open(path, "r", encoding="utf-8") as handle:
            source = handle.read()
        return cls(source).parse()

    def parse(self) -> List[PineParameter]:
        matches = list(self.INPUT_CALL_START_REGEX.finditer(self.source))
        if not matches:
            raise PineScriptParseError("No Pine Script input declarations found in source.")

        parameters: List[PineParameter] = []
        for match in matches:
            arg_text = self._extract_call_arguments(match.end())
            parameters.append(self._parse_input(match.group("var"), match.group("type"), arg_text))
        return parameters

    def _parse_input(self, var_name: str, input_type: str, arg_text: str) -> PineParameter:
        parsed_args = self._parse_arguments(arg_text, input_type)

        parameter = PineParameter(
            id=var_name,
            name=self._parse_string(parsed_args.get("title", var_name)),
            type=input_type,
            default=self._parse_value(parsed_args.get("defval"), input_type),
            min_value=self._parse_numeric(parsed_args.get("minval")),
            max_value=self._parse_numeric(parsed_args.get("maxval")),
            step=self._parse_numeric(parsed_args.get("step")),
            category=self._parse_string(parsed_args.get("group")) if parsed_args.get("group") else None,
            options=self._parse_options(parsed_args.get("options")),
            description=self._parse_string(parsed_args.get("tooltip")) if parsed_args.get("tooltip") else None,
        )
        return parameter

    def _extract_call_arguments(self, start_index: int) -> str:
        depth = 1
        in_string = False
        quote_char = ""
        escaped = False
        chars: List[str] = []
        source = self.source
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
                    return "".join(chars)
                chars.append(char)
                continue

            chars.append(char)

        raise PineScriptParseError("Unbalanced parentheses in Pine Script input declaration.")

    def _parse_arguments(self, arg_text: str, input_type: str) -> Dict[str, Any]:
        args = self._split_args(arg_text)
        parsed: Dict[str, Any] = {}
        positional: List[str] = []
        for arg in args:
            if "=" in arg:
                key, value = arg.split("=", 1)
                parsed[key.strip()] = value.strip()
            elif arg:
                positional.append(arg.strip())

        if positional:
            positional_keys = self.POSITIONAL_KEYS.get(input_type, [])
            for index, value in enumerate(positional):
                if index >= len(positional_keys):
                    break
                parsed[positional_keys[index]] = value
        return parsed

    def _parse_value(self, raw_value: Optional[str], input_type: str) -> Any:
        if raw_value is None:
            return None
        if input_type == "bool":
            return self._parse_bool(raw_value)
        if input_type == "string":
            return self._parse_string(raw_value)
        return self._parse_numeric(raw_value)

    def _parse_numeric(self, raw_value: Optional[str]) -> Optional[float]:
        if raw_value is None:
            return None
        raw = raw_value.strip()
        if raw.lower() in {"na", "nan"}:
            return None
        raw = self._strip_quotes(raw)
        try:
            return int(raw) if raw.isdigit() else float(raw)
        except ValueError:
            return None

    def _parse_bool(self, raw_value: str) -> bool:
        raw = raw_value.strip().lower()
        if raw in {"true", "false"}:
            return raw == "true"
        raise PineScriptParseError(f"Invalid boolean value: {raw_value}")

    def _parse_string(self, raw_value: str) -> str:
        return self._strip_quotes(raw_value.strip())

    def _parse_options(self, raw_value: Optional[str]) -> Optional[List[str]]:
        if raw_value is None:
            return None
        raw = raw_value.strip()
        if raw.startswith("[") and raw.endswith("]"):
            matches = re.findall(r'"([^"]*)"|\'([^\']*)\'', raw)
            return [first or second for first, second in matches]
        return None

    @staticmethod
    def _strip_quotes(value: str) -> str:
        if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
            return value[1:-1]
        return value

    @staticmethod
    def _split_args(arg_text: str) -> List[str]:
        args: List[str] = []
        current: List[str] = []
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
