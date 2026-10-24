"""Deterministic fake chat model for tests and keyless local development.

Enabled only through `AAP_FAKE_PROVIDER=1` (provider id "fake"). It exercises
the real execution machinery: emits a calculator tool call for arithmetic
questions, then a final answer once the tool result is in the transcript.
"""

from __future__ import annotations

from typing import Any

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult


class FakePlatformModel(BaseChatModel):
    """Stateless scripted model: user arithmetic question -> tool call -> answer."""

    @property
    def _llm_type(self) -> str:
        return "fake-platform-model"

    def bind_tools(self, tools: Any, **kwargs: Any) -> FakePlatformModel:
        return self

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
            msg = AIMessage(
                content=f"The calculator returned {last.content}.",
                usage_metadata=usage,
            )
            return ChatResult(generations=[ChatGeneration(message=msg)])

        # Tool call for arithmetic-looking questions.
        if isinstance(last, HumanMessage):
            text = last.content if isinstance(last.content, str) else ""
            if any(ch in text for ch in "+-*/"):
                msg = AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "calculator",
                            "args": {"expression": "2+2"},
                            "id": "fake_call_1",
                        }
                    ],
                    usage_metadata=usage,
                )
                return ChatResult(generations=[ChatGeneration(message=msg)])
            msg = AIMessage(
                content=f"You said: {text}",
                usage_metadata=usage,
            )
            return ChatResult(generations=[ChatGeneration(message=msg)])

        msg = AIMessage(content="(fake model) I did not understand that.", usage_metadata=usage)
        return ChatResult(generations=[ChatGeneration(message=msg)])
