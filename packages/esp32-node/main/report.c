/*
 * Periodic status / telemetry / heartbeat, plus the evidence a device can only
 * report after it comes back: why it reset, the core dump summary of a crash,
 * and whether the bootloader rolled back a failed firmware.
 */
#include <inttypes.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "esp_app_desc.h"
#include "esp_bit_defs.h"
#include "esp_core_dump.h"
#include "esp_log.h"
#include "esp_ota_ops.h"
#include "esp_system.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "sdkconfig.h"

#include "node.h"

static const char *TAG = "report";

#define NOTIFY_BIRTH BIT0
#define NOTIFY_NOW BIT1
#define LOW_HEAP_BYTES (48 * 1024)

static TaskHandle_t s_task;
static esp_reset_reason_t s_reset_reason;
static bool s_sensor_failing;
static uint32_t s_sensor_failure_logged_at;

static const char *reset_reason_name(esp_reset_reason_t reason)
{
    switch (reason) {
    case ESP_RST_POWERON: return "POWERON";
    case ESP_RST_EXT: return "EXT";
    case ESP_RST_SW: return "SW";
    case ESP_RST_PANIC: return "PANIC";
    case ESP_RST_INT_WDT: return "INT_WDT";
    case ESP_RST_TASK_WDT: return "TASK_WDT";
    case ESP_RST_WDT: return "WDT";
    case ESP_RST_DEEPSLEEP: return "DEEPSLEEP";
    case ESP_RST_BROWNOUT: return "BROWNOUT";
    case ESP_RST_SDIO: return "SDIO";
    default: return "UNKNOWN";
    }
}

const char *report_reset_reason(void)
{
    return reset_reason_name(s_reset_reason);
}

#if CONFIG_XIAOYI_EMULATED_POWER_CYCLE
/*
 * QEMU restarts the emulator on every reboot (-no-reboot), so the hardware
 * always reports POWERON. Recover the cause from what a real reboot leaves in
 * flash: the core dump's panic reason after a crash, or the NVS marker that
 * reboot() writes before an intentional esp_restart().
 */
static esp_reset_reason_t recover_reset_reason(esp_reset_reason_t hardware, bool has_dump,
                                               const char *panic_reason)
{
    char hint[8] = "";
    config_get_str("rst_hint", hint, sizeof(hint));
    if (hint[0] != '\0') {
        config_set_str("rst_hint", "");
    }
    if (hardware != ESP_RST_POWERON) {
        return hardware;
    }
    if (has_dump) {
        if (strstr(panic_reason, "Task watchdog") != NULL || strstr(panic_reason, "task_wdt") != NULL) {
            return ESP_RST_TASK_WDT;
        }
        if (strstr(panic_reason, "Interrupt wdt") != NULL) {
            return ESP_RST_INT_WDT;
        }
        return ESP_RST_PANIC;
    }
    return strcmp(hint, "SW") == 0 ? ESP_RST_SW : hardware;
}
#endif

/* "Task watchdog got triggered. ...:\n - IDLE0 (CPU 0)\n" -> one line without list bullets. */
static void flatten_panic_reason(char *text)
{
    char *out = text;
    for (const char *in = text; *in != '\0'; in++) {
        char c = (*in == '\n' || *in == '\r') ? ' ' : *in;
        if (c == ' ' && (out == text || out[-1] == ' ')) {
            continue;
        }
        if (c == '-' && out > text && out[-1] == ' ' && in[1] == ' ') {
            continue; /* list bullet */
        }
        *out++ = c;
    }
    while (out > text && out[-1] == ' ') {
        out--;
    }
    *out = '\0';
}

/* Caller has already verified the image with esp_core_dump_image_check(). cpu_exception
 * is false for abort()-style panics (assert, task watchdog), where EXCCAUSE is stale. */
static void describe_core_dump(char *out, size_t len, bool cpu_exception)
{
    out[0] = '\0';
    esp_core_dump_summary_t *summary = calloc(1, sizeof(*summary));
    if (summary == NULL) {
        return;
    }
    if (esp_core_dump_get_summary(summary) == ESP_OK) {
        int used = snprintf(out, len, "，core dump：任务 %s，PC 0x%08" PRIx32, summary->exc_task,
                            summary->exc_pc);
#if CONFIG_IDF_TARGET_ARCH_XTENSA
        if (cpu_exception && used > 0 && (size_t)used < len) {
            used += snprintf(out + used, len - used, "，EXCCAUSE %" PRIu32,
                             summary->ex_info.exc_cause);
        }
#endif
        if (used > 0 && (size_t)used < len) {
            used += snprintf(out + used, len - used, "，回溯");
        }
        /* Only whole " 0x%08x" frames (11 bytes), never a cut-off address. */
        for (uint32_t i = 0; i < summary->exc_bt_info.depth && used > 0 && (size_t)used + 12 <= len;
             i++) {
            used += snprintf(out + used, len - used, " 0x%08" PRIx32, summary->exc_bt_info.bt[i]);
        }
        if (summary->exc_bt_info.corrupted && used > 0 && (size_t)used + 15 <= len) {
            snprintf(out + used, len - used, " |<-CORRUPTED");
        }
    }
    free(summary);
    esp_core_dump_image_erase();
}

