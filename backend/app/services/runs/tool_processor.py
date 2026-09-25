"""工具调用结果处理、提案收集和语义事件适配逻辑。"""

import logging

from app.agent.tool_semantics import SemanticEventError, ToolSemanticAdapter
from app.db import SessionFactory
from app.models import AgentRun
from app.services.workflows import (
    WorkflowError,
    apply_semantic_event,
    get_workflow_for_run,
    workflow_view,
)

logger = logging.getLogger("xiaoyi.runs.tool_processor")


def collect_proposal(event_data: dict, proposals: list[dict[str, object]]) -> dict | None:
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


async def process_tool_semantic_events(
    run_id: str,
    event_data: dict,
    runtime,
    workflow_enabled: bool,
) -> None:
    """处理工具调用的语义事件，更新工作流状态。"""
    if not workflow_enabled:
        return

    try:
        semantic_events = ToolSemanticAdapter.adapt_tool_result(run_id, event_data)
    except SemanticEventError as exc:
        raise WorkflowError("SEMANTIC_EVENT_INVALID", str(exc)) from exc

    for semantic_event in semantic_events:
        async with SessionFactory() as workflow_db:
            workflow_run = await workflow_db.get(AgentRun, run_id)
            if workflow_run is None:
                raise RuntimeError("RUN_NOT_FOUND")
            await apply_semantic_event(workflow_db, workflow_run, semantic_event)
            workflow, workflow_steps = await get_workflow_for_run(workflow_db, run_id)
            if workflow is not None:
                runtime.workflow_snapshot = workflow_view(workflow, workflow_steps)
            await workflow_db.commit()
