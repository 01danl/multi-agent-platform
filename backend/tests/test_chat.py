"""End-to-end chat tests over the SSE endpoint using the deterministic fake
provider (real deepagents/LangGraph execution, no external LLM calls)."""

from __future__ import annotations

import asyncio

from httpx import AsyncClient

from tests.conftest import create_agent, parse_sse


async def create_conversation(client: AsyncClient, agent_id: str) -> dict:
    resp = await client.post("/api/conversations", json={"agent_id": agent_id})
    assert resp.status_code == 201, resp.text
    return resp.json()


async def send(client: AsyncClient, conv_id: str, content: str) -> list[tuple[str, dict]]:
    resp = await client.post(f"/api/conversations/{conv_id}/messages", json={"content": content})
    assert resp.status_code == 200, resp.text
    return parse_sse(resp.text)


async def test_chat_tool_call_run(user_client: AsyncClient):
    agent = await create_agent(user_client, enabled_tools=["calculator"])
    conv = await create_conversation(user_client, agent["id"])

    events = await send(user_client, conv["id"], "What is 2+2?")
    types = [t for t, _ in events]
    data = {t: d for t, d in events}

    assert types[0] == "run_started"
    assert "tool_started" in types and "tool_completed" in types
    tool_started = data["tool_started"]
    assert tool_started["name"] == "calculator"
    assert data["tool_completed"]["output"] == "4"
    assert "assistant_delta" in types
    assert types[-1] == "run_completed"
    usage = data["run_completed"]["usage"]
    assert usage["model_calls"] == 2  # tool-call turn + final answer turn
    assert usage["total_tokens"] > 0


async def test_chat_persists_transcript_and_run(user_client: AsyncClient):
    agent = await create_agent(user_client)
    conv = await create_conversation(user_client, agent["id"])
    await send(user_client, conv["id"], "What is 2+2?")

    detail = (await user_client.get(f"/api/conversations/{conv['id']}")).json()
    roles = [m["role"] for m in detail["messages"]]
    assert roles == ["user", "assistant", "tool", "assistant"]
    tool_msg = detail["messages"][2]
    assert tool_msg["name"] == "calculator"
    assert tool_msg["content"] == "4"

    runs = (await user_client.get(f"/api/runs?conversation_id={conv['id']}")).json()
    assert len(runs) == 1
    assert runs[0]["status"] == "completed"
    assert runs[0]["usage"]["model_calls"] == 2

    run_detail = (await user_client.get(f"/api/runs/{runs[0]['id']}")).json()
    event_types = [e["event_type"] for e in run_detail["events"]]
    assert "model_call" in event_types
    assert "run_completed" in event_types


async def test_chat_conversation_continues(user_client: AsyncClient):
    agent = await create_agent(user_client)
    conv = await create_conversation(user_client, agent["id"])
    await send(user_client, conv["id"], "What is 2+2?")
    events = await send(user_client, conv["id"], "and again 5+5")
    assert events[-1][0] == "run_completed"

    detail = (await user_client.get(f"/api/conversations/{conv['id']}")).json()
    roles = [m["role"] for m in detail["messages"]]
    assert roles == ["user", "assistant", "tool", "assistant", "user", "assistant", "tool", "assistant"]
    runs = (await user_client.get(f"/api/runs?conversation_id={conv['id']}")).json()
    assert len(runs) == 2


async def test_conversation_isolation(user_client: AsyncClient, other_user_client: AsyncClient):
    agent = await create_agent(user_client)
    conv = await create_conversation(user_client, agent["id"])
    assert (await other_user_client.get(f"/api/conversations/{conv['id']}")).status_code == 404
    resp = await other_user_client.post(
        f"/api/conversations/{conv['id']}/messages", json={"content": "hi"}
    )
    assert resp.status_code == 404
    assert (await other_user_client.delete(f"/api/conversations/{conv['id']}")).status_code == 404


async def test_provider_not_configured_fails_cleanly(client: AsyncClient, user_client: AsyncClient):
    # Provider "openai" exists but has no API key in the test environment.
    resp = await user_client.post(
        "/api/agents",
        json={"name": "Real", "model_provider": "openai", "model_name": "gpt-4o-mini"},
    )
    assert resp.status_code == 201
    conv = await create_conversation(user_client, resp.json()["id"])
    events = await send(user_client, conv["id"], "hello")
    assert events[-1][0] == "run_failed"
    assert events[-1][1]["code"] == "provider_not_configured"


async def test_run_cancel(client: AsyncClient, user_client: AsyncClient):
    agent = await create_agent(user_client)
    conv = await create_conversation(user_client, agent["id"])

    # Start a run and cancel it immediately via the runs endpoint.
    task = asyncio.create_task(user_client.post(
        f"/api/conversations/{conv['id']}/messages", json={"content": "What is 2+2?"}
    ))
    await asyncio.sleep(0.05)
    runs = (await user_client.get(f"/api/runs?conversation_id={conv['id']}")).json()
    if runs:
        resp = await user_client.post(f"/api/runs/{runs[0]['id']}/cancel")
        assert resp.status_code == 200
        assert resp.json()["cancelled"] is True
    await task
    final = (await user_client.get(f"/api/runs?conversation_id={conv['id']}")).json()
    assert final[0]["status"] in {"completed", "cancelled"}


async def test_delete_conversation_cascades(user_client: AsyncClient):
    agent = await create_agent(user_client)
    conv = await create_conversation(user_client, agent["id"])
    await send(user_client, conv["id"], "What is 2+2?")
    assert (await user_client.delete(f"/api/conversations/{conv['id']}")).status_code == 204
    assert (await user_client.get(f"/api/conversations/{conv['id']}")).status_code == 404
