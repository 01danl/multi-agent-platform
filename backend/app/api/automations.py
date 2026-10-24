"""Automation endpoints: CRUD, enable/disable, trigger-now.

Execution history is the normal Execution Logs view filtered by
`automation_id` (GET /api/runs?automation_id=...).
"""

from __future__ import annotations

import datetime as dt
import re
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.api.deps import CurrentSession, CurrentUser
from app.db.models import Agent, Automation

router = APIRouter(prefix="/api/automations", tags=["automations"])

_TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


class AutomationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    agent_id: UUID
    prompt: str = Field(min_length=1, max_length=8000)
    schedule_type: str = Field(pattern="^(interval|daily)$")
    interval_minutes: int | None = Field(default=None, ge=1, le=525600)
    daily_at: str | None = Field(default=None, max_length=5)
    enabled: bool = True


class AutomationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    prompt: str | None = Field(default=None, min_length=1, max_length=8000)
    schedule_type: str | None = Field(default=None, pattern="^(interval|daily)$")
    interval_minutes: int | None = Field(default=None, ge=1, le=525600)
    daily_at: str | None = Field(default=None, max_length=5)
    enabled: bool | None = None


class AutomationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    agent_id: UUID
    name: str
    prompt: str
    schedule_type: str
    interval_minutes: int | None
    daily_at: str | None
    enabled: bool
    last_run_at: dt.datetime | None = None
    created_at: dt.datetime


async def _validate_schedule(schedule_type: str | None, interval: int | None, daily_at: str | None) -> None:
    st = schedule_type or "interval"
    if st == "interval" and not interval:
        raise HTTPException(422, "interval schedule requires interval_minutes")
    if st == "daily":
        if not daily_at or not _TIME_RE.match(daily_at):
            raise HTTPException(422, "daily schedule requires daily_at in HH:MM (24h)")


def _scheduler(request: Request):
    from app.scheduler.service import AutomationScheduler

    scheduler = getattr(request.app.state, "automation_scheduler", None)
    if not isinstance(scheduler, AutomationScheduler):
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Scheduler unavailable")
    return scheduler


@router.get("", response_model=list[AutomationOut])
async def list_automations(user: CurrentUser, db: CurrentSession) -> list[Automation]:
    result = await db.execute(
        select(Automation).where(Automation.owner_id == user.id).order_by(Automation.created_at.desc())
    )
    return list(result.scalars().all())


@router.post("", response_model=AutomationOut, status_code=status.HTTP_201_CREATED)
async def create_automation(
    body: AutomationCreate, user: CurrentUser, db: CurrentSession, request: Request
) -> Automation:
    agent = await db.get(Agent, body.agent_id)
    if agent is None or agent.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Agent not found")
    await _validate_schedule(body.schedule_type, body.interval_minutes, body.daily_at)
    automation = Automation(
        owner_id=user.id,
        agent_id=agent.id,
        name=body.name,
        prompt=body.prompt,
        schedule_type=body.schedule_type,
        interval_minutes=body.interval_minutes if body.schedule_type == "interval" else None,
        daily_at=body.daily_at if body.schedule_type == "daily" else None,
        enabled=body.enabled,
    )
    db.add(automation)
    await db.commit()
    await db.refresh(automation)
    if automation.enabled:
        _scheduler(request).sync(automation)
    return automation


@router.patch("/{automation_id}", response_model=AutomationOut)
async def update_automation(
    automation_id: UUID,
    body: AutomationUpdate,
    user: CurrentUser,
    db: CurrentSession,
    request: Request,
) -> Automation:
    automation = await db.get(Automation, automation_id)
    if automation is None or automation.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Automation not found")

    updates = body.model_dump(exclude_unset=True)
    schedule_type = updates.get("schedule_type", automation.schedule_type)
    interval = updates.get("interval_minutes", automation.interval_minutes)
    daily_at = updates.get("daily_at", automation.daily_at)
    await _validate_schedule(schedule_type, interval, daily_at)
    for field, value in updates.items():
        setattr(automation, field, value)
    automation.interval_minutes = interval if schedule_type == "interval" else None
    automation.daily_at = daily_at if schedule_type == "daily" else None
    db.add(automation)
    await db.commit()
    await db.refresh(automation)
    _scheduler(request).sync(automation)
    return automation


@router.delete("/{automation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_automation(
    automation_id: UUID, user: CurrentUser, db: CurrentSession, request: Request
) -> None:
    automation = await db.get(Automation, automation_id)
    if automation is None or automation.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Automation not found")
    _scheduler(request).unregister(automation_id)
    await db.delete(automation)
    await db.commit()


@router.post("/{automation_id}/run", status_code=status.HTTP_202_ACCEPTED)
async def trigger_now(
    automation_id: UUID, user: CurrentUser, db: CurrentSession, request: Request
) -> dict:
    automation = await db.get(Automation, automation_id)
    if automation is None or automation.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Automation not found")
    run = await _scheduler(request).fire(automation_id)
    if run is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Automation is disabled or its agent is gone")
    return {"run_id": str(run.id), "status": "running"}
