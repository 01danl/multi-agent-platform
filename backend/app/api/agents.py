"""Agent CRUD endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from app.agents.providers import ModelProviderManager
from app.api.deps import CurrentSession, CurrentUser, OwnedAgent
from app.api.schemas import AgentCreate, AgentOut, AgentUpdate
from app.db.models import Agent

router = APIRouter(prefix="/api/agents", tags=["agents"])


def _providers(request: Request) -> ModelProviderManager:
    return request.app.state.providers


def _validate_provider(body: AgentCreate | AgentUpdate, providers: ModelProviderManager) -> None:
    pid = body.model_provider
    if pid is not None and pid not in providers.provider_ids():
        raise HTTPException(
            422,
            f"Unknown provider {pid!r}. Available: {', '.join(providers.provider_ids())}",
        )


@router.get("", response_model=list[AgentOut])
async def list_agents(user: CurrentUser, db: CurrentSession) -> list[Agent]:
    result = await db.execute(
        select(Agent).where(Agent.owner_id == user.id).order_by(Agent.created_at.desc())
    )
    return list(result.scalars().all())


@router.post("", response_model=AgentOut, status_code=status.HTTP_201_CREATED)
async def create_agent(body: AgentCreate, user: CurrentUser, db: CurrentSession, request: Request) -> Agent:
    _validate_provider(body, _providers(request))
    agent = Agent(owner_id=user.id, **body.model_dump())
    db.add(agent)
    await db.flush()
    await db.refresh(agent)  # server-side defaults (created_at/updated_at)
    return agent


@router.get("/{agent_id}", response_model=AgentOut)
async def get_agent(agent: OwnedAgent) -> Agent:
    return agent


@router.patch("/{agent_id}", response_model=AgentOut)
async def update_agent(
    body: AgentUpdate, agent: OwnedAgent, db: CurrentSession, request: Request
) -> Agent:
    _validate_provider(body, _providers(request))
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(agent, field, value)
    db.add(agent)
    await db.flush()
    await db.refresh(agent)  # updated_at is a server-side onupdate
    return agent


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(agent: OwnedAgent, db: CurrentSession) -> None:
    await db.delete(agent)
    await db.commit()
