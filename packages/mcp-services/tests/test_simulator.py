"""机群模拟器的单元测试：fleet 解析校验、拟真遥测与 unstable 离线片段状态机。"""

from __future__ import annotations

import json

import pytest

from iot_diagnosis.simulator import (
    UNSTABLE_GRACE_SECONDS,
    DeviceProfile,
    DeviceState,
    build_cycle,
    current_status,
    handle_command,
    load_fleet,
)

FLEET_PATH = "iot_diagnosis/fleet.json"


class FakeRng:
    """确定性随机源：random() 返回预设序列，其余方法返回区间端点内的固定值。"""

    def __init__(self, random_values: list[float] | None = None):
        self.random_values = list(random_values or [])
        self.choice_calls = 0

    def random(self) -> float:
        if not self.random_values:
            return 1.0  # 默认永不触发概率事件
        return self.random_values.pop(0)

    def randint(self, low: int, high: int) -> int:
        return low

    def uniform(self, low: float, high: float) -> float:
        return low

    def choice(self, seq):
        self.choice_calls += 1
        return seq[0]


def _suffixes(messages: list[tuple[str, dict]]) -> list[str]:
    return [suffix for suffix, _ in messages]


def _profile(**overrides) -> DeviceProfile:
    fields = {
        "device_id": "ESP32_01",
        "name": "车间A-环境监测01",
        "scenario": "normal",
        "interval": 10.0,
        "firmware_version": "1.2.0",
        "temperature_base": 26.0,
        "rssi_base": -55,
        "info_log_every": 300.0,
    }
    fields.update(overrides)
    return DeviceProfile(**fields)


def test_load_fleet_builds_twelve_profiles() -> None:
    profiles = load_fleet(FLEET_PATH)

    assert len(profiles) == 12
    assert len({p.device_id for p in profiles}) == 12
    by_id = {p.device_id: p for p in profiles}
    # 与既有种子/评测脚本兼容：ESP32_05 保持 mqtt_timeout，ESP32_06 保持 wifi_weak
    assert by_id["ESP32_05"].scenario == "mqtt_timeout"
    assert by_id["ESP32_06"].scenario == "wifi_weak"
    assert by_id["ESP32_10"].scenario == "unstable"
    assert by_id["ESP32_09"].scenario == "sensor_error"
    for profile in profiles:
        assert profile.display_name != profile.device_id, "机群设备应带友好名称"
        assert profile.interval > 0
        assert profile.temperature_base < 70


def test_load_fleet_rejects_duplicate_device_id(tmp_path) -> None:
    config = {
        "devices": [
            {"device_id": "ESP32_01", "scenario": "normal"},
            {"device_id": "ESP32_01", "scenario": "normal"},
        ]
    }
    path = tmp_path / "fleet.json"
    path.write_text(json.dumps(config), encoding="utf-8")

    with pytest.raises(ValueError, match="重复"):
        load_fleet(path)


def test_load_fleet_rejects_invalid_scenario(tmp_path) -> None:
    config = {"devices": [{"device_id": "ESP32_01", "scenario": "on_fire"}]}
    path = tmp_path / "fleet.json"
    path.write_text(json.dumps(config), encoding="utf-8")

    with pytest.raises(ValueError, match="场景非法"):
        load_fleet(path)


def test_load_fleet_rejects_hot_normal_baseline(tmp_path) -> None:
    config = {
        "devices": [{"device_id": "ESP32_01", "scenario": "normal", "temperature_base": 85.0}]
    }
    path = tmp_path / "fleet.json"
    path.write_text(json.dumps(config), encoding="utf-8")

    with pytest.raises(ValueError, match="temperature_base"):
        load_fleet(path)


def test_current_status_reports_profile_identity() -> None:
    state = DeviceState("normal", 10.0)
    profile = _profile()

    status = current_status(state, "2026-01-01T00:00:00+00:00", profile=profile, rng=FakeRng())

    assert status["name"] == "车间A-环境监测01"
    assert status["device_type"] == "ESP32"
    assert status["firmware_version"] == "1.2.0"
    assert status["online"] is True
    assert status["wifi_status"] == "connected"
    assert status["mqtt_status"] == "connected"
    # 温度围绕画像基线 ±1 °C 抖动，RSSI 围绕基线 -4..+4 抖动
    assert 25.0 <= status["temperature"] <= 27.0
    assert -59 <= status["rssi"] <= -51


