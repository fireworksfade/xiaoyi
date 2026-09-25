"""设备状态生命周期测试（specs WP-06 / §6.1–6.6）。

覆盖：status/telemetry/heartbeat 分流、遥测去重、心跳先于状态、
元数据更新规则、设备时钟漂移与非法时间。
"""

from datetime import datetime, timedelta, timezone

from iot_diagnosis.repository import DiagnosisRepository


def _repo(tmp_path) -> DiagnosisRepository:
    return DiagnosisRepository(str(tmp_path / "devices.db"), offline_after_seconds=30)


def test_status_telemetry_heartbeat_routes_are_separated(tmp_path) -> None:
    repo = _repo(tmp_path)
    received = datetime.now(timezone.utc).isoformat()
    repo.apply_status(
        "ESP32_A",
        {
            "online": True,
            "wifi_status": "connected",
            "mqtt_status": "connected",
            "rssi": -50,
            "temperature": 25.0,
            "uptime": 100,
        },
        received,
    )
    for i in range(5):
        repo.append_telemetry(
            "ESP32_A",
            {"temperature": 25.0 + i, "rssi": -50 - i},
            received,
        )
    repo.touch_heartbeat("ESP32_A", {"uptime": 160}, received)

    with repo._connect() as db:
        state_rows = db.execute(
            "SELECT COUNT(*) FROM device_current_state WHERE device_id = 'ESP32_A'"
        ).fetchone()[0]
        telemetry_rows = db.execute(
            "SELECT COUNT(*) FROM device_telemetry WHERE device_id = 'ESP32_A'"
        ).fetchone()[0]
    assert state_rows == 1  # current state 每设备一行
    assert telemetry_rows == 5  # heartbeat 不产生历史行
    status = repo.get_device_status("ESP32_A")
    assert status["uptime"] == 160
    assert status["temperature"] == 29.0  # 最后一条遥测合并进 current state
    assert status["last_event_kind"] == "heartbeat"


def test_identical_telemetry_is_deduplicated(tmp_path) -> None:
    repo = _repo(tmp_path)
    received = datetime.now(timezone.utc).isoformat()
    device_time = "2026-09-14T08:00:00+00:00"
    payload = {"temperature": 25.0, "rssi": -50}
    for _ in range(3):
        repo.append_telemetry("ESP32_B", {**payload, "timestamp": device_time}, received)
    with repo._connect() as db:
        count = db.execute("SELECT COUNT(*) FROM device_telemetry").fetchone()[0]
    assert count == 1  # 同设备 + 同时间 + 同载荷只保留一条


def test_heartbeat_before_status_for_new_device(tmp_path) -> None:
    repo = _repo(tmp_path)
    received = datetime.now(timezone.utc).isoformat()
    repo.touch_heartbeat("ESP32_C", {}, received)
    status = repo.get_device_status("ESP32_C")
    assert status is not None
    assert status["online"] is True
    assert status["last_event_kind"] == "heartbeat"

    repo.apply_status(
        "ESP32_C",
        {"online": True, "wifi_status": "connected", "temperature": 21.0},
        received,
    )
    status = repo.get_device_status("ESP32_C")
    assert status["wifi_status"] == "connected"
    assert status["temperature"] == 21.0


def test_firmware_and_name_metadata_updates(tmp_path) -> None:
    repo = _repo(tmp_path)
    received = datetime.now(timezone.utc).isoformat()
    repo.apply_status(
        "ESP32_D",
        {"online": True, "name": "节点 D", "device_type": "ESP32", "firmware_version": "1.1.4"},
        received,
    )
    assert repo.get_device_status("ESP32_D")["firmware_version"] == "1.1.4"

    # 固件升级后的下一帧状态立即可见
    repo.apply_status(
        "ESP32_D",
        {"online": True, "firmware_version": "1.2.0"},
        received,
    )
    assert repo.get_device_status("ESP32_D")["firmware_version"] == "1.2.0"

    with repo._connect() as db:
        updated_at = db.execute(
            "SELECT updated_at FROM device WHERE device_id = 'ESP32_D'"
        ).fetchone()[0]
    assert updated_at is not None


def test_empty_and_unknown_fields_do_not_regress_metadata(tmp_path) -> None:
    repo = _repo(tmp_path)
    received = datetime.now(timezone.utc).isoformat()
    repo.apply_status(
        "ESP32_E", {"online": True, "name": "节点 E", "firmware_version": "1.1.4"}, received
    )
    # 缺失字段不覆盖
    repo.apply_status("ESP32_E", {"online": True}, received)
    assert repo.get_device_status("ESP32_E")["name"] == "节点 E"
    # unknown 不覆盖已有非 unknown 值
    repo.apply_status(
        "ESP32_E", {"online": True, "name": "unknown", "firmware_version": "unknown"}, received
    )
    status = repo.get_device_status("ESP32_E")
    assert status["name"] == "节点 E"
    assert status["firmware_version"] == "1.1.4"
    # 真实值可以覆盖 unknown（新设备首帧 unknown 后更名）
    repo.apply_status("ESP32_F", {"online": True, "name": "unknown"}, received)
    repo.apply_status("ESP32_F", {"online": True, "name": "正式名称"}, received)
    assert repo.get_device_status("ESP32_F")["name"] == "正式名称"


def test_device_clock_drift_does_not_break_online_state(tmp_path) -> None:
    repo = _repo(tmp_path)
    now = datetime.now(timezone.utc)
    # 设备时钟快 24 小时
    repo.apply_status(
        "ESP32_G",
        {"online": True, "timestamp": (now + timedelta(hours=24)).isoformat()},
        now.isoformat(),
    )
    # 设备时钟慢 24 小时
    repo.apply_status(
        "ESP32_H",
        {"online": True, "timestamp": (now - timedelta(hours=24)).isoformat()},
        now.isoformat(),
    )
    for device_id in ("ESP32_G", "ESP32_H"):
        status = repo.get_device_status(device_id)
        assert status["online"] is True, device_id
        assert status["heartbeat_fresh"] is True, device_id


def test_invalid_device_timestamp_keeps_device_online(tmp_path) -> None:
    repo = _repo(tmp_path)
    now = datetime.now(timezone.utc).isoformat()
    repo.apply_status("ESP32_I", {"online": True, "timestamp": "not-a-timestamp"}, now)
    status = repo.get_device_status("ESP32_I")
    assert status["online"] is True


def test_stale_received_at_marks_device_offline(tmp_path) -> None:
    repo = _repo(tmp_path)
    stale = (datetime.now(timezone.utc) - timedelta(seconds=60)).isoformat()
    repo.apply_status("ESP32_J", {"online": True}, stale)
    status = repo.get_device_status("ESP32_J")
    assert status["online"] is False
    assert status["reported_online"] is True
    assert status["heartbeat_fresh"] is False
