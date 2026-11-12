"""Action-specific acceptance criteria. Missing evidence is inconclusive."""

import math
from typing import Any, TypeGuard

ACCEPTANCE_CRITERIA = {
    "reconnect_mqtt": "新状态 online=true 且 mqtt_status=connected",
    "reconnect_wifi": "新状态 online=true、wifi_status=connected 且 RSSI≥-75 dBm",
    "calibrate_sensor": "新状态 sensor_valid=true、sensor_calibrated=true 且温度读数有效",
    "set_reporting_interval": "新状态 reporting_interval_seconds 等于目标 seconds",
    "set_mqtt_keepalive": "新状态 online=true、mqtt_status=connected 且 mqtt_keepalive_seconds 等于目标 seconds",
    "restart_device": "新状态 online=true 且 uptime 低于执行前快照",
    "update_firmware": "新状态 online=true 且 firmware_version 等于目标 version",
    "rollback_firmware": "新状态 online=true 且 firmware_version 等于执行前快照中的 rollback_version",
}


def finite_number(value: Any) -> TypeGuard[int | float]:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def evaluate(action: str, parameters: dict, state: dict, baseline: dict) -> str:
    if state.get("online") is not True:
        return "inconclusive" if "online" not in state else "failed"
    if action == "reconnect_mqtt":
        value = state.get("mqtt_status")
        passed = value == "connected"
    elif action == "reconnect_wifi":
        value = state.get("rssi") if "wifi_status" in state else None
        if not finite_number(value):
            return "inconclusive"
        passed = state["wifi_status"] == "connected" and value >= -75
    elif action == "calibrate_sensor":
        if not finite_number(state.get("temperature")):
            return "inconclusive"
        value = state.get("sensor_valid")
        if "sensor_calibrated" not in state:
            return "inconclusive"
        passed = value is True and state["sensor_calibrated"] is True
    elif action == "set_reporting_interval":
        value = state.get("reporting_interval_seconds")
        passed = finite_number(value) and value == parameters.get("seconds")
    elif action == "set_mqtt_keepalive":
        value = state.get("mqtt_keepalive_seconds")
        passed = (finite_number(value) and value == parameters.get("seconds")
                  and state.get("mqtt_status") == "connected")
    elif action == "restart_device":
        value = state.get("uptime")
        if not finite_number(value) or not finite_number(baseline.get("uptime")):
            return "inconclusive"
        passed = 0 <= value < baseline["uptime"]
    elif action == "update_firmware":
        value = state.get("firmware_version")
        passed = value == parameters.get("version")
    elif action == "rollback_firmware":
        target = baseline.get("rollback_version")
        if not target:
            return "inconclusive"
        value = state.get("firmware_version")
        passed = value == target
    else:
        return "inconclusive"
    if value is None:
        return "inconclusive"
    return "succeeded" if passed else "failed"
