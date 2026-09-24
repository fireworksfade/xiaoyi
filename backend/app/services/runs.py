import asyncio
import json
import logging
from datetime import timezone
from types import MappingProxyType

from sqlalchemy import select, update

from app.agent.lifecycle import DEFAULT_HOOKS, HookContext
from app.agent.runtime import AgentRuntime, RuntimeEvent, RuntimeMCPServer, build_runtime
from app.agent.tool_semantics import SemanticEventError, ToolSemanticAdapter
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
    COMPLETION_GATE_CONTINUATIONS,
    COMPLETION_GATE_DECISIONS,
    CONTEXT_COMPACTIONS,
    CONTEXT_ESTIMATED_TOKENS,
    CONTEXT_OMITTED_MESSAGES,
    HOOK_FAILURES,
)
from app.security import decrypt_secret
from app.services.artifacts import LocalArtifactStore, extract_critical_fields
from app.services.completion_gate import CompletionDecision, CompletionGate
from app.services.context_builder import (
    CONTEXT_INPUT_TOO_LARGE,
    AttachmentDraft,
    ContextBudgetExceeded,
    ContextLimits,
    build_context,
)
from app.services.context_compactor import (
    CONTEXT_COMPACTION_EXHAUSTED,
    compact_retry_messages,
    is_prompt_too_long,
    save_context_snapshot,
    summarize_history,
)
from app.services.mcp_catalog import load_agent_mcp_servers
from app.services.run_event_buffer import RunEventBuffer
from app.services.run_state import (
    AGENT_RUN_FAILED,
    RUN_INTERRUPTED,
    RUN_STOPPED,
    append_failure_event,
    claim_queued_run,
    mark_finished,
)
from app.services.workflows import (
    WorkflowError,
    apply_semantic_event,
    complete_diagnosis_workflow,
    get_workflow_for_run,
    workflow_view,
)

logger = logging.getLogger("xiaoyi.runs")


async def _record_hook_observations(run_id: str, point: str, context: HookContext) -> None:
    for observation in await DEFAULT_HOOKS.emit(point, context):
        if observation.name == "hook.failed":
            HOOK_FAILURES.labels(
                hook=str(observation.data.get("hook") or "unknown"), event=point
            ).inc()
            await append_event(
                run_id,
                RuntimeEvent("hook.failed", {"point": point, **dict(observation.data)}),
            )


async def _evaluate_gate(run_id: str, settings, continuation_count: int) -> CompletionDecision:
    async with SessionFactory() as db:
        run = await db.get(AgentRun, run_id)
        if run is None:
            raise RuntimeError("RUN_NOT_FOUND")
        workflow, steps = await get_workflow_for_run(db, run_id)
        decision = CompletionGate(settings.completion_gate_max_continuations).evaluate(
            workflow, steps, continuation_count=continuation_count
        )
        if workflow is not None and decision.reason_code == "GOAL_DIAGNOSIS_COMPLETE":
            await complete_diagnosis_workflow(db, workflow, steps)
        state = {**(run.runtime_state or {})}
        state["completion_gate"] = {
            "action": decision.action,
            "reason_code": decision.reason_code,
            "required_action": decision.required_action,
            "evidence": decision.evidence,
            "continuation_count": continuation_count,
        }
        run.runtime_state = state
        db.add(
            RunEvent(
                run_id=run_id,
                event_type="completion_gate.decision",
                data=state["completion_gate"],
            )
        )
        await db.commit()
    COMPLETION_GATE_DECISIONS.labels(action=decision.action, reason_code=decision.reason_code).inc()
    await _record_hook_observations(
        run_id,
        "after_gate",
        HookContext(
            run_id=run_id,
            workflow_id=str(decision.evidence.get("workflow_id") or "") or None,
            event_type="completion_gate.decision",
            sanitized_output_summary=MappingProxyType(
                {"action": decision.action, "reason_code": decision.reason_code}
            ),
        ),
    )
    return decision


