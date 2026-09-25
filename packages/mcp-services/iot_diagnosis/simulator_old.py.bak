"""ESP32 设备模拟器，支持单设备与机群两种模式。

- 单设备模式（向后兼容）：
  ``python -m iot_diagnosis.simulator --device-id ESP32_05 --scenario mqtt_timeout``
- 机群模式：一个进程内以线程模拟整个 ESP32 机群，拓扑见 ``fleet.json``：
  ``python -m iot_diagnosis.simulator --host mqtt --fleet iot_diagnosis/fleet.json``

每台设备独立 MQTT 连接（client_id、遗嘱、命令订阅互不干扰），遥测数据按
设备画像生成：各自的部署位置命名、温度/RSSI 基线、固件版本与上报间隔。
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import signal
import threading
import time
import zlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import paho.mqtt.client as mqtt

logger = logging.getLogger(__name__)

SCENARIOS = (
    "normal",
    "mqtt_timeout",
    "wifi_weak",
    "sensor_error",
    "unstable",
    "memory_leak",
    "watchdog_reset",
)

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


def current_status(
    state: DeviceState,
    timestamp: str | None = None,
    *,
    profile: DeviceProfile | None = None,
    rng: random.Random | None = None,
) -> dict:
    """根据设备状态与画像生成一帧 status/telemetry 载荷。"""
    randomizer: Any = rng or random
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


def _offline_status(timestamp: str | None = None, reason: str = "client_lost") -> dict:
    return {
        "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
        "online": False,
        "offline_reason": reason,
    }


class DeviceSimulator:
    """单台模拟设备：独立 MQTT 连接与上报循环，运行在自己的线程里。"""

    def __init__(
        self,
        profile: DeviceProfile,
        host: str,
        port: int,
        *,
        rng: random.Random | None = None,
    ):
        self.profile = profile
        self.host = host
        self.port = port
        self.state = DeviceState(profile.scenario, profile.interval, profile.firmware_version)
        # 以 device_id 派生随机种子，机群行为跨重启可复现
        self.rng = rng or random.Random(zlib.crc32(profile.device_id.encode("utf-8")))
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._run, name=f"simulator-{self.profile.device_id}", daemon=True
        )
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)

    def _connect_with_retry(self, client: mqtt.Client, attempts: int = 5) -> None:
        for attempt in range(1, attempts + 1):
            try:
                client.connect(self.host, self.port, keepalive=60)
                return
            except OSError:
                if attempt == attempts:
                    raise
                logger.warning(
                    "设备 %s 连接 MQTT 失败，%.0f 秒后重试（%d/%d）",
                    self.profile.device_id,
                    2,
                    attempt,
                    attempts,
                )
                time.sleep(2)

    def _run(self) -> None:
        profile = self.profile
        device_id = profile.device_id
        client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"simulator-{device_id}",
        )
        # 遗嘱消息：模拟进程崩溃（而非正常退出）时，Broker 代发离线状态，
        # 诊断服务无需等心跳超时即可感知设备掉线。
        client.will_set(
            f"iot/{device_id}/status",
            json.dumps(_offline_status(), ensure_ascii=False),
            qos=1,
            retain=True,
        )

        def on_command(_client, _userdata, message) -> None:
            try:
                payload = json.loads(message.payload.decode("utf-8"))
                if not isinstance(payload, dict):
                    return
                ack = handle_command(self.state, payload)
                publish(client, f"iot/{device_id}/cmd_ack", ack)
                if ack["status"] == "applied":
                    publish(
                        client,
                        f"iot/{device_id}/logs",
                        {
                            "timestamp": ack["timestamp"],
                            "level": "INFO",
                            "module": "remediation",
                            "message": f"命令 {payload.get('command_id')} 已执行: {ack['detail']}",
                        },
                    )
                    publish(
                        client,
                        f"iot/{device_id}/status",
                        current_status(self.state, profile=profile),
                    )
            except Exception:
                logger.exception("设备 %s 处理下行命令失败", device_id)

        client.on_message = on_command
        self._connect_with_retry(client)
        client.subscribe(f"iot/{device_id}/cmd", qos=1)
        client.loop_start()
        logger.info(
            "设备 %s（%s, 场景 %s）已上线", device_id, profile.display_name, profile.scenario
        )
        started_at = time.monotonic()
        try:
            while not self._stop.is_set():
                now = time.monotonic()
                timestamp = datetime.now(timezone.utc).isoformat()
                snapshot = self.state.snapshot()
                messages = build_cycle(
                    self.state,
                    profile,
                    self.rng,
                    elapsed=now - started_at,
                    timestamp=timestamp,
                )
                for suffix, payload in messages:
                    publish(client, f"iot/{device_id}/{suffix}", payload)
                with self.state.lock:
                    if not snapshot["watchdog_reset"]:
                        # 看门狗场景下设备反复重启，uptime 不累积
                        self.state.uptime += int(snapshot["interval"])
                # 分片睡眠，保证下行命令能及时修改上报间隔并快速响应停止信号
                remaining = snapshot["interval"]
                while remaining > 0 and not self._stop.is_set():
                    step = min(0.5, remaining)
                    self._stop.wait(step)
                    remaining -= step
        finally:
            # 优雅下线：主动发布 offline 状态后断开（遗嘱仅覆盖异常掉线）
            try:
                publish(
                    client,
                    f"iot/{device_id}/status",
                    _offline_status(reason="graceful_shutdown"),
                )
            except Exception:
                logger.exception("设备 %s 发布下线状态失败", device_id)
            client.loop_stop()
            client.disconnect()
        logger.info("设备 %s 已下线", device_id)


def publish(client: mqtt.Client, topic: str, payload: dict) -> None:
    client.publish(topic, json.dumps(payload, ensure_ascii=False), qos=1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="ESP32 设备模拟器（单设备模式或 --fleet 机群模式）"
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--device-id", default="ESP32_05")
    parser.add_argument("--scenario", choices=list(SCENARIOS), default="mqtt_timeout")
    parser.add_argument("--interval", type=float, default=5.0)
    parser.add_argument(
        "--fleet",
        help="机群配置 JSON 路径；提供后忽略 --device-id/--scenario/--interval",
    )
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.fleet:
        profiles = load_fleet(args.fleet)
    else:
        profiles = [
            DeviceProfile(
                device_id=args.device_id,
                scenario=args.scenario,
                interval=args.interval,
            )
        ]

    logger.info("启动 %d 台模拟设备（MQTT %s:%d）", len(profiles), args.host, args.port)
    simulators = [DeviceSimulator(profile, args.host, args.port) for profile in profiles]
    for simulator in simulators:
        simulator.start()

    # SIGTERM（docker stop）与 SIGINT 统一走优雅下线：每台设备主动发布
    # online:false 后断开，而不是触发遗嘱里的 client_lost
    stop_requested = threading.Event()

    def _request_stop(signum, _frame) -> None:
        logger.info("收到退出信号（%s），正在下线全部模拟设备…", signal.Signals(signum).name)
        stop_requested.set()

    signal.signal(signal.SIGINT, _request_stop)
    signal.signal(signal.SIGTERM, _request_stop)
    try:
        while not stop_requested.is_set():
            time.sleep(1)
    finally:
        for simulator in simulators:
            simulator.stop()


if __name__ == "__main__":
    main()
