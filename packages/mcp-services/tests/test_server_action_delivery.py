"""Unified MCP tools use the MQTT client created by the service lifecycle."""

import pytest

from iot_control.repository import ControlRepository
from iot_mcp import server

DIAGNOSIS_ID = "DIA_20260922_DEADBEEF"


@pytest.fixture
def control(tmp_path, monkeypatch):
    repository = ControlRepository(str(tmp_path / "control.db"))
    monkeypatch.setattr(server, "control_repository", repository)
    monkeypatch.setattr(server.diagnosis_repository, "get_diagnosis_trace",
                        lambda _id: {"device_id": "D1"})
    monkeypatch.setattr(server.diagnosis_repository, "get_device_status",
                        lambda _id: {"device_id": "D1", "device_type": "ESP32", "uptime": 1000})
    monkeypatch.setattr(server, "control_mqtt", None)
    return repository


def test_action_and_approved_proposal_use_service_mqtt(control, monkeypatch):
    sent = []

    class FakeMQTT:
        def send_command(self, device_id, command):
            sent.append((device_id, command["command_id"]))
            return "broker_confirmed"

    monkeypatch.setattr(server, "control_mqtt", FakeMQTT())

    direct = server.execute_device_action("D1", "reconnect_mqtt", "test", "DIA_20260922_DEADBEEF", correlation_key="K1")
    assert direct["ok"] is True and direct["data"]["delivered"] is True

    proposed = server.create_remediation_proposal("D1", "restart_device", "test", "reboot",
                                                 DIAGNOSIS_ID, correlation_key="K2")
    approved = server.decide_remediation_proposal(proposed["data"]["proposal_id"], "approved", "admin", 1)
    assert approved["ok"] is True and approved["data"]["delivered"] is True
    assert sent == [("D1", direct["data"]["command_id"]),
                    ("D1", approved["data"]["command"]["command_id"])]
    assert control.get_action_by_correlation("K2")["delivery_status"] == "delivered"


def test_offline_approval_returns_committed_state_and_recovers(control):
    proposed = server.create_remediation_proposal("D1", "restart_device", "test", "reboot",
                                                 DIAGNOSIS_ID)
    approved = server.decide_remediation_proposal(proposed["data"]["proposal_id"], "approved", "admin", 1)
    assert approved["ok"]
    data = approved["data"]
    assert data["status"] == "approved" and data["delivered"] is False
    assert data["command"]["delivery_status"] == "pending"
    sent = []
    restarted = ControlRepository(control.path)
    restarted.dispatch_pending(lambda device, command: sent.append(command["command_id"]) or "broker_confirmed")
    assert sent == [data["command"]["command_id"]]
    assert restarted.get_command(sent[0])["delivery_status"] == "broker_confirmed"


def test_action_replay_and_conflict_are_structured(control):
    first = server.execute_device_action("D1", "reconnect_mqtt", "test", DIAGNOSIS_ID, correlation_key="K1")
    replay = server.execute_device_action("D1", "reconnect_mqtt", "test", DIAGNOSIS_ID, correlation_key="K1")
    assert replay["ok"] and replay["data"]["command_id"] == first["data"]["command_id"]
    conflict = server.execute_device_action("D1", "reconnect_wifi", "test", DIAGNOSIS_ID, correlation_key="K1")
    assert conflict["error"]["code"] == "ACTION_CORRELATION_CONFLICT"
    assert conflict["error"]["retryable"] is False
    server.create_remediation_proposal("D1", "restart_device", "test", "reboot", DIAGNOSIS_ID, correlation_key="K2")
    conflict = server.create_remediation_proposal("D1", "restart_device", "changed", "reboot", DIAGNOSIS_ID, correlation_key="K2")
    assert conflict["error"]["code"] == "ACTION_CORRELATION_CONFLICT"


def test_device_catalog_filters_protocol_and_exposes_acceptance(control, monkeypatch):
    catalog = server.list_device_actions("D1")["data"]["actions"]
    assert all(item["acceptance_criteria"] and item["parameter_schema"] for item in catalog)
    monkeypatch.setattr(server.diagnosis_repository, "get_device_status",
                        lambda _id: {"device_type": "OTHER"})
    assert server.list_device_actions("D1")["data"]["actions"] == []
    result = server.execute_device_action("D1", "reconnect_mqtt", "test", DIAGNOSIS_ID)
    assert result["error"]["code"] == "ACTION_NOT_SUPPORTED_BY_DEVICE"
