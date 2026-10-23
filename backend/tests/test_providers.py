"""Provider manager tests."""

from __future__ import annotations

from dataclasses import replace

from app.agents.providers import ModelProviderManager, ProviderError
from app.config import Settings


def _settings(**overrides) -> Settings:
    base = {
        "openai_api_key": "sk-test",
        "openrouter_api_key": None,
        "custom_openai_base_url": "https://llm.local/v1",
        "custom_openai_api_key": "local-key",
        "fake_provider_enabled": True,
    }
    base.update(overrides)
    return Settings(**base)


def _cfg(provider: str, model: str = "m1"):
    from app.agents.runner import AgentRuntimeConfig
    from uuid import uuid4

    return AgentRuntimeConfig(
        agent_id=uuid4(),
        owner_id=uuid4(),
        name="a",
        system_prompt="",
        model_provider=provider,
        model_name=model,
        temperature=0.5,
        max_output_tokens=None,
    )


def test_provider_listing():
    mgr = ModelProviderManager(_settings())
    infos = {p.id: p for p in mgr.list_providers()}
    assert infos["openai"].configured is True
    assert infos["openrouter"].configured is False
    assert infos["custom"].configured is True
    assert infos["fake"].configured is True


def test_build_openai_model():
    mgr = ModelProviderManager(_settings())
    model = mgr.build_model(_cfg("openai", "gpt-test"))
    assert model.model_name == "gpt-test"


def test_build_openrouter_uses_base_url():
    mgr = ModelProviderManager(_settings())
    model = mgr.build_model(_cfg("openrouter", "x/y"))
    assert "openrouter" in str(getattr(model, "openai_api_base", "") or "")


def test_build_custom_model():
    mgr = ModelProviderManager(_settings())
    model = mgr.build_model(_cfg("custom", "local-model"))
    assert getattr(model, "openai_api_base", "") == "https://llm.local/v1"


def test_unknown_provider_raises():
    mgr = ModelProviderManager(_settings())
    try:
        mgr.build_model(_cfg("does-not-exist"))
        raise AssertionError("expected ProviderError")
    except ProviderError as e:
        assert "Unknown model provider" in str(e)


def test_missing_key_raises():
    mgr = ModelProviderManager(_settings(openai_api_key=None))
    try:
        mgr.build_model(_cfg("openai"))
        raise AssertionError("expected ProviderError")
    except ProviderError as e:
        assert "no API key" in str(e)
