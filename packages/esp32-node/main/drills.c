/*
 * Fault drills (inject_fault). Each one makes the firmware genuinely misbehave
 * so the platform sees the real symptoms: a heap that actually shrinks, a task
 * watchdog that actually fires, a panic with a real core dump.
 *
 * Network faults are deliberately absent: they are injected on the network
 * (Toxiproxy for QEMU, Wokwi or a real access point for WiFi).
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "esp_app_desc.h"
#include "esp_log.h"
#include "esp_random.h"
#include "esp_system.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "node.h"

static const char *TAG = "drill";

#define LEAK_CHUNK 512
#define LEAK_FLOOR (24 * 1024)
#define LEAK_FAST_PERIOD_MS 250   /* inject_fault: about 2 KB/s, minutes to exhaustion */
#define LEAK_SLOW_PERIOD_MS 10000 /* factory boot fault: about an hour to exhaustion */

static TaskHandle_t s_leak_task;
static TaskHandle_t s_hog_task;
static volatile bool s_leak_enabled;
static volatile uint32_t s_leak_period_ms = LEAK_FAST_PERIOD_MS;

static void leak_task(void *arg)
{
    size_t leaked = 0;
    bool exhausted = false;
    for (;;) {
        if (!s_leak_enabled) {
            vTaskDelay(pdMS_TO_TICKS(1000));
            continue;
        }
        if (esp_get_free_heap_size() <= LEAK_FLOOR) {
            if (!exhausted) {
                char message[160];
                snprintf(message, sizeof(message),
                         "heap: Allocation failed, out of memory（空闲堆 %lu 字节，已泄漏 %u 字节）",
                         (unsigned long)esp_get_free_heap_size(), (unsigned)leaked);
                ESP_LOGE("heap", "%s", message);
                logfwd_fault("out_of_memory", message);
                exhausted = true;
            }
        } else {
            void *block = malloc(LEAK_CHUNK); /* intentionally never freed */
            if (block != NULL) {
                memset(block, 0xA5, LEAK_CHUNK);
                leaked += LEAK_CHUNK;
            }
        }
        vTaskDelay(pdMS_TO_TICKS(s_leak_period_ms));
    }
}

static void hog_task(void *arg)
{
    uint32_t delay_s = (uint32_t)(uintptr_t)arg;
    ESP_LOGW(TAG, "watchdog drill armed: data_worker will monopolise CPU0 in %lu s",
             (unsigned long)delay_s);
    vTaskDelay(pdMS_TO_TICKS(delay_s * 1000));
    ESP_LOGW(TAG, "data_worker entering a busy loop without yielding");
    vTaskDelay(pdMS_TO_TICKS(500));
    volatile uint32_t spins = 0;
    for (;;) {
        spins++;
    }
}

static void start_leak(uint32_t period_ms)
{
    s_leak_period_ms = period_ms;
    s_leak_enabled = true;
    if (s_leak_task == NULL) {
        xTaskCreate(leak_task, "cache_worker", 3072, NULL, 3, &s_leak_task);
    }
}

static void start_hog(uint32_t delay_s)
{
    if (s_hog_task == NULL) {
        xTaskCreatePinnedToCore(hog_task, "data_worker", 3072, (void *)(uintptr_t)delay_s, 3,
                                &s_hog_task, 0);
    }
}

static void panic_task(void *arg)
{
    vTaskDelay(pdMS_TO_TICKS(2000));
    ESP_LOGW(TAG, "writing through a NULL pointer");
    volatile uint32_t *target = NULL;
    *target = 0xDEADBEEF;
    vTaskDelete(NULL);
}

esp_err_t drill_start(const char *scenario, char *detail, size_t len)
{
    const char *running = esp_app_get_description()->version;
    if (strcmp(scenario, "memory_leak") == 0) {
        start_leak(LEAK_FAST_PERIOD_MS);
        snprintf(detail, len, "已开始真实堆泄漏：每秒约 %d 字节，底线 %d 字节，重启后消失",
                 LEAK_CHUNK * 1000 / LEAK_FAST_PERIOD_MS, LEAK_FLOOR);
    } else if (strcmp(scenario, "watchdog_reset") == 0) {
        esp_err_t err = config_set_boot_fault("watchdog_reset", running);
        if (err != ESP_OK) {
            snprintf(detail, len, "写入 NVS 失败：%s", esp_err_to_name(err));
            return err;
        }
        start_hog(10);
        snprintf(detail, len,
                 "固件 %s 将在每次启动后触发任务看门狗并重启，升级到其他版本或注入 normal 后解除",
                 running);
    } else if (strcmp(scenario, "panic") == 0) {
        xTaskCreate(panic_task, "panic_drill", 2048, NULL, 5, NULL);
        snprintf(detail, len, "2 秒后写空指针触发 StoreProhibited，设备将生成 core dump 并重启");
    } else if (strcmp(scenario, "sensor_error") == 0) {
        sensor_set_bus_fault(true);
        snprintf(detail, len, "传感器驱动开始返回总线超时，calibrate_sensor 或重启后恢复");
    } else if (strcmp(scenario, "normal") == 0) {
        s_leak_enabled = false;
        sensor_set_bus_fault(false);
        config_set_boot_fault("", "");
        snprintf(detail, len, "已停止演练并清除启动故障；已泄漏的内存需重启后释放%s",
                 s_hog_task ? "；看门狗演练任务已在运行，将在本次复位后停止" : "");
    } else if (strcmp(scenario, "mqtt_timeout") == 0 || strcmp(scenario, "unstable") == 0 ||
               strcmp(scenario, "wifi_weak") == 0) {
        snprintf(detail, len, "%s 属于网络故障，不在固件中伪造：QEMU 节点用 Toxiproxy 注入，弱信号用 Wokwi 或真机",
                 scenario);
        return ESP_ERR_NOT_SUPPORTED;
    } else {
        snprintf(detail, len, "scenario 必须是 memory_leak、watchdog_reset、panic、sensor_error、normal 之一");
        return ESP_ERR_INVALID_ARG;
    }
    ESP_LOGW(TAG, "drill %s started", scenario);
    return ESP_OK;
}

void drill_apply_boot_fault(void)
{
    if (g_node.boot_fault[0] == '\0') {
        return;
    }
    const char *running = esp_app_get_description()->version;
    if (g_node.fault_firmware[0] != '\0' && strcmp(g_node.fault_firmware, running) != 0) {
        ESP_LOGI(TAG, "boot fault %s belongs to firmware %s, not active on %s", g_node.boot_fault,
                 g_node.fault_firmware, running);
        return;
    }
    if (strcmp(g_node.boot_fault, "watchdog_reset") == 0) {
        start_hog(40 + esp_random() % 51);
    } else if (strcmp(g_node.boot_fault, "memory_leak") == 0) {
        start_leak(LEAK_SLOW_PERIOD_MS);
        ESP_LOGW(TAG, "boot fault memory_leak active on firmware %s", running);
    } else if (strcmp(g_node.boot_fault, "sensor_error") == 0) {
        sensor_set_bus_fault(true);
        ESP_LOGW(TAG, "boot fault sensor_error active on firmware %s", running);
    } else {
        ESP_LOGW(TAG, "unknown boot fault %s ignored", g_node.boot_fault);
    }
}
