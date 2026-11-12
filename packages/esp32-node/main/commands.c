/*
 * Executes platform commands from iot/{id}/cmd. Runs in its own task so a slow
 * action (OTA download, reconnect) never blocks the MQTT task and its pings.
 */
#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#include "esp_app_desc.h"
#include "esp_log.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/task.h"
#include "sdkconfig.h"

#include "node.h"

static const char *TAG = "cmd";

#define RECENT 8
/* Longest ack detail (OTA version mismatch with two 31-char versions) is ~135 bytes. */
#define DETAIL_LEN 160

typedef struct {
    char *data;
    int len;
} command_msg_t;

typedef struct {
    char id[64];
    bool applied;
    char detail[DETAIL_LEN];
} recent_ack_t;

static QueueHandle_t s_queue;
static recent_ack_t s_recent[RECENT];
static size_t s_recent_next;

void commands_enqueue(const char *data, int len)
{
    command_msg_t msg = {.data = malloc(len + 1), .len = len};
    if (msg.data == NULL) {
        ESP_LOGE(TAG, "no memory to queue a %d byte command", len);
        return;
    }
    memcpy(msg.data, data, len);
    msg.data[len] = '\0';
    if (xQueueSend(s_queue, &msg, 0) != pdTRUE) {
        ESP_LOGW(TAG, "command queue full, command dropped");
        free(msg.data);
    }
}

static void send_ack(const char *command_id, bool applied, const char *detail)
{
    cJSON *ack = cJSON_CreateObject();
    cJSON_AddStringToObject(ack, "command_id", command_id);
    cJSON_AddStringToObject(ack, "status", applied ? "applied" : "failed");
    cJSON_AddStringToObject(ack, "detail", detail);
    char now[40];
    if (clock_iso_now(now, sizeof(now))) {
        cJSON_AddStringToObject(ack, "timestamp", now);
    }
    if (!link_wait_connected(30000) || link_publish_json("cmd_ack", ack, 1, false) < 0) {
        ESP_LOGW(TAG, "could not publish ack for %s", command_id);
    }
    cJSON_Delete(ack);

    if (*command_id) {
        recent_ack_t *slot = &s_recent[s_recent_next++ % RECENT];
        strlcpy(slot->id, command_id, sizeof(slot->id));
        slot->applied = applied;
        strlcpy(slot->detail, detail, sizeof(slot->detail));
    }
    if (applied) {
        ESP_LOGI(TAG, "命令 %s 已执行: %s", command_id, detail);
    } else {
        ESP_LOGW(TAG, "命令 %s 执行失败: %s", command_id, detail);
    }
}

static const recent_ack_t *find_recent(const char *command_id)
{
    for (size_t i = 0; i < RECENT; i++) {
        if (s_recent[i].id[0] && strcmp(s_recent[i].id, command_id) == 0) {
            return &s_recent[i];
        }
    }
    return NULL;
}

static const char *string_field(const cJSON *object, const char *name)
{
    const cJSON *item = cJSON_GetObjectItemCaseSensitive(object, name);
    return cJSON_IsString(item) ? item->valuestring : NULL;
}

static bool valid_version(const char *version)
{
    size_t len = version ? strlen(version) : 0;
    if (len == 0 || len > 31) {
        return false;
    }
    for (size_t i = 0; i < len; i++) {
        char c = version[i];
        if (!isalnum((unsigned char)c) && c != '.' && c != '_' && c != '-') {
            return false;
        }
    }
    return true;
}

/* Reboot-type commands survive the reboot so a broker redelivery is not re-run. */
static bool already_rebooted_for(const char *command_id)
{
    char last[64] = "";
    return config_get_str("last_cmd", last, sizeof(last)) == ESP_OK &&
           strcmp(last, command_id) == 0;
}

static void reboot(const char *reason)
{
    link_shutdown(reason);
    ESP_LOGW(TAG, "rebooting (%s)", reason);
#if CONFIG_XIAOYI_EMULATED_POWER_CYCLE
    config_set_str("rst_hint", "SW"); /* read back by report_boot_evidence() */
#endif
    vTaskDelay(pdMS_TO_TICKS(200));
    esp_restart();
}

