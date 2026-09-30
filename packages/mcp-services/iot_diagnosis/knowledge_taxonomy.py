"""Document domains are independent of the legacy retrieval source keys."""

SOURCE_CATEGORIES = {
    "mqtt_docs": "protocol",
    "wifi_docs": "network",
    "sensor_docs": "hardware",
    "device_docs": "hardware",
}

SOFTWARE_DOCUMENTS = {
    "ESP_FATAL_RESET_DIAG",
    "ESP_HEAP_MEMORY_DIAG",
    "ESP_WATCHDOG_TASK_DIAG",
    "ESP_CORE_DUMP_DIAG",
    "ESP_OTA_UPGRADE_DIAG",
    "ESP_FATAL_ERRORS_GUIDE",
    "ESP_WATCHDOG_OFFICIAL_GUIDE",
    "ESP_EVENT_GUIDE",
    "ESP_HTTPS_OTA_GUIDE",
    "ESP_MEM_ALLOC_GUIDE",
    "ESP_LOG_LIBRARY_GUIDE",
    "ESP_NVS_STORAGE_GUIDE",
}

CURATED_DOCUMENT_TYPES = {
    **dict.fromkeys(
        (
            "ESP_MQTT_ERROR_DIAG",
            "ESP_WIFI_DISCONNECT_DIAG",
            "ESP_FATAL_RESET_DIAG",
            "ESP_HEAP_MEMORY_DIAG",
            "ESP_I2C_SENSOR_DIAG",
            "MQTT_SESSION_QOS_DIAG",
            "ESP_WATCHDOG_TASK_DIAG",
            "ESP_CORE_DUMP_DIAG",
            "ESP_ADC_CALIBRATION_DIAG",
            "MOSQUITTO_BROKER_DIAG",
            "ESP_INTERMITTENT_OFFLINE_DIAG",
            "ESP_OTA_UPGRADE_DIAG",
            "ESP_FATAL_ERRORS_GUIDE",
        ),
        "troubleshooting",
    ),
    **dict.fromkeys(
        (
            "ESP_MQTT_OFFICIAL_GUIDE",
            "ESP_WIFI_DRIVER_GUIDE",
            "ESP_RESET_REASONS_GUIDE",
            "ESP_WATCHDOG_OFFICIAL_GUIDE",
            "ESP_NETIF_GUIDE",
            "ESP_LWIP_STACK_GUIDE",
            "ESP_EVENT_GUIDE",
            "ESP_I2C_DRIVER_GUIDE",
            "ESP_ADC_CALIBRATION_GUIDE",
            "ESP_GPIO_DRIVER_GUIDE",
            "ESP_POWER_MANAGEMENT_GUIDE",
            "ESP_SLEEP_MODES_GUIDE",
            "ESP_HTTPS_OTA_GUIDE",
            "ESP_MEM_ALLOC_GUIDE",
            "ESP_LOG_LIBRARY_GUIDE",
            "ESP_NVS_STORAGE_GUIDE",
        ),
        "manual",
    ),
    **dict.fromkeys(
        (
            "MOSQUITTO_CONF_MAN_PAGE",
            "MOSQUITTO_TLS_MAN_PAGE",
            "MOSQUITTO_PASSWD_MAN_PAGE",
        ),
        "configuration",
    ),
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
