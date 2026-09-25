"""诊断侧修复事件处理测试：案例组装、诊断关联与确认回发。"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from iot_diagnosis.mqtt import MQTTIngestor
from iot_diagnosis.remediation import build_case_payload, handle_remediation_event
from iot_diagnosis.repository import DiagnosisRepository, iso

DIAGNOSIS_RESULT = {
    "diagnosis_id": "DIA_20260912_DEADBEEF",
    "request_id": "req-1",
    "device_id": "ESP32_06",
    "query": "ESP32_06 WiFi 信号很弱",
    "fault_type": "wifi_connection",
    "fault_name": "WiFi 弱信号",
    "cause": "RSSI 长期低于阈值",
    "confidence": 0.87,
    "evidence": ["RSSI=-82 dBm", "mqtt_status=connected"],
    "severity": "medium",
    "solutions": ["重启设备"],
    "route": {"router": "rule", "selected_sources": []},
    "sources": [],
    "trace_contexts": [],
    "observability": {
        "retrieval_count": 0,
        "rerank_count": 0,
        "retrieval_latency_ms": 0,
        "llm_latency_ms": 0,
        "total_latency_ms": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "error": None,
    },
}


@pytest.fixture()
def repo(tmp_path) -> DiagnosisRepository:
    return DiagnosisRepository(str(tmp_path / "iot_diagnosis.db"))


def _seed_diagnosis(
    repo: DiagnosisRepository,
    device_id: str = "ESP32_06",
    diagnosis_id: str = "DIA_20260912_DEADBEEF",
) -> None:
    repo.save_diagnosis({**DIAGNOSIS_RESULT, "device_id": device_id, "diagnosis_id": diagnosis_id})


def _completed_event(**overrides) -> dict:
    event = {
        "event": "completed",
        "command_id": "CMD_20260912_ABCD1234",
        "proposal_id": None,
        "device_id": "ESP32_06",
        "action": "restart_device",
        "parameters": {},
        "reason": "WiFi 弱信号",
        "status": "applied",
        "verify_status": "succeeded",
        "ack": {"detail": "设备已重启"},
        "diagnosis_id": "DIA_20260912_DEADBEEF",
    }
    event.update(overrides)
    return event


def test_build_case_payload_maps_diagnosis_fields() -> None:
    case = build_case_payload(_completed_event(), DIAGNOSIS_RESULT)
    assert case["device_id"] == "ESP32_06"
    assert case["fault_type"] == "wifi_connection"
    assert case["fault_name"] == "WiFi 弱信号"
    assert case["symptoms"] == ["RSSI=-82 dBm", "mqtt_status=connected"]
    assert case["verified"] is True
    assert case["verified_by"] == "auto-remediation:CMD_20260912_ABCD1234"
    assert "CMD_20260912_ABCD1234" in case["solution"]
    assert "恢复验证通过" in case["solution"]


def test_build_case_payload_includes_parameters_and_falls_back() -> None:
    event = _completed_event(action="set_reporting_interval", parameters={"seconds": 10}, ack={})
    trace = {**DIAGNOSIS_RESULT, "evidence": [], "cause": ""}
    case = build_case_payload(event, trace)
    assert "set_reporting_interval（seconds=10）" in case["solution"]
    assert case["symptoms"] == [DIAGNOSIS_RESULT["query"]]
    assert case["cause"] == "根因信息缺失"


def test_event_with_diagnosis_id_writes_case(repo: DiagnosisRepository) -> None:
    _seed_diagnosis(repo)
    confirmation = handle_remediation_event(repo, "ESP32_06", _completed_event())
    assert confirmation is not None
    assert confirmation["command_id"] == "CMD_20260912_ABCD1234"
    assert confirmation["device_id"] == "ESP32_06"
    assert confirmation["case_id"].startswith("F")
    # 案例已写入案例库
    cases = repo.fault_cases(device_type="ESP32")
    assert any(item["fault_id"] == confirmation["case_id"] for item in cases)


def test_event_without_diagnosis_id_is_rejected(repo: DiagnosisRepository) -> None:
    _seed_diagnosis(repo, diagnosis_id="DIA_LATEST")
    event = _completed_event(diagnosis_id=None)
    confirmation = handle_remediation_event(repo, "ESP32_06", event)
    assert confirmation is None


def test_event_with_wrong_device_diagnosis_is_rejected(repo: DiagnosisRepository) -> None:
    _seed_diagnosis(repo)
    confirmation = handle_remediation_event(repo, "ESP32_99", _completed_event())
    assert confirmation is None


def test_event_without_recent_diagnosis_returns_none(repo: DiagnosisRepository) -> None:
    confirmation = handle_remediation_event(repo, "ESP32_06", _completed_event())
    assert confirmation is None


def test_failed_or_invalid_events_are_ignored(repo: DiagnosisRepository) -> None:
    _seed_diagnosis(repo)
    assert (
        handle_remediation_event(repo, "ESP32_06", _completed_event(verify_status="failed")) is None
    )
    assert handle_remediation_event(repo, "ESP32_06", {"verify_status": "succeeded"}) is None


def test_mqtt_remediation_event_publishes_confirmation(
    repo: DiagnosisRepository, monkeypatch
) -> None:
    _seed_diagnosis(repo)
    published: list[tuple[str, str]] = []

    ingestor = MQTTIngestor(repo)
    monkeypatch.setattr(
        ingestor.client,
        "publish",
        lambda topic, payload, qos=0: published.append((topic, payload)) or SimpleNamespace(rc=0),
    )
    ingestor._on_message(
        None,
        None,
        SimpleNamespace(
            topic="iot/ESP32_06/remediation",
            payload=json.dumps(_completed_event()).encode("utf-8"),
        ),
    )
    assert len(published) == 1
    topic, payload = published[0]
    assert topic == "iot/ESP32_06/remediation_case"
    body = json.loads(payload)
    assert body["command_id"] == "CMD_20260912_ABCD1234"
    assert body["case_id"].startswith("F")


def test_mqtt_case_link_event_is_ignored_by_diagnosis(repo: DiagnosisRepository) -> None:
    # diagnosis 不订阅 remediation_case；此处确认未知 kind 不抛错
    ingestor = MQTTIngestor(repo)
    ingestor._on_message(
        None,
        None,
        SimpleNamespace(
            topic="iot/ESP32_06/unknown_kind",
            payload=json.dumps({"foo": "bar"}).encode("utf-8"),
        ),
    )
    assert iso()  # 仅为可读性；未抛异常即通过
