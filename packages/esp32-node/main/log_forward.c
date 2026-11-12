/*
 * Ships the device's own ESP-IDF log lines to iot/{id}/logs, so the platform
 * sees exactly what a serial console would show (tags, wording, error codes).
 * Lines are queued while offline and published once MQTT is back.
 */
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/semphr.h"
#include "freertos/task.h"

#include "node.h"

#define QUEUE_DEPTH 48

typedef struct {
    bool fault;
    char level[8];
    char tag[24]; /* module for logs, fault_type for faults */
    char message[LOGFWD_MESSAGE_LEN];
    int64_t epoch_ms; /* 0 when captured before SNTP sync */
    uint32_t uptime_ms;
} logfwd_item_t;

static QueueHandle_t s_queue;
static SemaphoreHandle_t s_lock;
static vprintf_like_t s_console;
static volatile uint32_t s_dropped;
static char s_line[256];
static logfwd_item_t s_scratch;

/* INFO lines are forwarded only for this firmware's own modules. */
static bool forward_info(const char *tag)
{
    static const char *const ours[] = {"app",    "boot",  "clock", "cmd", "config", "drill",
                                       "heap",   "link",  "net",   "ota", "report", "sensor"};
    for (size_t i = 0; i < sizeof(ours) / sizeof(ours[0]); i++) {
        if (strcmp(tag, ours[i]) == 0) {
            return true;
        }
    }
    return false;
}

/* Drops a multi-byte UTF-8 character cut in half at the end of s, so a
 * truncated Chinese message still serialises to valid JSON. */
static void trim_partial_utf8(char *s)
{
    size_t len = strlen(s);
    size_t lead = len;
    while (lead > 0 && len - lead < 4 && ((unsigned char)s[lead - 1] & 0xC0) == 0x80) {
        lead--;
    }
    if (lead == 0) {
        return;
    }
    unsigned char first = (unsigned char)s[lead - 1];
    size_t need = first >= 0xF0 ? 4 : first >= 0xE0 ? 3 : first >= 0xC0 ? 2 : 1;
    if (len - (lead - 1) < need) {
        s[lead - 1] = '\0';
    }
}

/* Callers may hand over text their own snprintf already cut, so always trim. */
static void copy_message(char *dst, const char *src, size_t size)
{
    strlcpy(dst, src, size);
    trim_partial_utf8(dst);
}

static void enqueue(const logfwd_item_t *item)
{
    if (s_queue == NULL || xQueueSend(s_queue, item, 0) != pdTRUE) {
        s_dropped++;
    }
}

/* Parses "L (12345) tag: message" produced by ESP_LOGx. */
static void capture(void)
{
    char *line = s_line;
    char level = line[0];
    if ((level != 'E' && level != 'W' && level != 'I') || line[1] != ' ' || line[2] != '(') {
        return;
    }
    char *close = strchr(line + 3, ')');
    if (close == NULL || close[1] != ' ') {
        return;
    }
    char *tag = close + 2;
    char *separator = strstr(tag, ": ");
    if (separator == NULL) {
        return;
    }
    *separator = '\0';
    if (level == 'I' && !forward_info(tag)) {
        return;
    }
    char *message = separator + 2;
    size_t len = strlen(message);
    while (len > 0 && (message[len - 1] == '\n' || message[len - 1] == '\r')) {
        message[--len] = '\0';
    }

    logfwd_item_t *item = &s_scratch;
    memset(item, 0, sizeof(*item));
    strlcpy(item->level, level == 'E' ? "ERROR" : level == 'W' ? "WARNING" : "INFO",
            sizeof(item->level));
    strlcpy(item->tag, tag, sizeof(item->tag));
    copy_message(item->message, message, sizeof(item->message));
    item->uptime_ms = (uint32_t)strtoul(line + 3, NULL, 10);
    item->epoch_ms = clock_epoch_ms();
    enqueue(item);
}

static int hook(const char *format, va_list args)
{
    va_list console_args;
    va_copy(console_args, args);
    int written = s_console ? s_console(format, console_args) : vprintf(format, console_args);
    va_end(console_args);

    /* Never block a logging task; skip forwarding if another task holds the buffer. */
    if (s_lock != NULL && xSemaphoreTake(s_lock, 0) == pdTRUE) {
        int formatted = vsnprintf(s_line, sizeof(s_line), format, args);
        if (formatted > 0) {
            if ((size_t)formatted >= sizeof(s_line)) {
                trim_partial_utf8(s_line);
            }
            capture();
        }
        xSemaphoreGive(s_lock);
    }
    return written;
}

void logfwd_init(void)
{
    s_queue = xQueueCreate(QUEUE_DEPTH, sizeof(logfwd_item_t));
    s_lock = xSemaphoreCreateMutex();
    s_console = esp_log_set_vprintf(hook);
}

void logfwd_fault(const char *fault_type, const char *message)
{
    logfwd_item_t item = {.fault = true};
    strlcpy(item.level, "ERROR", sizeof(item.level));
    strlcpy(item.tag, fault_type, sizeof(item.tag));
    copy_message(item.message, message, sizeof(item.message));
    item.uptime_ms = esp_log_timestamp(); /* same clock as the "(ms)" of log lines */
    item.epoch_ms = clock_epoch_ms();
    enqueue(&item);
}

static cJSON *render(const logfwd_item_t *item)
{
    cJSON *entry = cJSON_CreateObject();
    int64_t epoch = item->epoch_ms;
    int64_t now = clock_epoch_ms();
    if (epoch == 0 && now != 0) {
        /* Captured before SNTP: backfill on the log line's own clock (esp_log_timestamp
         * counts from CPU start, esp_timer only from app start). */
        epoch = now - (int64_t)(uint32_t)(esp_log_timestamp() - item->uptime_ms);
    }
    if (epoch != 0) {
        char timestamp[40];
        clock_format_ms(epoch, timestamp, sizeof(timestamp));
        cJSON_AddStringToObject(entry, "timestamp", timestamp);
    }
    cJSON_AddStringToObject(entry, "level", item->level);
    cJSON_AddStringToObject(entry, item->fault ? "fault_type" : "module", item->tag);
    cJSON_AddStringToObject(entry, "message", item->message);
    cJSON_AddNumberToObject(entry, "uptime_ms", item->uptime_ms);
    return entry;
}

static void pump(void *arg)
{
    logfwd_item_t item;
    for (;;) {
        if (xQueuePeek(s_queue, &item, portMAX_DELAY) != pdTRUE) {
            continue;
        }
        if (!link_wait_connected(5000)) {
            continue;
        }
        if (!clock_synced() && uptime_s() < 60) {
            /* Shortly after boot, wait for SNTP so the backlog gets real timestamps. */
            vTaskDelay(pdMS_TO_TICKS(1000));
            continue;
        }
        cJSON *entry = render(&item);
        int id = link_publish_json(item.fault ? "fault" : "logs", entry, 1, false);
        cJSON_Delete(entry);
        if (id < 0) {
            vTaskDelay(pdMS_TO_TICKS(1000));
            continue;
        }
        xQueueReceive(s_queue, &item, 0);
        if (s_dropped > 0 && uxQueueMessagesWaiting(s_queue) == 0) {
            uint32_t dropped = s_dropped;
            s_dropped = 0;
            ESP_LOGW("report", "log buffer overflowed, %lu lines were dropped while offline",
                     (unsigned long)dropped);
        }
    }
}

void logfwd_start(void)
{
    xTaskCreate(pump, "log_pump", 4096, NULL, 4, NULL);
}
