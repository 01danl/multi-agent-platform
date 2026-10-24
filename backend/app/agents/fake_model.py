"""Deterministic fake chat model for tests and keyless local development.

Enabled only through `FAKE_PROVIDER_ENABLED=true` (provider id "fake"). It
exercises the real execution machinery with scripted tool calls:
- arithmetic questions -> calculator call -> answer,
- questions while knowledge_search is bound -> search call -> grounded answer,
- everything else echoes the input.
"""

from __future__ import annotations

from typing import Any

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult


class FakePlatformModel(BaseChatModel):
    """Stateless scripted model driving the real tool-calling loop."""

    _bound_tool_names: tuple[str, ...] = ()
    _bound_tool_args: dict[str, tuple[str, ...]] = {}

    @property
    def _llm_type(self) -> str:
        return "fake-platform-model"

    def bind_tools(self, tools: Any, **kwargs: Any) -> FakePlatformModel:
        names: list[str] = []
        arg_keys: dict[str, tuple[str, ...]] = {}
        for tool in tools:
            name = getattr(tool, "name", None) or getattr(tool, "__name__", "")
            if not name:
                continue
            names.append(name)
            try:
                args = getattr(tool, "args", None)
            except Exception:
                args = None
            if isinstance(args, dict):
                arg_keys[name] = tuple(args.keys())
        clone = FakePlatformModel()
        clone._bound_tool_names = tuple(names)
        clone._bound_tool_args = arg_keys
        return clone

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        usage = {"input_tokens": 12, "output_tokens": 6, "total_tokens": 18}
        last = messages[-1] if messages else None

        # Tool result is in the transcript -> produce the final answer.
        if isinstance(last, ToolMessage):
            result = last.content if isinstance(last.content, str) else str(last.content)
            if last.name == "calculator":
                content = f"The calculator returned {result}."
            elif last.name == "task":
                content = f"The specialist agent reported: {result[:400]}"
            else:
                preview = result[:400]
                content = f"Based on the retrieved sources: {preview}"
            msg = AIMessage(content=content, usage_metadata=usage)
            return ChatResult(generations=[ChatGeneration(message=msg)])

        if isinstance(last, HumanMessage):
            text = last.content if isinstance(last.content, str) else ""

            if any(ch in text for ch in "+-*/") and "calculator" in self._bound_tool_names:
                msg = AIMessage(
                    content="",
                    tool_calls=[
                        {"name": "calculator", "args": {"expression": "2+2"}, "id": "fake_call_1"}
                    ],
                    usage_metadata=usage,
                )
                return ChatResult(generations=[ChatGeneration(message=msg)])

            if "task" in self._bound_tool_names:
                import re

                match = re.search(r"delegate to ([a-z0-9-]+)", text.lower())
                if match:
                    msg = AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": "task",
                                "args": {
                                    "subagent_type": match.group(1),
                                    "description": text,
                                },
                                "id": "fake_task_1",
                            }
                        ],
                        usage_metadata=usage,
                    )
                    return ChatResult(generations=[ChatGeneration(message=msg)])

            # MCP demo rule: "use mcp <tool> with A and B" -> call that tool
            import re as _re

            mcp_match = _re.search(r"use mcp ([a-z0-9_-]+) with (-?\d+) and (-?\d+)", text.lower())
            if (
                mcp_match
                and mcp_match.group(1) in self._bound_tool_names
                and self._bound_tool_args.get(mcp_match.group(1))
            ):
                tool_name = mcp_match.group(1)
                keys = self._bound_tool_args[tool_name]
                args = {keys[0]: int(mcp_match.group(2)), keys[1]: int(mcp_match.group(3))}
                msg = AIMessage(
                    content="",
                    tool_calls=[{"name": tool_name, "args": args, "id": "fake_mcp_1"}],
                    usage_metadata=usage,
                )
                return ChatResult(generations=[ChatGeneration(message=msg)])

            if "knowledge_search" in self._bound_tool_names and "?" in text:
                msg = AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "knowledge_search",
                            "args": {"query": text[:200]},
                            "id": "fake_kb_1",
                        }
                    ],
                    usage_metadata=usage,
                )
                return ChatResult(generations=[ChatGeneration(message=msg)])

            msg = AIMessage(content=f"You said: {text}", usage_metadata=usage)
            return ChatResult(generations=[ChatGeneration(message=msg)])

        msg = AIMessage(content="(fake model) I did not understand that.", usage_metadata=usage)
        return ChatResult(generations=[ChatGeneration(message=msg)])
