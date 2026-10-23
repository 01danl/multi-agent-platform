"""AgentRunner — the platform's execution harness around Deep Agents.

Responsibilities (and nothing more):
- translate a persisted `Agent` config into a `create_deep_agent(...)` graph,
- stream that graph, adapting LangGraph stream items into platform events,
- persist the transcript (assistant/tool messages) and run trace while streaming,
- enforce limits (model-call cap, recursion limit, wall-clock timeout),
- classify failures into structured error codes.

The tool-calling loop, state management and checkpointing belong to the
framework — this module never reimplements them.

Session discipline: the runner receives plain data (`AgentRuntimeConfig`,
ids) — never ORM objects owned by another session — and works exclusively
through its own session.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from uuid import UUID

from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, ToolMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.errors import GraphRecursionError

from app.agents import events as ev
from app.agents.tools import ToolContext, ToolRegistry

if TYPE_CHECKING:
    from langchain_core.language_models.chat_models import BaseChatModel
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.agents.providers import ModelProviderManager
    from app.config import Settings

logger = logging.getLogger("agent-platform.runner")

ModelFactory = Callable[["AgentRuntimeConfig"], "BaseChatModel"]


@dataclass(frozen=True)
class AgentRuntimeConfig:
    """Plain-data snapshot of an agent configuration, safe to pass across sessions."""

    agent_id: UUID
    owner_id: UUID
    name: str
    system_prompt: str
    model_provider: str
    model_name: str
    temperature: float
    max_output_tokens: int | None
    enabled_tools: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_agent(cls, agent) -> "AgentRuntimeConfig":
        return cls(
            agent_id=agent.id,
            owner_id=agent.owner_id,
            name=agent.name,
            system_prompt=agent.system_prompt,
            model_provider=agent.model_provider,
            model_name=agent.model_name,
            temperature=agent.temperature,
            max_output_tokens=agent.max_output_tokens,
            enabled_tools=tuple(agent.enabled_tools or []),
        )


class RunError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _text_of(content: object) -> str:
    """Extract plain text from str or content-block list."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
        return "".join(parts)
    return ""


def _serialize_tool_calls(msg: AIMessage | AIMessageChunk) -> list[dict]:
    out = []
    for tc in msg.tool_calls or []:
        out.append({"id": tc.get("id"), "name": tc.get("name"), "args": tc.get("args")})
    return out


