"""FastAPI dependencies shared by routers."""

from __future__ import annotations

import datetime as dt
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Agent, Conversation, Session, User


def get_session_factory(request: Request) -> async_sessionmaker[AsyncSession]:
    return request.app.state.session_factory


async def db_session(
    factory: Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)],
) -> AsyncSession:
    session = factory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


CurrentSession = Annotated[AsyncSession, Depends(db_session)]


async def current_user(request: Request, db: CurrentSession) -> User:
    token = request.cookies.get("aap_session")
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    from app.security import hash_token

    stmt = select(Session).where(Session.token_hash == hash_token(token))
    sess = (await db.execute(stmt)).scalar_one_or_none()
    if sess is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid session")
    if sess.expires_at.replace(tzinfo=None) < dt.datetime.utcnow():
        await db.delete(sess)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired")
    user = await db.get(User, sess.user_id)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")
    return user


CurrentUser = Annotated[User, Depends(current_user)]


async def owned_agent(agent_id: UUID, user: CurrentUser, db: CurrentSession) -> Agent:
    agent = await db.get(Agent, agent_id)
    if agent is None or agent.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Agent not found")
    return agent


OwnedAgent = Annotated[Agent, Depends(owned_agent)]


async def owned_conversation(
    conversation_id: UUID, user: CurrentUser, db: CurrentSession
) -> Conversation:
    conv = await db.get(Conversation, conversation_id)
    if conv is None or conv.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
    return conv


OwnedConversation = Annotated[Conversation, Depends(owned_conversation)]
