import os
import tempfile
from pathlib import Path

TEST_DATA_DIR = Path(tempfile.mkdtemp(prefix="xiaoyi-backend-tests-"))
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{(TEST_DATA_DIR / 'test.db').as_posix()}"
os.environ["AGENT_RUNTIME"] = "mock"

import pytest
from sqlalchemy import delete

from app.db import SessionFactory
from app.migrations import upgrade_to_head
from app.models import AgentRun, Conversation, Message, RunEvent


@pytest.fixture(autouse=True)
async def _migrated_clean_db():
    """服务级测试直接操作数据库：先保证 schema 迁移到 head（幂等），
    再清空运行相关数据，避免共享测试库中遗留任务影响 FIFO/计数断言。"""
    upgrade_to_head()
    async with SessionFactory() as db:
        await db.execute(delete(RunEvent))
        await db.execute(delete(AgentRun))
        await db.execute(delete(Message))
        await db.execute(delete(Conversation))
        await db.commit()
    yield
