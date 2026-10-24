"""Authentication flow tests."""

from __future__ import annotations

from httpx import AsyncClient


async def test_register_login_me_flow(user_client: AsyncClient):
    resp = await user_client.get("/api/auth/me")
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"].endswith("@test.io")
    assert "password" not in body and "password_hash" not in body


async def test_register_duplicate_email(user_client: AsyncClient):
    resp = await user_client.post(
        "/api/auth/register",
        json={"email": (await user_client.get("/api/auth/me")).json()["email"], "name": "Dup", "password": "password123"},
    )
    assert resp.status_code == 409


async def test_register_short_password(client: AsyncClient):
    resp = await client.post(
        "/api/auth/register",
        json={"email": "x@test.io", "name": "X", "password": "short"},
    )
    assert resp.status_code == 422


async def test_login_wrong_password(user_client: AsyncClient):
    email = (await user_client.get("/api/auth/me")).json()["email"]
    resp = await user_client.post(
        "/api/auth/login",
        json={"email": email, "password": "wrong-password"},
    )
    assert resp.status_code == 401


async def test_logout_invalidates_session(user_client: AsyncClient):
    resp = await user_client.post("/api/auth/logout")
    assert resp.status_code == 204
    resp = await user_client.get("/api/auth/me")
    assert resp.status_code == 401


async def test_protected_endpoint_requires_auth(client: AsyncClient):
    resp = await client.get("/api/agents")
    assert resp.status_code == 401


async def test_login_after_logout(user_client: AsyncClient):
    email = (await user_client.get("/api/auth/me")).json()["email"]
    await user_client.post("/api/auth/logout")
    resp = await user_client.post(
        "/api/auth/login",
        json={"email": email, "password": "password123"},
    )
    assert resp.status_code == 200
    me = await user_client.get("/api/auth/me")
    assert me.status_code == 200
