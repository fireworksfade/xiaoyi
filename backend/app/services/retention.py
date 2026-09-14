"""数据保留与清理（specs WP-11 / §6.4、§9.3、§15.2、§15.3、§15.5）。

覆盖三类主后端数据：
- 未绑定附件（message_id IS NULL 超过保留期）；
- 过期 Session（expires_at 已过宽限期）；
- 运行事件压缩（终态后删除可重建的 answer.delta）。

安全阀：
- 默认 dry-run，只输出统计不改数据；删除由 RETENTION_DELETE_ENABLED 显式开启；
- 分批删除、每批独立提交，进程内存不随候选规模增长；
- 只删除可重建数据；不触碰对话、消息、审计与已完成 outbox。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from sqlalchemy import and_, delete, func, or_, select

from app.config import get_settings
from app.db import SessionFactory
from app.models import AgentRun, Attachment, RunEvent, RunStatus, Session, utc_now

logger = logging.getLogger("xiaoyi.retention")


async def _ids_batch(db, stmt, limit: int) -> list[str]:
    return list((await db.scalars(stmt.limit(limit))).all())


async def cleanup_unbound_attachments(
    db,
    *,
    older_than_hours: int,
    batch_size: int,
    delete_enabled: bool,
) -> dict[str, Any]:
    cutoff = utc_now() - timedelta(hours=older_than_hours)
    conditions = (Attachment.message_id.is_(None), Attachment.created_at < cutoff)
    scanned = (
        await db.scalar(select(func.count()).select_from(Attachment).where(*conditions)) or 0
    )
    extracted_chars = (
        await db.scalar(
            select(func.coalesce(func.sum(func.length(Attachment.extracted_text)), 0)).where(
                *conditions
            )
        )
        or 0
    )
    size_bytes = (
        await db.scalar(
            select(func.coalesce(func.sum(Attachment.size_bytes), 0)).where(*conditions)
        )
        or 0
    )
    deleted = 0
    if delete_enabled:
        while True:
            ids = await _ids_batch(
                db, select(Attachment.id).where(*conditions).order_by(Attachment.id), batch_size
            )
            if not ids:
                break
            await db.execute(delete(Attachment).where(Attachment.id.in_(ids)))
            await db.commit()
            deleted += len(ids)
            if len(ids) < batch_size:
                break
    return {
        "scanned": int(scanned),
        "deleted": deleted,
        "extracted_chars": int(extracted_chars),
        "size_bytes": int(size_bytes),
        "dry_run": not delete_enabled,
    }


async def cleanup_expired_sessions(
    db,
    *,
    grace_days: int,
    batch_size: int,
    delete_enabled: bool,
) -> dict[str, Any]:
    cutoff = utc_now() - timedelta(days=grace_days)
    conditions = (Session.expires_at < cutoff,)
    scanned = await db.scalar(select(func.count()).select_from(Session).where(*conditions)) or 0
    deleted = 0
    if delete_enabled:
        while True:
            ids = await _ids_batch(
                db, select(Session.id).where(*conditions).order_by(Session.id), batch_size
            )
            if not ids:
                break
            await db.execute(delete(Session).where(Session.id.in_(ids)))
            await db.commit()
            deleted += len(ids)
            if len(ids) < batch_size:
                break
    return {"scanned": int(scanned), "deleted": deleted, "dry_run": not delete_enabled}


async def compact_run_events(
    db,
    *,
    completed_after_hours: int,
    failed_after_hours: int,
    batch_size: int,
    delete_enabled: bool,
) -> dict[str, Any]:
    """终态 run 的 answer.delta 压缩：完成后按短诊断期、失败按长诊断期删除。

    前置条件：已完成 run 必须已有 final_message_id（assistant 内容持久化成功），
    否则不删除其 delta。
    """
    now = utc_now()
    completed_cutoff = now - timedelta(hours=completed_after_hours)
    failed_cutoff = now - timedelta(hours=failed_after_hours)
    run_conditions = or_(
        and_(
            AgentRun.status == RunStatus.COMPLETED,
            AgentRun.final_message_id.is_not(None),
            AgentRun.finished_at < completed_cutoff,
        ),
        and_(AgentRun.status == RunStatus.FAILED, AgentRun.finished_at < failed_cutoff),
    )
    run_ids = list(
        (await db.scalars(select(AgentRun.id).where(run_conditions).limit(batch_size))).all()
    )
    delta_conditions = (RunEvent.event_type == "answer.delta",)
    if run_ids:
        delta_conditions = (
            RunEvent.event_type == "answer.delta",
            RunEvent.run_id.in_(run_ids),
        )
    delta_count = (
        await db.scalar(select(func.count()).select_from(RunEvent).where(*delta_conditions)) or 0
    )
    deleted = 0
    compacted_runs = 0
    if delete_enabled and run_ids:
        while True:
            ids = await _ids_batch(
                db, select(RunEvent.id).where(*delta_conditions).order_by(RunEvent.id), batch_size
            )
            if not ids:
                break
            await db.execute(delete(RunEvent).where(RunEvent.id.in_(ids)))
            await db.commit()
            deleted += len(ids)
            if len(ids) < batch_size:
                break
        for run_id in run_ids:
            run = await db.get(AgentRun, run_id)
            if run is None:
                continue
            run.runtime_state = {
                **(run.runtime_state or {}),
                "events_compacted_at": now.isoformat(),
            }
            compacted_runs += 1
        await db.commit()
    return {
        "candidate_runs": len(run_ids),
        "delta_events": int(delta_count),
        "deleted": deleted,
        "compacted_runs": compacted_runs,
        "dry_run": not delete_enabled,
    }


async def run_retention(*, delete_enabled: bool = False, settings=None) -> dict[str, Any]:
    """执行一轮清理（或 dry-run 统计），返回可序列化报告。"""
    settings = settings or get_settings()
    batch_size = settings.retention_batch_size
    async with SessionFactory() as db:
        attachments = await cleanup_unbound_attachments(
            db,
            older_than_hours=settings.unbound_attachment_retention_hours,
            batch_size=batch_size,
            delete_enabled=delete_enabled,
        )
        sessions = await cleanup_expired_sessions(
            db,
            grace_days=settings.expired_session_grace_days,
            batch_size=batch_size,
            delete_enabled=delete_enabled,
        )
        events = await compact_run_events(
            db,
            completed_after_hours=settings.run_events_compact_after_hours,
            failed_after_hours=settings.run_events_failed_retention_hours,
            batch_size=batch_size,
            delete_enabled=delete_enabled,
        )
    return {"attachments": attachments, "sessions": sessions, "run_events": events}


async def retention_loop(delete_enabled: bool, interval_hours: int) -> None:
    """后台周期清理；删除开关关闭时持续输出 dry-run 统计。"""
    interval_seconds = max(interval_hours, 1) * 3600
    while True:
        try:
            report = await run_retention(delete_enabled=delete_enabled)
            logger.info(
                "retention pass",
                extra={"event": "retention_pass", **report},
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("retention pass failed", extra={"event": "retention_failed"})
        await asyncio.sleep(interval_seconds)
