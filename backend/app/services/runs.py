from sqlalchemy import select

from app.agent.runtime import RuntimeEvent, build_runtime
from app.config import get_settings
from app.db import SessionFactory
from app.models import AgentRun, Attachment, Message, ModelConfiguration, RunEvent, RunStatus
from app.security import decrypt_secret
from app.services.mcp_catalog import load_agent_mcp_servers


async def append_event(run_id: str, event: RuntimeEvent) -> RunEvent:
    async with SessionFactory() as db:
        record = RunEvent(run_id=run_id, event_type=event.event_type, data=event.data)
        db.add(record)
        await db.commit()
        await db.refresh(record)
        return record


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


async def process_agent_run(run_id: str) -> None:
    settings = get_settings()
    final_content = ""
    proposals: list[dict[str, object]] = []
    try:
        async with SessionFactory() as db:
            run = await db.get(AgentRun, run_id)
            if not run or run.status != RunStatus.QUEUED:
                return
            run.status = RunStatus.RUNNING
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
            messages = list(
                (
                    await db.scalars(
                        select(Message)
                        .where(Message.conversation_id == run.conversation_id)
                        .order_by(Message.created_at, Message.id)
                    )
                ).all()
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
        runtime_messages = []
        for item in messages:
            content = item.content
            message_attachments = attachments_by_message.get(item.id, [])
            if message_attachments:
                appendix = "\n\n".join(
                    f"[附件：{attachment.filename}]\n{attachment.extracted_text}"
                    for attachment in message_attachments
                )
                content = f"{content}\n\n{appendix}"
            runtime_messages.append({"role": item.role, "content": content})
        async for event in runtime.stream(runtime_messages, mcp_servers):
            if event.event_type == "answer.final":
                final_content = str(event.data.get("content", ""))
                continue
            if event.event_type == "tool.finished":
                proposal = _collect_proposals(event.data, proposals)
                if proposal is not None:
                    # 语义事件：前端只依赖这个稳定契约，不解析 MCP 信封
                    await append_event(
                        run_id,
                        RuntimeEvent("remediation.proposal_created", {"proposal": proposal}),
                    )
            await append_event(run_id, event)

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
            completed = RunEvent(
                run_id=run_id,
                event_type="run.completed",
                data={"message_id": assistant_message.id},
            )
            db.add(completed)
            await db.commit()
    except Exception as exc:
        async with SessionFactory() as db:
            run = await db.get(AgentRun, run_id)
            if run:
                run.status = RunStatus.FAILED
                run.error_code = "AGENT_RUN_FAILED"
                run.error_message = str(exc)[:1000]
                db.add(
                    RunEvent(
                        run_id=run_id,
                        event_type="run.failed",
                        data={
                            "error": {
                                "code": "AGENT_RUN_FAILED",
                                "message": "小yi 运行失败",
                                "retryable": False,
                            }
                        },
                    )
                )
                await db.commit()
