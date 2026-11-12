/*
 * Network bring-up. QEMU exposes an OpenCores Ethernet MAC behind user-mode
 * NAT; Wokwi and real boards use the WiFi station driver. Both paths log the
 * same events a field engineer would look for (link changes, IP, reasons).
 */
#include <string.h>

#include "esp_check.h"
#include "esp_event.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"
#include "sdkconfig.h"

#if CONFIG_XIAOYI_NET_OPENETH
#include "esp_eth.h"
#else
#include "esp_wifi.h"
#endif

#include "node.h"

static const char *TAG = "net";

#define NET_GOT_IP BIT0

static EventGroupHandle_t s_events;
static esp_netif_t *s_netif;

static void on_got_ip(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    const ip_event_got_ip_t *event = data;
    ESP_LOGI(TAG, "got ip " IPSTR ", gateway " IPSTR, IP2STR(&event->ip_info.ip),
             IP2STR(&event->ip_info.gw));
    xEventGroupSetBits(s_events, NET_GOT_IP);
}

static void on_lost_ip(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    ESP_LOGW(TAG, "lost ip address");
    xEventGroupClearBits(s_events, NET_GOT_IP);
}

#if CONFIG_XIAOYI_NET_OPENETH

static esp_eth_handle_t s_eth;

static void on_eth(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    switch (id) {
    case ETHERNET_EVENT_CONNECTED:
        ESP_LOGI(TAG, "ethernet link up");
        break;
    case ETHERNET_EVENT_DISCONNECTED:
        ESP_LOGW(TAG, "ethernet link down");
        xEventGroupClearBits(s_events, NET_GOT_IP);
        break;
    case ETHERNET_EVENT_START:
        ESP_LOGI(TAG, "ethernet started");
        break;
    case ETHERNET_EVENT_STOP:
        ESP_LOGI(TAG, "ethernet stopped");
        break;
    default:
        break;
    }
}

static esp_err_t link_layer_start(void)
{
    esp_netif_config_t netif_config = ESP_NETIF_DEFAULT_ETH();
    s_netif = esp_netif_new(&netif_config);

    eth_mac_config_t mac_config = ETH_MAC_DEFAULT_CONFIG();
    eth_phy_config_t phy_config = ETH_PHY_DEFAULT_CONFIG();
    phy_config.autonego_timeout_ms = 100;
    esp_eth_mac_t *mac = esp_eth_mac_new_openeth(&mac_config);
    esp_eth_phy_t *phy = esp_eth_phy_new_dp83848(&phy_config);
    ESP_RETURN_ON_FALSE(mac && phy, ESP_FAIL, TAG, "OpenETH MAC/PHY allocation failed");

    esp_eth_config_t config = ETH_DEFAULT_CONFIG(mac, phy);
    ESP_RETURN_ON_ERROR(esp_eth_driver_install(&config, &s_eth), TAG, "ethernet driver install");
    ESP_RETURN_ON_ERROR(esp_netif_attach(s_netif, esp_eth_new_netif_glue(s_eth)), TAG,
                        "attach ethernet netif");
    ESP_RETURN_ON_ERROR(esp_event_handler_register(ETH_EVENT, ESP_EVENT_ANY_ID, on_eth, NULL), TAG,
                        "eth events");
    ESP_RETURN_ON_ERROR(esp_event_handler_register(IP_EVENT, IP_EVENT_ETH_GOT_IP, on_got_ip, NULL),
                        TAG, "ip events");
    ESP_RETURN_ON_ERROR(
        esp_event_handler_register(IP_EVENT, IP_EVENT_ETH_LOST_IP, on_lost_ip, NULL), TAG,
        "ip events");
    return esp_eth_start(s_eth);
}

esp_err_t net_reconnect(uint32_t timeout_ms)
{
    ESP_LOGW(TAG, "restarting ethernet interface and DHCP");
    xEventGroupClearBits(s_events, NET_GOT_IP);
    esp_err_t err = esp_eth_stop(s_eth);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "esp_eth_stop: %s", esp_err_to_name(err));
    }
    vTaskDelay(pdMS_TO_TICKS(500));
    ESP_RETURN_ON_ERROR(esp_eth_start(s_eth), TAG, "esp_eth_start");
    return net_wait_ip(timeout_ms) ? ESP_OK : ESP_ERR_TIMEOUT;
}

bool net_is_wifi(void)
{
    return false;
}

bool net_rssi(int *rssi)
{
    return false;
}

#else /* WiFi station */

static esp_timer_handle_t s_retry_timer;
static uint32_t s_retry;

static const char *wifi_reason(uint8_t reason)
{
    switch (reason) {
    case WIFI_REASON_AUTH_EXPIRE: return "AUTH_EXPIRE";
    case WIFI_REASON_AUTH_LEAVE: return "AUTH_LEAVE";
    case WIFI_REASON_ASSOC_EXPIRE: return "ASSOC_EXPIRE";
    case WIFI_REASON_ASSOC_LEAVE: return "ASSOC_LEAVE";
    case WIFI_REASON_4WAY_HANDSHAKE_TIMEOUT: return "4WAY_HANDSHAKE_TIMEOUT";
    case WIFI_REASON_BEACON_TIMEOUT: return "BEACON_TIMEOUT";
    case WIFI_REASON_NO_AP_FOUND: return "NO_AP_FOUND";
    case WIFI_REASON_AUTH_FAIL: return "AUTH_FAIL";
    case WIFI_REASON_ASSOC_FAIL: return "ASSOC_FAIL";
    case WIFI_REASON_HANDSHAKE_TIMEOUT: return "HANDSHAKE_TIMEOUT";
    case WIFI_REASON_CONNECTION_FAIL: return "CONNECTION_FAIL";
    default: return "OTHER";
    }
}

