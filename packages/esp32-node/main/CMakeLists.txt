idf_component_register(
    SRCS
        "main.c"
        "config.c"
        "clock.c"
        "net.c"
        "link.c"
        "log_forward.c"
        "report.c"
        "commands.c"
        "ota.c"
        "sensor.c"
        "drills.c"
    INCLUDE_DIRS "."
    REQUIRES
        app_update
        esp_adc
        esp_app_format
        esp_eth
        esp_event
        esp_http_client
        esp_https_ota
        esp_netif
        esp_timer
        esp_wifi
        espcoredump
        json
        mqtt
        nvs_flash
)

# A deliberately broken release used to rehearse OTA rollback.
if(XIAOYI_FAULTY_BUILD)
    target_compile_definitions(${COMPONENT_LIB} PRIVATE XIAOYI_FAULTY_BUILD=1)
endif()
