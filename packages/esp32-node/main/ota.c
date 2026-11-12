#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "esp_app_desc.h"
#include "esp_http_client.h"
#include "esp_https_ota.h"
#include "esp_log.h"
#include "esp_ota_ops.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "node.h"

static const char *TAG = "ota";

/*
 * An interrupted download leaves a valid-looking image header in the slot, so the header
 * alone does not prove the slot can boot. NVS remembers, per slot, the version known to be
 * complete: the running image, or one whose download finished and verified.
 */
static void slot_key(const esp_partition_t *slot, char *key, size_t len)
{
    snprintf(key, len, "slot_%d", (int)(slot->subtype - ESP_PARTITION_SUBTYPE_APP_OTA_MIN) & 0xf);
}

static bool slot_holds(const esp_partition_t *slot, const char *version)
{
    char key[16];
    char recorded[32] = "";
    slot_key(slot, key, sizeof(key));
    return config_get_str(key, recorded, sizeof(recorded)) == ESP_OK &&
           strcmp(recorded, version) == 0;
}

static void mark_slot(const esp_partition_t *slot, const char *version)
{
    if (slot_holds(slot, version)) {
        return;
    }
    char key[16];
    slot_key(slot, key, sizeof(key));
    config_set_str(key, version);
}

void ota_record_running_slot(void)
{
    mark_slot(esp_ota_get_running_partition(), esp_app_get_description()->version);
}

esp_err_t ota_update(const char *version, char *detail, size_t len)
{
    char url[200];
    snprintf(url, sizeof(url), "%s/xiaoyi-node-%s.bin", g_node.ota_base_url, version);
    ESP_LOGI(TAG, "downloading %s", url);

    esp_http_client_config_t http = {
        .url = url,
        .timeout_ms = 15000,
        .keep_alive_enable = true,
    };
    esp_https_ota_config_t config = {.http_config = &http};
    esp_https_ota_handle_t handle = NULL;
    const esp_partition_t *target = esp_ota_get_next_update_partition(NULL);
    if (target != NULL) {
        mark_slot(target, ""); /* about to be overwritten: no longer a rollback target */
    }
    esp_err_t err = esp_https_ota_begin(&config, &handle);
    if (err != ESP_OK) {
        snprintf(detail, len, "无法从 OTA 服务器获取固件 %s：%s", version, esp_err_to_name(err));
        return err;
    }

    esp_app_desc_t incoming;
    err = esp_https_ota_get_img_desc(handle, &incoming);
    if (err != ESP_OK) {
        snprintf(detail, len, "读取镜像描述失败：%s", esp_err_to_name(err));
        esp_https_ota_abort(handle);
        return err;
    }
    if (strcmp(incoming.version, version) != 0) {
        snprintf(detail, len, "服务器镜像内版本为 %s，与请求的 %s 不一致，已放弃写入",
                 incoming.version, version);
        esp_https_ota_abort(handle);
        return ESP_ERR_INVALID_VERSION;
    }

    int reported = -1;
    while ((err = esp_https_ota_perform(handle)) == ESP_ERR_HTTPS_OTA_IN_PROGRESS) {
        int total = esp_https_ota_get_image_size(handle);
        int read = esp_https_ota_get_image_len_read(handle);
        int percent = total > 0 ? read * 100 / total : 0;
        if (percent / 25 != reported) {
            reported = percent / 25;
            ESP_LOGI(TAG, "firmware %s: %d%% (%d/%d bytes)", version, percent, read, total);
        }
    }
    if (err != ESP_OK || !esp_https_ota_is_complete_data_received(handle)) {
        snprintf(detail, len, "固件下载中断：%s", esp_err_to_name(err));
        esp_https_ota_abort(handle);
        return err != ESP_OK ? err : ESP_FAIL;
    }
    err = esp_https_ota_finish(handle);
    if (err != ESP_OK) {
        snprintf(detail, len, "镜像校验失败：%s", esp_err_to_name(err));
        return err;
    }
    const esp_partition_t *next = esp_ota_get_boot_partition();
    if (next != NULL) {
        mark_slot(next, version);
    }
    snprintf(detail, len, "固件 %s 已写入 %s 分区，重启后生效", version, next ? next->label : "?");
    return ESP_OK;
}

/* The other OTA slot, if it holds an image the bootloader is still allowed to start. */
static const esp_partition_t *previous_slot(esp_app_desc_t *desc)
{
    const esp_partition_t *running = esp_ota_get_running_partition();
    const esp_partition_t *other = esp_ota_get_next_update_partition(running);
    if (other == NULL || other == running) {
        return NULL;
    }
    esp_ota_img_states_t state;
    if (esp_ota_get_state_partition(other, &state) == ESP_OK &&
        (state == ESP_OTA_IMG_INVALID || state == ESP_OTA_IMG_ABORTED)) {
        return NULL; /* a release that already failed its self-test is never offered again */
    }
    if (esp_ota_get_partition_description(other, desc) != ESP_OK) {
        return NULL;
    }
    return slot_holds(other, desc->version) ? other : NULL; /* not a half-written download */
}

const char *ota_rollback_version(void)
{
    static bool checked;
    static esp_app_desc_t desc;
    static bool available;
    if (!checked) {
        available = previous_slot(&desc) != NULL;
        checked = true;
    }
    return available ? desc.version : NULL;
}

esp_err_t ota_select_previous(char *detail, size_t len)
{
    esp_app_desc_t desc;
    const esp_partition_t *other = previous_slot(&desc);
    if (other == NULL) {
        snprintf(detail, len, "另一个 OTA 分区没有可以启动的旧固件，无法回退");
        return ESP_ERR_NOT_FOUND;
    }
    ESP_LOGW(TAG, "switching boot partition to %s (firmware %s)", other->label, desc.version);
    esp_err_t err = esp_ota_set_boot_partition(other);
    if (err != ESP_OK) {
        snprintf(detail, len, "切换启动分区失败：%s", esp_err_to_name(err));
        return err;
    }
    snprintf(detail, len, "已切换到 %s 分区的固件 %s，重启后生效", other->label, desc.version);
    return ESP_OK;
}

void ota_confirm_running_image(void)
{
#ifdef XIAOYI_FAULTY_BUILD
    /* Release used to rehearse rollback: it never passes its own self-test. */
    ESP_LOGE("app", "self-test failed: sensor bus pin map missing from this build");
    vTaskDelay(pdMS_TO_TICKS(3000));
    abort();
#endif
    const esp_partition_t *running = esp_ota_get_running_partition();
    esp_ota_img_states_t state;
    if (esp_ota_get_state_partition(running, &state) != ESP_OK ||
        state != ESP_OTA_IMG_PENDING_VERIFY) {
        return;
    }
    esp_err_t err = esp_ota_mark_app_valid_cancel_rollback();
    if (err == ESP_OK) {
        ESP_LOGI(TAG, "firmware %s confirmed after reaching the broker, rollback cancelled",
                 esp_app_get_description()->version);
    } else {
        ESP_LOGW(TAG, "could not confirm firmware: %s", esp_err_to_name(err));
    }
}
