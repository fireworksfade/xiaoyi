"""IoT Control MQTT 通道：下发命令、接收回执并采样验证窗口内的状态与日志。"""

from __future__ import annotations

import json
import logging
import os

import paho.mqtt.client as mqtt

from iot_control.repository import ControlRepository

logger = logging.getLogger("xiaoyi.iot_control.mqtt")

COMMAND_TOPIC = "iot/{device_id}/cmd"
ACK_TOPIC = "iot/+/cmd_ack"
STATUS_TOPIC = "iot/+/status"
LOGS_TOPIC = "iot/+/logs"
FAULT_TOPIC = "iot/+/fault"
CASE_LINK_TOPIC = "iot/+/remediation_case"


class ControlMQTT:
    """诊断 MCP 只上行；本客户端具备发布能力，用于把修复命令下发到设备。"""

    def __init__(self, repository: ControlRepository):
        self.repository = repository
        self.client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id="iot-control-mcp",
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
        for topic in (ACK_TOPIC, STATUS_TOPIC, LOGS_TOPIC, FAULT_TOPIC, CASE_LINK_TOPIC):
            client.subscribe(topic, qos=1)
        logger.info("Subscribed to IoT control topics")

    def _on_message(self, _client, _userdata, message) -> None:
        try:
            payload = json.loads(message.payload.decode("utf-8"))
            parts = message.topic.split("/")
            if len(parts) != 3 or parts[0] != "iot" or not isinstance(payload, dict):
                return
            device_id, kind = parts[1], parts[2]
            if kind == "cmd_ack":
                command_id = payload.get("command_id")
                if command_id:
                    self.repository.mark_command_ack(
                        command_id, str(payload.get("status", "failed")), payload
                    )
            elif kind == "remediation_case":
                # 诊断服务写入案例后的确认：把 case_id 关联回命令，供前端展示
                command_id = payload.get("command_id")
                case_id = payload.get("case_id")
                if command_id and case_id:
                    self.repository.mark_case_archived(str(command_id), str(case_id))
            elif kind == "status":
                self.repository.record_status_sample(device_id, payload.get("online"))
            elif kind in ("logs", "fault"):
                entries = payload if isinstance(payload, list) else [payload]
                for entry in entries:
                    if isinstance(entry, dict):
                        level = entry.get("level", "ERROR" if kind == "fault" else "INFO")
                        self.repository.record_log_sample(device_id, level)
        except Exception:
            logger.exception("Failed to process MQTT message from %s", message.topic)

    def publish(self, topic: str, payload_json: str) -> bool:
        """通用事件发布；返回是否成功交予 Broker。"""
        try:
            info = self.client.publish(topic, payload_json, qos=1)
            return info.rc == mqtt.MQTT_ERR_SUCCESS
        except Exception:
            logger.exception("Failed to publish to %s", topic)
            return False

    def send_command(
        self,
        device_id: str,
        command: dict,
    ) -> bool:
        """QoS1 下发命令；返回是否成功交予 Broker（不保证设备已收到）。"""
        topic = COMMAND_TOPIC.format(device_id=device_id)
        payload = json.dumps(
            {
                "command_id": command["command_id"],
                "action": command["action"],
                "parameters": command.get("parameters") or {},
                "reason": command.get("reason", ""),
                "issued_by": command.get("issued_by", ""),
                "issued_at": command["created_at"],
            },
            ensure_ascii=False,
        )
        try:
            info = self.client.publish(topic, payload, qos=1)
            return info.rc == mqtt.MQTT_ERR_SUCCESS
        except Exception:
            logger.exception("Failed to publish command to %s", topic)
            return False

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
