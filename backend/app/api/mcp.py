"""MCP server endpoints: CRUD, tool discovery, snapshot listing."""

from __future__ import annotations

import datetime as dt
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.api.deps import CurrentSession, CurrentUser
from app.db.models import McpServer

router = APIRouter(prefix="/api/mcp", tags=["mcp"])


class McpServerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    transport: str = Field(pattern="^(stdio|http)$")
    command: str | None = Field(default=None, max_length=500)
    args: list[str] = Field(default_factory=list)
    url: str | None = Field(default=None, max_length=500)
    enabled: bool = True


class McpServerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    command: str | None = Field(default=None, max_length=500)
    args: list[str] | None = None
    url: str | None = Field(default=None, max_length=500)
    enabled: bool | None = None


class McpServerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    transport: str
    command: str | None
    args_json: list[str]
    url: str | None
    enabled: bool
    created_at: dt.datetime


class McpToolOut(BaseModel):
    name: str
    description: str


def _validate_transport(transport: str, command: str | None, url: str | None) -> None:
    if transport == "stdio" and not command:
        raise HTTPException(422, "stdio transport requires a command")
    if transport == "http" and not url:
        raise HTTPException(422, "http transport requires a url")


def _service(request: Request):
    from app.mcp.service import McpService

    service = getattr(request.app.state, "mcp_service", None)
    if not isinstance(service, McpService):
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "MCP service unavailable")
    return service


async def _owned_server(server_id: UUID, user, db) -> McpServer:
    server = await db.get(McpServer, server_id)
    if server is None or server.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "MCP server not found")
    return server


@router.get("", response_model=list[McpServerOut])
async def list_servers(user: CurrentUser, db: CurrentSession) -> list[McpServer]:
    result = await db.execute(
        select(McpServer).where(McpServer.owner_id == user.id).order_by(McpServer.created_at.desc())
    )
    return list(result.scalars().all())


@router.post("", response_model=McpServerOut, status_code=status.HTTP_201_CREATED)
async def create_server(
    body: McpServerCreate, user: CurrentUser, db: CurrentSession
) -> McpServer:
    _validate_transport(body.transport, body.command, body.url)
    server = McpServer(
        owner_id=user.id,
        name=body.name,
        transport=body.transport,
        command=body.command,
        args_json=body.args,
        url=body.url,
        enabled=body.enabled,
    )
    db.add(server)
    await db.commit()
    await db.refresh(server)
    return server


@router.patch("/{server_id}", response_model=McpServerOut)
async def update_server(
    server_id: UUID,
    body: McpServerUpdate,
    user: CurrentUser,
    db: CurrentSession,
) -> McpServer:
    server = await _owned_server(server_id, user, db)
    for field, value in body.model_dump(exclude_unset=True).items():
        if field == "args":
            server.args_json = value
        else:
            setattr(server, field, value)
    _validate_transport(server.transport, server.command, server.url)
    db.add(server)
    await db.commit()
    await db.refresh(server)
    return server


@router.delete("/{server_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_server(server_id: UUID, user: CurrentUser, db: CurrentSession) -> None:
    server = await _owned_server(server_id, user, db)
    await db.delete(server)
    await db.commit()


@router.post("/{server_id}/discover", response_model=list[McpToolOut])
async def discover_tools(server_id: UUID, user: CurrentUser, db: CurrentSession, request: Request):
    server = await _owned_server(server_id, user, db)
    if not server.enabled:
        raise HTTPException(status.HTTP_409_CONFLICT, "Server is disabled")
    try:
        return await _service(request).discover(owner_id=user.id, server_id=server_id)
    except LookupError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "MCP server not found") from None
    except Exception as exc:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, f"MCP server connection failed: {str(exc)[:300]}"
        ) from exc


@router.get("/{server_id}/tools", response_model=list[McpToolOut])
async def list_tools(server_id: UUID, user: CurrentUser, db: CurrentSession, request: Request):
    await _owned_server(server_id, user, db)
    snapshots = await _service(request).list_snapshots(owner_id=user.id, server_id=server_id)
    return [{"name": s.name, "description": s.description} for s in snapshots]
