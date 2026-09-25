"""运行事件处理、缓冲和持久化逻辑。"""

import logging

from sqlalchemy import update

from app.agent.runtime import RuntimeEvent
from app.db import SessionFactory
from app.models import AgentRun, RunEvent, utc_now

logger = logging.getLogger("xiaoyi.runs.events")


async def append_event(run_id: str, event: RuntimeEvent) -> RunEvent:
    """写事件并在同一事务内推进 last_progress_at。"""
    now = utc_now()
    async with SessionFactory() as db:
        record = RunEvent(run_id=run_id, event_type=event.event_type, data=event.data)
        db.add(record)
        await db.execute(update(AgentRun).where(AgentRun.id == run_id).values(last_progress_at=now))
        await db.commit()
        await db.refresh(record)
        return record
