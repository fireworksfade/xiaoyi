"""修复完成事件的发布与确认回联。

Control MCP 在恢复验证收敛后向 `iot/{device_id}/remediation` 发布事件，
由诊断服务自行沉淀案例（所有权归诊断服务，本服务不感知其实现）；
诊断写入案例后经 `iot/{device_id}/remediation_case` 回发确认，
本服务据此把 case_id 关联回命令行，供前端审批卡展示。
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger("xiaoyi.iot_control.remediation_events")

COMPLETED_TOPIC = "iot/{device_id}/remediation"


def completed_event(command: dict[str, Any]) -> dict[str, Any]:
    """由最终态命令构造修复完成事件载荷。"""
    return {
        "event": "completed",
        "command_id": command["command_id"],
        "proposal_id": command.get("proposal_id"),
        "device_id": command["device_id"],
        "action": command["action"],
        "parameters": command.get("parameters") or {},
        "reason": command.get("reason", ""),
        "status": command["status"],
        "verify_status": command.get("verify_status"),
        "ack": command.get("ack"),
        "diagnosis_id": command.get("diagnosis_id"),
        "issued_by": command.get("issued_by", ""),
    }


def publish_completed_events(channel, repository, finalized: list[dict[str, Any]]) -> list[str]:
    """把本轮收敛的命令逐条发布为完成事件，返回已发布的 command_id。"""
    published: list[str] = []
    for item in finalized:
        command = repository.get_command(item["command_id"])
        if not command:
            continue
        topic = COMPLETED_TOPIC.format(device_id=command["device_id"])
        payload_json = json.dumps(completed_event(command), ensure_ascii=False)
        if channel.publish(topic, payload_json):
            published.append(command["command_id"])
        else:
            logger.warning("Failed to publish remediation event to %s", topic)
    return published
