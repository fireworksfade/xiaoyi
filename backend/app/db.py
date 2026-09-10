from collections.abc import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()
engine = create_async_engine(settings.database_url, pool_pre_ping=True)
SessionFactory = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    async with SessionFactory() as session:
        yield session


async def create_schema() -> None:
    settings.ensure_local_paths()
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        if settings.database_url.startswith("sqlite"):
            conversation_columns = await connection.execute(text("PRAGMA table_info(conversations)"))
            if "deleted_at" not in {row[1] for row in conversation_columns}:
                await connection.execute(
                    text("ALTER TABLE conversations ADD COLUMN deleted_at DATETIME")
                )
            await connection.execute(
                text(
                    "UPDATE agent_runs SET status = 'FAILED' "
                    "WHERE status NOT IN ('QUEUED', 'RUNNING', 'COMPLETED', 'FAILED')"
                )
            )
