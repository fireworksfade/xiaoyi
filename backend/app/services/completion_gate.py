"""Deterministic completion gate based exclusively on persisted evidence."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from app.models import OperationWorkflow, OperationWorkflowStep

GateAction = Literal["pass_final", "pass_handoff", "continue", "fail"]


@dataclass(frozen=True, slots=True)
class CompletionDecision:
    action: GateAction
    reason_code: str
    message: str
    required_action: dict[str, Any] | None = None
    evidence: dict[str, Any] = field(default_factory=dict)


class CompletionGate:
    def __init__(self, max_continuations: int = 2) -> None:
        self.max_continuations = max(0, max_continuations)

    def evaluate(
        self,
        workflow: OperationWorkflow | None,
        steps: list[OperationWorkflowStep] | None = None,
        *,
        continuation_count: int = 0,
        capability_available: bool = True,
    ) -> CompletionDecision:
        if workflow is None:
            return CompletionDecision("pass_final", "NO_IOT_WORKFLOW", "No IoT workflow is active")
        evidence = {
            "workflow_id": workflow.id,
            "status": workflow.status,
            "outcome": workflow.outcome,
            "current_step": workflow.current_step,
            "diagnosis_id": workflow.diagnosis_id,
            "proposal_id": workflow.proposal_id,
            "command_id": workflow.command_id,
            "case_id": workflow.case_id,
            "fault_type": next(
                (
                    (step.evidence_json or {}).get("fault_type")
                    for step in (steps or [])
                    if step.step_key == "diagnose"
                ),
                None,
            ),
        }
        state = workflow.state_json or {}
        if state.get("conflict"):
            return CompletionDecision(
                "fail", "WORKFLOW_STATE_CONFLICT", "Workflow evidence conflicts", evidence=evidence
            )
        if not capability_available:
            return CompletionDecision(
                "fail",
                "WORKFLOW_CAPABILITY_UNAVAILABLE",
                "Required capability is unavailable",
                evidence=evidence,
            )
        if workflow.status == "waiting_approval":
            return CompletionDecision(
                "pass_handoff",
                "WAITING_USER_APPROVAL",
                "Waiting for user approval",
                {"type": "approve_proposal", "proposal_id": workflow.proposal_id},
                evidence,
            )
        if workflow.status == "cancelled":
            reason = (
                "PROPOSAL_EXPIRED"
                if state.get("proposal_decision") == "expired"
                else "PROPOSAL_REJECTED"
            )
            return CompletionDecision(
                "pass_handoff", reason, "Remediation was not executed", evidence=evidence
            )
        if workflow.status == "failed":
            return CompletionDecision(
                "pass_final",
                "REMEDIATION_FAILED",
                "Remediation or verification failed",
                evidence=evidence,
            )
        if workflow.goal == "diagnosis" and workflow.diagnosis_id:
            return CompletionDecision(
                "pass_final",
                "GOAL_DIAGNOSIS_COMPLETE",
                "Diagnosis evidence is complete",
                evidence=evidence,
            )
        verify_status = state.get("verify_status")
        if verify_status == "succeeded":
            reason = (
                "CASE_ARCHIVE_PENDING"
                if state.get("case_status") != "archived"
                else "GOAL_REMEDIATION_VERIFIED"
            )
            return CompletionDecision(
                "pass_final", reason, "Remediation was verified", evidence=evidence
            )
        if continuation_count < self.max_continuations:
            return CompletionDecision(
                "continue",
                "WAITING_DEVICE_VERIFICATION",
                "Verification evidence is still required",
                {"tool": "get_action_result", "command_id": workflow.command_id},
                evidence,
            )
        return CompletionDecision(
            "pass_handoff",
            "COMPLETION_GATE_LIMIT_REACHED",
            "Verification remains pending",
            {"type": "wait_for_verification", "command_id": workflow.command_id},
            evidence,
        )
