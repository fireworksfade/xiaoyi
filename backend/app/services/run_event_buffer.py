"""Run 事件缓冲（specs WP-11 / §9.4、§15.4）。

- answer.delta 按字符阈值或时间窗合并，一批事件一次事务提交；
- 语义事件先刷新已积压 delta，再按原顺序入批；
- tool.finished 输出超过上限时保存摘要、原始字节数与 SHA-256；
- run 终态与失败路径必须 flush。
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from sqlalchemy import update

from app.agent.runtime import RuntimeEvent
from app.db import SessionFactory
from app.models import AgentRun, RunEvent, utc_now

DELTA_EVENT_TYPE = "answer.delta"

# 摘要正文中保留的原始 JSON 前缀长度（供排障参考，不承载完整输出）
SUMMARY_HEAD_CHARS = 1024


def summarize_tool_output(output: Any, *, max_bytes: int) -> Any:
    """输出序列化后超过 max_bytes 时替换为可验证的摘要结构。"""
    raw = json.dumps(output, ensure_ascii=False, default=str).encode("utf-8")
    if len(raw) <= max_bytes:
        return output
    return {
        "truncated": True,
        "original_bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "summary": raw[:SUMMARY_HEAD_CHARS].decode("utf-8", errors="replace"),
    }


class RunEventBuffer:
    """为单个 run 缓冲事件；flush 时以单事务写入并推进 last_progress_at。"""

    def __init__(
        self,
        run_id: str,
        *,
        max_delta_chars: int = 256,
        flush_after_seconds: float = 0.2,
        tool_output_max_bytes: int = 64 * 1024,
    ) -> None:
        self._run_id = run_id
        self._max_delta_chars = max(1, max_delta_chars)
        self._flush_after_seconds = max(0.0, flush_after_seconds)
        self._tool_output_max_bytes = tool_output_max_bytes
        self._batch: list[RuntimeEvent] = []
        self._pending_delta: str | None = None
        self._pending_since: float | None = None

    @property
    def pending_count(self) -> int:
        return len(self._batch) + (1 if self._pending_delta is not None else 0)

    def append(self, event: RuntimeEvent) -> None:
        if event.event_type == DELTA_EVENT_TYPE:
            self._append_delta(str(event.data.get("delta", "")))
            return
        # 语义事件：先刷新 delta 保证顺序，再原样入批
        self._coalesce_delta()
        self._batch.append(self._summarize(event))

    def _append_delta(self, delta: str) -> None:
        if self._pending_delta is None:
            self._pending_delta = ""
            self._pending_since = time.monotonic()
        self._pending_delta += delta
        if len(self._pending_delta) >= self._max_delta_chars:
            self._coalesce_delta()

    def _coalesce_delta(self) -> None:
        if self._pending_delta is None:
            return
        self._batch.append(RuntimeEvent(DELTA_EVENT_TYPE, {"delta": self._pending_delta}))
        self._pending_delta = None
        self._pending_since = None

    def _summarize(self, event: RuntimeEvent) -> RuntimeEvent:
        if event.event_type != "tool.finished":
            return event
        output = event.data.get("output")
        if output is None:
            return event
        summarized = summarize_tool_output(output, max_bytes=self._tool_output_max_bytes)
        if summarized is output:
            return event
        return RuntimeEvent(event.event_type, {**event.data, "output": summarized})

    async def flush_due(self) -> int:
        """时间窗到期则合并 delta 并写入；返回本批事件数。"""
        if self._pending_delta is not None and self._pending_since is not None:
            if time.monotonic() - self._pending_since >= self._flush_after_seconds:
                self._coalesce_delta()
        return await self.flush()

    async def flush(self) -> int:
        """把当前批次写入数据库（单事务）；无待写事件时返回 0。"""
        self._coalesce_delta()
        if not self._batch:
            return 0
        rows = [
            RunEvent(run_id=self._run_id, event_type=event.event_type, data=event.data)
            for event in self._batch
        ]
        self._batch.clear()
        await self._write_batch(rows)
        return len(rows)

    async def _write_batch(self, rows: list[RunEvent]) -> None:
        now = utc_now()
        async with SessionFactory() as db:
            db.add_all(rows)
            await db.execute(
                update(AgentRun).where(AgentRun.id == self._run_id).values(last_progress_at=now)
            )
            await db.commit()
