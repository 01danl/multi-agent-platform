"""FastAPI application factory and lifespan wiring.

Lifespan responsibilities:
- ensure the data directory exists and run Alembic migrations (dev default),
- open the platform database engine + session factory,
- open the LangGraph checkpoint database (AsyncSqliteSaver),
- build the harness singletons (providers, tool registry, runner, run registry).
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from app.agents.providers import ModelProviderManager
from app.agents.runner import AgentRunner
from app.agents.runs import RunTaskRegistry
from app.agents.tools import get_tool_registry
from app.api import agents, auth, conversations, meta, runs
from app.config import Settings, get_settings
from app.db.models import AgentRun
from app.db.session import create_engine_from_settings, create_session_factory

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("agent-platform")


def _run_migrations() -> None:
    from alembic.config import Config

    from alembic import command

    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("script_location", "alembic")
    command.upgrade(alembic_cfg, "head")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: Settings = get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.checkpoint_db_path.parent.mkdir(parents=True, exist_ok=True)

    if settings.run_migrations_on_startup:
        try:
            # Alembic's async template calls asyncio.run(), which cannot run
            # inside the already-running lifespan loop; use a worker thread.
            await asyncio.to_thread(_run_migrations)
        except Exception:
            logger.exception("Alembic migration on startup failed; continuing (tables may already exist)")

    engine = create_engine_from_settings(settings)
    session_factory = create_session_factory(engine)
    providers = ModelProviderManager(settings)

    # Single-process MVP: runs cannot survive a server restart — mark the
    # leftovers from a previous process as failed instead of blocking
    # conversations with forever-"running" runs.
    from sqlalchemy import update

    async with session_factory() as cleanup_session:
        await cleanup_session.execute(
            update(AgentRun)
            .where(AgentRun.status == "running")
            .values(
                status="failed",
                error_code="server_restarted",
                error_message="The server restarted while this run was active.",
            )
        )
        await cleanup_session.commit()

    async with AsyncSqliteSaver.from_conn_string(str(settings.checkpoint_db_path)) as checkpointer:
        runner = AgentRunner(
            settings=settings,
            providers=providers,
            tool_registry=get_tool_registry(),
            checkpointer=checkpointer,
            session_factory=session_factory,
        )
        app.state.settings = settings
        app.state.session_factory = session_factory
        app.state.providers = providers
        app.state.agent_runner = runner
        app.state.run_registry = RunTaskRegistry()
        logger.info("AI Agent Platform backend started (providers configured: %s)",
                    ", ".join(p.id for p in providers.list_providers() if p.configured) or "none")
        yield

    await engine.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
        debug=settings.debug,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(meta.router)
    app.include_router(auth.router)
    app.include_router(agents.router)
    app.include_router(conversations.router)
    app.include_router(runs.router)

    @app.get("/api")
    async def root() -> dict:
        return {"name": settings.app_name, "docs": "/docs"}

    return app


app = create_app()