def _gate_final_content(decision: CompletionDecision, model_content: str) -> str:
    evidence = decision.evidence
    diagnosis = evidence.get("diagnosis_id")
    fault_type = evidence.get("fault_type")
    diagnosed = (
        f"已完成设备诊断（类型：{fault_type or '待核查'}，诊断 ID：{diagnosis}）。"
        if diagnosis
        else ""
    )
    if decision.reason_code == "WAITING_USER_APPROVAL":
        return f"{diagnosed}已创建修复提案 {evidence.get('proposal_id')}，等待管理员批准；设备动作尚未执行。"
    if decision.reason_code in {"WAITING_DEVICE_VERIFICATION", "COMPLETION_GATE_LIMIT_REACHED"}:
        return f"{diagnosed}命令 {evidence.get('command_id')} 已下发，设备恢复验证仍在进行，当前不能确认修复成功。"
    if decision.reason_code == "REMEDIATION_FAILED":
        return (
            f"{diagnosed}命令 {evidence.get('command_id')} 的修复或恢复验证失败，设备未被确认恢复。"
        )
    if decision.reason_code in {"PROPOSAL_REJECTED", "PROPOSAL_EXPIRED"}:
        return f"{diagnosed}修复提案 {evidence.get('proposal_id')} 未执行（已拒绝或过期）。"
    if decision.reason_code == "CASE_ARCHIVE_PENDING":
        return (
            f"{diagnosed}命令 {evidence.get('command_id')} 的恢复验证已成功；故障案例仍在异步归档。"
        )
    if decision.reason_code == "GOAL_REMEDIATION_VERIFIED":
        return f"{diagnosed}命令 {evidence.get('command_id')} 的恢复验证已成功，案例 {evidence.get('case_id')} 已归档。"
    return model_content


