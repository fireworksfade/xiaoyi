"""单台设备模拟器：独立 MQTT 连接与上报循环。"""

from __future__ import annotations

import json
import logging
import random
import threading
import time
import zlib
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

from .models import DeviceProfile, DeviceState
from .command_handler import handle_command
from .telemetry import build_cycle, current_status

logger = logging.getLogger(__name__)


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
