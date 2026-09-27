"""Collect remediation proposals from tool results."""


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
