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
class ToolServices:
    """Service handles available to tool implementations.

    Kept optional so the pure built-ins (calculator, clock) never depend on
    infrastructure; service-backed tools (memory, knowledge) resolve their
    store through this object and fail with a clear error if absent.
    """

    memory_store: object | None = None  # app.memory.service.MemoryStore
    knowledge_store: object | None = None  # app.knowledge.service.KnowledgeStore


@dataclass
class ToolContext:
    """Per-run context handed to tool factories."""

    user_id: UUID
    agent_id: UUID
    conversation_id: UUID
    run_id: UUID
    services: ToolServices | None = None


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

    def _memory(ctx: ToolContext):
        from app.memory.service import MemoryStore

        store = ctx.services.memory_store if ctx.services else None
        if not isinstance(store, MemoryStore):
            raise RuntimeError("Memory is not available in this run")

        @tool
        async def save_memory(content: str, category: str = "fact") -> str:
            """Persist a durable fact, preference, or project note for future conversations.

            Only save information the user would expect you to remember.
            Do not save secrets, passwords, or sensitive personal data.

            Args:
                content: The fact to remember, one concise sentence.
                category: One of "preference", "project", "fact".
            """
            if category not in {"preference", "project", "fact"}:
                return "Error: category must be preference, project, or fact."
            memory = await store.save(
                owner_id=ctx.user_id,
                agent_id=ctx.agent_id,
                category=category,
                content=content,
                conversation_id=ctx.conversation_id,
                source="agent",
            )
            return f"Saved memory [{memory.category}]: {memory.content}"

        @tool
        async def recall_memory(query: str) -> str:
            """Search previously saved memories relevant to a query.

            Args:
                query: What to look for, e.g. "preferred language" or "project deadline".
            """
            matches = await store.recall(
                owner_id=ctx.user_id, agent_id=ctx.agent_id, query=query
            )
            if not matches:
                return "No saved memories match this query."
            lines = [f"[{m.category}] {m.content}" for m in matches]
            return "\n".join(lines)

        return [save_memory, recall_memory]

    def _memory_save_factory(ctx: ToolContext):
        return _memory(ctx)[0]

    def _memory_recall_factory(ctx: ToolContext):
        return _memory(ctx)[1]

    registry.register(
        ToolSpec("save_memory", "Persist a fact/preference for future conversations.", "memory", _memory_save_factory)
    )
    registry.register(
        ToolSpec("recall_memory", "Search saved memories by keyword.", "memory", _memory_recall_factory)
    )
    return registry


_tool_registry: ToolRegistry | None = None


def get_tool_registry() -> ToolRegistry:
    global _tool_registry
    if _tool_registry is None:
        _tool_registry = _build_registry()
    return _tool_registry
