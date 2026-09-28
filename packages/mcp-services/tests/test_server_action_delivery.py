"""Unified MCP tools use the MQTT client created by the service lifecycle."""

import importlib


def test_action_and_approved_proposal_use_service_mqtt(tmp_path, monkeypatch):
    monkeypatch.setenv("DIAGNOSIS_DATABASE_PATH", str(tmp_path / "diagnosis.db"))
    monkeypatch.setenv("CONTROL_DATABASE_PATH", str(tmp_path / "control.db"))
    server = importlib.import_module("iot_mcp.server")
    sent = []

    class FakeMQTT:
        def send_command(self, device_id, command):
            sent.append((device_id, command["command_id"]))
            return True

    monkeypatch.setattr(server, "control_mqtt", FakeMQTT())
    monkeypatch.setattr(server.diagnosis_repository, "get_diagnosis_trace", lambda _id: {"device_id": "D1"})
    monkeypatch.setattr(server.control_repository, "create_command", lambda **_kwargs: {"command_id": "C1"})
    monkeypatch.setattr(server.control_repository, "set_correlation_delivery", lambda *_args: None)

    direct = server.execute_device_action("D1", "reconnect_mqtt", "test", "DIA_20260922_DEADBEEF", correlation_key="K1")
    assert direct["ok"] is True and direct["data"]["delivered"] is True

    monkeypatch.setattr(server.control_repository, "get_proposal", lambda _id: {"device_id": "D1", "diagnosis_id": "DIA_20260922_DEADBEEF"})
    monkeypatch.setattr(server.control_repository, "decide_proposal", lambda *_args, **_kwargs: (
        {"proposal_id": "P1", "device_id": "D1"}, {"command_id": "C2"}
    ))
    approved = server.decide_remediation_proposal("P1", "approved", "admin", 1)
    assert approved["ok"] is True and approved["data"]["delivered"] is True
    assert sent == [("D1", "C1"), ("D1", "C2")]
