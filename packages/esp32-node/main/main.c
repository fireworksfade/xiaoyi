/*
 * xiaoyi-node: ESP32 field device firmware for the Xiaoyi IoT platform.
 * Protocol: docs/device-protocol.md. Runs unchanged in QEMU (Ethernet) and,
 * built with sdkconfig.defaults.wokwi, in Wokwi or on a real board (WiFi).
 */
#include "esp_event.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "node.h"

static const char *TAG = "app";

void app_main(void)
{
    logfwd_init(); /* first, so boot-time warnings reach the platform too */
    link_init();
    ESP_ERROR_CHECK(config_load());
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());

    report_boot_evidence();
    ESP_ERROR_CHECK(net_start());
    clock_start();
    sensor_init();
    commands_start();
    ota_record_running_slot();
    report_start();
    logfwd_start();
    /* Connecting before DHCP finishes fails DNS (getaddrinfo 202) and sends the platform a
     * misleading transport error, so wait for an address first; MQTT retries on its own after. */
    if (!net_wait_ip(30000)) {
        ESP_LOGW(TAG, "no IP address after 30 s, MQTT will keep retrying");
    }
    ESP_ERROR_CHECK(link_start());

    /* A new OTA image stays "pending verify" until it proves it can reach the broker. */
    while (!link_wait_connected(60000)) {
        ESP_LOGW(TAG, "still waiting for the broker at %s", g_node.broker_uri);
    }
    ota_confirm_running_image();
    drill_apply_boot_fault();
}
