"""Conversation endpoints, including the SSE chat streaming endpoint.

POST /api/conversations/{id}/messages streams one agent run:

    request session          RunTaskRegistry
         |                        |
    create user Message       register task
    create AgentRun               |
         |                        |
         +--> runner.stream_run() |  (asyncio task)
                  |               |
             PlatformEvents --> asyncio.Queue --> SSE response

The queue decouples framework streaming from the HTTP response so client
disconnects and explicit cancellation both reduce to `task.cancel()`.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.agents import events as ev
from app.agents.runner import AgentRunner, AgentRuntimeConfig
from app.agents.runs import RunTaskRegistry
from app.api.deps import CurrentSession, CurrentUser, OwnedConversation
from app.api.schemas import (
    ConversationCreate,
    ConversationDetail,
    ConversationOut,
    ConversationUpdate,
    MessageOut,
    SendMessageRequest,
)
from app.db.models import Agent, AgentRun, Conversation, Message, utcnow

router = APIRouter(prefix="/api/conversations", tags=["conversations"])

_SENTINEL = object()


@router.get("", response_model=list[ConversationOut])
async def list_conversations(
    user: CurrentUser,
    db: CurrentSession,
    agent_id: str | None = Query(default=None),
) -> list[Conversation]:
    stmt = select(Conversation).where(Conversation.owner_id == user.id)
    if agent_id:
        stmt = stmt.where(Conversation.agent_id == agent_id)
    stmt = stmt.order_by(Conversation.updated_at.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.post("", response_model=ConversationOut, status_code=status.HTTP_201_CREATED)
async def create_conversation(body: ConversationCreate, user: CurrentUser, db: CurrentSession) -> Conversation:
    agent = await db.get(Agent, body.agent_id)
    if agent is None or agent.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Agent not found")
    conv = Conversation(
        owner_id=user.id,
        agent_id=agent.id,
        title=body.title or "New conversation",
    )
    db.add(conv)
    await db.flush()
    await db.refresh(conv)
    return conv


@router.get("/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(conv: OwnedConversation, db: CurrentSession) -> ConversationDetail:
    messages = await db.execute(
        select(Message)
        .where(Message.conversation_id == conv.id)
        .order_by(Message.id.asc())
    )
    detail = ConversationDetail.model_validate(conv)
    detail.messages = [MessageOut.model_validate(m) for m in messages.scalars().all()]
    return detail


@router.patch("/{conversation_id}", response_model=ConversationOut)
async def update_conversation(
    body: ConversationUpdate, conv: OwnedConversation, db: CurrentSession
) -> Conversation:
    conv.title = body.title
    conv.updated_at = utcnow()
    db.add(conv)
    await db.flush()
    await db.refresh(conv)
    return conv


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(conv: OwnedConversation, db: CurrentSession) -> None:
    await db.delete(conv)
    await db.commit()


@router.post("/{conversation_id}/messages")
async def send_message(
    body: SendMessageRequest,
    conv: OwnedConversation,
    user: CurrentUser,
    db: CurrentSession,
    request: Request,
) -> StreamingResponse:
    registry: RunTaskRegistry = request.app.state.run_registry

    agent = await db.get(Agent, conv.agent_id)
    if agent is None or agent.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Agent not found")

    active = await db.execute(
        select(AgentRun)
        .where(AgentRun.conversation_id == conv.id, AgentRun.status == "running")
        .limit(1)
    )
    if active.scalar_one_or_none() is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "A run is already active in this conversation")

    # Persist the user message and open the run before streaming starts.
    run = AgentRun(
        conversation_id=conv.id,
        agent_id=agent.id,
        user_id=user.id,
        status="running",
        input_text=body.content,
    )
    db.add(run)
    db.add(
        Message(
            conversation_id=conv.id,
            run_id=run.id,
            role="user",
            content=body.content,
        )
    )
    conv.updated_at = utcnow()
    db.add(conv)
    await db.commit()  # commit explicitly: the run must exist before streaming

    runner: AgentRunner = request.app.state.agent_runner
    run_config = AgentRuntimeConfig.from_agent(agent)

    queue: asyncio.Queue = asyncio.Queue()

    async def _drive() -> None:
        try:
            async for event in runner.stream_run(
                config=run_config,
                conversation_id=conv.id,
                run_id=run.id,
                user_message=body.content,
            ):
                await queue.put(event)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # defensive: runner is expected to handle its own
            from app.agents.runner import classify_error

            code, message = classify_error(exc)
            await queue.put(ev.PlatformEvent(ev.RUN_FAILED, {"run_id": str(run.id), "code": code, "message": message}))
        finally:
            await queue.put(_SENTINEL)

    task = asyncio.create_task(_drive(), name=f"run-{run.id}")
    registry.register(run.id, task)

    async def sse():
        try:
            while True:
                item = await queue.get()
                if item is _SENTINEL:
                    break
                yield item.to_sse()
        finally:
            if not task.done():
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass

    return StreamingResponse(
        sse(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "X-Run-Id": str(run.id),
        },
    )
