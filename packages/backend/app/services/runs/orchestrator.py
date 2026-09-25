"""主运行编排逻辑 - execute_claimed_run 核心实现。"""

import asyncio
import json
import logging
from datetime import timezone
from types import MappingProxyType

from sqlalchemy import select

from app.agent.lifecycle import DEFAULT_HOOKS, HookContext
from app.agent.runtime import AgentRuntime, RuntimeEvent, RuntimeMCPServer, build_runtime
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
    complete_diagnosis_workflow,
    get_workflow_for_run,
)

from .event_handler import append_event
from .tool_processor import collect_proposal, process_tool_semantic_events

logger = logging.getLogger("xiaoyi.runs.orchestrator")


async def _record_hook_observations(run_id: str, point: str, context: HookContext) -> None:
    """记录生命周期钩子观察结果。"""
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
    """评估 Completion Gate 决策。"""
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
        await db.commit()
        COMPLETION_GATE_DECISIONS.labels(
            action=decision.action, reason_code=decision.reason_code
        ).inc()
        await append_event(
            run_id,
            RuntimeEvent(
                "completion_gate.decision",
                {
                    "action": decision.action,
                    "reason_code": decision.reason_code,
                    "required_action": decision.required_action,
                    "evidence": decision.evidence,
                    "continuation_count": continuation_count,
                },
            ),
        )
        return decision


def _gate_final_content(decision: CompletionDecision, model_content: str) -> str:
    """根据 Gate 决策调整最终内容。"""
    if decision.action == "complete":
        if decision.reason_code == "GOAL_DIAGNOSIS_COMPLETE":
            return model_content or "诊断已完成。"
        if decision.reason_code == "GOAL_REMEDIATION_COMPLETE":
            return model_content or "修复已完成并验证。"
        if decision.reason_code == "APPROVAL_REQUIRED":
            return model_content or "修复提案已生成，等待审批。"
        return model_content or "任务已完成。"
    if decision.action == "pass":
        if decision.reason_code == "PASS_HANDOFF":
            return model_content or "已达最大续轮次数。如需继续，请调整问题或在新对话中重试。"
        return model_content
    if decision.action == "fail":
        return f"运行失败：{decision.message}"
    return model_content


async def _stream_with_context_recovery(
    run_id: str,
    runtime: AgentRuntime,
    runtime_messages: list[dict],
    mcp_servers: list[RuntimeMCPServer],
    settings,
    allow_retry: bool,
):
    """流式执行运行，带上下文压缩恢复能力。"""
    tool_started = False
    try:
        async for event in runtime.stream(runtime_messages, mcp_servers):
            if event.event_type == "tool.started":
                tool_started = True
            yield event
    except Exception as exc:
        # 如果工具已经开始执行，不能重试（工具可能有副作用）
        if tool_started or not (allow_retry and is_prompt_too_long(exc)):
            raise
        logger.info(
            "context budget exceeded, retrying with compact",
            extra={"event": "context_recovery", "run_id": run_id},
        )
        try:
            compacted = compact_retry_messages(
                runtime_messages, workflow_snapshot=runtime.workflow_snapshot
            )
            if compacted == runtime_messages:
                raise WorkflowError(
                    CONTEXT_COMPACTION_EXHAUSTED, "model input cannot be compacted further"
                )

            # 保存压缩前的转录并发出事件
            async with SessionFactory() as db:
                artifact = await LocalArtifactStore(
                    settings.run_artifact_root, settings.run_artifact_retention_hours
                ).write(
                    db, run_id=run_id, kind="transcript", content={"messages": runtime_messages}
                )
                await db.commit()

            CONTEXT_COMPACTIONS.labels(layer="L2").inc()
            yield RuntimeEvent(
                "context.compacted",
                {
                    "layer": "L2",
                    "artifact_id": artifact.id,
                    "original_bytes": artifact.size_bytes,
                    "sha256": artifact.sha256,
                },
            )

            async for event in runtime.stream(compacted, mcp_servers):
                yield event
        except Exception as inner_exc:
            if is_prompt_too_long(inner_exc):
                raise WorkflowError(
                    CONTEXT_COMPACTION_EXHAUSTED, "model input still exceeds its context window"
                ) from inner_exc
            raise


async def execute_claimed_run(run_id: str) -> None:
    """执行已处于 RUNNING 的 run（由 Dispatcher 或 legacy 入口认领后调用）。"""
    settings = get_settings()
    DEFAULT_HOOKS.set_timeout_ms(settings.hook_timeout_ms)
    final_content = ""
    proposals: list[dict[str, object]] = []
    gate_decision: CompletionDecision | None = None
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

        # 上下文压缩 L3: 历史快照
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
                                        "covers_through_message_id": snapshot.covers_through_message_id,
                                        "source_transcript_artifact_id": snapshot.source_artifact_id,
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
                    proposal = collect_proposal(event.data, proposals)
                    if proposal is not None:
                        buffer.append(
                            RuntimeEvent("remediation.proposal_created", {"proposal": proposal}),
                        )
                    try:
                        await process_tool_semantic_events(
                            run_id, event.data, runtime, settings.workflow_runtime_enabled
                        )
                    except WorkflowError as exc:
                        buffer.append(event)
                        buffer.append(
                            RuntimeEvent(
                                "semantic.invalid",
                                {"tool_name": event.data.get("tool_name"), "error": str(exc)},
                            )
                        )
                        raise

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
        if buffer is not None:
            try:
                await buffer.flush()
            except Exception:
                pass
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


async def process_agent_run(run_id: str) -> None:
    """完整执行入口：认领 + 执行（供 legacy BackgroundTasks 模式使用）。"""
    if not await claim_queued_run(run_id):
        return
    await execute_claimed_run(run_id)
