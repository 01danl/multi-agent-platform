"""Application settings.

All configuration comes from environment variables (see `.env.example`).
Provider API keys are read here and never leave the server process.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        env_prefix="",
        extra="ignore",
    )

    app_name: str = "AI Agent Platform"
    debug: bool = False

    # --- Storage -----------------------------------------------------------
    data_dir: Path = Field(default=BACKEND_DIR / "data")
    # SQLite for local development; swap for postgresql+asyncpg in production.
    database_url: str = "sqlite+aiosqlite:///./data/platform.sqlite"
    checkpoint_db_path: Path = Field(default=BACKEND_DIR / "data" / "checkpoints.sqlite")

    # Dev convenience: run `alembic upgrade head` on startup.
    run_migrations_on_startup: bool = True

    # --- Security ----------------------------------------------------------
    # Used for future signing needs; sessions themselves are random tokens
    # stored hashed in the database.
    secret_key: str = "dev-insecure-secret-key-change-me"
    session_ttl_hours: int = 24 * 14
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    # --- Uploads (Phase 2+, reserved) ---------------------------------------
    max_upload_size_mb: int = 20

    # --- Agent runtime limits ------------------------------------------------
    max_model_calls_per_run: int = 40
    graph_recursion_limit: int = 120
    run_timeout_seconds: int = 600

    # --- LLM providers -------------------------------------------------------
    # Keys are environment-only in the MVP (never persisted, never returned).
    openai_api_key: str | None = None
    openrouter_api_key: str | None = None
    custom_provider_name: str = "custom"
    custom_openai_base_url: str | None = None
    custom_openai_api_key: str | None = None

    # Deterministic fake provider for tests / keyless local development.
    fake_provider_enabled: bool = False

    # Catalog of suggested models per provider (free text always allowed).
    openai_models: list[str] = Field(
        default_factory=lambda: ["gpt-4o-mini", "gpt-4o", "gpt-4.1-mini", "gpt-4.1"]
    )
    openrouter_models: list[str] = Field(
        default_factory=lambda: ["openai/gpt-4o-mini", "anthropic/claude-3.5-sonnet", "meta-llama/llama-3.3-70b-instruct"]
    )
    custom_models: list[str] = Field(default_factory=list)

    @field_validator("cors_origins", "openai_models", "openrouter_models", "custom_models", mode="before")
    @classmethod
    def _split_csv(cls, v: object) -> object:
        if isinstance(v, str):
            return [item.strip() for item in v.split(",") if item.strip()]
        return v

    @property
    def sqlite_path(self) -> Path:
        name = self.database_url.split("///")[-1]
        return (BACKEND_DIR / name).resolve() if not name.startswith("/") else Path(name)

    def resolved_database_url(self) -> str:
        """SQLite URLs resolved to absolute paths (cwd-independent), parent dir created."""
        if self.database_url.startswith("sqlite") and "///" in self.database_url:
            path = self.sqlite_path
            path.parent.mkdir(parents=True, exist_ok=True)
            prefix = self.database_url.split("///")[0]
            return f"{prefix}///{path}"
        return self.database_url


@lru_cache
def get_settings() -> Settings:
    return Settings()
