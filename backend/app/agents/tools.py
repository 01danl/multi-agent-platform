"""Tool registry and built-in platform tools.

Tools are declared once with metadata (name, description, permission category)
and instantiated per run with a `ToolContext` so future tools can scope file or
knowledge access to the acting user and workspace. Agent configs reference
tools by name (`Agent.enabled_tools`); the registry is the only place that
knows how to build them.

No tool here executes shell commands or touches the host filesystem.
"""

from __future__ import annotations

import ast
import math
import operator
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timezone
from uuid import UUID

from langchain_core.tools import BaseTool

# --- Allowed arithmetic operators for the calculator (safe AST evaluation) ---
# Keys are ast.operator / ast.unaryop subclasses (not ast.expr subclasses).
_OPS: dict[type, Callable[..., float]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
    ast.FloorDiv: operator.floordiv,
}

# Guards against denial-of-service via huge exponents (e.g. 9 ** 9 ** 9).
_MAX_EXPONENT = 4096
_MAX_RESULT_DIGITS = 308
_MAX_EXPRESSION_LENGTH = 500


def _guarded_pow(base: float, exponent: float) -> float:
    if abs(exponent) > _MAX_EXPONENT:
        raise ValueError("Exponent too large")
    log_base = math.log10(abs(base)) if base != 0 else 0.0
    if log_base * abs(exponent) > _MAX_RESULT_DIGITS:
        raise ValueError("Result would be too large")
    return base**exponent


def _safe_eval(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, int | float):
        return node.value
    if isinstance(node, ast.BinOp):
        left = _safe_eval(node.left)
        right = _safe_eval(node.right)
        if isinstance(node.op, ast.Pow):
            return _guarded_pow(left, right)
        op = _OPS.get(type(node.op))
        if op is None:
            raise ValueError(f"Unsupported operator: {type(node.op).__name__}")
        return op(left, right)
    if isinstance(node, ast.UnaryOp):
        op = _OPS.get(type(node.op))
        if op is None:
            raise ValueError(f"Unsupported operator: {type(node.op).__name__}")
        return op(_safe_eval(node.operand))
    raise ValueError(f"Unsupported expression element: {type(node).__name__}")


@dataclass
class ToolContext:
    """Per-run context handed to tool factories."""

    user_id: UUID
    agent_id: UUID
    conversation_id: UUID
    run_id: UUID


def _calculator(expression: str) -> str:
    """Evaluate an arithmetic expression.

    Supports +, -, *, /, //, %, ** and parentheses on numbers.

    Args:
        expression: Arithmetic expression, e.g. "(2 + 3) * 7.5".

    Returns:
        The numeric result as a string.
    """
    if len(expression) > _MAX_EXPRESSION_LENGTH:
        raise ValueError("Expression too long")
    tree = ast.parse(expression, mode="eval")
    result = _safe_eval(tree)
    if abs(result) > 1e308:
        raise ValueError("Result is too large")
    return str(result)


def _current_datetime(timezone_name: str | None = None) -> str:
    """Get the current date and time.

    Args:
        timezone_name: Optional IANA timezone name (e.g. "Europe/Moscow").
            Defaults to UTC.

    Returns:
        ISO-8601 date and time with timezone offset.
    """
    from zoneinfo import ZoneInfo

    try:
        tz: timezone | ZoneInfo = ZoneInfo(timezone_name) if timezone_name else UTC
        return datetime.now(tz).isoformat()
    except Exception:
        return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    category: str
    factory: Callable[[ToolContext], BaseTool]


class ToolRegistry:
    def __init__(self) -> None:
        self._specs: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._specs:
            raise ValueError(f"Duplicate tool name: {spec.name}")
        self._specs[spec.name] = spec

    def get(self, name: str) -> ToolSpec | None:
        return self._specs.get(name)

    def all(self) -> list[ToolSpec]:
        return list(self._specs.values())

    def build_tools(self, names: list[str], context: ToolContext) -> list[BaseTool]:
        """Instantiate tools by name, ignoring unknown names (defensive)."""
        tools: list[BaseTool] = []
        for name in names:
            spec = self._specs.get(name)
            if spec is not None:
                tools.append(spec.factory(context))
        return tools


def _build_registry() -> ToolRegistry:
    from langchain_core.tools import tool

    registry = ToolRegistry()

    @tool
    def calculator(expression: str) -> str:
        """Evaluate an arithmetic expression."""
        return _calculator(expression)

    @tool
    def current_datetime(timezone_name: str | None = None) -> str:
        """Get the current date and time, optionally in a given IANA timezone."""
        return _current_datetime(timezone_name)

    registry.register(ToolSpec("calculator", "Evaluate arithmetic expressions.", "builtin", lambda _ctx: calculator))
    registry.register(
        ToolSpec("current_datetime", "Current date and time in a timezone.", "builtin", lambda _ctx: current_datetime)
    )
    return registry


_tool_registry: ToolRegistry | None = None


def get_tool_registry() -> ToolRegistry:
    global _tool_registry
    if _tool_registry is None:
        _tool_registry = _build_registry()
    return _tool_registry
