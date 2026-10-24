"""Automations: CRUD, schedule validation, trigger-now through the real
execution path (fake provider), ownership isolation, run linkage."""

from __future__ import annotations

import asyncio

from httpx import AsyncClient

from tests.conftest import create_agent


async def make_automation(
    client: AsyncClient,
    agent_id: str,
    name: str = "Daily summary",
    schedule_type: str = "interval",
    **overrides,
) -> dict:
    payload = {
        "name": name,
        "agent_id": agent_id,
        "prompt": "Summarize the current state of the project.",
        "schedule_type": schedule_type,
        "interval_minutes": 60,
        "daily_at": "09:30" if schedule_type == "daily" else None,
    }
    payload.update(overrides)
    resp = await client.post("/api/automations", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def wait_run_done(client: AsyncClient, run_id: str, timeout: float = 10.0) -> dict:
    for _ in range(int(timeout / 0.1)):
        runs = (await client.get("/api/runs?limit=200")).json()
        run = next((r for r in runs if r["id"] == run_id), None)
        if run and run["status"] in {"completed", "failed", "cancelled"}:
            return run
        await asyncio.sleep(0.1)
    raise AssertionError(f"run {run_id} did not finish")


async def test_automation_crud(user_client: AsyncClient, other_user_client: AsyncClient):
    agent = await create_agent(user_client)
    automation = await make_automation(user_client, agent["id"])

    listed = (await user_client.get("/api/automations")).json()
    assert [a["name"] for a in listed] == ["Daily summary"]
    assert listed[0]["schedule_type"] == "interval"
    assert listed[0]["interval_minutes"] == 60

    # isolation
    assert (await other_user_client.get("/api/automations")).json() == []
    assert (await other_user_client.delete(f"/api/automations/{automation['id']}")).status_code == 404

    # update: switch to daily
    resp = await user_client.patch(
        f"/api/automations/{automation['id']}",
        json={"schedule_type": "daily", "daily_at": "08:15", "interval_minutes": None},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["schedule_type"] == "daily" and body["daily_at"] == "08:15"
    assert body["interval_minutes"] is None

    assert (await user_client.delete(f"/api/automations/{automation['id']}")).status_code == 204


async def test_automation_schedule_validation(user_client: AsyncClient):
    agent = await create_agent(user_client)
    # interval without minutes
    resp = await user_client.post(
        "/api/automations",
        json={"name": "X", "agent_id": agent["id"], "prompt": "p", "schedule_type": "interval"},
    )
    assert resp.status_code == 422
    # daily without valid time
    resp = await user_client.post(
        "/api/automations",
        json={"name": "X", "agent_id": agent["id"], "prompt": "p", "schedule_type": "daily"},
    )
    assert resp.status_code == 422
    # unknown agent id
    resp = await user_client.post(
        "/api/automations",
        json={
            "name": "X",
            "agent_id": "00000000-0000-0000-0000-000000000000",
            "prompt": "p",
            "schedule_type": "interval",
            "interval_minutes": 5,
        },
    )
    assert resp.status_code == 404


async def test_automation_trigger_now_runs_through_execution_service(user_client: AsyncClient):
    """Acceptance: a scheduled task executes and the execution is inspectable."""
    agent = await create_agent(user_client, enabled_tools=["calculator"])
    automation = await make_automation(user_client, agent["id"], prompt="compute 2+2 please")

    resp = await user_client.post(f"/api/automations/{automation['id']}/run")
    assert resp.status_code == 202, resp.text
    run_id = resp.json()["run_id"]

    run = await wait_run_done(user_client, run_id)
    assert run["status"] == "completed"
    assert run["input_text"] == "compute 2+2 please"

    # linked to the automation and inspectable via the runs filter
    runs = (
        await user_client.get(f"/api/runs?automation_id={automation['id']}")
    ).json()
    assert [r["id"] for r in runs] == [run_id]

    # a dedicated conversation holds the transcript
    detail = (await user_client.get(f"/api/conversations/{run['conversation_id']}")).json()
    assert detail["title"].startswith("Automation: Daily summary")
    roles = [m["role"] for m in detail["messages"]]
    assert roles[0] == "user"
    assert "tool" in roles  # the calculator ran through the normal path
    assert any("4" in m["content"] for m in detail["messages"])


async def test_disabled_automation_cannot_trigger(user_client: AsyncClient):
    agent = await create_agent(user_client)
    automation = await make_automation(user_client, agent["id"], enabled=False)
    resp = await user_client.post(f"/api/automations/{automation['id']}/run")
    assert resp.status_code == 409


async def test_scheduler_registers_and_unregisters_jobs(user_client: AsyncClient, app):
    from app.scheduler.service import AutomationScheduler

    agent = await create_agent(user_client)
    automation = await make_automation(user_client, agent["id"], interval_minutes=15)
    scheduler: AutomationScheduler = app.state.automation_scheduler

    assert scheduler.job_count >= 1
    assert scheduler.job_id(automation["id"]) in {job.id for job in scheduler._scheduler.get_jobs()}

    # disable via PATCH -> job removed
    await user_client.patch(f"/api/automations/{automation['id']}", json={"enabled": False})
    assert scheduler.job_id(automation["id"]) not in {job.id for job in scheduler._scheduler.get_jobs()}

    # re-enable -> back
    await user_client.patch(f"/api/automations/{automation['id']}", json={"enabled": True})
    assert scheduler.job_id(automation["id"]) in {job.id for job in scheduler._scheduler.get_jobs()}

    # delete -> removed
    await user_client.delete(f"/api/automations/{automation['id']}")
    assert scheduler.job_id(automation["id"]) not in {job.id for job in scheduler._scheduler.get_jobs()}
