from collections.abc import AsyncIterator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()
engine = create_async_engine(settings.database_url, pool_pre_ping=True, connect_args={"timeout": 30})
SessionFactory = async_sessionmaker(engine, expire_on_commit=False)

if settings.database_url.startswith("sqlite"):
    @event.listens_for(engine.sync_engine, "connect")
    def _sqlite_write_friendly(dbapi_connection, connection_record):
        """WAL + 长 busy timeout：后台 worker 与请求写入并发时排队而非报错。"""
        dbapi_connection.run_async(
            lambda conn: conn.execute("PRAGMA journal_mode=WAL")
        )


async def get_db() -> AsyncIterator[AsyncSession]:
    async with SessionFactory() as session:
        yield session
