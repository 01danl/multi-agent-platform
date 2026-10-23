"""Agent CRUD and ownership isolation tests."""

from __future__ import annotations

from httpx import AsyncClient

from tests.conftest import create_agent


async def test_create_and_get_agent(user_client: AsyncClient):
    agent = await create_agent(user_client, name="Calc Bot", enabled_tools=["calculator", "current_datetime"])
    resp = await user_client.get(f"/api/agents/{agent['id']}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Calc Bot"
    assert body["model_provider"] == "fake"
    assert body["enabled_tools"] == ["calculator", "current_datetime"]


async def test_list_agents_scoped_to_owner(user_client: AsyncClient, other_user_client: AsyncClient):
    await create_agent(user_client, name="Mine")
    await create_agent(other_user_client, name="Theirs")
    mine = (await user_client.get("/api/agents")).json()
    theirs = (await other_user_client.get("/api/agents")).json()
    assert [a["name"] for a in mine] == ["Mine"]
    assert [a["name"] for a in theirs] == ["Theirs"]


async def test_update_agent(user_client: AsyncClient):
    agent = await create_agent(user_client)
    resp = await user_client.patch(
        f"/api/agents/{agent['id']}",
        json={"name": "Renamed", "temperature": 0.2, "system_prompt": "New prompt"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Renamed"
    assert body["temperature"] == 0.2
    assert body["system_prompt"] == "New prompt"
    # unchanged fields survive
    assert body["model_name"] == "fake-agent"


async def test_delete_agent(user_client: AsyncClient):
    agent = await create_agent(user_client)
    resp = await user_client.delete(f"/api/agents/{agent['id']}")
    assert resp.status_code == 204
    resp = await user_client.get(f"/api/agents/{agent['id']}")
    assert resp.status_code == 404


async def test_agent_isolation_between_users(user_client: AsyncClient, other_user_client: AsyncClient):
    agent = await create_agent(user_client)
    # other user cannot read, update or delete it
    assert (await other_user_client.get(f"/api/agents/{agent['id']}")).status_code == 404
    assert (
        await other_user_client.patch(f"/api/agents/{agent['id']}", json={"name": "Hacked"})
    ).status_code == 404
    assert (await other_user_client.delete(f"/api/agents/{agent['id']}")).status_code == 404
    # owner still can
    assert (await user_client.get(f"/api/agents/{agent['id']}")).status_code == 200


async def test_unknown_provider_rejected(user_client: AsyncClient):
    resp = await user_client.post(
        "/api/agents",
        json={"name": "Bad", "model_provider": "nope", "model_name": "x"},
    )
    assert resp.status_code == 422
    assert "nope" in resp.json()["detail"]
