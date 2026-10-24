"""Tool registry and built-in tool tests (safe evaluation etc.)."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.agents.tools import ToolContext, _calculator, _current_datetime, get_tool_registry


@pytest.fixture
def registry():
    return get_tool_registry()


def test_registry_lists_builtin_tools(registry):
    names = {spec.name for spec in registry.all()}
    assert {"calculator", "current_datetime"} <= names


def test_build_tools_by_name(registry):
    ctx = ToolContext(user_id=uuid4(), agent_id=uuid4(), conversation_id=uuid4(), run_id=uuid4())
    tools = registry.build_tools(["calculator", "unknown_tool"], ctx)
    assert len(tools) == 1
    assert tools[0].name == "calculator"


def test_calculator_basic():
    assert _calculator("2+2") == "4"
    assert _calculator("(2 + 3) * 7.5") == "37.5"
    assert _calculator("2 ** 10") == "1024"
    assert _calculator("-5 + 3") == "-2"


def test_calculator_rejects_code_injection():
    with pytest.raises(ValueError):
        _calculator("__import__('os').system('ls')")
    with pytest.raises(ValueError):
        _calculator("open('/etc/passwd')")
    with pytest.raises(ValueError):
        _calculator("[x for x in range(10)]")


def test_calculator_rejects_huge_exponent():
    with pytest.raises(ValueError):
        _calculator("9 ** 9 ** 9")


def test_current_datetime_utc():
    result = _current_datetime()
    assert "T" in result and ("+00:00" in result or "Z" in result)


def test_current_datetime_with_timezone():
    result = _current_datetime("Europe/Moscow")
    assert "+03:00" in result


def test_current_datetime_invalid_timezone_falls_back():
    result = _current_datetime("Not/AZone")
    assert "T" in result
