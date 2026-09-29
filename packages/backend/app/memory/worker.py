import asyncio
import logging
from datetime import timedelta

from sqlalchemy import or_, select, update

from app.config import get_settings
from app.db import SessionFactory
from app.memory.models import Memory, MemoryJob, MemoryRevision
from app.memory.service import eligible, index_change
from app.models import new_id, utc_now

logger = logging.getLogger("xiaoyi.memory")


async def claim():
    now, token = utc_now(), new_id()
    async with SessionFactory() as db:
        criteria = (MemoryJob.next_run_at <= now, or_(MemoryJob.status == "pending",
            (MemoryJob.status == "running") & (MemoryJob.lease_until < now)))
        job_id = await db.scalar(select(MemoryJob.id).where(*criteria).order_by(MemoryJob.next_run_at).limit(1))
        if not job_id:
            return None
        result = await db.execute(update(MemoryJob).where(MemoryJob.id == job_id, *criteria).values(
            status="running", lease_token=token, lease_until=now + timedelta(minutes=5), attempts=MemoryJob.attempts + 1))
        await db.commit()
        return await db.get(MemoryJob, job_id) if result.rowcount else None


async def revalidate(db, owner):
    items = (await db.scalars(select(Memory).where(Memory.owner_user_id == owner))).all()
    for item in items:
        if item.status == "active" and not await eligible(db, item):
            from app.memory.service import revision
            rev = await revision(db, item)
            if item.kind == "episodic" and rev.content_json.get("outcome") == "pending":
                continue
            item.status = "suspended"
            await index_change(db, item, "purge")
        if item.status == "deleted" and item.deleted_at and item.deleted_at.replace(tzinfo=utc_now().tzinfo) < utc_now() - timedelta(days=get_settings().memory_deleted_content_retention_days):
            await db.execute(update(MemoryRevision).where(MemoryRevision.memory_id == item.id).values(summary="", content_json={}, search_text="", applicability_json={}))


async def process_one():
    job = await claim()
    if not job:
        return False
    error = None
    try:
        if job.kind == "propose_experience":
            from app.memory.extraction import extract
            await extract(job)
        elif job.kind == "sync_vector":
            from app.memory.indexing import sync
            await sync(job)
        elif job.kind == "track_action":
            from app.memory.actions import track
            await track(job)
        elif job.kind == "reconcile_experience":
            from app.memory.reconcile import reconcile
            await reconcile(job)
        else:
            async with SessionFactory() as db:
                if job.kind == "capture_episode":
                    from app.memory.capture import capture_job
                    await capture_job(db, job)
                elif job.kind == "revalidate_dependents":
                    await revalidate(db, job.owner_user_id)
                await db.commit()
    except Exception as exc:
        error = str(exc) if str(exc).startswith("MEMORY_") else type(exc).__name__
        logger.warning("memory job failed kind=%s code=%s", job.kind, error)
    from app.observability.metrics import MEMORY_EVENTS, MEMORY_JOBS
    MEMORY_JOBS.labels(kind=job.kind, result="failed" if error else "done").inc()
    if error:
        MEMORY_EVENTS.labels(event="job_failed").inc()
    async with SessionFactory() as db:
        await db.execute(update(MemoryJob).where(MemoryJob.id == job.id, MemoryJob.lease_token == job.lease_token).values(
            status="done" if error is None else "failed" if job.attempts >= get_settings().memory_job_max_attempts else "pending",
            error_code=error, lease_until=None, lease_token=None,
            next_run_at=utc_now() + timedelta(seconds=min(3600, 2 ** job.attempts))))
        await db.commit()
    return True


async def worker_loop(stop: asyncio.Event | None = None):
    """持久任务循环；stop 事件用于优雅退出，避免取消时打断在途数据库写入。"""
    while not (stop is not None and stop.is_set()):
        try:
            if get_settings().memory_enabled:
                await process_one()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("memory worker iteration failed")
        try:
            timeout = get_settings().memory_job_poll_seconds
            if stop is None:
                await asyncio.sleep(timeout)
            else:
                await asyncio.wait_for(stop.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            pass