static void run_restart(const char *id)
{
    config_set_str("last_cmd", id);
    send_ack(id, true, "设备即将重启");
    reboot("restart");
}

static void run_update(const char *id, const cJSON *params)
{
    const char *version = string_field(params, "version");
    if (!valid_version(version)) {
        send_ack(id, false, "version 必须是 1-31 位字母、数字、点、下划线或连字符");
        return;
    }
    const char *running = esp_app_get_description()->version;
    if (strcmp(version, running) == 0) {
        send_ack(id, true, "设备已运行目标版本，无需升级");
        return;
    }
    char detail[DETAIL_LEN];
    if (ota_update(version, detail, sizeof(detail)) != ESP_OK) {
        send_ack(id, false, detail);
        return;
    }
    config_set_str("last_cmd", id);
    send_ack(id, true, detail);
    reboot("firmware_update");
}

static void run_rollback(const char *id)
{
    char detail[DETAIL_LEN];
    if (ota_select_previous(detail, sizeof(detail)) != ESP_OK) {
        send_ack(id, false, detail);
        return;
    }
    config_set_str("last_cmd", id);
    send_ack(id, true, detail);
    reboot("firmware_rollback");
}

static void run_keepalive(const char *id, const cJSON *params)
{
    const cJSON *seconds = cJSON_GetObjectItemCaseSensitive(params, "seconds");
    if (!cJSON_IsNumber(seconds) || seconds->valuedouble != (double)(int)seconds->valuedouble ||
        seconds->valueint < 10 || seconds->valueint > 600) {
        send_ack(id, false, "seconds 必须是 10-600 的整数");
        return;
    }
    uint32_t previous = g_node.keepalive_s;
    esp_err_t err = config_set_keepalive((uint32_t)seconds->valueint);
    if (err != ESP_OK) {
        char detail[96];
        snprintf(detail, sizeof(detail), "写入 NVS 失败：%s", esp_err_to_name(err));
        send_ack(id, false, detail);
        return;
    }
    if (link_set_keepalive(g_node.keepalive_s, 30000) != ESP_OK) {
        send_ack(id, false, "Keep Alive 已保存，但 MQTT 30 秒内未重新连接");
        return;
    }
    char detail[96];
    snprintf(detail, sizeof(detail), "Keep Alive 已从 %lu 秒调整为 %d 秒，MQTT 已重新连接",
             (unsigned long)previous, seconds->valueint);
    send_ack(id, true, detail);
}

static void run_reconnect_mqtt(const char *id)
{
    int64_t started = esp_timer_get_time();
    if (link_reconnect(20000) != ESP_OK) {
        send_ack(id, false, "MQTT 重连超时（20 秒内未收到 CONNACK）");
        return;
    }
    char detail[96];
    snprintf(detail, sizeof(detail), "MQTT 已重新连接，耗时 %lld ms",
             (long long)((esp_timer_get_time() - started) / 1000));
    send_ack(id, true, detail);
}

static void run_reconnect_network(const char *id)
{
    if (net_reconnect(30000) != ESP_OK) {
        send_ack(id, false, net_is_wifi() ? "WiFi 重新关联超时" : "以太网 30 秒内未重新获取 IP");
        return;
    }
    if (!link_wait_connected(30000)) {
        send_ack(id, false, "网络已恢复，但 MQTT 30 秒内未重新连接");
        return;
    }
    char detail[128];
    int rssi;
    if (net_is_wifi() && net_rssi(&rssi)) {
        snprintf(detail, sizeof(detail), "WiFi 已重新连接，RSSI %d dBm", rssi);
    } else {
        snprintf(detail, sizeof(detail), "以太网接口已重启并重新获取 IP（QEMU 节点没有 WiFi 射频）");
    }
    send_ack(id, true, detail);
}

static void run_interval(const char *id, const cJSON *params)
{
    const cJSON *seconds = cJSON_GetObjectItemCaseSensitive(params, "seconds");
    if (!cJSON_IsNumber(seconds) || seconds->valuedouble != (double)(int)seconds->valuedouble ||
        seconds->valueint < 1 || seconds->valueint > 3600) {
        send_ack(id, false, "seconds 必须是 1-3600 的整数");
        return;
    }
    esp_err_t err = config_set_interval((uint32_t)seconds->valueint);
    if (err != ESP_OK) {
        char detail[96];
        snprintf(detail, sizeof(detail), "写入 NVS 失败：%s", esp_err_to_name(err));
        send_ack(id, false, detail);
        return;
    }
    char detail[64];
    snprintf(detail, sizeof(detail), "上报间隔已调整为 %d 秒", seconds->valueint);
    send_ack(id, true, detail);
}

