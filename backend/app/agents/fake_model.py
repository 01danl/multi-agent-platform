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

    @property
    def _llm_type(self) -> str:
        return "fake-platform-model"

    def bind_tools(self, tools: Any, **kwargs: Any) -> FakePlatformModel:
        names: list[str] = []
        for tool in tools:
            name = getattr(tool, "name", None) or getattr(tool, "__name__", "")
            if name:
                names.append(name)
        clone = FakePlatformModel()
        clone._bound_tool_names = tuple(names)
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
