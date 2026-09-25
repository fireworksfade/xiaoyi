"""遥测数据生成：状态、心跳、日志构建逻辑。"""

from __future__ import annotations

import random
from datetime import datetime, timezone

from .models import DeviceProfile, DeviceState

# unstable 场景参数：运行保护期后每个上报周期以该概率进入离线片段，
# 片段时长在闭区间内随机，期间停止一切上报，模拟现场网络间歇性中断。
UNSTABLE_OFFLINE_PROBABILITY = 0.01
UNSTABLE_OFFLINE_MIN_SECONDS = 60.0
UNSTABLE_OFFLINE_MAX_SECONDS = 120.0
UNSTABLE_GRACE_SECONDS = 120.0

# 健康设备周期性发布的运行日志，按上报周期轮换，避免内容单一
PERIODIC_LOG_MESSAGES = (
    "周期性自检完成，各模块运行正常",
    "WiFi 链路质量良好",
    "传感器读数在正常范围内",
    "本地缓存队列已清空",
)


def current_status(
    state: DeviceState,
    timestamp: str | None = None,
    *,
    profile: DeviceProfile | None = None,
    rng: random.Random | None = None,
) -> dict:
    """根据设备状态与画像生成一帧 status/telemetry 载荷。"""
    randomizer = rng or random
    timestamp = timestamp or datetime.now(timezone.utc).isoformat()
    snapshot = state.snapshot()

    if snapshot["sensor_error"]:
        # 传感器故障：读数卡死在异常高温
        temperature = 78.0
    else:
        base = profile.temperature_base if profile else 27.0
        temperature = round(base + randomizer.uniform(-1.0, 1.0), 2)

    if snapshot["wifi_weak"]:
        rssi = -82
    elif snapshot["offline"]:
        rssi = randomizer.randint(-92, -85)
    elif snapshot["unstable"]:
        # 信号在诊断阈值 -75 附近波动，制造间歇性弱信号
        rssi = randomizer.randint(-78, -70)
    else:
        base = profile.rssi_base if profile else -50
        rssi = int(base) + randomizer.randint(-4, 4)

    online = not snapshot["offline"]
    status = {
        "timestamp": timestamp,
        "online": online,
        "wifi_status": "connected" if online else "disconnected",
        "rssi": rssi,
        "mqtt_status": "disconnected" if snapshot["mqtt_timeout"] else "connected",
        "temperature": temperature,
        "uptime": snapshot["uptime"],
        "device_type": "ESP32",
        "firmware_version": snapshot["firmware_version"],
    }
    if profile is not None:
        status["name"] = profile.display_name
    return status


def build_cycle(
    state: DeviceState,
    profile: DeviceProfile,
    rng: random.Random,
    *,
    elapsed: float,
    timestamp: str,
) -> list[tuple[str, dict]]:
    """构建一个上报周期的全部消息（topic 后缀, 载荷），便于单元测试。

    会按 unstable 场景的进入/恢复/静默规则修改 state 中的离线片段标记。
    """
    messages: list[tuple[str, dict]] = []
    snapshot = state.snapshot()

    if snapshot["unstable"]:
        if snapshot["offline"]:
            if elapsed >= snapshot["offline_until"]:
                # 离线片段结束：设备自行恢复上线，随后走正常上报
                with state.lock:
                    state.offline = False
                    state.offline_until = 0.0
                messages.append(
                    (
                        "logs",
                        {
                            "timestamp": timestamp,
                            "level": "INFO",
                            "module": "wifi",
                            "message": "网络已恢复，设备重新上线",
                        },
                    )
                )
            else:
                # 离线片段进行中：设备完全静默
                return []
        elif elapsed >= UNSTABLE_GRACE_SECONDS and rng.random() < UNSTABLE_OFFLINE_PROBABILITY:
            with state.lock:
                state.offline = True
                state.offline_until = elapsed + rng.uniform(
                    UNSTABLE_OFFLINE_MIN_SECONDS, UNSTABLE_OFFLINE_MAX_SECONDS
                )
            messages.append(
                (
                    "logs",
                    {
                        "timestamp": timestamp,
                        "level": "WARNING",
                        "module": "wifi",
                        "message": "WiFi 连接丢失，设备即将离线",
                    },
                )
            )
            messages.append(("status", current_status(state, timestamp, profile=profile, rng=rng)))
            return messages

    # 正常周期上报（健康设备与 unstable 恢复后/常态在线时共用）
    status = current_status(state, timestamp, profile=profile, rng=rng)
    messages.append(("status", status))
    messages.append(("telemetry", status))
    messages.append(
        (
            "heartbeat",
            {"timestamp": timestamp, "online": True, "uptime": snapshot["uptime"]},
        )
    )
    if snapshot["mqtt_timeout"]:
        messages.append(
            (
                "logs",
                {
                    "timestamp": timestamp,
                    "level": "ERROR",
                    "module": "mqtt",
                    "message": "MQTT keep alive timeout",
                },
            )
        )
        messages.append(
            (
                "fault",
                {
                    "timestamp": timestamp,
                    "fault_type": "mqtt_timeout",
                    "level": "ERROR",
                    "message": "MQTT keep alive timeout",
                },
            )
        )
    if snapshot["memory_leak"]:
        messages.append(
            (
                "logs",
                {
                    "timestamp": timestamp,
                    "level": "WARNING",
                    "module": "heap",
                    "message": (
                        f"free heap {int(rng.uniform(24000, 42000))} bytes, "
                        f"min ever {int(rng.uniform(18000, 23900))} bytes"
                    ),
                },
            )
        )
        if rng.random() < 0.35:
            messages.append(
                (
                    "fault",
                    {
                        "timestamp": timestamp,
                        "fault_type": "out_of_memory",
                        "level": "ERROR",
                        "message": "heap: Allocation failed, out of memory",
                    },
                )
            )
    if snapshot["watchdog_reset"]:
        messages.append(
            (
                "fault",
                {
                    "timestamp": timestamp,
                    "fault_type": "watchdog_reset",
                    "level": "ERROR",
                    "message": (
                        "Task watchdog got triggered: task uart_event did not "
                        "reset the watchdog in time"
                    ),
                },
            )
        )
        messages.append(
            (
                "logs",
                {
                    "timestamp": timestamp,
                    "level": "CRITICAL",
                    "module": "runtime",
                    "message": "abort() was called at PC 0x400d1a2c, rebooting after panic",
                },
            )
        )
    # 健康设备低频发布运行日志，保持日志流真实又不至于撑爆日志表
    with state.lock:
        if profile.info_log_every > 0 and not snapshot["mqtt_timeout"]:
            if state.next_info_log_at <= 0.0:
                # 首个周期只校准节奏，不补发日志
                state.next_info_log_at = profile.info_log_every
            emit_info_log = elapsed >= state.next_info_log_at
            if emit_info_log:
                state.next_info_log_at = elapsed + profile.info_log_every
        else:
            emit_info_log = False
    if emit_info_log:
        messages.append(
            (
                "logs",
                {
                    "timestamp": timestamp,
                    "level": "INFO",
                    "module": "runtime",
                    "message": rng.choice(PERIODIC_LOG_MESSAGES),
                },
            )
        )
    return messages