def test_current_status_fault_scenarios() -> None:
    weak = current_status(
        DeviceState("wifi_weak", 5.0), profile=_profile(scenario="wifi_weak"), rng=FakeRng()
    )
    stuck = current_status(
        DeviceState("sensor_error", 5.0), profile=_profile(scenario="sensor_error"), rng=FakeRng()
    )
    timeout = current_status(
        DeviceState("mqtt_timeout", 5.0), profile=_profile(scenario="mqtt_timeout"), rng=FakeRng()
    )

    assert weak["rssi"] == -82
    assert stuck["temperature"] == 78.0
    assert timeout["mqtt_status"] == "disconnected"


def test_normal_cycle_publishes_status_telemetry_heartbeat() -> None:
    state = DeviceState("normal", 10.0)
    profile = _profile()

    messages = build_cycle(state, profile, FakeRng(), elapsed=60.0, timestamp="t1")

    assert _suffixes(messages) == ["status", "telemetry", "heartbeat"]
    status = messages[0][1]
    assert status["name"] == "车间A-环境监测01"
    heartbeat = messages[2][1]
    assert heartbeat["online"] is True


def test_periodic_info_log_fires_once_per_window() -> None:
    state = DeviceState("normal", 10.0)
    profile = _profile()

    first = build_cycle(state, profile, FakeRng(), elapsed=301.0, timestamp="t1")
    second = build_cycle(state, profile, FakeRng(), elapsed=305.0, timestamp="t2")
    third = build_cycle(state, profile, FakeRng(), elapsed=610.0, timestamp="t3")

    assert "logs" in _suffixes(first)
    info_log = next(payload for suffix, payload in first if suffix == "logs")
    assert info_log["level"] == "INFO"
    assert info_log["module"] == "runtime"
    assert "logs" not in _suffixes(second)
    assert "logs" in _suffixes(third)


def test_unstable_offline_episode_round_trip() -> None:
    state = DeviceState("unstable", 10.0)
    profile = _profile(scenario="unstable")
    # random()=0.0 必然触发掉线；uniform 取下界 → 片段时长 60 秒
    rng = FakeRng(random_values=[0.0])

    before_grace = build_cycle(state, profile, rng, elapsed=30.0, timestamp="t0")
    assert _suffixes(before_grace) == ["status", "telemetry", "heartbeat"], "保护期内不应掉线"

    entering = build_cycle(state, profile, rng, elapsed=UNSTABLE_GRACE_SECONDS + 10, timestamp="t1")
    assert _suffixes(entering) == ["logs", "status"]
    assert entering[0][1]["level"] == "WARNING"
    assert entering[1][1]["online"] is False
    assert entering[1][1]["wifi_status"] == "disconnected"
    assert state.offline is True

    silent = build_cycle(
        state, profile, FakeRng(), elapsed=UNSTABLE_GRACE_SECONDS + 40, timestamp="t2"
    )
    assert silent == [], "离线片段中设备应完全静默"

    recovered = build_cycle(
        state, profile, FakeRng(), elapsed=UNSTABLE_GRACE_SECONDS + 80, timestamp="t3"
    )
    assert _suffixes(recovered) == ["logs", "status", "telemetry", "heartbeat"]
    assert recovered[0][1]["level"] == "INFO"
    assert recovered[1][1]["online"] is True
    assert state.offline is False

    steady = build_cycle(
        state, profile, FakeRng(), elapsed=UNSTABLE_GRACE_SECONDS + 90, timestamp="t4"
    )
    assert _suffixes(steady) == ["status", "telemetry", "heartbeat"], "恢复后回到常态上报"


def test_unstable_recovered_by_reconnect_wifi() -> None:
    state = DeviceState("unstable", 10.0)
    profile = _profile(scenario="unstable")
    rng = FakeRng(random_values=[0.0])
    build_cycle(state, profile, rng, elapsed=UNSTABLE_GRACE_SECONDS + 10, timestamp="t1")
    assert state.offline is True

    ack = handle_command(state, {"command_id": "CMD_1", "action": "reconnect_wifi"})

    assert ack["status"] == "applied"
    assert state.offline is False
    status = current_status(state, profile=profile, rng=FakeRng())
    assert status["online"] is True


