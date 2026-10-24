"""MCP integration: server CRUD, live tool discovery against a real stdio
server, per-agent allowlists, and a full agent run calling an MCP tool."""

from __future__ import annotations

import sys
from pathlib import Path

from httpx import AsyncClient

from tests.conftest import create_agent, parse_sse

FIXTURE = Path(__file__).parent / "fixtures" / "mini_mcp_server.py"


async def make_server(client: AsyncClient, name: str = "mini") -> str:
    resp = await client.post(
        "/api/mcp",
        json={
            "name": name,
            "transport": "stdio",
            "command": sys.executable,
            "args": [str(FIXTURE)],
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def test_mcp_server_crud_and_isolation(user_client: AsyncClient, other_user_client: AsyncClient):
    server_id = await make_server(user_client)
    listed = (await user_client.get("/api/mcp")).json()
    assert [s["name"] for s in listed] == ["mini"]
    assert listed[0]["transport"] == "stdio"

    assert (await other_user_client.get("/api/mcp")).json() == []
    assert (await other_user_client.delete(f"/api/mcp/{server_id}")).status_code == 404
    assert (await user_client.delete(f"/api/mcp/{server_id}")).status_code == 204


async def test_mcp_transport_validation(user_client: AsyncClient):
    resp = await user_client.post("/api/mcp", json={"name": "x", "transport": "stdio"})
    assert resp.status_code == 422
    resp = await user_client.post("/api/mcp", json={"name": "x", "transport": "http"})
    assert resp.status_code == 422
    resp = await user_client.post("/api/mcp", json={"name": "x", "transport": "carrier-pigeon"})
    assert resp.status_code == 422


async def test_discover_real_server_and_snapshot(user_client: AsyncClient):
    server_id = await make_server(user_client)
    resp = await user_client.post(f"/api/mcp/{server_id}/discover")
    assert resp.status_code == 200, resp.text
    tools = resp.json()
    assert any(t["name"] == "add" and "Add two integers" in t["description"] for t in tools)

    # snapshot persists for the UI
    snapshotted = (await user_client.get(f"/api/mcp/{server_id}/tools")).json()
    assert any(t["name"] == "add" for t in snapshotted)


async def test_discover_unreachable_server_fails_cleanly(user_client: AsyncClient):
    resp = await user_client.post(
        "/api/mcp",
        json={
            "name": "broken",
            "transport": "stdio",
            "command": sys.executable,
            "args": ["-c", "import sys; sys.exit(1)"],
        },
    )
    server_id = resp.json()["id"]
    resp = await user_client.post(f"/api/mcp/{server_id}/discover")
    assert resp.status_code == 502


async def test_agent_calls_mcp_tool_end_to_end(user_client: AsyncClient):
    """Acceptance: connect an MCP server, assign its tool to an agent, run."""
    server_id = await make_server(user_client)
    await user_client.post(f"/api/mcp/{server_id}/discover")

    agent = await create_agent(
        user_client,
        name="MCP Agent",
        mcp_tools=[{"server_id": server_id, "tool": "add"}],
    )
    conv = (await user_client.post("/api/conversations", json={"agent_id": agent["id"]})).json()

    resp = await user_client.post(
        f"/api/conversations/{conv['id']}/messages",
        json={"content": "use mcp add with 20 and 22"},
    )
    assert resp.status_code == 200, resp.text
    events = parse_sse(resp.text)
    types = [t for t, _ in events]
    data = {t: d for t, d in events}

    assert types[-1] == "run_completed"
    tool_starts = [d for t, d in events if t == "tool_started"]
    assert any(t["name"] == "add" for t in tool_starts), tool_starts
    completed = data.get("tool_completed", {})
    assert "42" in (completed.get("output") or "")

    detail = (await user_client.get(f"/api/conversations/{conv['id']}")).json()
    tool_rows = [m for m in detail["messages"] if m["role"] == "tool" and m["name"] == "add"]
    assert tool_rows and "42" in tool_rows[0]["content"]


async def test_agent_without_allowlist_never_sees_mcp_tools(user_client: AsyncClient):
    """The permission layer is the allowlist filter — no ref, no tool."""
    server_id = await make_server(user_client, name="hidden")
    await user_client.post(f"/api/mcp/{server_id}/discover")

    agent = await create_agent(user_client, name="No MCP")
    assert agent["mcp_tools"] == []
    conv = (await user_client.post("/api/conversations", json={"agent_id": agent["id"]})).json()
    resp = await user_client.post(
        f"/api/conversations/{conv['id']}/messages", json={"content": "use mcp add with 1 and 2"}
    )
    events = parse_sse(resp.text)
    assert events[-1][0] == "run_completed"
    # fake model never sees an `add` tool to call
    assert all(t != "tool_completed" or d["name"] != "add" for t, d in events)
