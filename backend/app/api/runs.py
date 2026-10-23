"""Execution inspector endpoints: list runs, run detail with trace, cancel."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, status
from sqlalchemy import select

from app.agents.runs import RunTaskRegistry
from app.api.deps import CurrentSession, CurrentUser
from app.api.schemas import RunDetail, RunEventOut, RunOut
from app.db.models import AgentRun, RunEvent

router = APIRouter(prefix="/api/runs", tags=["runs"])


@router.get("", response_model=list[RunOut])
async def list_runs(
    user: CurrentUser,
    db: CurrentSession,
    conversation_id: UUID | None = Query(default=None),
    agent_id: UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[AgentRun]:
    stmt = select(AgentRun).where(AgentRun.user_id == user.id)
    if conversation_id is not None:
        stmt = stmt.where(AgentRun.conversation_id == conversation_id)
    if agent_id is not None:
        stmt = stmt.where(AgentRun.agent_id == agent_id)
    stmt = stmt.order_by(AgentRun.started_at.desc()).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/{run_id}", response_model=RunDetail)
async def get_run(run_id: UUID, user: CurrentUser, db: CurrentSession) -> RunDetail:
    run = await db.get(AgentRun, run_id)
    if run is None or run.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found")
    events = await db.execute(
        select(RunEvent).where(RunEvent.run_id == run.id).order_by(RunEvent.id.asc())
    )
    detail = RunDetail.model_validate(run)
    detail.events = [RunEventOut.model_validate(e) for e in events.scalars().all()]
    return detail


@router.post("/{run_id}/cancel")
async def cancel_run(run_id: UUID, user: CurrentUser, db: CurrentSession, request: Request) -> dict:
    run = await db.get(AgentRun, run_id)
    if run is None or run.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found")
    registry: RunTaskRegistry = request.app.state.run_registry
    cancelled = registry.cancel(run.id)
    return {"cancelled": cancelled, "status": "cancelling" if cancelled else run.status}