def test_inject_fault_sets_flags_and_clears_with_normal() -> None:
    state = DeviceState("normal", 10.0)
    profile = _profile()

    ack = handle_command(
        state,
        {
            "command_id": "CMD_I1",
            "action": "inject_fault",
            "parameters": {"scenario": "mqtt_timeout"},
        },
    )
    assert ack["status"] == "applied"
    assert state.mqtt_timeout is True
    assert current_status(state, profile=profile, rng=FakeRng())["mqtt_status"] == "disconnected"

    handle_command(
        state,
        {
            "command_id": "CMD_I2",
            "action": "inject_fault",
            "parameters": {"scenario": "sensor_error"},
        },
    )
    assert state.sensor_error is True
    assert current_status(state, profile=profile, rng=FakeRng())["temperature"] == 78.0

    recovered = handle_command(
        state,
        {"command_id": "CMD_I3", "action": "inject_fault", "parameters": {"scenario": "normal"}},
    )
    assert recovered["status"] == "applied"
    assert state.mqtt_timeout is False and state.sensor_error is False
    status = current_status(state, profile=profile, rng=FakeRng())
    assert status["mqtt_status"] == "connected" and status["temperature"] != 78.0


def test_inject_fault_unstable_then_reconnect_wifi_clears() -> None:
    state = DeviceState("normal", 10.0)
    profile = _profile()

    ack = handle_command(
        state,
        {"command_id": "CMD_I4", "action": "inject_fault", "parameters": {"scenario": "unstable"}},
    )
    assert ack["status"] == "applied"
    assert state.unstable is True

    handle_command(state, {"command_id": "CMD_I5", "action": "reconnect_wifi"})

    # reconnect_wifi 终结离线片段；unstable 是持久场景标志，由 inject normal 清除
    assert state.offline is False
    status = current_status(state, profile=profile, rng=FakeRng())
    assert status["online"] is True


def test_inject_fault_rejects_unknown_scenario() -> None:
    state = DeviceState("normal", 10.0)

    ack = handle_command(
        state,
        {"command_id": "CMD_I6", "action": "inject_fault", "parameters": {"scenario": "on_fire"}},
    )
    assert ack["status"] == "failed"

    missing = handle_command(state, {"command_id": "CMD_I7", "action": "inject_fault"})
    assert missing["status"] == "failed"


def test_inject_fault_memory_leak_publishes_oom_logs_and_restart_clears() -> None:
    state = DeviceState("normal", 10.0)
    profile = _profile()

    ack = handle_command(
        state,
        {
            "command_id": "CMD_I8",
            "action": "inject_fault",
            "parameters": {"scenario": "memory_leak"},
        },
    )
    assert ack["status"] == "applied"
    assert state.memory_leak is True

    # random()=0.0 触发 35% 概率的 OOM 错误日志
    cycle = build_cycle(state, profile, FakeRng(random_values=[0.0]), elapsed=10.0, timestamp="t")
    suffixes = _suffixes(cycle)
    assert "logs" in suffixes and "fault" in suffixes
    heap_log = next(p for s, p in cycle if s == "logs")
    assert heap_log["module"] == "heap" and "heap" in heap_log["message"]
    oom_fault = next(p for s, p in cycle if s == "fault")
    assert oom_fault["fault_type"] == "out_of_memory"

    handle_command(state, {"command_id": "CMD_I9", "action": "restart_device"})
    assert state.memory_leak is False


def test_inject_fault_watchdog_resets_uptime_and_firmware_clears() -> None:
    state = DeviceState("normal", 10.0)
    profile = _profile()

    ack = handle_command(
        state,
        {
            "command_id": "CMD_I10",
            "action": "inject_fault",
            "parameters": {"scenario": "watchdog_reset"},
        },
    )
    assert ack["status"] == "applied"
    assert state.watchdog_reset is True and state.uptime == 600

    cycle = build_cycle(state, profile, FakeRng(), elapsed=10.0, timestamp="t")
    fault = next(p for s, p in cycle if s == "fault")
    assert "watchdog" in fault["message"]
    logs = [p for s, p in cycle if s == "logs"]
    assert any(item["level"] == "CRITICAL" for item in logs)

    handle_command(
        state,
        {"command_id": "CMD_I11", "action": "update_firmware", "parameters": {"version": "1.3.1"}},
    )
    assert state.watchdog_reset is False
