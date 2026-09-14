import asyncio
import logging
from datetime import timezone

from sqlalchemy import select, update

from app.agent.runtime import RuntimeEvent, build_runtime
from app.config import get_settings
from app.db import SessionFactory
from app.models import (
    AgentRun,
    Attachment,
    Message,
    ModelConfiguration,
    RunEvent,
    RunStatus,
    utc_now,
)
from app.observability.metrics import (
    AGENT_RUN_DURATION,
    AGENT_RUNS,
    CONTEXT_ESTIMATED_TOKENS,
    CONTEXT_OMITTED_MESSAGES,
)
from app.security import decrypt_secret
from app.services.context_builder import (
    CONTEXT_INPUT_TOO_LARGE,
    AttachmentDraft,
    ContextBudgetExceeded,
    ContextLimits,
    build_context,
)
from app.services.mcp_catalog import load_agent_mcp_servers
from app.services.run_event_buffer import RunEventBuffer
from app.services.run_state import (
    AGENT_RUN_FAILED,
    RUN_INTERRUPTED,
    append_failure_event,
    claim_queued_run,
    mark_finished,
)

logger = logging.getLogger("xiaoyi.runs")


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


async def process_agent_run(run_id: str) -> None:
    """完整执行入口：认领 + 执行（供 legacy BackgroundTasks 模式使用）。"""
    if not await claim_queued_run(run_id):
        return
    await execute_claimed_run(run_id)


def _collect_proposals(event_data: dict, proposals: list[dict[str, object]]) -> dict | None:
    """从 tool.finished 事件中提取、规范化并收集修复提案。

    返回后端定义的干净载荷（不透传 MCP 信封），并写入 proposals 供消息元数据持久化。
    """
    output = event_data.get("output")
    if (
        event_data.get("tool_name") != "create_remediation_proposal"
        or not isinstance(output, dict)
        or output.get("ok") is not True
    ):
        return None
    data = output.get("data")
    if not isinstance(data, dict) or not data.get("proposal_id"):
        return None
    proposal = {
        "proposal_id": data["proposal_id"],
        "device_id": data.get("device_id"),
        "action": data.get("action"),
        "parameters": data.get("parameters") or {},
        "reason": data.get("reason", ""),
        "impact": data.get("impact", ""),
        "status": data.get("status", "pending"),
        "version": data.get("version", 1),
        "expires_at": data.get("expires_at"),
        "task_status": data.get("task_status"),
        "created_at": data.get("created_at"),
    }
    proposals.append(proposal)
    return proposal