static void handle(const char *text)
{
    cJSON *root = cJSON_Parse(text);
    if (!cJSON_IsObject(root)) {
        ESP_LOGW(TAG, "ignored a command that is not a JSON object");
        cJSON_Delete(root);
        return;
    }
    const char *id = string_field(root, "command_id");
    const char *action = string_field(root, "action");
    const cJSON *params = cJSON_GetObjectItemCaseSensitive(root, "parameters");
    if (id == NULL || !*id || action == NULL || !*action) {
        send_ack(id ? id : "", false, "command_id 与 action 不能为空");
        goto done;
    }

    const recent_ack_t *previous = find_recent(id);
    if (previous != NULL) {
        ESP_LOGW(TAG, "duplicate delivery of %s, re-sending the earlier ack", id);
        char detail[DETAIL_LEN];
        strlcpy(detail, previous->detail, sizeof(detail));
        send_ack(id, previous->applied, detail);
        goto done;
    }
    if ((strcmp(action, "restart_device") == 0 || strcmp(action, "update_firmware") == 0 ||
         strcmp(action, "rollback_firmware") == 0) &&
        already_rebooted_for(id)) {
        ESP_LOGW(TAG, "%s was executed before the last reboot, acknowledging only", id);
        send_ack(id, true, "命令已在上次重启前执行");
        goto done;
    }

    const char *expires_at = string_field(root, "expires_at");
    if (expires_at != NULL && *expires_at) {
        int64_t expires;
        if (!clock_parse_iso(expires_at, &expires)) {
            send_ack(id, false, "命令有效期无效");
            goto done;
        }
        if (!clock_synced()) {
            ESP_LOGW(TAG, "clock not synchronised, expires_at of %s not enforced", id);
        } else if (expires <= (int64_t)time(NULL)) {
            send_ack(id, false, "命令已过期");
            goto done;
        }
    }

    ESP_LOGI(TAG, "executing %s (%s)", action, id);
    if (strcmp(action, "reconnect_mqtt") == 0) {
        run_reconnect_mqtt(id);
    } else if (strcmp(action, "reconnect_wifi") == 0) {
        run_reconnect_network(id);
    } else if (strcmp(action, "calibrate_sensor") == 0) {
        char detail[128];
        esp_err_t err = sensor_calibrate(detail, sizeof(detail));
        send_ack(id, err == ESP_OK, detail);
    } else if (strcmp(action, "set_reporting_interval") == 0) {
        run_interval(id, params);
    } else if (strcmp(action, "restart_device") == 0) {
        run_restart(id);
    } else if (strcmp(action, "update_firmware") == 0) {
        run_update(id, params);
    } else if (strcmp(action, "rollback_firmware") == 0) {
        run_rollback(id);
    } else if (strcmp(action, "set_mqtt_keepalive") == 0) {
        run_keepalive(id, params);
    } else if (strcmp(action, "inject_fault") == 0) {
        char detail[DETAIL_LEN];
        const char *scenario = string_field(params, "scenario");
        esp_err_t err = drill_start(scenario ? scenario : "", detail, sizeof(detail));
        send_ack(id, err == ESP_OK, detail);
    } else {
        char detail[96];
        snprintf(detail, sizeof(detail), "不支持的动作: %s", action);
        send_ack(id, false, detail);
    }
    report_now();

done:
    cJSON_Delete(root);
}

static void command_task(void *arg)
{
    command_msg_t msg;
    for (;;) {
        if (xQueueReceive(s_queue, &msg, portMAX_DELAY) == pdTRUE) {
            handle(msg.data);
            free(msg.data);
        }
    }
}

void commands_start(void)
{
    s_queue = xQueueCreate(8, sizeof(command_msg_t));
    xTaskCreate(command_task, "commands", 8192, NULL, 5, NULL);
}
