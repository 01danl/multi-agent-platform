"""Long-term memory endpoints — explicit create/list/delete, user-scoped."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.api.deps import CurrentSession, CurrentUser
from app.api.schemas import MemoryCreate, MemoryOut
from app.db.models import Memory

router = APIRouter(prefix="/api/memories", tags=["memories"])


@router.get("", response_model=list[MemoryOut])
async def list_memories(
    user: CurrentUser,
    db: CurrentSession,
    agent_id: Annotated[UUID | None, Query()] = None,
) -> list[Memory]:
    stmt = select(Memory).where(Memory.owner_id == user.id)
    if agent_id is not None:
        stmt = stmt.where(Memory.agent_id == agent_id)
    stmt = stmt.order_by(Memory.created_at.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.post("", response_model=MemoryOut, status_code=status.HTTP_201_CREATED)
async def create_memory(body: MemoryCreate, user: CurrentUser, db: CurrentSession) -> Memory:
    memory = Memory(
        owner_id=user.id,
        agent_id=body.agent_id,
        category=body.category,
        content=body.content.strip(),
        source="manual",
    )
    db.add(memory)
    await db.flush()
    await db.refresh(memory)
    return memory


@router.delete("/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_memory(memory_id: UUID, user: CurrentUser, db: CurrentSession) -> None:
    memory = await db.get(Memory, memory_id)
    if memory is None or memory.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Memory not found")
    await db.delete(memory)
    await db.commit()
