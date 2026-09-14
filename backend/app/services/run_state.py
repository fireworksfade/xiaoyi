"""AgentRun 状态转换与错误分类。

主状态机保持 QUEUED → RUNNING → COMPLETED | FAILED；
本模块提供事务性的状态迁移 helper，供 Dispatcher、恢复扫描和处理函数共用。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, cast

from sqlalchemy import update
from sqlalchemy.engine import CursorResult

from app.db import SessionFactory
from app.models import AgentRun, RunEvent, RunStatus, utc_now

# 允许用户重试的错误码（其余失败不自动/不建议重试）
RETRYABLE_ERROR_CODES = {"RUN_INTERRUPTED"}

RUN_INTERRUPTED = "RUN_INTERRUPTED"
AGENT_RUN_FAILED = "AGENT_RUN_FAILED"


def is_retryable(error_code: str | None) -> bool:
    return error_code in RETRYABLE_ERROR_CODES


async def claim_queued_run(run_id: str) -> bool:
    """把 QUEUED 原子置为 RUNNING 并写时间线；返回是否抢占成功。

    单执行器语义下这是执行前的认领动作：避免恢复扫描或重试路径重复执行。
    """
    now = utc_now()
    async with SessionFactory() as db:
        result = cast(
            CursorResult[Any],
            await db.execute(
                update(AgentRun)
                .where(AgentRun.id == run_id, AgentRun.status == RunStatus.QUEUED)
                .values(
                    status=RunStatus.RUNNING,
                    started_at=now,
                    last_progress_at=now,
                    attempt_count=AgentRun.attempt_count + 1,
                )
            ),
        )
        await db.commit()
        return result.rowcount > 0


async def touch_progress(run_id: str, when: datetime | None = None) -> None:
    async with SessionFactory() as db:
        await db.execute(
            update(AgentRun).where(AgentRun.id == run_id).values(last_progress_at=when or utc_now())
        )
        await db.commit()


async def mark_finished(
    run_id: str,
    *,
    status: RunStatus,
    error_code: str | None = None,
    error_message: str | None = None,
    interruption_reason: str | None = None,
) -> None:
    async with SessionFactory() as db:
        await db.execute(
            update(AgentRun)
            .where(AgentRun.id == run_id)
            .values(
                status=status,
                finished_at=utc_now(),
                error_code=error_code,
                error_message=error_message,
                interruption_reason=interruption_reason,
            )
        )
        await db.commit()


async def append_failure_event(run_id: str, code: str, message: str, retryable: bool) -> RunEvent:
    async with SessionFactory() as db:
        event = RunEvent(
            run_id=run_id,
            event_type="run.failed",
            data={"error": {"code": code, "message": message, "retryable": retryable}},
        )
        db.add(event)
        await db.commit()
        await db.refresh(event)
        return event


def failure_payload(code: str, message: str, retryable: bool) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "retryable": retryable}}
