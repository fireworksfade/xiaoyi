/*
 * MQTT session with the platform broker (see docs/device-protocol.md).
 * Persistent session + QoS1 so commands issued while the device is offline
 * are delivered after it reconnects.
 */
#include <errno.h>
#include <stdio.h>
#include <string.h>

#include "esp_check.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"
#include "mqtt_client.h"

#include "node.h"

static const char *TAG = "link";

#define LINK_UP BIT0
#define MAX_COMMAND_BYTES 4096

static esp_mqtt_client_handle_t s_client;
static EventGroupHandle_t s_bits;
static uint32_t s_connects;
static char s_cmd_topic[96];
static char s_status_topic[96];
static esp_mqtt_client_config_t s_config;
static const char s_will[] = "{\"online\":false,\"offline_reason\":\"client_lost\"}";

static void topic_for(char *out, size_t len, const char *suffix)
{
    snprintf(out, len, "iot/%s/%s", g_node.device_id, suffix);
}

static void log_error(const esp_mqtt_error_codes_t *error)
{
    if (error == NULL) {
        return;
    }
    switch (error->error_type) {
    case MQTT_ERROR_TYPE_TCP_TRANSPORT:
        ESP_LOGE(TAG,
                 "transport error: esp_tls_last_esp_err=0x%x (%s), tls_stack_err=0x%x, "
                 "sock_errno=%d (%s)",
                 error->esp_tls_last_esp_err, esp_err_to_name(error->esp_tls_last_esp_err),
                 error->esp_tls_stack_err, error->esp_transport_sock_errno,
                 strerror(error->esp_transport_sock_errno));
        break;
    case MQTT_ERROR_TYPE_CONNECTION_REFUSED:
        ESP_LOGE(TAG, "connection refused by broker, CONNACK return code=0x%x",
                 error->connect_return_code);
        break;
    case MQTT_ERROR_TYPE_SUBSCRIBE_FAILED:
        ESP_LOGE(TAG, "subscribe to %s rejected by broker", s_cmd_topic);
        break;
    default:
        ESP_LOGE(TAG, "mqtt error type=%d", error->error_type);
        break;
    }
}

static void on_data(const esp_mqtt_event_t *event)
{
    if (event->current_data_offset != 0) {
        return; /* continuation fragments were already rejected below */
    }
    if (event->topic_len != (int)strlen(s_cmd_topic) ||
        strncmp(event->topic, s_cmd_topic, event->topic_len) != 0) {
        return;
    }
    if (event->total_data_len > MAX_COMMAND_BYTES || event->data_len != event->total_data_len) {
        ESP_LOGW(TAG, "command of %d bytes exceeds the receive buffer, dropped",
                 event->total_data_len);
        return;
    }
    commands_enqueue(event->data, event->data_len);
}

static void on_mqtt(void *args, esp_event_base_t base, int32_t id, void *data)
{
    esp_mqtt_event_handle_t event = data;
    switch ((esp_mqtt_event_id_t)id) {
    case MQTT_EVENT_BEFORE_CONNECT:
        ESP_LOGI(TAG, "connecting to %s as %s", g_node.broker_uri, g_node.device_id);
        break;
    case MQTT_EVENT_CONNECTED:
        s_connects++;
        ESP_LOGI(TAG, "MQTT connected (session_present=%d, connection #%lu)",
                 event->session_present, (unsigned long)s_connects);
        esp_mqtt_client_subscribe(s_client, s_cmd_topic, 1);
        xEventGroupSetBits(s_bits, LINK_UP);
        report_birth();
        break;
    case MQTT_EVENT_DISCONNECTED:
        xEventGroupClearBits(s_bits, LINK_UP);
        ESP_LOGW(TAG, "MQTT disconnected");
        break;
    case MQTT_EVENT_SUBSCRIBED:
        ESP_LOGI(TAG, "subscribed to %s", s_cmd_topic);
        break;
    case MQTT_EVENT_DATA:
        on_data(event);
        break;
    case MQTT_EVENT_ERROR:
        log_error(event->error_handle);
        break;
    default:
        break;
    }
}

void link_init(void)
{
    /* Other tasks wait on the link state before the MQTT client exists. */
    static StaticEventGroup_t storage;
    s_bits = xEventGroupCreateStatic(&storage);
}

