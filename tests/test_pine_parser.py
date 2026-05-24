from pine.parser import PineScriptParser, PineScriptParseError
from pine.strategy_manager import PineStrategyManager


def test_parse_example_strategy_file() -> None:
    parameters = PineScriptParser.parse_file("strategies/example_strategy.pine")
    assert len(parameters) == 6

    length_param = next((param for param in parameters if param.id == "length"), None)
    assert length_param is not None
    assert length_param.type == "int"
    assert length_param.default == 10
    assert length_param.min_value == 2
    assert length_param.max_value == 50
    assert length_param.step == 1
    assert length_param.category == "Strategy Inputs"

    trend_source = next((param for param in parameters if param.id == "trend_source"), None)
    assert trend_source is not None
    assert trend_source.type == "string"
    assert trend_source.options == ["open", "high", "low", "close"]
    assert trend_source.default == "close"


def test_parse_luxalgo_tl_ma_fvg_tp_sl_strategy() -> None:
    parameters = PineScriptParser.parse_file("strategies/luxalgo_tl_ma_fvg_tp_sl.pine")
    assert len(parameters) == 10

    tp_points = next((param for param in parameters if param.id == "tpPoints"), None)
    assert tp_points is not None
    assert tp_points.type == "float"
    assert tp_points.default == 38.0
    assert tp_points.category == "Trade Management"

    sl_cooldown = next((param for param in parameters if param.id == "slCooldownMins"), None)
    assert sl_cooldown is not None
    assert sl_cooldown.type == "int"
    assert sl_cooldown.default == 205
    assert sl_cooldown.min_value == 0


def test_parse_invalid_pine_script_throws() -> None:
    invalid_source = "strategy('Bad', overlay=true)\nfoo = input.int(defval=10, minval=1, maxval=20"
    parser = PineScriptParser(invalid_source)
    try:
        parser.parse()
        assert False, "Expected PineScriptParseError for invalid Pine Script"
    except PineScriptParseError:
        pass


def test_pine_strategy_manager_save_version() -> None:
    manager = PineStrategyManager("strategies/example_strategy.pine", output_dir="reports/strategy_versions_test")
    output_path = manager.save_version({"length": 12, "threshold": 0.01, "stop_loss_pct": 0.03, "take_profit_pct": 0.06}, prefix="example_strategy_test")
    assert output_path.endswith(".pine")
    with open(output_path, "r", encoding="utf-8") as handle:
        content = handle.read()
    assert "defval=12" in content or "defval = 12" in content
    assert "defval=0.01" in content or "defval = 0.01" in content