static void retry_connect(void *arg)
{
    esp_err_t err = esp_wifi_connect();
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "esp_wifi_connect: %s", esp_err_to_name(err));
    }
}

static void on_wifi(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    switch (id) {
    case WIFI_EVENT_STA_START:
        ESP_LOGI(TAG, "wifi station started, connecting to \"%s\"", CONFIG_XIAOYI_WIFI_SSID);
        esp_wifi_connect();
        break;
    case WIFI_EVENT_STA_CONNECTED: {
        const wifi_event_sta_connected_t *event = data;
        ESP_LOGI(TAG, "wifi associated, channel %d", event->channel);
        s_retry = 0;
        break;
    }
    case WIFI_EVENT_STA_DISCONNECTED: {
        const wifi_event_sta_disconnected_t *event = data;
        xEventGroupClearBits(s_events, NET_GOT_IP);
        uint32_t shift = s_retry < 5 ? s_retry : 5;
        uint32_t delay_ms = 1000u << shift;
        s_retry++;
        ESP_LOGW(TAG, "wifi disconnected, reason=%d (%s), rssi=%d, retry #%lu in %lu ms",
                 event->reason, wifi_reason(event->reason), event->rssi, (unsigned long)s_retry,
                 (unsigned long)delay_ms);
        esp_timer_stop(s_retry_timer);
        esp_timer_start_once(s_retry_timer, (uint64_t)delay_ms * 1000);
        break;
    }
    default:
        break;
    }
}

static esp_err_t link_layer_start(void)
{
    s_netif = esp_netif_create_default_wifi_sta();
    wifi_init_config_t init = WIFI_INIT_CONFIG_DEFAULT();
    ESP_RETURN_ON_ERROR(esp_wifi_init(&init), TAG, "wifi init");
    const esp_timer_create_args_t timer = {.callback = retry_connect, .name = "wifi_retry"};
    ESP_RETURN_ON_ERROR(esp_timer_create(&timer, &s_retry_timer), TAG, "retry timer");
    ESP_RETURN_ON_ERROR(esp_event_handler_register(WIFI_EVENT, ESP_EVENT_ANY_ID, on_wifi, NULL),
                        TAG, "wifi events");
    ESP_RETURN_ON_ERROR(esp_event_handler_register(IP_EVENT, IP_EVENT_STA_GOT_IP, on_got_ip, NULL),
                        TAG, "ip events");
    ESP_RETURN_ON_ERROR(
        esp_event_handler_register(IP_EVENT, IP_EVENT_STA_LOST_IP, on_lost_ip, NULL), TAG,
        "ip events");

    wifi_config_t config = {0};
    strlcpy((char *)config.sta.ssid, CONFIG_XIAOYI_WIFI_SSID, sizeof(config.sta.ssid));
    strlcpy((char *)config.sta.password, CONFIG_XIAOYI_WIFI_PASSWORD, sizeof(config.sta.password));
    config.sta.channel = CONFIG_XIAOYI_WIFI_CHANNEL;
    config.sta.threshold.authmode =
        strlen(CONFIG_XIAOYI_WIFI_PASSWORD) ? WIFI_AUTH_WPA2_PSK : WIFI_AUTH_OPEN;
    ESP_RETURN_ON_ERROR(esp_wifi_set_mode(WIFI_MODE_STA), TAG, "wifi mode");
    ESP_RETURN_ON_ERROR(esp_wifi_set_config(WIFI_IF_STA, &config), TAG, "wifi config");
    return esp_wifi_start();
}

esp_err_t net_reconnect(uint32_t timeout_ms)
{
    ESP_LOGW(TAG, "forcing wifi re-association");
    s_retry = 0;
    xEventGroupClearBits(s_events, NET_GOT_IP);
    esp_timer_stop(s_retry_timer);
    esp_err_t err = esp_wifi_disconnect();
    if (err != ESP_OK) {
        /* Not associated: the disconnect event will not fire, connect directly. */
        esp_wifi_connect();
    }
    return net_wait_ip(timeout_ms) ? ESP_OK : ESP_ERR_TIMEOUT;
}

bool net_is_wifi(void)
{
    return true;
}

bool net_rssi(int *rssi)
{
    wifi_ap_record_t ap;
    if (esp_wifi_sta_get_ap_info(&ap) != ESP_OK) {
        return false;
    }
    *rssi = ap.rssi;
    return true;
}

#endif

esp_err_t net_start(void)
{
    s_events = xEventGroupCreate();
    ESP_RETURN_ON_FALSE(s_events, ESP_ERR_NO_MEM, TAG, "event group");
    return link_layer_start();
}

bool net_wait_ip(uint32_t timeout_ms)
{
    return xEventGroupWaitBits(s_events, NET_GOT_IP, pdFALSE, pdTRUE, pdMS_TO_TICKS(timeout_ms)) &
           NET_GOT_IP;
}

bool net_has_ip(void)
{
    return xEventGroupGetBits(s_events) & NET_GOT_IP;
}
