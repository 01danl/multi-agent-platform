"""Database engine and session management (SQLAlchemy 2.0 async)."""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import Settings


def create_engine_from_settings(settings: Settings) -> AsyncEngine:
    kwargs: dict = {"echo": False}
    url = settings.resolved_database_url()
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"timeout": 30}
    engine = create_async_engine(url, **kwargs)
    if url.startswith("sqlite"):

        # SQLite does not enforce foreign keys unless told to.
        @event.listens_for(engine.sync_engine, "connect")
        def _enable_sqlite_fk(dbapi_connection, _record):  # noqa: ANN001
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def session_dependency(
    factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    session = factory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()