esp_err_t link_start(void)
{
    topic_for(s_cmd_topic, sizeof(s_cmd_topic), "cmd");
    topic_for(s_status_topic, sizeof(s_status_topic), "status");

    /* Kept for the life of the client: esp_mqtt_set_config() replaces every field. */
    s_config = (esp_mqtt_client_config_t){
        .broker.address.uri = g_node.broker_uri,
        .credentials.client_id = g_node.device_id,
        .session =
            {
                .keepalive = (int)g_node.keepalive_s,
                .disable_clean_session = true,
                .last_will =
                    {
                        .topic = s_status_topic,
                        .msg = s_will,
                        .qos = 1,
                        .retain = 1,
                    },
            },
        .network =
            {
                .reconnect_timeout_ms = 5000,
                .timeout_ms = 10000,
            },
        .buffer =
            {
                .size = MAX_COMMAND_BYTES,
                .out_size = 2048,
            },
        .task.stack_size = 6144,
    };
    s_client = esp_mqtt_client_init(&s_config);
    ESP_RETURN_ON_FALSE(s_client, ESP_FAIL, TAG, "esp_mqtt_client_init");
    ESP_RETURN_ON_ERROR(esp_mqtt_client_register_event(s_client, ESP_EVENT_ANY_ID, on_mqtt, NULL),
                        TAG, "register events");
    return esp_mqtt_client_start(s_client);
}

bool link_connected(void)
{
    return s_bits && (xEventGroupGetBits(s_bits) & LINK_UP);
}

bool link_wait_connected(uint32_t timeout_ms)
{
    return xEventGroupWaitBits(s_bits, LINK_UP, pdFALSE, pdTRUE, pdMS_TO_TICKS(timeout_ms)) &
           LINK_UP;
}

esp_err_t link_reconnect(uint32_t timeout_ms)
{
    ESP_LOGW(TAG, "restarting MQTT client on request");
    xEventGroupClearBits(s_bits, LINK_UP);
    esp_err_t err = esp_mqtt_client_stop(s_client);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "esp_mqtt_client_stop: %s", esp_err_to_name(err));
    }
    ESP_RETURN_ON_ERROR(esp_mqtt_client_start(s_client), TAG, "esp_mqtt_client_start");
    return link_wait_connected(timeout_ms) ? ESP_OK : ESP_ERR_TIMEOUT;
}

esp_err_t link_set_keepalive(uint32_t seconds, uint32_t timeout_ms)
{
    /* The keep alive travels in CONNECT, so the new value needs a fresh session handshake. */
    s_config.session.keepalive = (int)seconds;
    ESP_RETURN_ON_ERROR(esp_mqtt_set_config(s_client, &s_config), TAG, "esp_mqtt_set_config");
    ESP_LOGW(TAG, "keep alive set to %lu s, reconnecting", (unsigned long)seconds);
    return link_reconnect(timeout_ms);
}

void link_shutdown(const char *reason)
{
    if (!link_connected()) {
        return;
    }
    cJSON *status = cJSON_CreateObject();
    char now[40];
    if (clock_iso_now(now, sizeof(now))) {
        cJSON_AddStringToObject(status, "timestamp", now);
    }
    cJSON_AddBoolToObject(status, "online", false);
    cJSON_AddStringToObject(status, "offline_reason", reason);
    link_publish_json("status", status, 1, true);
    cJSON_Delete(status);
    /* Give the outbox a moment so PUBACKs and the offline status leave the socket. */
    vTaskDelay(pdMS_TO_TICKS(800));
    esp_mqtt_client_stop(s_client);
}

int link_publish(const char *suffix, const char *payload, int qos, bool retain)
{
    if (!link_connected()) {
        return -1;
    }
    char topic[96];
    topic_for(topic, sizeof(topic), suffix);
    return esp_mqtt_client_publish(s_client, topic, payload, 0, qos, retain ? 1 : 0);
}

int link_publish_json(const char *suffix, const cJSON *payload, int qos, bool retain)
{
    char *text = cJSON_PrintUnformatted(payload);
    if (text == NULL) {
        return -1;
    }
    int id = link_publish(suffix, text, qos, retain);
    cJSON_free(text);
    return id;
}

uint32_t link_reconnects(void)
{
    return s_connects > 0 ? s_connects - 1 : 0;
}
