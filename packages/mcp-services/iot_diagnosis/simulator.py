"""ESP32 设备模拟器 - 向后兼容导入层。

此文件保持向后兼容性，所有功能已迁移到 simulator/ 包。
旧代码可以继续使用：
    from iot_diagnosis.simulator import DeviceSimulator, load_fleet
    python -m iot_diagnosis.simulator --fleet fleet.json
"""

from .simulator import (
    SCENARIOS,
    DeviceProfile,
    DeviceSimulator,
    DeviceState,
    build_cycle,
    current_status,
    handle_command,
    load_fleet,
)

__all__ = [
    "SCENARIOS",
    "DeviceProfile",
    "DeviceSimulator",
    "DeviceState",
    "build_cycle",
    "current_status",
    "handle_command",
    "load_fleet",
]