class AgentRunner:
    def __init__(
        self,
        settings: Settings,
        providers: ModelProviderManager,
        tool_registry: ToolRegistry,
        checkpointer: BaseCheckpointSaver,
        session_factory: async_sessionmaker[AsyncSession],
        model_factory: ModelFactory | None = None,
    ) -> None:
        self._settings = settings
        self._providers = providers
        self._tools = tool_registry
        self._checkpointer = checkpointer
        self._sessions = session_factory
        self._model_factory = model_factory or providers.build_model

    # ------------------------------------------------------------------ graph

    def build_graph(self, config: AgentRuntimeConfig, tool_context: ToolContext):
        from deepagents import create_deep_agent
        from langchain.agents.middleware import ModelCallLimitMiddleware

        model = self._model_factory(config)
        tools = self._tools.build_tools(list(config.enabled_tools), tool_context)
        return create_deep_agent(
            model=model,
            tools=tools,
            system_prompt=config.system_prompt or "You are a helpful assistant.",
            middleware=[ModelCallLimitMiddleware(run_limit=self._settings.max_model_calls_per_run)],
            checkpointer=self._checkpointer,
        )

    # ------------------------------------------------------------------- run

    async def stream_run(
        self,
        *,
        config: AgentRuntimeConfig,
        conversation_id: UUID,
        run_id: UUID,
        user_message: str,
    ) -> AsyncIterator[ev.PlatformEvent]:
        """Stream one run, persisting transcript and trace as events arrive.

        Cancellation: the caller cancels the task consuming this generator;
        we mark the run cancelled and stop.
        """
        from app.db.models import AgentRun, Message, RunEvent

        thread_id = f"conv:{conversation_id}"
        graph_config = {
            "configurable": {"thread_id": thread_id},
            "recursion_limit": self._settings.graph_recursion_limit,
        }
        tool_context = ToolContext(
            user_id=config.owner_id,
            agent_id=config.agent_id,
            conversation_id=conversation_id,
            run_id=run_id,
        )

        started = time.monotonic()
        usage_totals = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "model_calls": 0}
        announced_tools: set[str] = set()
        persisted_assistant_ids: set[str] = set()
        session = self._sessions()

        async def record_event(event_type: str, payload: dict) -> None:
            session.add(RunEvent(run_id=run_id, event_type=event_type, payload=payload))
            await session.commit()

        async def load_run() -> AgentRun | None:
            return await session.get(AgentRun, run_id)

        try:
            graph = self.build_graph(config, tool_context)
        except Exception as exc:
            yield await self._fail(session, run_id, exc, started, usage_totals)
            return

        yield ev.PlatformEvent(ev.RUN_STARTED, {"run_id": str(run_id), "agent_id": str(config.agent_id)})

        try:
            async with asyncio.timeout(self._settings.run_timeout_seconds):
                stream = graph.astream(
                    {"messages": [("user", user_message)]},
                    config=graph_config,
                    stream_mode=["messages", "updates"],
                )
                async for mode, data in stream:
                    if mode == "messages":
                        for event in self._adapt_message_item(data, announced_tools):
                            yield event
                    elif mode == "updates":
                        async for event in self._consume_update(
                            data,
                            conversation_id=conversation_id,
                            run_id=run_id,
                            session=session,
                            usage_totals=usage_totals,
                            persisted_ids=persisted_assistant_ids,
                        ):
                            yield event
            await self._finalize(session, run_id, "completed", started, usage_totals)
        except asyncio.CancelledError:
            await self._finalize(session, run_id, "cancelled", started, usage_totals)
            raise
        except asyncio.TimeoutError:
            error = RunError("run_timeout", "The run exceeded the configured time limit.")
            yield await self._fail(session, run_id, error, started, usage_totals)
            return
        except Exception as exc:
            yield await self._fail(session, run_id, exc, started, usage_totals)
            return
        finally:
            await session.close()

        if usage_totals["model_calls"]:
            yield ev.PlatformEvent(ev.USAGE, dict(usage_totals))
        yield ev.PlatformEvent(
            ev.RUN_COMPLETED,
            {
                "run_id": str(run_id),
                "duration_ms": int((time.monotonic() - started) * 1000),
                "usage": usage_totals,
            },
        )

    # ------------------------------------------------------------- adaptation

    def _adapt_message_item(
        self, item: tuple[BaseMessage, dict], announced: set[str]
    ) -> list[ev.PlatformEvent]:
        """Adapt a `stream_mode="messages"` item into user-facing events."""
        msg, metadata = item
        node = metadata.get("langgraph_node") or ""
        out: list[ev.PlatformEvent] = []
        if isinstance(msg, ToolMessage):
            status = getattr(msg, "status", "success")
            payload = {"tool_call_id": msg.tool_call_id, "name": msg.name or "", "node": node}
            if status == "error":
                payload["error"] = _text_of(msg.content)[:2000]
                out.append(ev.PlatformEvent(ev.TOOL_FAILED, payload))
            else:
                payload["output"] = _text_of(msg.content)[:4000]
                out.append(ev.PlatformEvent(ev.TOOL_COMPLETED, payload))
            return out
        if isinstance(msg, AIMessage | AIMessageChunk):
            text = _text_of(msg.content)
            if text:
                out.append(ev.PlatformEvent(ev.ASSISTANT_DELTA, {"delta": text}))
            for tc in getattr(msg, "tool_call_chunks", None) or []:
                name, call_id = tc.get("name"), tc.get("id")
                if name and call_id and call_id not in announced:
                    announced.add(call_id)
                    out.append(ev.PlatformEvent(ev.TOOL_STARTED, {"tool_call_id": call_id, "name": name}))
            # Fakes and some providers emit complete tool calls without chunks.
            for tc in msg.tool_calls or []:
                call_id = tc.get("id")
                if call_id and call_id not in announced:
                    announced.add(call_id)
                    out.append(
                        ev.PlatformEvent(
                            ev.TOOL_STARTED,
                            {"tool_call_id": call_id, "name": tc.get("name", "")},
                        )
                    )
        return out

    async def _consume_update(
        self,
        update: dict,
        *,
        conversation_id: UUID,
        run_id: UUID,
        session,
        usage_totals: dict,
        persisted_ids: set[str],
    ) -> AsyncIterator[ev.PlatformEvent]:
        """Persist final messages from a `stream_mode="updates"` node update."""
        from app.db.models import Message, RunEvent

        if not isinstance(update, dict):
            return
        for node, node_update in update.items():
            if not isinstance(node_update, dict):
                continue
            for msg in node_update.get("messages") or []:
                if isinstance(msg, AIMessage):
                    um = msg.usage_metadata or {}
                    usage_totals["input_tokens"] += um.get("input_tokens") or 0
                    usage_totals["output_tokens"] += um.get("output_tokens") or 0
                    usage_totals["total_tokens"] += um.get("total_tokens") or 0
                    usage_totals["model_calls"] += 1
                    session.add(
                        RunEvent(
                            run_id=run_id,
                            event_type="model_call",
                            payload={
                                "node": node,
                                "tool_calls": _serialize_tool_calls(msg),
                                "content_preview": _text_of(msg.content)[:500],
                                "usage": {
                                    "input_tokens": um.get("input_tokens"),
                                    "output_tokens": um.get("output_tokens"),
                                    "total_tokens": um.get("total_tokens"),
                                },
                            },
                        )
                    )
                    if msg.id and msg.id in persisted_ids:
                        continue
                    if msg.id:
                        persisted_ids.add(msg.id)
                    session.add(
                        Message(
                            conversation_id=conversation_id,
                            run_id=run_id,
                            role="assistant",
                            content=_text_of(msg.content),
                            tool_calls=_serialize_tool_calls(msg) or None,
                        )
                    )
                    await session.commit()
                    yield ev.PlatformEvent(
                        ev.ASSISTANT_MESSAGE,
                        {"content": _text_of(msg.content), "tool_calls": _serialize_tool_calls(msg)},
                    )
                elif isinstance(msg, ToolMessage):
                    session.add(
                        Message(
                            conversation_id=conversation_id,
                            run_id=run_id,
                            role="tool",
                            content=_text_of(msg.content),
                            tool_call_id=msg.tool_call_id,
                            name=msg.name,
                        )
                    )
                    await session.commit()

    # --------------------------------------------------------------- finalize

    async def _fail(
        self, session, run_id: UUID, exc: Exception, started: float, usage: dict
    ) -> ev.PlatformEvent:
        code, message = classify_error(exc)
        logger.warning("Run %s failed: %s: %s", run_id, code, exc)
        await self._finalize(session, run_id, "failed", started, usage, error_code=code, error_message=message)
        return ev.PlatformEvent(ev.RUN_FAILED, {"run_id": str(run_id), "code": code, "message": message})

    async def _finalize(
        self,
        session,
        run_id: UUID,
        status: str,
        started: float,
        usage: dict,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None:
        from app.db.models import AgentRun, RunEvent

        run = await session.get(AgentRun, run_id)
        if run is not None:
            from app.db.models import utcnow

            run.status = status
            run.finished_at = utcnow()
            run.usage = dict(usage)
            run.error_code = error_code
            run.error_message = error_message
            session.add(run)
        session.add(
            RunEvent(
                run_id=run_id,
                event_type=f"run_{status}",
                payload={
                    "duration_ms": int((time.monotonic() - started) * 1000),
                    "code": error_code,
                    "usage": dict(usage),
                },
            )
        )
        await session.commit()


def classify_error(exc: Exception) -> tuple[str, str]:
    """Map framework/provider exceptions to (code, user-facing message).

    Matching is by exception class name so we do not need to import every
    provider's exception hierarchy (OpenAI/Anthropic/etc. reuse these names).
    """
    name = type(exc).__name__
    mapping = {
        "AuthenticationError": ("provider_auth_error", "The model provider rejected the API key."),
        "RateLimitError": ("provider_rate_limited", "The model provider rate limit was hit. Try again later."),
        "APITimeoutError": ("provider_timeout", "The model provider timed out."),
        "APIConnectionError": ("provider_connection_error", "Could not connect to the model provider."),
        "NotFoundError": ("provider_model_not_found", "The configured model was not found at the provider."),
        "BadRequestError": ("provider_bad_request", "The model provider rejected the request."),
        "GraphRecursionError": ("run_limit_exceeded", "The run exceeded the execution step limit."),
        "OutputParserException": ("run_invalid_model_output", "The model produced output that could not be parsed."),
    }
    if isinstance(exc, GraphRecursionError):
        return mapping["GraphRecursionError"]
    if name in mapping:
        return mapping[name]
    from app.agents.providers import ProviderError

    if isinstance(exc, ProviderError):
        return ("provider_not_configured", str(exc))
    if isinstance(exc, RunError):
        return (exc.code, exc.message)
    return ("run_error", "The agent run failed. Check the execution log for details.")


def thread_id_for(conversation_id: UUID | str) -> str:
    return f"conv:{conversation_id}"
