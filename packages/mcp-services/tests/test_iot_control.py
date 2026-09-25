"""IoT Control MCP 单元测试：动作白名单、命令状态机、提案乐观锁与恢复验证。"""

from __future__ import annotations

import json
from datetime import timedelta

import pytest

from iot_control import actions
from iot_control.repository import ControlRepository, iso, utc_now
from iot_diagnosis.simulator import DeviceState, handle_command

DIAGNOSIS_ID = "DIA_20260922_DEADBEEF"


@pytest.fixture()
def repo(tmp_path) -> ControlRepository:
    return ControlRepository(
        str(tmp_path / "iot_control.db"),
        command_timeout_seconds=30,
        verify_window_seconds=60,
        proposal_ttl_minutes=30,
    )


def test_action_catalog_risk_levels() -> None:
    catalog = {item["action"]: item for item in actions.action_catalog()}
    assert catalog["reconnect_mqtt"]["risk_level"] == actions.LOW_RISK
    assert catalog["restart_device"]["risk_level"] == actions.HIGH_RISK
    assert catalog["update_firmware"]["risk_level"] == actions.HIGH_RISK
    assert "seconds" in catalog["set_reporting_interval"]["parameters"]


def test_parameter_validation_rejects_missing_and_out_of_range() -> None:
    assert actions.validate_parameters("set_reporting_interval", {}) == "MISSING_PARAMETER"
    assert (
        actions.validate_parameters("set_reporting_interval", {"seconds": 0}) == "INVALID_PARAMETER"
    )
    assert actions.validate_parameters("set_reporting_interval", {"seconds": 30}) is None
    assert actions.validate_parameters("set_reporting_interval", {"foo": 1}) == "UNKNOWN_PARAMETER"
    assert actions.validate_parameters("reconnect_mqtt", None) is None


def test_low_risk_command_lifecycle_with_recovery(repo: ControlRepository) -> None:
    command = repo.create_command(
        device_id="ESP32_05",
        action="reconnect_mqtt",
        risk_level=actions.LOW_RISK,
        diagnosis_id=DIAGNOSIS_ID,
        parameters={},
        reason="MQTT keep alive timeout",
        issued_by="agent",
    )
    assert command["status"] == "pending"

    acked = repo.mark_command_ack(
        command["command_id"],
        "applied",
        {"command_id": command["command_id"], "status": "applied"},
    )
    assert acked is not None and acked["status"] == "applied"

    # 验证窗口内收到在线状态且无错误日志 => 恢复成功
    repo.record_status_sample("ESP32_05", True)
    repo.record_log_sample("ESP32_05", "INFO")
    finalized = repo.finalize_watches(utc_now() + timedelta(seconds=120))
    assert len(finalized) == 1
    assert finalized[0]["verify_status"] == "succeeded"

    stored = repo.get_command(command["command_id"])
    assert stored is not None and stored["verify_status"] == "succeeded"


def test_watch_fails_on_error_log(repo: ControlRepository) -> None:
    command = repo.create_command(
        device_id="ESP32_06",
        action="reconnect_wifi",
        risk_level=actions.LOW_RISK,
        diagnosis_id=DIAGNOSIS_ID,
    )
    repo.mark_command_ack(command["command_id"], "applied", {"command_id": command["command_id"]})
    repo.record_status_sample("ESP32_06", True)
    repo.record_log_sample("ESP32_06", "ERROR")
    finalized = repo.finalize_watches(utc_now() + timedelta(seconds=120))
    assert finalized[0]["verify_status"] == "failed"


def test_command_timeout_marks_pending_only(repo: ControlRepository) -> None:
    command = repo.create_command("ESP32_05", "reconnect_mqtt", actions.LOW_RISK, DIAGNOSIS_ID)
    # 把创建时间回拨到超时线之前
    past = iso(utc_now() - timedelta(seconds=120))
    with repo._lock, repo._connect() as db:
        db.execute(
            "UPDATE device_command SET created_at = ? WHERE command_id = ?",
            (past, command["command_id"]),
        )
    assert repo.mark_timed_out_commands() == [command["command_id"]]
    stored = repo.get_command(command["command_id"])
    assert stored is not None and stored["status"] == "timeout"


