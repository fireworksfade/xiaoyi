"""设备控制动作目录：动作、风险级别、参数与适用故障类型。

低风险动作可由 Agent 通过 execute_device_action 直接执行；
高风险动作必须先由 Agent 创建提案并经人工批准后执行。
"""

from __future__ import annotations

from typing import Any

LOW_RISK = "low"
HIGH_RISK = "high"

ACTIONS: dict[str, dict[str, Any]] = {
    "reconnect_mqtt": {
        "risk_level": LOW_RISK,
        "description": "重置设备的 MQTT 连接并重新接入 Broker",
        "parameters": {},
        "applicable_fault_types": ["mqtt_connection", "network_connection"],
    },
    "reconnect_wifi": {
        "risk_level": LOW_RISK,
        "description": "让设备重新扫描并连接 WiFi，改善弱信号或断线",
        "parameters": {},
        "applicable_fault_types": ["wifi_connection"],
    },
    "calibrate_sensor": {
        "risk_level": LOW_RISK,
        "description": "对传感器执行零点校准，清除读数异常",
        "parameters": {},
        "applicable_fault_types": ["sensor_anomaly"],
    },
    "set_reporting_interval": {
        "risk_level": LOW_RISK,
        "description": "调整设备状态与遥测的上报间隔",
        "parameters": {
            "seconds": {
                "type": "integer",
                "required": True,
                "minimum": 1,
                "maximum": 3600,
                "description": "新的上报间隔（秒）",
            },
        },
        "applicable_fault_types": ["device_runtime", "network_connection"],
    },
    "restart_device": {
        "risk_level": HIGH_RISK,
        "description": "远程重启设备，会短暂中断服务，用于清除运行时异常",
        "parameters": {},
        "applicable_fault_types": ["device_runtime", "mqtt_connection", "sensor_anomaly"],
    },
    "update_firmware": {
        "risk_level": HIGH_RISK,
        "description": "将设备固件升级到指定版本并自动重启",
        "parameters": {
            "version": {
                "type": "string",
                "required": True,
                "max_length": 40,
                "description": "目标固件版本号，例如 1.3.0",
            },
        },
        "applicable_fault_types": ["device_runtime"],
    },
}

PARAMETER_TYPES = {"integer", "string"}


def get_action(action: str) -> dict[str, Any] | None:
    return ACTIONS.get(action)


def risk_level(action: str) -> str | None:
    item = ACTIONS.get(action)
    return item["risk_level"] if item else None


def validate_parameters(action: str, parameters: dict[str, Any] | None) -> str | None:
    """校验参数，返回错误码或 None 表示通过。"""
    schema = ACTIONS.get(action, {}).get("parameters", {})
    params = parameters or {}
    unknown = set(params) - set(schema)
    if unknown:
        return "UNKNOWN_PARAMETER"
    for name, rule in schema.items():
        value = params.get(name)
        if value is None:
            if rule.get("required"):
                return "MISSING_PARAMETER"
            continue
        if rule["type"] == "integer":
            if isinstance(value, bool) or not isinstance(value, int):
                return "INVALID_PARAMETER"
            if "minimum" in rule and value < rule["minimum"]:
                return "INVALID_PARAMETER"
            if "maximum" in rule and value > rule["maximum"]:
                return "INVALID_PARAMETER"
        else:
            if not isinstance(value, str) or not value.strip():
                return "INVALID_PARAMETER"
            if "max_length" in rule and len(value) > rule["max_length"]:
                return "INVALID_PARAMETER"
    return None


def action_catalog() -> list[dict[str, Any]]:
    return [
        {
            "action": action,
            "risk_level": item["risk_level"],
            "description": item["description"],
            "parameters": item["parameters"],
            "applicable_fault_types": item["applicable_fault_types"],
        }
        for action, item in sorted(ACTIONS.items())
    ]
