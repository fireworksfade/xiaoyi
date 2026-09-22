import pytest

from app.agent.remediation_correlation import (
    RemediationCorrelationError,
    RemediationCorrelationState,
)


def test_successful_diagnosis_is_injected_into_control_call() -> None:
    state = RemediationCorrelationState()
    state.begin_tool_call("diagnose_fault", {"device_id": "ESP32_05"})
    state.record_tool_result(
        "diagnose_fault",
        {
            "ok": True,
            "data": {
                "device_id": "ESP32_05",
                "diagnosis_id": "DIA_20260922_DEADBEEF",
            },
        },
    )

    prepared = state.prepare_arguments(
        "execute_device_action",
        {"device_id": "ESP32_05", "action": "reconnect_mqtt"},
    )

    assert prepared["diagnosis_id"] == "DIA_20260922_DEADBEEF"


def test_control_call_without_successful_diagnosis_is_rejected() -> None:
    state = RemediationCorrelationState()
    with pytest.raises(RemediationCorrelationError) as excinfo:
        state.prepare_arguments(
            "create_remediation_proposal",
            {"device_id": "ESP32_05", "action": "restart_device"},
        )
    assert excinfo.value.code == "DIAGNOSIS_REQUIRED"


def test_model_cannot_replace_trusted_diagnosis_id() -> None:
    state = RemediationCorrelationState(
        diagnosis_by_device={"ESP32_05": "DIA_20260922_DEADBEEF"}
    )
    with pytest.raises(RemediationCorrelationError) as excinfo:
        state.prepare_arguments(
            "execute_device_action",
            {
                "device_id": "ESP32_05",
                "diagnosis_id": "DIA_20260922_BAD00000",
            },
        )
    assert excinfo.value.code == "DIAGNOSIS_CONTEXT_MISMATCH"


def test_new_failed_diagnosis_clears_stale_device_context() -> None:
    state = RemediationCorrelationState(
        diagnosis_by_device={"ESP32_05": "DIA_20260922_DEADBEEF"}
    )
    state.begin_tool_call("diagnose_fault", {"device_id": "ESP32_05"})
    state.record_tool_result("diagnose_fault", {"ok": False, "data": None})
    assert "ESP32_05" not in state.diagnosis_by_device