async def execute_claimed_run(run_id: str) -> None:
    """执行已处于 RUNNING 的 run（由 Dispatcher 或 legacy 入口认领后调用）。"""
    settings = get_settings()
    final_content = ""
    proposals: list[dict[str, object]] = []
    # 事件缓冲：delta 合并 + 批量事务提交；异常路径也要 flush 已缓冲事件
    buffer: RunEventBuffer | None = None
    try:
        async with SessionFactory() as db:
            run = await db.get(AgentRun, run_id)
            if not run or run.status != RunStatus.RUNNING:
                return
            model_config = await db.scalar(
                select(ModelConfiguration).where(
                    ModelConfiguration.user_id == run.user_id,
                    ModelConfiguration.enabled.is_(True),
                )
            )
            if model_config and model_config.api_key_ciphertext:
                settings = settings.model_copy(
                    update={
                        "agent_runtime": "openai",
                        "openai_api_key": decrypt_secret(
                            model_config.api_key_ciphertext,
                            settings.app_secret_key,
                        ),
                        "openai_base_url": model_config.base_url,
                        "openai_model": model_config.model_name,
                        "openai_api_mode": model_config.api_mode,
                    }
                )
            # 只加载当前消息及向前最多 N 条候选历史，不先加载整段对话
            candidate_limit = settings.agent_context_max_history_messages + 1
            messages = list(
                reversed(
                    (
                        await db.scalars(
                            select(Message)
                            .where(Message.conversation_id == run.conversation_id)
                            .order_by(Message.created_at.desc(), Message.id.desc())
                            .limit(candidate_limit)
                        )
                    ).all()
                )
            )
            mcp_servers = await load_agent_mcp_servers(db, settings)
            user_message = next(
                (message for message in messages if message.id == run.user_message_id),
                None,
            )
            tool_mode = (
                str(user_message.metadata_json.get("tool_mode", "auto")) if user_message else "auto"
            )
            if tool_mode == "none":
                mcp_servers = []
            elif tool_mode == "selected" and user_message:
                selected_ids = set(user_message.metadata_json.get("mcp_server_ids", []))
                mcp_servers = [server for server in mcp_servers if server.server_id in selected_ids]
            attachments = list(
                (
                    await db.scalars(
                        select(Attachment).where(
                            Attachment.message_id.in_([message.id for message in messages])
                        )
                    )
                ).all()
            )
            attachments_by_message: dict[str, list[Attachment]] = {}
            for attachment in attachments:
                if attachment.message_id:
                    attachments_by_message.setdefault(attachment.message_id, []).append(attachment)
            await db.commit()

        runtime = build_runtime(settings)
        await append_event(run_id, RuntimeEvent("run.started", {}))
        limits = ContextLimits.from_settings(settings)
        current_message = next(
            (item for item in messages if item.id == run.user_message_id), messages[-1]
        )
        history = [item for item in messages if item.id != current_message.id]
        try:
            context = build_context(
                current_message={
                    "id": current_message.id,
                    "role": current_message.role,
                    "content": current_message.content,
                },
                current_attachments=[
                    AttachmentDraft(filename=a.filename, text=a.extracted_text)
                    for a in attachments_by_message.get(current_message.id, [])
                ],
                history=[
                    {"id": item.id, "role": item.role, "content": item.content}
                    for item in history
                ],
                history_attachments={
                    message_id: [
                        AttachmentDraft(filename=a.filename, text=a.extracted_text)
                        for a in items
                    ]
                    for message_id, items in attachments_by_message.items()
                },
                limits=limits,
            )
        except ContextBudgetExceeded as exc:
            await append_failure_event(
                run_id, CONTEXT_INPUT_TOO_LARGE, str(exc), retryable=False
            )
            await mark_finished(
                run_id,
                status=RunStatus.FAILED,
                error_code=CONTEXT_INPUT_TOO_LARGE,
                error_message=str(exc),
            )
            AGENT_RUNS.labels(status="failed").inc()
            return
        runtime_messages = context.messages
        # 预算指标与元数据（写入 run.runtime_state，不污染用户消息）
        CONTEXT_ESTIMATED_TOKENS.observe(context.metadata["estimated_input_tokens"])
        if context.metadata["omitted_message_count"]:
            CONTEXT_OMITTED_MESSAGES.inc(context.metadata["omitted_message_count"])
        async with SessionFactory() as db:
            run = await db.get(AgentRun, run_id)
            if run:
                run.runtime_state = {**(run.runtime_state or {}), "context": context.metadata}
                await db.commit()
        buffer = RunEventBuffer(
            run_id,
            max_delta_chars=settings.run_delta_merge_chars,
            flush_after_seconds=settings.run_delta_merge_ms / 1000,
            tool_output_max_bytes=settings.run_tool_output_max_bytes,
        )
        async for event in runtime.stream(runtime_messages, mcp_servers):
            if event.event_type == "answer.final":
                final_content = str(event.data.get("content", ""))
                continue
            if event.event_type == "tool.finished":
                proposal = _collect_proposals(event.data, proposals)
                if proposal is not None:
                    # 语义事件：前端只依赖这个稳定契约，不解析 MCP 信封
                    buffer.append(
                        RuntimeEvent("remediation.proposal_created", {"proposal": proposal}),
                    )
            buffer.append(event)
            await buffer.flush_due()
        # 终态前强制 flush；assistant 消息与 run.completed 随后写入
        await buffer.flush()

        async with SessionFactory() as db:
            run = await db.get(AgentRun, run_id)
            if not run:
                return
            assistant_metadata: dict[str, object] = {"run_id": run_id}
            if proposals:
                # 提案数据随消息持久化，前端刷新后仍能渲染审批卡
                assistant_metadata["remediation_proposals"] = proposals
            assistant_message = Message(
                conversation_id=run.conversation_id,
                role="assistant",
                content=final_content,
                metadata_json=assistant_metadata,
            )
            db.add(assistant_message)
            await db.flush()
            run.final_message_id = assistant_message.id
            run.status = RunStatus.COMPLETED
            run.finished_at = utc_now()
            run.error_code = None
            run.error_message = None
            completed = RunEvent(
                run_id=run_id,
                event_type="run.completed",
                data={"message_id": assistant_message.id},
            )
            db.add(completed)
            await db.commit()
            AGENT_RUNS.labels(status="completed").inc()
            if run.started_at is not None:
                # SQLite 不保存时区：取回的 started_at 是 naive（按 UTC 存储）
                started_at = run.started_at
                if started_at.tzinfo is None:
                    started_at = started_at.replace(tzinfo=timezone.utc)
                AGENT_RUN_DURATION.observe((utc_now() - started_at).total_seconds())
    except asyncio.CancelledError:
        # Dispatcher 取消/优雅关闭超时：先落盘已缓冲事件，再写中断终态，供用户重试
        if buffer is not None:
            try:
                await buffer.flush()
            except Exception:
                pass
        AGENT_RUNS.labels(status="interrupted").inc()
        async with SessionFactory() as db:
            run = await db.get(AgentRun, run_id)
            if run and run.status == RunStatus.RUNNING:
                run.status = RunStatus.FAILED
                run.finished_at = utc_now()
                run.error_code = RUN_INTERRUPTED
                run.error_message = "运行被取消，可重试"
                run.interruption_reason = RUN_INTERRUPTED
                db.add(
                    RunEvent(
                        run_id=run_id,
                        event_type="run.failed",
                        data={
                            "error": {
                                "code": RUN_INTERRUPTED,
                                "message": "运行被取消，可重试",
                                "retryable": True,
                            }
                        },
                    )
                )
                await db.commit()
        raise
    except Exception as exc:
        # 失败路径也强制 flush 已有事件，再写 run.failed，保证运行记录可解释
        if buffer is not None:
            try:
                await buffer.flush()
            except Exception:
                pass
        # 内部堆栈只进结构化日志；对客户端保持稳定的公共错误结构
        logger.exception(
            "agent run failed",
            extra={
                "event": "agent_run_failed",
                "run_id": run_id,
                "error_code": AGENT_RUN_FAILED,
            },
        )
        AGENT_RUNS.labels(status="failed").inc()
        async with SessionFactory() as db:
            run = await db.get(AgentRun, run_id)
            if run:
                run.status = RunStatus.FAILED
                run.finished_at = utc_now()
                run.error_code = AGENT_RUN_FAILED
                run.error_message = f"{type(exc).__name__}: {exc}"[:1000]
                db.add(
                    RunEvent(
                        run_id=run_id,
                        event_type="run.failed",
                        data={
                            "error": {
                                "code": AGENT_RUN_FAILED,
                                "message": "小yi 运行失败",
                                "retryable": False,
                            }
                        },
                    )
                )
                await db.commit()
