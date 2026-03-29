"""SQLAlchemy async engine and session setup."""

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from src.utils.config import settings

logger = logging.getLogger(__name__)

engine = create_async_engine(settings.database_url, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


_MIGRATIONS = [
    "ALTER TABLE users ADD COLUMN referral_code TEXT DEFAULT '' NOT NULL",
    "ALTER TABLE users ADD COLUMN referred_by BIGINT",
    "ALTER TABLE users ADD COLUMN referral_count INTEGER DEFAULT 0 NOT NULL",
    "ALTER TABLE users ADD COLUMN referral_bonus_given BOOLEAN DEFAULT 0 NOT NULL",
]


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Apply migrations for existing DBs
    async with engine.begin() as conn:
        for sql in _MIGRATIONS:
            try:
                await conn.execute(text(sql))
            except Exception:
                pass  # Column already exists
