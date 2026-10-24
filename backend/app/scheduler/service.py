"""Automation scheduler: recurring agent tasks through the normal runner.

Design points (spec: jobs run through the same agent execution services as
the chat interface; no separate incompatible path):
- Each fire creates a fresh conversation titled "Automation: <name> <n>" so
  transcripts are isolated and inspectable like any chat.
- The AgentRun row carries automation_id — Execution Logs filter by it.
- APScheduler AsyncIOScheduler, one process (documented limitation):
  jobs are re-registered from the database at startup; coalesce + one
  instance per job prevents duplicate concurrent execution.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select, update

from app.db.models import Agent, AgentRun, Automation, Conversation, Message

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.agents.runner import AgentRunner

logger = logging.getLogger("agent-platform.scheduler")

_EXECUTION_TASKS: set = set()

_MISFIRE_GRACE_SECONDS = 300


def _as_uuid(value: UUID | str) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


class AutomationScheduler:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession], runner: AgentRunner) -> None:
        self._sessions = session_factory
        self._runner = runner
        self._scheduler = AsyncIOScheduler(
            job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": _MISFIRE_GRACE_SECONDS}
        )
        self._fire_counts: dict[UUID, int] = {}

    # ------------------------------------------------------------- lifecycle

    async def start(self) -> None:
        async with self._sessions() as session:
            automations = (
                await session.execute(select(Automation).where(Automation.enabled.is_(True)))
            ).scalars().all()
        for automation in automations:
            self._register(automation)
        self._scheduler.start()
        logger.info("Scheduler started with %d automation(s)", len(automations))

    def shutdown(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)

    # -------------------------------------------------------------- triggers

    def _trigger(self, automation: Automation):
        if automation.schedule_type == "interval":
            minutes = max(1, int(automation.interval_minutes or 60))
            return IntervalTrigger(minutes=minutes)
        hour, minute = (automation.daily_at or "09:00").split(":")
        return CronTrigger(hour=int(hour), minute=int(minute))

    def _register(self, automation: Automation) -> None:
        job_id = self.job_id(automation.id)
        self._scheduler.add_job(
            self._fire,
            trigger=self._trigger(automation),
            id=job_id,
            replace_existing=True,
            kwargs={"automation_id": automation.id},
        )

    def unregister(self, automation_id: UUID | str) -> None:
        from apscheduler.jobstores.base import JobLookupError

        try:
            self._scheduler.remove_job(self.job_id(automation_id))
        except JobLookupError:
            pass

    def sync(self, automation: Automation) -> None:
        """Register, update, or remove the job to match the automation row."""
        if automation.enabled:
            self._register(automation)
        else:
            self.unregister(automation.id)

    @staticmethod
    def job_id(automation_id: UUID | str) -> str:
        return f"automation-{_as_uuid(automation_id)}"

    @property
    def job_count(self) -> int:
        return len(self._scheduler.get_jobs())

    # ------------------------------------------------------------------ fire

    async def _load(self, automation_id: UUID) -> tuple[Automation, Agent] | None:
        async with self._sessions() as session:
            automation = await session.get(Automation, automation_id)
            if automation is None or not automation.enabled:
                return None
            agent = await session.get(Agent, automation.agent_id)
            if agent is None or agent.owner_id != automation.owner_id:
                return None
            return automation, agent

    async def _fire(self, automation_id: UUID) -> None:
        try:
            await self.fire(automation_id)
        except Exception:
            logger.exception("Automation %s failed", automation_id)

    async def fire(self, automation_id: UUID | str) -> AgentRun | None:
        """Execute an automation now (used by the scheduler and trigger-now)."""
        from app.agents.runner import AgentRuntimeConfig

        automation_id = _as_uuid(automation_id)
        loaded = await self._load(automation_id)
        if loaded is None:
            self.unregister(automation_id)
            return None
        automation, agent = loaded

        async with self._sessions() as session:
            count = self._fire_counts.get(automation_id, 0) + 1
            self._fire_counts[automation_id] = count
            conversation = Conversation(
                owner_id=automation.owner_id,
                agent_id=agent.id,
                title=f"Automation: {automation.name} #{count}",
            )
            session.add(conversation)
            await session.flush()
            run = AgentRun(
                conversation_id=conversation.id,
                agent_id=agent.id,
                user_id=automation.owner_id,
                status="running",
                input_text=automation.prompt,
                automation_id=automation_id,
            )
            session.add(run)
            session.add(
                Message(
                    conversation_id=conversation.id,
                    run_id=run.id,
                    role="user",
                    content=automation.prompt,
                )
            )
            await session.execute(
                update(Automation)
                .where(Automation.id == automation_id)
                .values(last_run_at=datetime.now(UTC))
            )
            await session.commit()
            await session.refresh(run)

        config = AgentRuntimeConfig.from_agent(agent)
        logger.info("Automation %s firing run %s", automation.name, run.id)

        async def _execute() -> None:
            async for _ in self._runner.stream_run(
                config=config,
                conversation_id=conversation.id,
                run_id=run.id,
                user_message=automation.prompt,
            ):
                pass  # the runner persists transcript/trace; events are not streamed to anyone

        import asyncio

        # Fire-and-forget: the runner persists results; the scheduler loop
        # must not block on execution.
        task = asyncio.get_running_loop().create_task(_execute())
        _EXECUTION_TASKS.add(task)
        task.add_done_callback(_EXECUTION_TASKS.discard)
        return run
