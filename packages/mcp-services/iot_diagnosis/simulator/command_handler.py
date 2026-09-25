"""下行命令处理逻辑。"""

from __future__ import annotations

from datetime import datetime, timezone

from .models import DeviceState

SCENARIOS = (
    "normal",
    "mqtt_timeout",
    "wifi_weak",
    "sensor_error",
    "unstable",
    "memory_leak",
    "watchdog_reset",
)


def handle_command(state: DeviceState, payload: dict) -> dict:
    """处理一条下行命令，返回 cmd_ack 载荷。纯函数便于测试。"""
    command_id = payload.get("command_id", "")
    action = payload.get("action", "")
    parameters = payload.get("parameters") or {}

    def ack(status: str, detail: str) -> dict:
        return {
            "command_id": command_id,
            "status": status,
            "detail": detail,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def clear_network_faults() -> None:
        state.mqtt_timeout = False
        state.wifi_weak = False
        if state.unstable:
            # 重启/重连会立即终结 unstable 设备的离线片段
            state.offline = False
            state.offline_until = 0.0

    if not command_id or not action:
        return ack("failed", "command_id 与 action 不能为空")

    with state.lock:
        if action == "reconnect_mqtt":
            state.mqtt_timeout = False
            return ack("applied", "MQTT 已重新连接")
        if action == "reconnect_wifi":
            clear_network_faults()
            return ack("applied", "WiFi 已重新连接")
        if action == "calibrate_sensor":
            state.sensor_error = False
            return ack("applied", "传感器校准完成")
        if action == "set_reporting_interval":
            seconds = parameters.get("seconds")
            if not isinstance(seconds, int) or isinstance(seconds, bool) or seconds < 1:
                return ack("failed", "seconds 必须为正整数")
            state.interval = float(seconds)
            return ack("applied", f"上报间隔已调整为 {seconds} 秒")
        if action == "restart_device":
            clear_network_faults()
            state.sensor_error = False
            state.memory_leak = False
            state.watchdog_reset = False
            state.uptime = 0
            return ack("applied", "设备已重启")
        if action == "update_firmware":
            version = parameters.get("version")
            if not isinstance(version, str) or not version.strip():
                return ack("failed", "version 不能为空")
            clear_network_faults()
            state.sensor_error = False
            state.memory_leak = False
            state.watchdog_reset = False
            state.uptime = 0
            state.firmware_version = version.strip()
            return ack("applied", f"固件已升级到 {version.strip()}")
        if action == "inject_fault":
            scenario = parameters.get("scenario")
            if not isinstance(scenario, str) or scenario not in SCENARIOS:
                return ack("failed", f"scenario 必须是 {', '.join(SCENARIOS)} 之一")
            if scenario == "mqtt_timeout":
                state.mqtt_timeout = True
            elif scenario == "wifi_weak":
                state.wifi_weak = True
            elif scenario == "sensor_error":
                state.sensor_error = True
            elif scenario == "memory_leak":
                state.memory_leak = True
            elif scenario == "watchdog_reset":
                state.watchdog_reset = True
                # 看门狗反复触发重启，uptime 停留在低位且不再累积
                state.uptime = 600
            elif scenario == "unstable":
                state.unstable = True
                state.offline = False
                state.offline_until = 0.0
            else:  # normal：清除全部故障标志，恢复健康上报
                state.mqtt_timeout = False
                state.wifi_weak = False
                state.sensor_error = False
                state.unstable = False
                state.memory_leak = False
                state.watchdog_reset = False
                state.offline = False
                state.offline_until = 0.0
            return ack("applied", f"已注入故障场景 {scenario}")
        return ack("failed", f"不支持的动作: {action}")
