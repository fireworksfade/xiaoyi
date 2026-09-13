"""AgentRun 单进程调度器。

契约：
- API 事务提交 QUEUED 任务后调用 notify(run_id)——这只是降低启动延迟的快速通道，
  不是唯一执行保证；周期扫描兜底。
- 单执行器：同一时间只执行一个 run，按 created_at FIFO。
- 优雅停止：先停止取新任务，宽限期内等待当前任务完成，超时则标记
  RUN_INTERRUPTED 并取消。
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select

from app.db import SessionFactory
from app.models import AgentRun, RunStatus
from app.services.run_state import (
    AGENT_RUN_FAILED,
    RUN_INTERRUPTED,
    append_failure_event,
    claim_queued_run,
    mark_finished,
)

logger = logging.getLogger("xiaoyi.run_dispatcher")


class RunDispatcher:
    def __init__(
        self,
        process_run,
        *,
        poll_interval_seconds: float = 1.0,
        shutdown_grace_seconds: float = 30.0,
    ) -> None:
        self._process_run = process_run
        self._poll_interval_seconds = poll_interval_seconds
        self._shutdown_grace_seconds = shutdown_grace_seconds
        self._notify_queue: asyncio.Queue[str] = asyncio.Queue()
        self._worker_task: asyncio.Task | None = None
        self._current_task: asyncio.Task | None = None
        self._stopping = False
        self._running = False

    @property
    def running(self) -> bool:
        return self._running and not self._stopping

    def start(self) -> None:
        if self._worker_task is not None:
            return
        self._stopping = False
        self._running = True
        self._worker_task = asyncio.create_task(self._worker(), name="run-dispatcher")

    async def stop(self) -> None:
        """优雅停止：不再取新任务；当前任务宽限期内完成，超时标记中断并取消。"""
        self._stopping = True
        worker, self._worker_task = self._worker_task, None
        current, self._current_task = self._current_task, None
        if current is not None and not current.done():
            await asyncio.wait({current}, timeout=self._shutdown_grace_seconds)
            if current.done():
                self._collect(current)
            else:
                logger.warning(
                    "dispatcher shutdown grace exceeded; interrupting current run",
                    extra={"event": "run_dispatcher_grace_timeout"},
                )
                current.cancel()
                self._collect(await asyncio.gather(current, return_exceptions=True))
        if worker is not None:
            try:
                await asyncio.wait_for(asyncio.shield(worker), timeout=2.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                worker.cancel()
                self._collect(await asyncio.gather(worker, return_exceptions=True))
        self._running = False

    @staticmethod
    def _collect(result: object) -> None:
        if isinstance(result, BaseException) and not isinstance(result, Exception):
            raise result

    def notify(self, run_id: str) -> None:
        """快速通道：任务已持久化为 QUEUED，请求立即执行；丢失由周期扫描兜底。"""
        if not self._stopping:
            self._notify_queue.put_nowait(run_id)

    async def _worker(self) -> None:
        while not self._stopping:
            try:
                await self._wait_for_work()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception(
                    "dispatcher poll failed", extra={"event": "run_dispatcher_poll_failed"}
                )
                await asyncio.sleep(self._poll_interval_seconds)
                continue
            await self._execute_next()

    async def _wait_for_work(self) -> None:
        """notify 立即返回；否则等待一个轮询间隔后由周期扫描接管。"""
        try:
            run_id = await asyncio.wait_for(
                self._notify_queue.get(), timeout=self._poll_interval_seconds
            )
        except asyncio.TimeoutError:
            return
        async with SessionFactory() as db:
            status = await db.scalar(select(AgentRun.status).where(AgentRun.id == run_id))
        if status != RunStatus.QUEUED:
            # 已被其他路径处理或任务不存在；周期扫描会在必要时接管
            await self._execute_next()

    async def _execute_next(self) -> None:
        if self._stopping:
            return
        run_id = await self._next_queued_run()
        if run_id is None:
            return
        self._current_task = asyncio.create_task(self._execute(run_id))
        try:
            await self._current_task
        finally:
            self._current_task = None

    async def _next_queued_run(self) -> str | None:
        async with SessionFactory() as db:
            return await db.scalar(
                select(AgentRun.id)
                .where(AgentRun.status == RunStatus.QUEUED)
                .order_by(AgentRun.created_at, AgentRun.id)
                .limit(1)
            )

    async def _execute(self, run_id: str) -> None:
        claimed = await claim_queued_run(run_id)
        if not claimed:
            return
        logger.info("run started", extra={"event": "run_started", "run_id": run_id})
        try:
            await self._process_run(run_id)
        except asyncio.CancelledError:
            await _finalize_cancelled(run_id)
            raise
        except Exception as exc:
            code = getattr(exc, "error_code", None) or AGENT_RUN_FAILED
            message = f"{type(exc).__name__}: {exc}"[:1000]
            await append_failure_event(run_id, code, message, retryable=False)
            await mark_finished(
                run_id,
                status=RunStatus.FAILED,
                error_code=code,
                error_message=message,
            )


async def _finalize_cancelled(run_id: str) -> None:
    """仅在处理函数未收敛终态时补写中断终态，避免重复 run.failed 事件。"""
    async with SessionFactory() as db:
        status = await db.scalar(select(AgentRun.status).where(AgentRun.id == run_id))
    if status in {RunStatus.COMPLETED, RunStatus.FAILED}:
        return
    await append_failure_event(run_id, RUN_INTERRUPTED, "运行被取消，可重试", retryable=True)
    await mark_finished(
        run_id,
        status=RunStatus.FAILED,
        error_code=RUN_INTERRUPTED,
        error_message="运行被取消，可重试",
        interruption_reason=RUN_INTERRUPTED,
    )
