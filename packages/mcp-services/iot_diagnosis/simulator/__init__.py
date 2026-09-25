"""ESP32 设备模拟器，支持单设备与机群两种模式。

- 单设备模式（向后兼容）：
  ``python -m iot_diagnosis.simulator --device-id ESP32_05 --scenario mqtt_timeout``
- 机群模式：一个进程内以线程模拟整个 ESP32 机群，拓扑见 ``fleet.json``：
  ``python -m iot_diagnosis.simulator --host mqtt --fleet iot_diagnosis/fleet.json``

每台设备独立 MQTT 连接（client_id、遗嘱、命令订阅互不干扰），遥测数据按
设备画像生成：各自的部署位置命名、温度/RSSI 基线、固件版本与上报间隔。
"""

from .models import DeviceProfile, DeviceState
from .command_handler import handle_command, SCENARIOS
from .telemetry import current_status, build_cycle
from .fleet_loader import load_fleet
from .device_simulator import DeviceSimulator

__all__ = [
    "DeviceProfile",
    "DeviceState",
    "handle_command",
    "SCENARIOS",
    "current_status",
    "build_cycle",
    "load_fleet",
    "DeviceSimulator",
]
