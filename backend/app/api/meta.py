"""Meta endpoints: tool catalog, provider status, health."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.agents.providers import ModelProviderManager
from app.agents.tools import get_tool_registry
from app.api.schemas import ProviderModelInfo, ToolOut

router = APIRouter(prefix="/api", tags=["meta"])


@router.get("/tools", response_model=list[ToolOut])
async def list_tools() -> list[ToolOut]:
    registry = get_tool_registry()
    return [ToolOut(name=s.name, description=s.description, category=s.category) for s in registry.all()]


@router.get("/providers", response_model=list[ProviderModelInfo])
async def list_providers(request: Request) -> list[ProviderModelInfo]:
    providers: ModelProviderManager = request.app.state.providers
    return [
        ProviderModelInfo(id=p.id, label=p.label, configured=p.configured, models=list(p.models))
        for p in providers.list_providers()
    ]


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}
