"""In-process registry of live run tasks (for cancellation).

The MVP runs a single backend process; a run is an asyncio task streaming SSE
to one client. The registry maps run_id -> task so POST /runs/{id}/cancel and
client disconnects take the same path. Multi-process deployments will need a
shared signal store — documented limitation.
"""

from __future__ import annotations

import asyncio
from uuid import UUID


class RunTaskRegistry:
    def __init__(self) -> None:
        self._tasks: dict[UUID, asyncio.Task] = {}

    def register(self, run_id: UUID, task: asyncio.Task) -> None:
        self._tasks[run_id] = task
        task.add_done_callback(lambda _t: self._tasks.pop(run_id, None))

    def cancel(self, run_id: UUID) -> bool:
        task = self._tasks.get(run_id)
        if task and not task.done():
            task.cancel()
            return True
        return False

    def is_active(self, run_id: UUID) -> bool:
        task = self._tasks.get(run_id)
        return task is not None and not task.done()

    def active_ids(self) -> list[UUID]:
        return [rid for rid, t in self._tasks.items() if not t.done()]
