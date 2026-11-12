"""Document domains are independent of the legacy retrieval source keys."""

SOURCE_CATEGORIES = {
    "mqtt_docs": "protocol",
    "wifi_docs": "network",
    "sensor_docs": "hardware",
    "device_docs": "hardware",
}

# 官方文档的默认标签，与 knowledge/manifest.json 保持一致；入库脚本也会显式传入。
SOFTWARE_DOCUMENTS = {
    "ESP_FATAL_ERRORS",
    "ESP_CORE_DUMP",
    "ESP_WATCHDOGS",
    "ESP_MISC_SYSTEM_API",
    "ESP_HEAP_ALLOCATION",
    "ESP_HEAP_DEBUGGING",
    "ESP_OTA",
    "ESP_HTTPS_OTA",
    "ESP_SYSTEM_TIME",
    "ESP_ERROR_CODES",
}

CURATED_DOCUMENT_TYPES = {
    **dict.fromkeys(("ESP_FATAL_ERRORS", "ESP_CORE_DUMP", "ESP_HEAP_DEBUGGING"), "troubleshooting"),
    **dict.fromkeys(
        (
            "ESP_WATCHDOGS",
            "ESP_HEAP_ALLOCATION",
            "ESP_OTA",
            "ESP_SYSTEM_TIME",
            "ESP_MQTT",
            "MOSQUITTO_BROKER",
            "ESP_LWIP",
            "ESP_WIFI_DRIVER",
            "ESP_ADC_ONESHOT",
            "ESP_ADC_CALIBRATION",
        ),
        "manual",
    ),
    **dict.fromkeys(
        ("ESP_MISC_SYSTEM_API", "ESP_HTTPS_OTA", "ESP_TLS", "ESP_ERROR_CODES"), "api"
    ),
    "MQTT_V311_SPEC": "specification",
    "MOSQUITTO_CONF": "configuration",
}


def default_document_metadata(source: str, document_id: str) -> dict[str, str | None]:
    return {
        "category": (
            "software"
            if document_id in SOFTWARE_DOCUMENTS
            else SOURCE_CATEGORIES.get(source, "other")
        ),
        "document_type": CURATED_DOCUMENT_TYPES.get(document_id),
    }
