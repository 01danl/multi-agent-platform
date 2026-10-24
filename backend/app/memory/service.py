"""Long-term memory storage and retrieval.

Deliberately simple and reliable for Phase 2: explicit rows, keyword-scored
recall (deterministic, testable), no automatic capture. Semantic recall is a
later upgrade behind this same interface (see docs/architecture/07).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Memory

_WORD = re.compile(r"[a-z0-9а-яё]+", re.IGNORECASE)


def _as_uuid(value: UUID | str) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


def _tokens(text: str) -> set[str]:
    return {t.lower() for t in _WORD.findall(text)}


class MemoryStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = session_factory

    async def save(
        self,
        *,
        owner_id: UUID | str,
        agent_id: UUID | str | None,
        category: str,
        content: str,
        conversation_id: UUID | str | None = None,
        source: str = "agent",
    ) -> Memory:
        owner_id, agent_id = _as_uuid(owner_id), agent_id and _as_uuid(agent_id)
        conversation_id = conversation_id and _as_uuid(conversation_id)
        async with self._sessions() as session:
            memory = Memory(
                owner_id=owner_id,
                agent_id=agent_id,
                category=category,
                content=content.strip(),
                source=source,
                conversation_id=conversation_id,
            )
            session.add(memory)
            await session.commit()
            await session.refresh(memory)
            return memory

    async def delete(self, *, owner_id: UUID | str, memory_id: UUID | str) -> bool:
        owner_id, memory_id = _as_uuid(owner_id), _as_uuid(memory_id)
        async with self._sessions() as session:
            memory = await session.get(Memory, memory_id)
            if memory is None or memory.owner_id != owner_id:
                return False
            await session.delete(memory)
            await session.commit()
            return True

    async def list_for_agent(self, *, owner_id: UUID | str, agent_id: UUID | str) -> Sequence[Memory]:
        """Memories visible to an agent run: its own plus the owner's global ones."""
        owner_id, agent_id = _as_uuid(owner_id), _as_uuid(agent_id)
        async with self._sessions() as session:
            stmt = (
                select(Memory)
                .where(
                    Memory.owner_id == owner_id,
                    or_(Memory.agent_id == agent_id, Memory.agent_id.is_(None)),
                )
                .order_by(Memory.created_at.asc())
                .limit(200)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def recall(
        self, *, owner_id: UUID, agent_id: UUID, query: str, limit: int = 5
    ) -> list[Memory]:
        """Keyword-overlap scoring over the agent-visible memories."""
        memories = await self.list_for_agent(owner_id=owner_id, agent_id=agent_id)
        query_tokens = _tokens(query)
        scored: list[tuple[int, int, Memory]] = []
        for i, memory in enumerate(memories):
            content_tokens = _tokens(memory.content)
            overlap = len(query_tokens & content_tokens)
            if overlap > 0:
                scored.append((overlap, -i, memory))  # recency tiebreak
        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [memory for _, _, memory in scored[:limit]]

    @staticmethod
    def build_preamble(memories: Sequence[Memory]) -> str:
        if not memories:
            return ""
        lines = [
            f"- [{memory.category}] {memory.content}" for memory in memories[-50:]
        ]
        return "\n## Stored memories (may be relevant; verify before relying on them)\n" + "\n".join(lines)