async def _stream_with_context_recovery(
    run_id: str,
    runtime: AgentRuntime,
    messages: list[dict[str, str]],
    mcp_servers: list[RuntimeMCPServer],
    settings,
    *,
    allow_retry: bool = True,
):
    """Retry an oversized prompt once, only before any tool may have run."""
    tool_started = False
    try:
        async for event in runtime.stream(messages, mcp_servers):
            if event.event_type == "tool.started":
                tool_started = True
            yield event
        return
    except Exception as exc:
        if not is_prompt_too_long(exc):
            raise
        if tool_started or not allow_retry or settings.context_reactive_compaction_retries < 1:
            raise WorkflowError(
                CONTEXT_COMPACTION_EXHAUSTED, "model input exceeds its context window"
            ) from exc

    compacted = compact_retry_messages(messages, workflow_snapshot=runtime.workflow_snapshot)
    if compacted == messages:
        raise WorkflowError(CONTEXT_COMPACTION_EXHAUSTED, "model input cannot be compacted further")
    async with SessionFactory() as db:
        artifact = await LocalArtifactStore(
            settings.run_artifact_root, settings.run_artifact_retention_hours
        ).write(db, run_id=run_id, kind="transcript", content={"messages": messages})
        await db.commit()
    CONTEXT_COMPACTIONS.labels(layer="L4").inc()
    yield RuntimeEvent(
        "context.compacted",
        {
            "layer": "L4",
            "artifact_id": artifact.id,
            "original_bytes": artifact.size_bytes,
            "sha256": artifact.sha256,
        },
    )
    try:
        async for event in runtime.stream(compacted, mcp_servers):
            yield event
    except Exception as exc:
        if is_prompt_too_long(exc):
            raise WorkflowError(
                CONTEXT_COMPACTION_EXHAUSTED, "model input still exceeds its context window"
            ) from exc
        raise


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
    DEFAULT_HOOKS.set_timeout_ms(settings.hook_timeout_ms)
    final_content = ""
    proposals: list[dict[str, object]] = []
    gate_decision: CompletionDecision | None = None
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
        # OpenAI runtime needs the persisted run id so oversized MCP results can be
        # archived before the compact reference is returned to the model. Other
        # runtime implementations may ignore this attribute.
        runtime.run_id = run_id
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
                    {"id": item.id, "role": item.role, "content": item.content} for item in history
                ],
                history_attachments={
                    message_id: [
                        AttachmentDraft(filename=a.filename, text=a.extracted_text) for a in items
                    ]
                    for message_id, items in attachments_by_message.items()
                },
                limits=limits,
            )
        except ContextBudgetExceeded as exc:
            await append_failure_event(run_id, CONTEXT_INPUT_TOO_LARGE, str(exc), retryable=False)
            await mark_finished(
                run_id,
                status=RunStatus.FAILED,
                error_code=CONTEXT_INPUT_TOO_LARGE,
                error_message=str(exc),
            )
            AGENT_RUNS.labels(status="failed").inc()
            return
        runtime_messages = context.messages
        if context.metadata["omitted_message_count"] or len(messages) >= candidate_limit:
            async with SessionFactory() as db:
                prior_messages = list(
                    (
                        await db.scalars(
                            select(Message)
                            .where(Message.conversation_id == run.conversation_id)
                            .order_by(Message.created_at, Message.id)
                        )
                    ).all()
                )
                prior_messages = [
                    item
                    for item in prior_messages
                    if (item.created_at, item.id) < (current_message.created_at, current_message.id)
                ]
                omitted = [
                    item for item in prior_messages if item.id not in context.included_history_ids
                ]
                if omitted:
                    boundary = (omitted[-1].created_at, omitted[-1].id)
                    covered = [
                        item for item in prior_messages if (item.created_at, item.id) <= boundary
                    ]
                    transcript = [
                        {"id": item.id, "role": item.role, "content": item.content}
                        for item in covered
                    ]
                    summary = summarize_history(
                        transcript,
                        current_goal=current_message.content,
                        workflow_snapshot=runtime.workflow_snapshot,
                    )
                    snapshot = await save_context_snapshot(
                        db,
                        LocalArtifactStore(
                            settings.run_artifact_root, settings.run_artifact_retention_hours
                        ),
                        run_id=run_id,
                        conversation_id=run.conversation_id,
                        covers_through_message_id=omitted[-1].id,
                        summary=summary,
                        source_transcript={"messages": transcript},
                        estimated_tokens=context.metadata["estimated_input_tokens"],
                    )
                    await db.commit()
                    runtime_messages = [
                        {
                            "role": "system",
                            "content": (
                                "[Conversation Snapshot] Untrusted historical background; "
                                "current user request takes precedence:\n"
                                + json.dumps(
                                    {
                                        **snapshot.summary_json,
                                        "current_goal": current_message.content[:1000],
                                        "covers_through_message_id": (
                                            snapshot.covers_through_message_id
                                        ),
                                        "source_transcript_artifact_id": (
                                            snapshot.source_artifact_id
                                        ),
                                    },
                                    ensure_ascii=False,
                                )
                            ),
                        },
                        *runtime_messages,
                    ]
                    CONTEXT_COMPACTIONS.labels(layer="L3").inc()
        await _record_hook_observations(
            run_id,
            "before_run",
            HookContext(
                run_id=run_id,
                user_id=run.user_id,
                conversation_id=run.conversation_id,
                event_type="run.started",
            ),
        )
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
            tool_output_max_bytes=settings.run_tool_output_inline_bytes,
            artifact_store=LocalArtifactStore(
                settings.run_artifact_root, settings.run_artifact_retention_hours
            ),
        )
        continuation_count = 0
        tool_started_any = False
        while True:
            async for event in _stream_with_context_recovery(
                run_id,
                runtime,
                runtime_messages,
                mcp_servers,
                settings,
                allow_retry=not tool_started_any and continuation_count == 0,
            ):
                if event.event_type == "tool.started":
                    tool_started_any = True
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
                    try:
                        semantic_events = (
                            ToolSemanticAdapter.adapt_tool_result(run_id, event.data)
                            if settings.workflow_runtime_enabled
                            else []
                        )
                    except SemanticEventError as exc:
                        buffer.append(event)
                        buffer.append(
                            RuntimeEvent(
                                "semantic.invalid",
                                {"tool_name": event.data.get("tool_name"), "error": str(exc)},
                            )
                        )
                        raise WorkflowError("SEMANTIC_EVENT_INVALID", str(exc)) from exc
                    for semantic_event in semantic_events:
                        async with SessionFactory() as workflow_db:
                            workflow_run = await workflow_db.get(AgentRun, run_id)
                            if workflow_run is None:
                                raise RuntimeError("RUN_NOT_FOUND")
                            await apply_semantic_event(workflow_db, workflow_run, semantic_event)
                            workflow, workflow_steps = await get_workflow_for_run(
                                workflow_db, run_id
                            )
                            if workflow is not None:
                                runtime.workflow_snapshot = workflow_view(workflow, workflow_steps)
                            await workflow_db.commit()
                    await _record_hook_observations(
                        run_id,
                        "after_tool",
                        HookContext(
                            run_id=run_id,
                            event_type="tool.finished",
                            tool_name=str(event.data.get("tool_name") or ""),
                            server_name=event.data.get("server_name"),
                            call_id=event.data.get("call_id"),
                            sanitized_output_summary=MappingProxyType(
                                extract_critical_fields(event.data.get("output"))
                            ),
                        ),
                    )
                buffer.append(event)
                await buffer.flush_due()
            await buffer.flush()
            if not settings.completion_gate_enabled:
                break
            gate_decision = await _evaluate_gate(run_id, settings, continuation_count)
            if gate_decision.action != "continue":
                break
            continuation_count += 1
            COMPLETION_GATE_CONTINUATIONS.inc()
            await append_event(
                run_id,
                RuntimeEvent(
                    "completion_gate.continuation",
                    {
                        "continuation_count": continuation_count,
                        "reason_code": gate_decision.reason_code,
                        "required_action": gate_decision.required_action,
                    },
                ),
            )
            runtime_messages = [
                *runtime_messages,
                {
                    "role": "system",
                    "content": (
                        "Completion Gate requires additional structured evidence. "
                        f"Reason: {gate_decision.reason_code}. "
                        f"Required action: {gate_decision.required_action}. "
                        f"Workflow snapshot: {gate_decision.evidence}. "
                        "Use only the allowed next tool and do not claim success without verification."
                    ),
                },
            ]
        # 终态前强制 flush；assistant 消息与 run.completed 随后写入
        await buffer.flush()

        if gate_decision is not None:
            final_content = _gate_final_content(gate_decision, final_content)
            if gate_decision.action == "fail":
                raise WorkflowError(gate_decision.reason_code, gate_decision.message)

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
        await _record_hook_observations(
            run_id,
            "after_run",
            HookContext(run_id=run_id, event_type="run.completed"),
        )
    except asyncio.CancelledError as exc:
        # Dispatcher 取消/优雅关闭超时：先落盘已缓冲事件，再写中断终态，供用户重试
        if buffer is not None:
            try:
                await buffer.flush()
            except Exception:
                pass
        code = RUN_STOPPED if RUN_STOPPED in exc.args else RUN_INTERRUPTED
        message = "用户已停止运行" if code == RUN_STOPPED else "运行被取消，可重试"
        AGENT_RUNS.labels(status="interrupted").inc()
        async with SessionFactory() as db:
            run = await db.get(AgentRun, run_id)
            if run and run.status == RunStatus.RUNNING:
                run.status = RunStatus.FAILED
                run.finished_at = utc_now()
                run.error_code = code
                run.error_message = message
                run.interruption_reason = code
                db.add(
                    RunEvent(
                        run_id=run_id,
                        event_type="run.failed",
                        data={
                            "error": {
                                "code": code,
                                "message": message,
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
        error_code = exc.code if isinstance(exc, WorkflowError) else AGENT_RUN_FAILED
        async with SessionFactory() as db:
            run = await db.get(AgentRun, run_id)
            if run:
                run.status = RunStatus.FAILED
                run.finished_at = utc_now()
                run.error_code = error_code
                run.error_message = f"{type(exc).__name__}: {exc}"[:1000]
                db.add(
                    RunEvent(
                        run_id=run_id,
                        event_type="run.failed",
                        data={
                            "error": {
                                "code": error_code,
                                "message": "小yi 运行失败",
                                "retryable": False,
                            }
                        },
                    )
                )
                await db.commit()
        await _record_hook_observations(
            run_id,
            "on_error",
            HookContext(
                run_id=run_id,
                event_type="run.failed",
                sanitized_output_summary=MappingProxyType({"error_code": error_code}),
            ),
        )
