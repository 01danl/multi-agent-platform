"""Platform streaming event schema.

Independent of both LangGraph's stream formats and any frontend rendering:
the runner adapts framework events into these, the SSE layer serializes them,
the frontend renders them. Adding a provider or changing the frontend never
changes this contract.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

RUN_STARTED = "run_started"
ASSISTANT_DELTA = "assistant_delta"
ASSISTANT_MESSAGE = "assistant_message"
TOOL_STARTED = "tool_started"
TOOL_COMPLETED = "tool_completed"
TOOL_FAILED = "tool_failed"
USAGE = "usage"
RUN_COMPLETED = "run_completed"
RUN_FAILED = "run_failed"
ERROR = "error"


@dataclass
class PlatformEvent:
    type: str
    data: dict[str, Any] = field(default_factory=dict)

    def to_sse(self) -> str:
        import json

        return f"event: {self.type}\ndata: {json.dumps(self.data, default=str)}\n\n"
