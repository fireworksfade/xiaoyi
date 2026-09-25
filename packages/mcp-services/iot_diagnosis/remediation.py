"""修复结果事件处理：订阅修复完成事件，把成功的修复沉淀为已验证故障案例。

Control MCP 在恢复验证收敛后向 `iot/{device_id}/remediation` 发布事件；
本模块只按明确的 diagnosis_id 关联诊断；缺失、无效或设备不匹配时拒绝沉淀案例，
组装案例写入本服务自有存储，并通过 `iot/{device_id}/remediation_case`
回发确认事件，供 Control MCP 把 case_id 关联回命令。
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("xiaoyi.iot_diagnosis.remediation")


def build_case_payload(event: dict[str, Any], diagnosis_result: dict[str, Any]) -> dict[str, Any]:
    """用诊断结果 + 实际执行的修复动作组装一条已验证故障案例。"""
    evidence = [str(item) for item in diagnosis_result.get("evidence", []) if str(item).strip()]
    query = str(diagnosis_result.get("query", "")).strip()
    parameters = event.get("parameters") or {}
    parameter_text = "、".join(f"{k}={v}" for k, v in parameters.items())
    action_text = event["action"] + (f"（{parameter_text}）" if parameter_text else "")
    ack = event.get("ack") or {}
    ack_detail = str(ack.get("detail", "设备已确认执行"))
    return {
        "device_id": event["device_id"],
        "fault_type": str(diagnosis_result.get("fault_type") or "unknown"),
        "fault_name": str(diagnosis_result.get("fault_name") or "未知故障"),
        "symptoms": evidence[:20] or [query or "症状信息缺失"],
        "logs": evidence[:50] or [query or "日志信息缺失"],
        "cause": str(diagnosis_result.get("cause") or "根因信息缺失"),
        "solution": (
            f"自动执行 {action_text} 修复（命令 {event['command_id']}），"
            f"设备回执「{ack_detail}」，恢复验证通过。"
            f"诊断依据：{diagnosis_result.get('diagnosis_id', '未知')}，"
            f"置信度 {diagnosis_result.get('confidence', '未知')}。"
        ),
        "verified": True,
        "verified_by": f"auto-remediation:{event['command_id']}",
    }


def _resolve_diagnosis(repository, event: dict[str, Any]) -> dict[str, Any] | None:
    diagnosis_id = event.get("diagnosis_id")
    if not diagnosis_id:
        logger.warning("Remediation event is missing diagnosis_id")
        return None
    trace = repository.get_diagnosis_trace(str(diagnosis_id))
    if not trace:
        logger.warning("Remediation event references missing diagnosis %s", diagnosis_id)
        return None
    if trace.get("device_id") != event.get("device_id"):
        logger.warning(
            "Remediation event diagnosis %s belongs to device %s, not %s",
            diagnosis_id,
            trace.get("device_id"),
            event.get("device_id"),
        )
        return None
    if (trace.get("observability") or {}).get("error"):
        logger.warning("Remediation event references failed diagnosis %s", diagnosis_id)
        return None
    if trace.get("fault_type") == "realtime_state":
        logger.warning("Remediation event references non-actionable diagnosis %s", diagnosis_id)
        return None
    return trace["result"]


def handle_remediation_event(
    repository, device_id: str, payload: dict[str, Any]
) -> dict[str, Any] | None:
    """处理一条修复完成事件；返回确认载荷（无需沉淀时返回 None）。"""
    if payload.get("verify_status") != "succeeded":
        return None
    command_id = str(payload.get("command_id", "")).strip()
    if not command_id:
        return None
    event = {
        "command_id": command_id,
        "device_id": device_id,
        "action": str(payload.get("action", "unknown")),
        "parameters": payload.get("parameters") or {},
        "ack": payload.get("ack") or {},
        "diagnosis_id": payload.get("diagnosis_id"),
    }
    diagnosis_result = _resolve_diagnosis(repository, event)
    if not diagnosis_result:
        logger.info("No correlatable diagnosis for remediation %s on %s", command_id, device_id)
        return None
    case = build_case_payload(event, diagnosis_result)
    written = repository.add_verified_fault_case(case)
    confirmation = {
        "command_id": command_id,
        "device_id": device_id,
        "case_id": written["fault_id"],
        "diagnosis_id": diagnosis_result.get("diagnosis_id"),
    }
    logger.info("Remediation %s archived as case %s", command_id, confirmation["case_id"])
    return confirmation
