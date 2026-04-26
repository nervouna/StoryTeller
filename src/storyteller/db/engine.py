"""Async SQLAlchemy engine and session factory."""
from __future__ import annotations

from pathlib import Path

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from storyteller.db.models import Base


async def create_engine(db_path: str | Path):
    """Create async engine and initialize tables."""
    url = f"sqlite+aiosqlite:///{db_path}"
    engine = create_async_engine(url, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine


def get_session_factory(engine) -> async_sessionmaker[AsyncSession]:
    """Create a session factory for the given engine."""
    return async_sessionmaker(engine, expire_on_commit=False)
