"""Multi-agent delegation: coordinator `task` calls through Deep Agents
subagents, target scoping, API validation. Real execution, fake models."""

from __future__ import annotations

from httpx import AsyncClient

from tests.conftest import create_agent, parse_sse


async def test_delegation_e2e(user_client: AsyncClient):
    """Coordinator delegates to a specialist, gets its output, consolidates."""
    specialist = await create_agent(
        user_client,
        name="Research",
        description="Computes things",
        system_prompt="You research carefully.",
        enabled_tools=["calculator"],
    )
    coordinator = await create_agent(
        user_client,
        name="Coordinator",
        system_prompt="You coordinate.",
        enabled_tools=[],
        delegation_targets=[specialist["id"]],
    )
    assert coordinator["delegation_targets"] == [specialist["id"]]

    conv = (
        await user_client.post("/api/conversations", json={"agent_id": coordinator["id"]})
    ).json()
    resp = await user_client.post(
        f"/api/conversations/{conv['id']}/messages",
        json={"content": "Please delegate to research: compute 2+2"},
    )
    assert resp.status_code == 200, resp.text
    events = parse_sse(resp.text)
    types = [t for t, _ in events]
    data = {t: d for t, d in events}

    # the fake coordinator calls task; the subagent runs the real calculator
    assert "tool_started" in types and data["tool_started"]["name"] == "task"
    assert "tool_completed" in types
    # subagent's calculator ran inside the subgraph and its result surfaces
    assert "4" in data["tool_completed"]["output"]
    assert types[-1] == "run_completed"
    # consolidated answer references the specialist's report
    assert any("specialist agent" in (d.get("content") or "") for t, d in events if t == "assistant_message")

    # transcript + trace persisted
    detail = (await user_client.get(f"/api/conversations/{conv['id']}")).json()
    tool_messages = [m for m in detail["messages"] if m["role"] == "tool"]
    assert tool_messages and tool_messages[0]["name"] == "task"
    runs = (await user_client.get(f"/api/runs?conversation_id={conv['id']}")).json()
    assert runs[0]["status"] == "completed"


async def test_delegation_target_validation(user_client: AsyncClient, other_user_client: AsyncClient):
    specialist = await create_agent(user_client, name="Mine")
    foreign = await create_agent(other_user_client, name="Theirs")

    # foreign target rejected
    resp = await user_client.post(
        "/api/agents",
        json={
            "name": "Bad",
            "model_provider": "fake",
            "model_name": "fake-agent",
            "delegation_targets": [foreign["id"]],
        },
    )
    assert resp.status_code == 422

    # unknown id rejected
    resp = await user_client.post(
        "/api/agents",
        json={
            "name": "Bad2",
            "model_provider": "fake",
            "model_name": "fake-agent",
            "delegation_targets": ["00000000-0000-0000-0000-000000000000"],
        },
    )
    assert resp.status_code == 422

    # self-reference rejected on update
    agent = await create_agent(user_client, name="SelfRef")
    resp = await user_client.patch(
        f"/api/agents/{agent['id']}", json={"delegation_targets": [agent["id"]]}
    )
    assert resp.status_code == 422

    # valid target accepted
    resp = await user_client.patch(
        f"/api/agents/{agent['id']}", json={"delegation_targets": [specialist["id"]]}
    )
    assert resp.status_code == 200
    assert resp.json()["delegation_targets"] == [specialist["id"]]


async def test_deleted_target_is_skipped_safely(user_client: AsyncClient):
    specialist = await create_agent(user_client, name="Gone")
    coordinator = await create_agent(
        user_client, name="Coord", delegation_targets=[specialist["id"]]
    )
    await user_client.delete(f"/api/agents/{specialist['id']}")

    # a normal run (no delegation attempt) must still work
    conv = (
        await user_client.post("/api/conversations", json={"agent_id": coordinator["id"]})
    ).json()
    resp = await user_client.post(
        f"/api/conversations/{conv['id']}/messages", json={"content": "hello there"}
    )
    assert resp.status_code == 200
    events = parse_sse(resp.text)
    assert events[-1][0] == "run_completed"


async def test_delegation_spec_resolution(user_client: AsyncClient):
    from sqlalchemy import select

    from app.agents.runner import AgentRunner, AgentRuntimeConfig
    from app.config import get_settings
    from app.db.models import Agent
    from app.db.session import create_engine_from_settings, create_session_factory

    specialist = await create_agent(
        user_client, name="Research Agent", description="Deep research", enabled_tools=["calculator"]
    )
    coordinator = await create_agent(user_client, name="Coord", delegation_targets=[specialist["id"]])

    engine = create_engine_from_settings(get_settings())
    factory = create_session_factory(engine)
    runner = AgentRunner.__new__(AgentRunner)  # only _sessions is needed
    runner._sessions = factory

    from uuid import UUID as UUIDType

    async with factory() as session:
        agent = (
            await session.execute(select(Agent).where(Agent.id == UUIDType(coordinator["id"])))
        ).scalar_one()
        config = AgentRuntimeConfig.from_agent(agent)
    specs = await runner._resolve_delegation_specs(config)
    assert len(specs) == 1
    assert specs[0].slug == "research-agent"
    assert "Deep research" in specs[0].description
    assert specs[0].config.enabled_tools == ("calculator",)
    await engine.dispose()