def test_duplicate_ack_is_ignored(repo: ControlRepository) -> None:
    command = repo.create_command("ESP32_05", "reconnect_mqtt", actions.LOW_RISK, DIAGNOSIS_ID)
    first = repo.mark_command_ack(
        command["command_id"], "applied", {"command_id": command["command_id"]}
    )
    second = repo.mark_command_ack(
        command["command_id"], "failed", {"command_id": command["command_id"]}
    )
    assert first is not None and second is None
    stored = repo.get_command(command["command_id"])
    assert stored is not None and stored["status"] == "applied"


def test_proposal_decision_optimistic_lock(repo: ControlRepository) -> None:
    proposal = repo.create_proposal(
        device_id="ESP32_05",
        action="restart_device",
        diagnosis_id=DIAGNOSIS_ID,
        parameters={},
        reason="watchdog reset loop",
        impact="设备将重启一次，短暂中断上报",
    )
    assert proposal["status"] == "pending" and proposal["version"] == 1

    with pytest.raises(ValueError):
        repo.decide_proposal(proposal["proposal_id"], "approved", "admin", 99, actions.risk_level)

    decided, command = repo.decide_proposal(
        proposal["proposal_id"], "approved", "admin", 1, actions.risk_level
    )
    assert decided["status"] == "approved"
    assert decided["version"] == 2
    assert decided["task_status"] == "running"
    assert command is not None and command["risk_level"] == actions.HIGH_RISK

    with pytest.raises(ValueError):
        repo.decide_proposal(proposal["proposal_id"], "rejected", "admin", 1, actions.risk_level)


def test_proposal_expiry_on_read(repo: ControlRepository) -> None:
    proposal = repo.create_proposal("ESP32_05", "restart_device", DIAGNOSIS_ID)
    past = iso(utc_now() - timedelta(hours=1))
    with repo._lock, repo._connect() as db:
        db.execute(
            "UPDATE remediation_proposal SET expires_at = ? WHERE proposal_id = ?",
            (past, proposal["proposal_id"]),
        )
    listed = repo.list_proposals("pending")
    assert listed["total"] == 0
    stored = repo.get_proposal(proposal["proposal_id"])
    assert stored is not None and stored["status"] == "expired"


def test_proposal_task_status_follows_command_verification(
    repo: ControlRepository,
) -> None:
    proposal = repo.create_proposal(
        "ESP32_07", "update_firmware", DIAGNOSIS_ID, {"version": "1.3.0"}
    )
    decided, command = repo.decide_proposal(
        proposal["proposal_id"], "approved", "admin", 1, actions.risk_level
    )
    assert command is not None
    repo.mark_command_ack(command["command_id"], "applied", {})
    repo.record_status_sample("ESP32_07", True)
    repo.finalize_watches(utc_now() + timedelta(seconds=120))
    stored = repo.get_proposal(proposal["proposal_id"])
    assert stored is not None and stored["task_status"] == "succeeded"


def test_simulator_command_handler_behaviors() -> None:
    state = DeviceState("mqtt_timeout", 5.0)
    state.wifi_weak = True

    ack = handle_command(state, {"command_id": "CMD_1", "action": "reconnect_mqtt"})
    assert ack["status"] == "applied" and state.snapshot()["mqtt_timeout"] is False
    assert state.snapshot()["wifi_weak"] is True

    ack = handle_command(
        state,
        {"command_id": "CMD_2", "action": "set_reporting_interval", "parameters": {"seconds": 10}},
    )
    assert ack["status"] == "applied" and state.snapshot()["interval"] == 10.0

    ack = handle_command(
        state,
        {"command_id": "CMD_3", "action": "set_reporting_interval", "parameters": {"seconds": -1}},
    )
    assert ack["status"] == "failed"

    ack = handle_command(state, {"command_id": "CMD_4", "action": "restart_device"})
    snapshot = state.snapshot()
    assert ack["status"] == "applied"
    assert not snapshot["mqtt_timeout"]
    assert not snapshot["wifi_weak"]
    assert snapshot["uptime"] == 0

    ack = handle_command(
        state,
        {"command_id": "CMD_5", "action": "update_firmware", "parameters": {"version": "1.3.0"}},
    )
    assert ack["status"] == "applied"
    assert state.snapshot()["firmware_version"] == "1.3.0"

    ack = handle_command(state, {"command_id": "CMD_6", "action": "no_such_action"})
    assert ack["status"] == "failed"

    ack = handle_command(state, {"action": "restart_device"})
    assert ack["status"] == "failed"


