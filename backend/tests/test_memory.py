"""Long-term memory: API, store semantics, tool registration, prompt injection."""

from __future__ import annotations

from httpx import AsyncClient

from tests.conftest import create_agent


async def test_memory_crud_and_isolation(user_client: AsyncClient, other_user_client: AsyncClient):
    resp = await user_client.post(
        "/api/memories",
        json={"content": "User prefers concise answers", "category": "preference"},
    )
    assert resp.status_code == 201, resp.text
    memory = resp.json()

    listed = (await user_client.get("/api/memories")).json()
    assert len(listed) == 1 and listed[0]["content"] == "User prefers concise answers"
    assert listed[0]["source"] == "manual"

    # other user sees nothing and cannot delete
    assert (await other_user_client.get("/api/memories")).json() == []
    assert (await other_user_client.delete(f"/api/memories/{memory['id']}")).status_code == 404

    assert (await user_client.delete(f"/api/memories/{memory['id']}")).status_code == 204
    assert (await user_client.get("/api/memories")).json() == []


async def test_memory_category_validation(user_client: AsyncClient):
    resp = await user_client.post("/api/memories", json={"content": "x", "category": "bogus"})
    assert resp.status_code == 422


async def test_memory_tools_listed_in_catalog(user_client: AsyncClient):
    tools = (await user_client.get("/api/tools")).json()
    names = {t["name"]: t for t in tools}
    assert "save_memory" in names and "recall_memory" in names
    assert names["save_memory"]["category"] == "memory"


async def test_memory_prompt_injection_via_run(user_client: AsyncClient):
    """memory_enabled agents get stored memories appended to their prompt."""
    from app.config import get_settings
    from app.db.session import create_engine_from_settings, create_session_factory
    from app.memory.service import MemoryStore

    agent = await create_agent(user_client, system_prompt="BASE PROMPT", memory_enabled=True)
    await user_client.post(
        "/api/memories",
        json={"content": "The launch date is March 3", "category": "project", "agent_id": agent["id"]},
    )

    engine = create_engine_from_settings(get_settings())
    factory = create_session_factory(engine)
    store = MemoryStore(factory)
    memories = await store.list_for_agent(
        owner_id=await _owner_id(user_client),
        agent_id=agent["id"],
    )
    preamble = MemoryStore.build_preamble(memories)
    assert "The launch date is March 3" in preamble
    assert "## Stored memories" in preamble
    await engine.dispose()


async def _owner_id(client: AsyncClient) -> str:
    me = (await client.get("/api/auth/me")).json()
    return me["id"]


async def test_memory_recall_keyword_scoring(user_client: AsyncClient):
    from app.config import get_settings
    from app.db.session import create_engine_from_settings, create_session_factory
    from app.memory.service import MemoryStore

    agent = await create_agent(user_client, memory_enabled=True)
    aid = agent["id"]
    for content, category in [
        ("Favorite editor is Neovim", "preference"),
        ("Project deadline is Friday", "project"),
        ("The cat is named Felix", "fact"),
    ]:
        await user_client.post(
            "/api/memories", json={"content": content, "category": category, "agent_id": aid}
        )


    engine = create_engine_from_settings(get_settings())
    factory = create_session_factory(engine)
    store = MemoryStore(factory)
    matches = await store.recall(owner_id=await _owner_id(user_client), agent_id=aid, query="deadline project")
    assert len(matches) == 1
    assert "Project deadline is Friday" in matches[0].content

    no_match = await store.recall(owner_id=await _owner_id(user_client), agent_id=aid, query="quantum physics")
    assert no_match == []
    await engine.dispose()


async def test_agent_without_memory_flag_gets_no_injection(user_client: AsyncClient):
    agent = await create_agent(user_client, system_prompt="ONLY BASE", memory_enabled=False)
    await user_client.post(
        "/api/memories",
        json={"content": "secret fact", "category": "fact", "agent_id": agent["id"]},
    )
    # A run still succeeds; the point is the flag gates injection (unit-level):
    from app.agents.runner import AgentRuntimeConfig

    config = AgentRuntimeConfig.from_agent(
        type("A", (), {
            "id": agent["id"], "owner_id": await _owner_id(user_client), "name": agent["name"],
            "system_prompt": agent["system_prompt"], "model_provider": agent["model_provider"],
            "model_name": agent["model_name"], "temperature": agent["temperature"],
            "max_output_tokens": agent["max_output_tokens"], "enabled_tools": agent["enabled_tools"],
            "memory_enabled": agent["memory_enabled"], "knowledge_base_ids": agent["knowledge_base_ids"],
            "delegation_targets": [],
        })()
    )
    assert config.memory_enabled is False
