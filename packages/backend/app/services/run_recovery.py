"""启动恢复扫描。

后端崩溃/重启后必然收敛：RUNNING 转为 FAILED/RUN_INTERRUPTED（可由用户重试），
QUEUED 保留并交给 Dispatcher 重新执行，终态任务不受影响。
不自动重放已进入 RUNNING 的任务，避免重复执行外部工具。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import select

from app.db import SessionFactory
from app.models import AgentRun, RunEvent, RunStatus, utc_now
from app.services.run_state import RUN_INTERRUPTED, append_failure_event, mark_finished

logger = logging.getLogger("xiaoyi.run_recovery")

_TERMINAL_STATUSES = {RunStatus.COMPLETED, RunStatus.FAILED}
_TERMINAL_EVENT_TYPES = {"run.completed", "run.failed"}


@dataclass
class RecoveryReport:
    interrupted: int = 0
    requeued: int = 0
    repaired: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "interrupted": self.interrupted,
            "requeued": self.requeued,
            "repaired": self.repaired,
        }


async def recover_interrupted_runs() -> RecoveryReport:
    """启动时执行一次；Dispatcher 启动之前调用。"""
    report = RecoveryReport()
    now = utc_now()
    async with SessionFactory() as db:
        runs = list(
            (
                await db.scalars(
                    select(AgentRun).where(
                        AgentRun.status.in_([RunStatus.QUEUED, RunStatus.RUNNING])
                    )
                )
            ).all()
        )
        for run in runs:
            if run.status == RunStatus.RUNNING:
                await append_failure_event(
                    run.id,
                    RUN_INTERRUPTED,
                    "服务重启导致运行中断，可重试",
                    retryable=True,
                )
                await mark_finished(
                    run.id,
                    status=RunStatus.FAILED,
                    error_code=RUN_INTERRUPTED,
                    error_message="服务重启导致运行中断，可重试",
                    interruption_reason=RUN_INTERRUPTED,
                )
                report.interrupted += 1
            else:  # QUEUED：保留，交由 Dispatcher 按创建时间重新执行
                report.requeued += 1

        # 修复"终态但缺终态事件"的旧数据，保证 SSE 与审计可解释
        for status, event_type in (
            (RunStatus.COMPLETED, "run.completed"),
            (RunStatus.FAILED, "run.failed"),
        ):
            terminal_runs = list(
                (await db.scalars(select(AgentRun).where(AgentRun.status == status))).all()
            )
            for run in terminal_runs:
                if not run.final_message_id and status == RunStatus.COMPLETED:
                    continue  # 数据不完整由人工处理，不伪造终态消息
                has_terminal_event = await db.scalar(
                    select(RunEvent.id)
                    .where(
                        RunEvent.run_id == run.id, RunEvent.event_type.in_(_TERMINAL_EVENT_TYPES)
                    )
                    .limit(1)
                )
                if has_terminal_event:
                    continue
                db.add(
                    RunEvent(
                        run_id=run.id,
                        event_type=event_type,
                        data={
                            "repaired_at": now.isoformat(),
                            **(
                                {"message_id": run.final_message_id} if run.final_message_id else {}
                            ),
                        },
                    )
                )
                report.repaired += 1
        await db.commit()

    if report.interrupted or report.requeued or report.repaired:
        logger.warning(
            "startup recovery: %s",
            report.to_dict(),
            extra={"event": "run_recovery_completed", **report.to_dict()},
        )
    return report


async def list_recoverable_runs() -> list[str]:
    """恢复扫描后仍处于 QUEUED 的任务，Dispatcher 启动时需要重新执行。"""
    async with SessionFactory() as db:
        runs = await db.scalars(
            select(AgentRun.id)
            .where(AgentRun.status == RunStatus.QUEUED)
            .order_by(AgentRun.created_at, AgentRun.id)
        )
        return list(runs.all())
