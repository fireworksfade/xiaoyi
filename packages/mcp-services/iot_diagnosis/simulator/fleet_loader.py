"""机群配置加载与验证。"""

from __future__ import annotations

import json
from pathlib import Path

from .command_handler import SCENARIOS
from .models import DeviceProfile


def load_fleet(path: str | Path) -> list[DeviceProfile]:
    """解析机群配置 JSON，校验 ID 唯一性与场景合法性。"""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    defaults = data.get("defaults") or {}
    devices = data.get("devices")
    if not isinstance(devices, list) or not devices:
        raise ValueError(f"机群配置 {path} 缺少非空的 devices 列表")

    profiles: list[DeviceProfile] = []
    seen: set[str] = set()
    for index, item in enumerate(devices):
        if not isinstance(item, dict):
            raise ValueError(f"机群配置第 {index + 1} 项必须是对象")
        device_id = str(item.get("device_id") or "").strip()
        if not device_id:
            raise ValueError(f"机群配置第 {index + 1} 项缺少 device_id")
        if device_id in seen:
            raise ValueError(f"机群配置中 device_id 重复: {device_id}")
        seen.add(device_id)

        merged: dict = {**defaults, **{k: v for k, v in item.items() if v is not None}}
        scenario = str(merged.get("scenario") or "normal")
        if scenario not in SCENARIOS:
            raise ValueError(f"设备 {device_id} 的场景非法: {scenario}")
        interval = float(merged.get("interval") or 10.0)
        if interval <= 0:
            raise ValueError(f"设备 {device_id} 的 interval 必须为正数")
        temperature_base = float(merged.get("temperature_base") or 26.0)
        if scenario != "sensor_error" and temperature_base >= 70:
            raise ValueError(
                f"设备 {device_id} 的 temperature_base({temperature_base}) ≥ 70 会触发传感器异常误报"
            )
        profiles.append(
            DeviceProfile(
                device_id=device_id,
                name=str(merged.get("name") or device_id),
                scenario=scenario,
                interval=interval,
                firmware_version=str(merged.get("firmware_version") or "1.2.0"),
                temperature_base=temperature_base,
                rssi_base=int(merged.get("rssi_base") or -55),
                info_log_every=float(merged.get("info_log_every") or 300.0),
            )
        )
    return profiles