void report_boot_evidence(void)
{
    /* Reading the core dump back takes seconds under QEMU's flash emulation. At idle
     * priority the IDLE task keeps running alongside, so the task watchdog is not
     * starved into another crash while the previous one is being reported. */
    UBaseType_t priority = uxTaskPriorityGet(NULL);
    vTaskPrioritySet(NULL, tskIDLE_PRIORITY);

    s_reset_reason = esp_reset_reason();
    bool has_dump = esp_core_dump_image_check() == ESP_OK;
    char panic_reason[160] = "";
    if (has_dump && esp_core_dump_get_panic_reason(panic_reason, sizeof(panic_reason)) != ESP_OK) {
        panic_reason[0] = '\0';
    }
    flatten_panic_reason(panic_reason);
#if CONFIG_XIAOYI_EMULATED_POWER_CYCLE
    s_reset_reason = recover_reset_reason(s_reset_reason, has_dump, panic_reason);
#endif
    const esp_app_desc_t *app = esp_app_get_description();
    const esp_partition_t *running = esp_ota_get_running_partition();
    ESP_LOGI("boot", "xiaoyi-node %s (ESP-IDF %s) device %s boot #%lu, reset_reason=%s, partition=%s",
             app->version, app->idf_ver, g_node.device_id, (unsigned long)g_node.boot_count,
             report_reset_reason(), running ? running->label : "?");

    bool watchdog = s_reset_reason == ESP_RST_TASK_WDT || s_reset_reason == ESP_RST_INT_WDT ||
                    s_reset_reason == ESP_RST_WDT;
    bool crashed = watchdog || s_reset_reason == ESP_RST_PANIC;
    if (crashed || s_reset_reason == ESP_RST_BROWNOUT) {
        char dump[200] = "";
        if (crashed && has_dump) {
            /* Only abort()-style panics record a panic reason. */
            describe_core_dump(dump, sizeof(dump), panic_reason[0] == '\0');
        }
        char message[LOGFWD_MESSAGE_LEN];
        /* Panic reason before the backtrace, so truncation only drops trailing frames. */
        snprintf(message, sizeof(message), "设备异常复位 reset_reason=%s，第 %lu 次启动",
                 report_reset_reason(), (unsigned long)g_node.boot_count);
        if (panic_reason[0] != '\0') {
            strlcat(message, "，panic 原因：", sizeof(message));
            strlcat(message, panic_reason, sizeof(message));
        }
        strlcat(message, dump, sizeof(message));
        logfwd_fault(watchdog                                   ? "watchdog_reset"
                     : s_reset_reason == ESP_RST_BROWNOUT       ? "brownout_reset"
                                                                : "panic_reset",
                     message);
    }

    const esp_partition_t *invalid = esp_ota_get_last_invalid_partition();
    esp_app_desc_t failed;
    if (invalid != NULL && esp_ota_get_partition_description(invalid, &failed) == ESP_OK) {
        char reported[32] = "";
        config_get_str("rollback_seen", reported, sizeof(reported));
        if (strcmp(reported, failed.version) != 0) {
            char message[200];
            snprintf(message, sizeof(message),
                     "固件 %s 在 %s 分区启动后未通过自检，引导程序已回滚到 %s", failed.version,
                     invalid->label, app->version);
            logfwd_fault("ota_rollback", message);
            config_set_str("rollback_seen", failed.version);
        }
    }
    if (has_dump && !crashed) {
        esp_core_dump_image_erase(); /* stale dump from an earlier crash, already reported */
    }
    vTaskPrioritySet(NULL, priority);
}