def test_simulator_ack_payload_is_json_serializable() -> None:
    state = DeviceState("normal", 5.0)
    ack = handle_command(state, {"command_id": "CMD_X", "action": "calibrate_sensor"})
    # 确保回执可以直接作为 MQTT JSON 载荷
    assert json.loads(json.dumps(ack, ensure_ascii=False))["status"] == "applied"


# ---------------------------------------------------------- 修复完成事件与案例关联

from iot_control import remediation_events  # noqa: E402


class FakeChannel:
    """捕获 publish 调用的假 MQTT 通道。"""

    def __init__(self):
        self.published: list[tuple[str, str]] = []

    def publish(self, topic: str, payload_json: str) -> bool:
        self.published.append((topic, payload_json))
        return True


def _finalize_command(repo: ControlRepository, **kwargs) -> dict:
    diagnosis_id = kwargs.pop("diagnosis_id", DIAGNOSIS_ID)
    command = repo.create_command(
        device_id="ESP32_06",
        action="restart_device",
        risk_level=actions.HIGH_RISK,
        diagnosis_id=diagnosis_id,
        **kwargs,
    )
    repo.mark_command_ack(command["command_id"], "applied", {"detail": "设备已重启"})
    repo.record_status_sample("ESP32_06", True)
    repo.finalize_watches(utc_now() + timedelta(seconds=120))
    return repo.get_command(command["command_id"])


def test_verify_success_queues_case_link(repo: ControlRepository) -> None:
    command = _finalize_command(repo)
    assert command["verify_status"] == "succeeded"
    assert command["case_status"] == "pending"


def test_failed_recovery_stays_unlinked(repo: ControlRepository) -> None:
    command = repo.create_command(
        device_id="ESP32_06",
        action="restart_device",
        risk_level=actions.HIGH_RISK,
        diagnosis_id=DIAGNOSIS_ID,
    )
    repo.mark_command_ack(command["command_id"], "applied", {})
    repo.record_log_sample("ESP32_06", "ERROR")
    repo.finalize_watches(utc_now() + timedelta(seconds=120))
    stored = repo.get_command(command["command_id"])
    assert stored["verify_status"] == "failed"
    assert stored["case_status"] is None


def test_case_link_confirmation_updates_command(repo: ControlRepository) -> None:
    command = _finalize_command(repo, diagnosis_id="DIA_20260912_DEADBEEF")
    repo.mark_case_archived(command["command_id"], "FAUTO0001")
    stored = repo.get_command(command["command_id"])
    assert stored["case_status"] == "archived"
    assert stored["case_id"] == "FAUTO0001"


def test_completed_event_payload_shape(repo: ControlRepository) -> None:
    command = _finalize_command(repo, diagnosis_id="DIA_20260912_DEADBEEF")
    event = remediation_events.completed_event(command)
    assert event["event"] == "completed"
    assert event["command_id"] == command["command_id"]
    assert event["device_id"] == "ESP32_06"
    assert event["action"] == "restart_device"
    assert event["verify_status"] == "succeeded"
    assert event["diagnosis_id"] == "DIA_20260912_DEADBEEF"
    assert event["ack"] == {"detail": "设备已重启"}


def test_publish_completed_events_uses_device_topic(
    repo: ControlRepository,
) -> None:
    command = repo.create_command(
        device_id="ESP32_07",
        action="reconnect_mqtt",
        risk_level=actions.LOW_RISK,
        diagnosis_id=DIAGNOSIS_ID,
    )
    repo.mark_command_ack(command["command_id"], "applied", {})
    repo.record_status_sample("ESP32_07", True)
    finalized = repo.finalize_watches(utc_now() + timedelta(seconds=120))
    channel = FakeChannel()
    published = remediation_events.publish_completed_events(channel, repo, finalized)
    assert published == [command["command_id"]]
    assert len(channel.published) == 1
    topic, payload = channel.published[0]
    assert topic == "iot/ESP32_07/remediation"
    assert '"event": "completed"' in payload


def test_proposal_diagnosis_id_flows_to_command_on_approval(
    repo: ControlRepository,
) -> None:
    proposal = repo.create_proposal(
        device_id="ESP32_06",
        action="restart_device",
        diagnosis_id="DIA_20260922_ABCDEF12",
    )
    decided, command = repo.decide_proposal(
        proposal["proposal_id"], "approved", "admin", 1, actions.risk_level
    )
    assert decided["diagnosis_id"] == "DIA_20260922_ABCDEF12"
    assert command["diagnosis_id"] == "DIA_20260922_ABCDEF12"
