"""Validated, stable semantic events derived from authorized MCP results."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any


class SemanticEventError(ValueError):
    code = "SEMANTIC_EVENT_INVALID"


@dataclass(frozen=True, slots=True)
class SemanticEvent:
    event_type: str
    event_key: str
    payload: dict[str, Any]


def _required_text(data: dict[str, Any], name: str) -> str:
    value = data.get(name)
    if not isinstance(value, str) or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}", value.strip()
    ):
        raise SemanticEventError(f"missing or invalid {name}")
    return value.strip()


def _optional_text(data: dict[str, Any], name: str) -> str | None:
    value = data.get(name)
    if value is None:
        return None
    if not isinstance(value, str) or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}", value.strip()
    ):
        raise SemanticEventError(f"invalid {name}")
    return value.strip()


def _required_label(data: dict[str, Any], name: str) -> str:
    value = data.get(name)
    if not isinstance(value, str):
        raise SemanticEventError(f"missing or invalid {name}")
    label = value.strip()
    if not label or len(label) > 160 or any(ord(char) < 32 for char in label):
        raise SemanticEventError(f"missing or invalid {name}")
    return label


class ToolSemanticAdapter:
    """The only MCP-envelope-to-workflow boundary.

    Unknown tools and unsuccessful results produce no semantic event. Malformed
    successful results are rejected and therefore cannot advance a workflow.
    """

    @classmethod
    def adapt_tool_result(cls, run_id: str, event_data: dict[str, Any]) -> list[SemanticEvent]:
        tool_name = event_data.get("tool_name")
        output = event_data.get("output")
        if not isinstance(tool_name, str) or not isinstance(output, dict):
            return []
        if output.get("ok") is not True:
            return []
        data = output.get("data")
        if not isinstance(data, dict):
            raise SemanticEventError("successful result has no object data")
        call_id = str(event_data.get("call_id") or "unknown")
        key = f"{run_id}:{{event_type}}:{call_id}"

        if tool_name == "diagnose_fault":
            try:
                confidence = float(data["confidence"])
            except (KeyError, TypeError, ValueError) as exc:
                raise SemanticEventError("invalid confidence") from exc
            if not math.isfinite(confidence) or not 0 <= confidence <= 1:
                raise SemanticEventError("invalid confidence")
            payload = {
                "device_id": _required_text(data, "device_id"),
                "diagnosis_id": _required_text(data, "diagnosis_id"),
                "fault_type": _required_label(data, "fault_type"),
                "confidence": confidence,
            }
            event_type = "diagnosis.completed"
        elif tool_name == "execute_device_action":
            payload = {
                "command_id": _required_text(data, "command_id"),
                "device_id": _required_text(data, "device_id"),
                "action": _required_text(data, "action"),
                "diagnosis_id": _required_text(data, "diagnosis_id"),
                "risk_level": str(data.get("risk_level") or "low"),
            }
            event_type = "remediation.command_started"
        elif tool_name == "create_remediation_proposal":
            payload = {
                "proposal_id": _required_text(data, "proposal_id"),
                "device_id": _required_text(data, "device_id"),
                "action": _required_text(data, "action"),
                "diagnosis_id": _required_text(data, "diagnosis_id"),
                "risk_level": str(data.get("risk_level") or "high"),
                "status": str(data.get("status") or "pending"),
            }
            event_type = "remediation.proposal_created"
        elif tool_name == "get_action_result":
            command = data.get("command") if isinstance(data.get("command"), dict) else data
            if not isinstance(command, dict) or not command.get("command_id"):
                return []
            payload = {
                "command_id": _required_text(command, "command_id"),
                "device_id": _required_text(command, "device_id"),
                "diagnosis_id": _optional_text(command, "diagnosis_id"),
                "command_status": str(
                    command.get("command_status") or command.get("status") or "unknown"
                ),
                "verify_status": str(command.get("verify_status") or "pending"),
                "case_status": str(command.get("case_status") or "pending"),
                "case_id": _optional_text(command, "case_id"),
            }
            event_type = "remediation.verification_updated"
        else:
            return []
        return [SemanticEvent(event_type, key.format(event_type=event_type), payload)]

    @staticmethod
    def proposal_decision(
        *, proposal_id: str, version: int, decision: str, data: dict[str, Any], decided_by: str
    ) -> SemanticEvent:
        if decision not in {"approved", "rejected", "expired"}:
            raise SemanticEventError("invalid proposal decision")
        payload = {
            "proposal_id": proposal_id,
            "decision": decision,
            "command_id": _optional_text(data, "command_id"),
            "decided_by": decided_by,
        }
        return SemanticEvent(
            "remediation.proposal_decided",
            f"{proposal_id}:{version}:{decision}",
            payload,
        )
