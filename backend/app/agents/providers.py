"""Model provider management.

Maps an agent's persisted provider/model choice to a LangChain chat model.
API keys come exclusively from server environment variables — they are never
persisted in the database, returned by the API, or written to logs.
"""

from __future__ import annotations

from dataclasses import dataclass

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI

from app.config import Settings

KNOWN_PROVIDERS: tuple[str, ...] = ("openai", "openrouter", "custom")


class ProviderError(Exception):
    """Raised when a provider is unknown or not configured with credentials."""


@dataclass(frozen=True)
class ProviderInfo:
    id: str
    label: str
    configured: bool
    base_url: str | None = None
    models: tuple[str, ...] = ()


@dataclass(frozen=True)
class _ProviderSpec:
    provider_id: str
    label: str
    base_url: str | None
    api_key: str | None
    models: tuple[str, ...]


class ModelProviderManager:
    def __init__(self, settings: Settings) -> None:
        self._s = settings
        self._specs: dict[str, _ProviderSpec] = {
            "openai": _ProviderSpec(
                "openai", "OpenAI", None, settings.openai_api_key, tuple(settings.openai_model_list)
            ),
            "openrouter": _ProviderSpec(
                "openrouter",
                "OpenRouter",
                "https://openrouter.ai/api/v1",
                settings.openrouter_api_key,
                tuple(settings.openrouter_model_list),
            ),
            "custom": _ProviderSpec(
                settings.custom_provider_name,
                "OpenAI-compatible endpoint",
                settings.custom_openai_base_url,
                settings.custom_openai_api_key,
                tuple(settings.custom_model_list),
            ),
        }
        # Allow addressing the custom provider by its configured name as well.
        if settings.custom_provider_name != "custom":
            self._specs[settings.custom_provider_name] = self._specs["custom"]
        # Deterministic fake provider (tests / keyless dev), explicitly enabled.
        if settings.fake_provider_enabled:
            self._specs["fake"] = _ProviderSpec("fake", "Fake (no external calls)", None, "not-a-real-key", ("fake-agent",))

    def provider_ids(self) -> list[str]:
        ids: list[str] = [pid for pid in ("openai", "openrouter", "custom", "fake") if pid in self._specs]
        return ids

    def list_providers(self) -> list[ProviderInfo]:
        infos: list[ProviderInfo] = []
        for pid in self.provider_ids():
            spec = self._specs[pid]
            infos.append(
                ProviderInfo(
                    id=pid,
                    label=spec.label,
                    configured=bool(spec.api_key) and (pid != "custom" or bool(spec.base_url)),
                    base_url=spec.base_url,
                    models=spec.models,
                )
            )
        return infos

    def is_configured(self, provider_id: str) -> bool:
        spec = self._specs.get(provider_id)
        if spec is None:
            return False
        if provider_id == "custom":
            return bool(spec.api_key and spec.base_url)
        return bool(spec.api_key)

    def build_model(self, config) -> BaseChatModel:
        """Build a chat model from a plain agent runtime config.

        Raises:
            ProviderError: unknown provider or missing credentials.
        """
        spec = self._specs.get(config.model_provider)
        if spec is None:
            raise ProviderError(f"Unknown model provider: {config.model_provider!r}")
        if config.model_provider == "fake":
            from app.agents.fake_model import FakePlatformModel

            return FakePlatformModel()
        if not spec.api_key:
            raise ProviderError(
                f"Provider {config.model_provider!r} has no API key configured on the server"
            )
        if config.model_provider == "custom" and not spec.base_url:
            raise ProviderError("Custom provider has no base URL configured on the server")

        kwargs: dict = {
            "model": config.model_name,
            "api_key": spec.api_key,
            "temperature": config.temperature,
            "timeout": 120,
            "max_retries": 2,
        }
        if spec.base_url:
            kwargs["base_url"] = spec.base_url
        if config.max_output_tokens:
            kwargs["max_tokens"] = config.max_output_tokens
        return ChatOpenAI(**kwargs)
