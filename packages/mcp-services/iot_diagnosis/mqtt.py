from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

from iot_diagnosis.remediation import handle_remediation_event
from iot_diagnosis.repository import DiagnosisRepository

logger = logging.getLogger("xiaoyi.iot_diagnosis.mqtt")


class MQTTIngestor:
    def __init__(self, repository: DiagnosisRepository):
        self.repository = repository
        # 持久会话 + QoS1 订阅：MCP 短暂重启期间 Broker 会保留并补发消息，
        # 不再依赖进程常驻才不漏数据。
        self.client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id="iot-diagnosis-mcp",
            protocol=mqtt.MQTTv311,
            clean_session=False,
        )
        username = os.getenv("MQTT_USERNAME")
        if username:
            self.client.username_pw_set(username, os.getenv("MQTT_PASSWORD"))
        if os.getenv("MQTT_USE_TLS", "false").lower() == "true":
            self.client.tls_set()
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message

    def _on_connect(self, client, _userdata, _flags, reason_code, _properties) -> None:
        if reason_code != 0:
            logger.error("MQTT connection failed: %s", reason_code)
            return
        for topic in (
            "iot/+/status",
            "iot/+/telemetry",
            "iot/+/logs",
            "iot/+/fault",
            "iot/+/heartbeat",
            "iot/+/remediation",
        ):
            client.subscribe(topic, qos=1)
        logger.info("Subscribed to IoT diagnosis topics")

    def _on_message(self, _client, _userdata, message) -> None:
        try:
            payload = json.loads(message.payload.decode("utf-8"))
            parts = message.topic.split("/")
            if len(parts) != 3 or parts[0] != "iot":
                return
            device_id, kind = parts[1], parts[2]
            # received_at：服务端收到消息的 UTC 时间；设备时间只作展示/诊断
            received_at = datetime.now(timezone.utc).isoformat()
            if kind == "logs":
                entries = payload if isinstance(payload, list) else [payload]
                for entry in entries:
                    if isinstance(entry, dict):
                        self.repository.add_log(device_id, entry)
            elif kind == "fault":
                if isinstance(payload, dict):
                    self.repository.add_fault(device_id, payload)
            elif kind == "remediation":
                # 修复完成事件：沉淀案例并回发确认，供 Control 关联 case_id
                if isinstance(payload, dict):
                    confirmation = handle_remediation_event(self.repository, device_id, payload)
                    if confirmation:
                        self.client.publish(
                            f"iot/{device_id}/remediation_case",
                            json.dumps(confirmation, ensure_ascii=False),
                            qos=1,
                        )
            elif kind == "status":
                if isinstance(payload, dict):
                    # /status：更新 current state 与元数据，不写历史序列
                    self.repository.apply_status(device_id, payload, received_at)
            elif kind == "telemetry":
                if isinstance(payload, dict):
                    # /telemetry：追加历史测量（去重）并合并 current state
                    self.repository.append_telemetry(device_id, payload, received_at)
            else:  # heartbeat：只更新 last seen / online / uptime
                if isinstance(payload, dict):
                    payload = {**payload, "online": True}
                    self.repository.touch_heartbeat(device_id, payload, received_at)
        except Exception:
            logger.exception("Failed to ingest MQTT message from %s", message.topic)

    def start(self) -> None:
        self.client.connect_async(
            os.getenv("MQTT_HOST", "127.0.0.1"),
            int(os.getenv("MQTT_PORT", "1883")),
            keepalive=60,
        )
        self.client.loop_start()

    def stop(self) -> None:
        self.client.loop_stop()
        self.client.disconnect()
