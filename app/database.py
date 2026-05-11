"""
Drive → Vimeo Sync: Database connection layer.
Provides async engine/session for FastAPI and sync engine/session for Celery workers.
"""

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase, Session

from app.config import get_settings

settings = get_settings()

# ─── Async engine (FastAPI) ───────────────────────────────────────────────────
async_engine = create_async_engine(settings.database_url, echo=False, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)

# ─── Sync engine (Celery workers) ────────────────────────────────────────────
sync_engine = create_engine(settings.database_url_sync, echo=False, pool_pre_ping=True)
SyncSessionLocal = sessionmaker(sync_engine, class_=Session, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    """FastAPI dependency: yields an async database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


def get_sync_db() -> Session:
    """Celery helper: returns a sync database session (caller must close)."""
    return SyncSessionLocal()
