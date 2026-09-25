from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from iot_diagnosis.ingestion import ingest_text
from iot_diagnosis.repository import DiagnosisRepository

DOCUMENTS = (
    (
        "esp_mqtt_error_diagnosis.md",
        "mqtt_docs",
        "ESP_MQTT_ERROR_DIAG",
        "ESP-MQTT 错误事件与连接故障诊断",
    ),
    (
        "esp_wifi_disconnect_diagnosis.md",
        "wifi_docs",
        "ESP_WIFI_DISCONNECT_DIAG",
        "ESP32 WiFi 断线原因与重连诊断",
    ),
    (
        "esp_fatal_reset_diagnosis.md",
        "device_docs",
        "ESP_FATAL_RESET_DIAG",
        "ESP32 致命错误、重启原因与 Backtrace 诊断",
    ),
    (
        "esp_heap_memory_diagnosis.md",
        "device_docs",
        "ESP_HEAP_MEMORY_DIAG",
        "ESP32 内存泄漏、碎片与低内存诊断",
    ),
    (
        "esp_i2c_sensor_diagnosis.md",
        "sensor_docs",
        "ESP_I2C_SENSOR_DIAG",
        "ESP32 I2C 传感器通信故障诊断",
    ),
    (
        "mqtt_session_qos_diagnosis.md",
        "mqtt_docs",
        "MQTT_SESSION_QOS_DIAG",
        "MQTT Keep Alive、Session 与 QoS 故障诊断",
    ),
    (
        "esp_watchdog_task_diagnosis.md",
        "device_docs",
        "ESP_WATCHDOG_TASK_DIAG",
        "ESP32 Watchdog 与任务阻塞诊断",
    ),
    (
        "esp_core_dump_backtrace_diagnosis.md",
        "device_docs",
        "ESP_CORE_DUMP_DIAG",
        "ESP32 Core Dump 与 Backtrace 分析",
    ),
    (
        "esp_adc_calibration_diagnosis.md",
        "sensor_docs",
        "ESP_ADC_CALIBRATION_DIAG",
        "ESP32 ADC 校准与传感器漂移诊断",
    ),
    (
        "mosquitto_broker_diagnosis.md",
        "mqtt_docs",
        "MOSQUITTO_BROKER_DIAG",
        "Mosquitto Broker 配置与日志诊断",
    ),
    # 官方技术文档：随服务打包的权威参考资料，入库后参与语义检索
    (
        "ESP_MQTT_OFFICIAL_GUIDE.md",
        "mqtt_docs",
        "ESP_MQTT_OFFICIAL_GUIDE",
        "ESP-IDF MQTT 官方指南",
    ),
    (
        "MOSQUITTO_CONF_MAN_PAGE.md",
        "mqtt_docs",
        "MOSQUITTO_CONF_MAN_PAGE",
        "Mosquitto.conf 配置手册",
    ),
    (
        "ESP_WIFI_DRIVER_GUIDE.md",
        "wifi_docs",
        "ESP_WIFI_DRIVER_GUIDE",
        "ESP32 WiFi 驱动官方指南",
    ),
    (
        "ESP_FATAL_ERRORS_GUIDE.md",
        "device_docs",
        "ESP_FATAL_ERRORS_GUIDE",
        "ESP32 致命错误官方指南",
    ),
    (
        "ESP_RESET_REASONS_GUIDE.md",
        "device_docs",
        "ESP_RESET_REASONS_GUIDE",
        "ESP32 复位原因官方指南",
    ),
    (
        "ESP_WATCHDOG_OFFICIAL_GUIDE.md",
        "device_docs",
        "ESP_WATCHDOG_OFFICIAL_GUIDE",
        "ESP32 Watchdog 官方指南",
    ),
    (
        "ESP_NETIF_GUIDE.md",
        "wifi_docs",
        "ESP_NETIF_GUIDE",
        "ESP-NETIF 网络接口官方指南",
    ),
    (
        "ESP_LWIP_STACK_GUIDE.md",
        "wifi_docs",
        "ESP_LWIP_STACK_GUIDE",
        "ESP-IDF LwIP 网络栈官方指南",
    ),
    (
        "ESP_EVENT_GUIDE.md",
        "device_docs",
        "ESP_EVENT_GUIDE",
        "ESP-IDF 事件循环（ESP Event）官方指南",
    ),
    (
        "ESP_I2C_DRIVER_GUIDE.md",
        "sensor_docs",
        "ESP_I2C_DRIVER_GUIDE",
        "ESP-IDF I2C 驱动官方指南",
    ),
    (
        "ESP_ADC_CALIBRATION_GUIDE.md",
        "sensor_docs",
        "ESP_ADC_CALIBRATION_GUIDE",
        "ESP-IDF ADC 校准官方指南",
    ),
    (
        "ESP_GPIO_DRIVER_GUIDE.md",
        "device_docs",
        "ESP_GPIO_DRIVER_GUIDE",
        "ESP-IDF GPIO 驱动官方指南",
    ),
    (
        "ESP_POWER_MANAGEMENT_GUIDE.md",
        "device_docs",
        "ESP_POWER_MANAGEMENT_GUIDE",
        "ESP-IDF 电源管理官方指南",
    ),
    (
        "ESP_SLEEP_MODES_GUIDE.md",
        "device_docs",
        "ESP_SLEEP_MODES_GUIDE",
        "ESP-IDF 睡眠模式与唤醒源官方指南",
    ),
    (
        "ESP_HTTPS_OTA_GUIDE.md",
        "device_docs",
        "ESP_HTTPS_OTA_GUIDE",
        "ESP-IDF HTTPS OTA 升级官方指南",
    ),
    (
        "ESP_MEM_ALLOC_GUIDE.md",
        "device_docs",
        "ESP_MEM_ALLOC_GUIDE",
        "ESP-IDF 堆内存分配官方指南",
    ),
    (
        "ESP_LOG_LIBRARY_GUIDE.md",
        "device_docs",
        "ESP_LOG_LIBRARY_GUIDE",
        "ESP-IDF 日志库官方指南",
    ),
    (
        "ESP_NVS_STORAGE_GUIDE.md",
        "device_docs",
        "ESP_NVS_STORAGE_GUIDE",
        "ESP-IDF NVS 存储官方指南",
    ),
    (
        "MOSQUITTO_TLS_MAN_PAGE.md",
        "mqtt_docs",
        "MOSQUITTO_TLS_MAN_PAGE",
        "Mosquitto TLS 配置手册",
    ),
    (
        "MOSQUITTO_PASSWD_MAN_PAGE.md",
        "mqtt_docs",
        "MOSQUITTO_PASSWD_MAN_PAGE",
        "mosquitto_passwd 认证手册",
    ),
    (
        "esp_intermittent_offline_diagnosis.md",
        "wifi_docs",
        "ESP_INTERMITTENT_OFFLINE_DIAG",
        "ESP32 设备间歇离线诊断",
    ),
    (
        "esp_ota_upgrade_diagnosis.md",
        "device_docs",
        "ESP_OTA_UPGRADE_DIAG",
        "ESP32 OTA 固件升级失败诊断",
    ),
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingest the curated ESP32 diagnosis documents shipped with the service"
    )
    parser.add_argument(
        "--database",
        default=os.getenv("DIAGNOSIS_DATABASE_PATH", "data/iot_diagnosis.db"),
    )
    # 缺省走 RAG_CHUNK_SIZE / RAG_CHUNK_OVERLAP（structure_token 分块，默认 512 / 64）
    parser.add_argument("--chunk-size", type=int, default=None)
    parser.add_argument("--overlap", type=int, default=None)
    args = parser.parse_args()

    knowledge_dir = Path(__file__).resolve().parents[1] / "knowledge"
    repository = DiagnosisRepository(args.database)
    results = []
    for filename, source, document_id, title in DOCUMENTS:
        results.append(
            ingest_text(
                repository,
                source=source,
                document_id=document_id,
                title=title,
                content=(knowledge_dir / filename).read_text(encoding="utf-8"),
                device_type="ESP32",
                chunk_size=args.chunk_size,
                overlap=args.overlap,
            )
        )
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
