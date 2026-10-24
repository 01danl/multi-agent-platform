"""MCP client service: server configs, tool discovery, per-run tool loading.

Lifecycle: tool sessions are opened per run (AsyncExitStack in the runner)
and closed when the run ends — stdio subprocesses do not outlive their run.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from langchain_core.tools import BaseTool
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import McpServer, McpToolSnapshot

logger = logging.getLogger("agent-platform.mcp")


def _as_uuid(value: UUID | str) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


@dataclass(frozen=True)
class McpToolRef:
    server_id: str
    tool: str

    @classmethod
    def parse(cls, raw: dict) -> McpToolRef | None:
        server_id, tool = raw.get("server_id"), raw.get("tool")
        if not server_id or not tool:
            return None
        return cls(server_id=str(server_id), tool=str(tool))


def connection_config(server: McpServer) -> dict[str, Any]:
    """Map a persisted server row to a langchain-mcp-adapters connection."""
    if server.transport == "stdio":
        if not server.command:
            raise ValueError(f"MCP server {server.name!r} has no command configured")
        return {"transport": "stdio", "command": server.command, "args": list(server.args_json or [])}
    if not server.url:
        raise ValueError(f"MCP server {server.name!r} has no URL configured")
    return {"transport": "streamable_http", "url": server.url}


class McpService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = session_factory

    # ------------------------------------------------------------- discovery

    async def discover(self, *, owner_id: UUID | str, server_id: UUID | str) -> list[dict]:
        """Connect, list tools, refresh the snapshot. Returns tool metadata."""
        from langchain_mcp_adapters.client import MultiServerMCPClient

        server = await self.get_server(owner_id=owner_id, server_id=server_id)
        if server is None:
            raise LookupError("MCP server not found")

        connections: dict[str, Any] = {server.name: connection_config(server)}
        client = MultiServerMCPClient(connections)
        tools = await client.get_tools()

        async with self._sessions() as session:
            await session.execute(
                delete(McpToolSnapshot).where(McpToolSnapshot.server_id == server.id)
            )
            for tool in tools:
                session.add(
                    McpToolSnapshot(server_id=server.id, name=tool.name, description=tool.description or "")
                )
            await session.commit()
        return [{"name": t.name, "description": t.description or ""} for t in tools]

    async def list_snapshots(self, *, owner_id: UUID | str, server_id: UUID | str) -> list[McpToolSnapshot]:
        async with self._sessions() as session:
            stmt = (
                select(McpToolSnapshot)
                .join(McpServer, McpServer.id == McpToolSnapshot.server_id)
                .where(McpServer.owner_id == _as_uuid(owner_id), McpToolSnapshot.server_id == _as_uuid(server_id))
                .order_by(McpToolSnapshot.name.asc())
            )
            return list((await session.execute(stmt)).scalars().all())

    # -------------------------------------------------------------- servers

    async def get_server(self, *, owner_id: UUID | str, server_id: UUID | str) -> McpServer | None:
        async with self._sessions() as session:
            server = await session.get(McpServer, _as_uuid(server_id))
            if server is None or server.owner_id != _as_uuid(owner_id):
                return None
            return server

    async def load_servers(self, *, owner_id: UUID | str, server_ids: list[UUID]) -> list[McpServer]:
        if not server_ids:
            return []
        async with self._sessions() as session:
            stmt = select(McpServer).where(
                McpServer.owner_id == _as_uuid(owner_id), McpServer.id.in_(server_ids)
            )
            return list((await session.execute(stmt)).scalars().all())

    # ------------------------------------------------------------- run tools

    async def open_tools(
        self,
        stack,
        *,
        owner_id: UUID | str,
        refs: list[McpToolRef],
    ) -> list[BaseTool]:
        """Open sessions for the referenced servers and return their tools.

        Only the explicitly allowed (server, tool) pairs are returned — the
        permission layer is this filter, applied before the model ever sees
        the tools. Unknown servers/tools are skipped with a warning.
        """
        from contextlib import AsyncExitStack

        from langchain_mcp_adapters.client import MultiServerMCPClient
        from langchain_mcp_adapters.tools import load_mcp_tools

        assert isinstance(stack, AsyncExitStack)
        servers = await self.load_servers(
            owner_id=owner_id, server_ids=[_as_uuid(r.server_id) for r in refs]
        )
        by_id = {str(s.id): s for s in servers if s.enabled}

        allowed: dict[str, set[str]] = {}
        for ref in refs:
            server = by_id.get(ref.server_id)
            if server is None:
                logger.warning("Skipping MCP ref to missing/disabled server %s", ref.server_id)
                continue
            allowed.setdefault(ref.server_id, set()).add(ref.tool)
        if not allowed:
            return []

        connections: dict[str, Any] = {
            by_id[sid].name: connection_config(by_id[sid]) for sid in allowed
        }
        client = MultiServerMCPClient(connections)
        tools: list[BaseTool] = []
        name_to_id = {by_id[sid].name: sid for sid in allowed}
        for server_name, sid in name_to_id.items():
            session = await stack.enter_async_context(client.session(server_name))
            server_tools = await load_mcp_tools(session, server_name=server_name)
            for tool in server_tools:
                if tool.name in allowed[sid]:
                    tools.append(tool)
        logger.info("Loaded %d MCP tool(s) from %d server(s)", len(tools), len(allowed))
        return tools
