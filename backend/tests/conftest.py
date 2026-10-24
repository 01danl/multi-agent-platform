"""Test fixtures: isolated app instance with tmp SQLite DBs and fake provider.

No real LLM calls happen in tests — the deterministic fake provider drives the
same deepagents/LangGraph machinery as production providers.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

TESTS_DIR = Path(__file__).resolve().parent


@pytest.fixture(scope="session")
def test_env(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("aap-test")
    os.environ.update(
        {
            "DATABASE_URL": f"sqlite+aiosqlite:///{tmp}/platform.sqlite",
            "CHECKPOINT_DB_PATH": str(tmp / "checkpoints.sqlite"),
            "FAKE_PROVIDER_ENABLED": "true",
            "RUN_MIGRATIONS_ON_STARTUP": "false",
            "DEBUG": "true",
        }
    )
    from app.config import get_settings

    get_settings.cache_clear()
    return get_settings()


@pytest_asyncio.fixture(scope="session")
async def app(test_env):
    from app.db.models import Base
    from app.db.session import create_engine_from_settings
    from app.main import create_app

    application = create_app()
    engine = create_engine_from_settings(test_env)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()
    return application


@pytest_asyncio.fixture(scope="session")
async def lifespan_app(app):
    async with app.router.lifespan_context(app):
        yield app


@pytest_asyncio.fixture(scope="session")
async def transport(lifespan_app) -> ASGITransport:
    return ASGITransport(app=lifespan_app)


@pytest_asyncio.fixture(scope="session")
async def client(transport: ASGITransport) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


async def make_user(client: AsyncClient, email: str, password: str = "password123") -> AsyncClient:
    """Register a user; the client keeps the session cookie."""
    resp = await client.post(
        "/api/auth/register",
        json={"email": email, "name": "Test User", "password": password},
    )
    assert resp.status_code == 201, resp.text
    return client


_user_counter = 0


def _next_email(prefix: str) -> str:
    global _user_counter
    _user_counter += 1
    return f"{prefix}-{_user_counter}@test.io"


async def _make_user(transport: ASGITransport, email: str, password: str = "password123") -> AsyncClient:
    """Register a user on a fresh client (own cookie jar), logged in."""
    client = AsyncClient(transport=transport, base_url="http://testserver")
    resp = await client.post(
        "/api/auth/register",
        json={"email": email, "name": "Test User", "password": password},
    )
    assert resp.status_code == 201, resp.text
    return client


@pytest_asyncio.fixture
async def user_client(transport: ASGITransport) -> AsyncIterator[AsyncClient]:
    client = await _make_user(transport, _next_email("user"))
    yield client
    await client.aclose()


@pytest_asyncio.fixture
async def other_user_client(transport: ASGITransport) -> AsyncIterator[AsyncClient]:
    client = await _make_user(transport, _next_email("other"))
    yield client
    await client.aclose()


async def create_agent(client: AsyncClient, **overrides) -> dict:
    payload = {
        "name": "Test Agent",
        "system_prompt": "You are a test agent.",
        "model_provider": "fake",
        "model_name": "fake-agent",
        "enabled_tools": ["calculator"],
    }
    payload.update(overrides)
    resp = await client.post("/api/agents", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


def parse_sse(text: str) -> list[tuple[str, dict]]:
    import json

    events: list[tuple[str, dict]] = []
    current_event = None
    for line in text.splitlines():
        if line.startswith("event: "):
            current_event = line[len("event: ") :].strip()
        elif line.startswith("data: ") and current_event:
            events.append((current_event, json.loads(line[len("data: ") :])))
            current_event = None
    return events