cJSON *report_status(void)
{
    const esp_app_desc_t *app = esp_app_get_description();
    cJSON *status = cJSON_CreateObject();
    char now[40];
    if (clock_iso_now(now, sizeof(now))) {
        cJSON_AddStringToObject(status, "timestamp", now);
    }
    cJSON_AddBoolToObject(status, "online", true);
    cJSON_AddStringToObject(status, "device_type", "ESP32");
    cJSON_AddStringToObject(status, "name", g_node.name);
    cJSON_AddStringToObject(status, "firmware_version", app->version);
    cJSON_AddStringToObject(status, "idf_version", app->idf_ver);
    cJSON_AddStringToObject(status, "link_type", net_is_wifi() ? "wifi" : "ethernet");
    if (net_is_wifi()) {
        int rssi;
        bool associated = net_rssi(&rssi);
        cJSON_AddStringToObject(status, "wifi_status", associated ? "connected" : "disconnected");
        if (associated) {
            cJSON_AddNumberToObject(status, "rssi", rssi);
        }
    }
    cJSON_AddStringToObject(status, "mqtt_status", "connected");

    float celsius;
    esp_err_t err = sensor_read(&celsius);
    if (err == ESP_OK) {
        cJSON_AddNumberToObject(status, "temperature", round(celsius * 100.0) / 100.0);
        if (s_sensor_failing) {
            ESP_LOGI("sensor", "sensor readings recovered");
        }
        s_sensor_failing = false;
    } else {
        uint32_t now_s = uptime_s();
        if (!s_sensor_failing || now_s - s_sensor_failure_logged_at >= 60) {
            ESP_LOGE("sensor", "sensor read failed: %s", esp_err_to_name(err));
            if (!s_sensor_failing) {
                char message[120];
                snprintf(message, sizeof(message), "传感器读取失败：%s（%s）", esp_err_to_name(err),
                         sensor_backend());
                logfwd_fault("sensor_read_failed", message);
            }
            s_sensor_failure_logged_at = now_s;
        }
        s_sensor_failing = true;
    }
    cJSON_AddBoolToObject(status, "sensor_valid", err == ESP_OK);
    cJSON_AddBoolToObject(status, "sensor_calibrated", g_node.sensor_calibrated);
    cJSON_AddStringToObject(status, "sensor_backend", sensor_backend());
    cJSON_AddNumberToObject(status, "reporting_interval_seconds", g_node.interval_s);
    cJSON_AddNumberToObject(status, "uptime", uptime_s());
    cJSON_AddNumberToObject(status, "free_heap", esp_get_free_heap_size());
    cJSON_AddNumberToObject(status, "min_free_heap", esp_get_minimum_free_heap_size());
    cJSON_AddNumberToObject(status, "boot_count", g_node.boot_count);
    cJSON_AddStringToObject(status, "reset_reason", report_reset_reason());
    cJSON_AddNumberToObject(status, "mqtt_reconnects", link_reconnects());
    cJSON_AddNumberToObject(status, "mqtt_keepalive_seconds", g_node.keepalive_s);
    const char *rollback = ota_rollback_version();
    if (rollback != NULL) {
        cJSON_AddStringToObject(status, "rollback_version", rollback);
    }
    return status;
}

static void publish_cycle(bool birth)
{
    cJSON *status = report_status();
    char *text = cJSON_PrintUnformatted(status);
    cJSON_Delete(status);
    if (text == NULL) {
        return;
    }
    if (birth) {
        /* Retained "birth" status replaces the retained last will. */
        link_publish("status", text, 1, true);
    }
    link_publish("status", text, 1, false);
    link_publish("telemetry", text, 1, false);
    cJSON_free(text);

    cJSON *heartbeat = cJSON_CreateObject();
    char now[40];
    if (clock_iso_now(now, sizeof(now))) {
        cJSON_AddStringToObject(heartbeat, "timestamp", now);
    }
    cJSON_AddBoolToObject(heartbeat, "online", true);
    cJSON_AddNumberToObject(heartbeat, "uptime", uptime_s());
    link_publish_json("heartbeat", heartbeat, 1, false);
    cJSON_Delete(heartbeat);

    uint32_t free_heap = esp_get_free_heap_size();
    if (free_heap < LOW_HEAP_BYTES) {
        ESP_LOGW("heap", "free heap %lu bytes, min ever %lu bytes", (unsigned long)free_heap,
                 (unsigned long)esp_get_minimum_free_heap_size());
    }
}

static void report_task(void *arg)
{
    /* The first connection may complete before this task exists, so the first
     * status published is always the retained birth that replaces the will. */
    bool birth = true;
    for (;;) {
        if (link_connected()) {
            publish_cycle(birth);
            birth = false;
        }
        uint32_t notified = 0;
        xTaskNotifyWait(0, UINT32_MAX, &notified, pdMS_TO_TICKS(g_node.interval_s * 1000));
        if (notified & NOTIFY_BIRTH) {
            birth = true;
        }
    }
}

void report_start(void)
{
    xTaskCreate(report_task, "report", 5120, NULL, 5, &s_task);
}

void report_now(void)
{
    if (s_task) {
        xTaskNotify(s_task, NOTIFY_NOW, eSetBits);
    }
}

void report_birth(void)
{
    if (s_task) {
        xTaskNotify(s_task, NOTIFY_BIRTH, eSetBits);
    } else {
        ESP_LOGD(TAG, "birth requested before report task started");
    }
}
