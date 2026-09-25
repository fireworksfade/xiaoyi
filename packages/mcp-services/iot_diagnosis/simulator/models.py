"""设备模拟器的数据模型：设备画像与状态。"""

from __future__ import annotations

import threading
from dataclasses import dataclass


@dataclass(frozen=True)
class DeviceProfile:
    """一台模拟设备的静态画像：命名、场景、遥测基线与上报节奏。"""

    device_id: str
    name: str = ""
    scenario: str = "normal"
    interval: float = 10.0
    firmware_version: str = "1.2.0"
    temperature_base: float = 26.0
    rssi_base: int = -55
    info_log_every: float = 300.0

    @property
    def display_name(self) -> str:
        return self.name or self.device_id


class DeviceState:
    """模拟设备的可变状态：场景故障标志、上报间隔与固件版本，可被下行命令修改。"""

    def __init__(self, scenario: str, interval: float, firmware_version: str = "1.2.0"):
        self.lock = threading.Lock()
        self.mqtt_timeout = scenario == "mqtt_timeout"
        self.wifi_weak = scenario == "wifi_weak"
        self.sensor_error = scenario == "sensor_error"
        self.unstable = scenario == "unstable"
        self.memory_leak = scenario == "memory_leak"
        self.watchdog_reset = scenario == "watchdog_reset"
        self.interval = interval
        self.firmware_version = firmware_version
        self.uptime = 86400
        # unstable 场景的离线片段：offline 为 True 时设备停止上报，直到片段结束或被命令修复
        self.offline = False
        self.offline_until = 0.0
        self.next_info_log_at = 0.0

    def snapshot(self) -> dict:
        with self.lock:
            return {
                "mqtt_timeout": self.mqtt_timeout,
                "wifi_weak": self.wifi_weak,
                "sensor_error": self.sensor_error,
                "unstable": self.unstable,
                "memory_leak": self.memory_leak,
                "watchdog_reset": self.watchdog_reset,
                "interval": self.interval,
                "firmware_version": self.firmware_version,
                "uptime": self.uptime,
                "offline": self.offline,
                "offline_until": self.offline_until,
                "next_info_log_at": self.next_info_log_at,
            }
