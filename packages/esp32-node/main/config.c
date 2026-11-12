/*
 * Factory data lives in the read-only NVS namespace "factory" (written by the
 * provisioning step, like a production line would). Settings changed at run
 * time live in the "node" namespace and survive reboots and OTA updates.
 */
#include <string.h>

#include "esp_log.h"
#include "nvs.h"
#include "nvs_flash.h"
#include "sdkconfig.h"

#include "node.h"

static const char *TAG = "config";

node_config_t g_node;

static void read_str(nvs_handle_t handle, const char *key, char *out, size_t len,
                     const char *fallback)
{
    size_t size = len;
    if (handle == 0 || nvs_get_str(handle, key, out, &size) != ESP_OK) {
        strlcpy(out, fallback, len);
    }
}

static uint32_t read_u32(nvs_handle_t handle, const char *key, uint32_t fallback)
{
    uint32_t value = 0;
    return handle != 0 && nvs_get_u32(handle, key, &value) == ESP_OK ? value : fallback;
}

static int32_t read_i32(nvs_handle_t handle, const char *key, int32_t fallback)
{
    int32_t value = 0;
    return handle != 0 && nvs_get_i32(handle, key, &value) == ESP_OK ? value : fallback;
}

esp_err_t config_load(void)
{
    esp_err_t err = nvs_flash_init();
    if (err == ESP_ERR_NVS_NO_FREE_PAGES || err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_LOGW(TAG, "NVS partition unusable (%s), erasing; factory data is lost",
                 esp_err_to_name(err));
        ESP_ERROR_CHECK(nvs_flash_erase());
        err = nvs_flash_init();
    }
    if (err != ESP_OK) {
        return err;
    }

    nvs_handle_t factory = 0;
    if (nvs_open("factory", NVS_READONLY, &factory) != ESP_OK) {
        ESP_LOGW(TAG, "factory namespace missing, using Kconfig defaults");
        factory = 0;
    }
    read_str(factory, "device_id", g_node.device_id, sizeof(g_node.device_id),
             CONFIG_XIAOYI_DEFAULT_DEVICE_ID);
    read_str(factory, "name", g_node.name, sizeof(g_node.name), CONFIG_XIAOYI_DEFAULT_DEVICE_NAME);
    read_str(factory, "broker_uri", g_node.broker_uri, sizeof(g_node.broker_uri),
             CONFIG_XIAOYI_DEFAULT_BROKER_URI);
    read_str(factory, "ota_base", g_node.ota_base_url, sizeof(g_node.ota_base_url),
             CONFIG_XIAOYI_DEFAULT_OTA_BASE_URL);
    uint32_t factory_interval = read_u32(factory, "interval", CONFIG_XIAOYI_DEFAULT_INTERVAL_S);
    g_node.temp_base_deci = read_i32(factory, "temp_base", CONFIG_XIAOYI_DEFAULT_TEMP_BASE_DECI);
    g_node.keepalive_s = read_u32(factory, "keepalive", CONFIG_XIAOYI_MQTT_KEEPALIVE_S);
    char factory_fault[24];
    char factory_fault_fw[32];
    read_str(factory, "boot_fault", factory_fault, sizeof(factory_fault), "");
    read_str(factory, "fault_fw", factory_fault_fw, sizeof(factory_fault_fw), "");
    if (factory != 0) {
        nvs_close(factory);
    }

    nvs_handle_t runtime;
    err = nvs_open("node", NVS_READWRITE, &runtime);
    if (err != ESP_OK) {
        return err;
    }
    g_node.interval_s = read_u32(runtime, "interval", factory_interval);
    g_node.keepalive_s = read_u32(runtime, "keepalive", g_node.keepalive_s);
    uint8_t calibrated = 0;
    nvs_get_u8(runtime, "calibrated", &calibrated);
    g_node.sensor_calibrated = calibrated != 0;

    /* The runtime copy of the boot fault wins once a drill or "normal" wrote it. */
    uint8_t fault_overridden = 0;
    nvs_get_u8(runtime, "fault_set", &fault_overridden);
    if (fault_overridden) {
        read_str(runtime, "boot_fault", g_node.boot_fault, sizeof(g_node.boot_fault), "");
        read_str(runtime, "fault_fw", g_node.fault_firmware, sizeof(g_node.fault_firmware), "");
    } else {
        strlcpy(g_node.boot_fault, factory_fault, sizeof(g_node.boot_fault));
        strlcpy(g_node.fault_firmware, factory_fault_fw, sizeof(g_node.fault_firmware));
    }

    uint32_t boots = 0;
    nvs_get_u32(runtime, "boot_count", &boots);
    g_node.boot_count = boots + 1;
    nvs_set_u32(runtime, "boot_count", g_node.boot_count);
    err = nvs_commit(runtime);
    nvs_close(runtime);
    return err;
}

static esp_err_t with_runtime(esp_err_t (*apply)(nvs_handle_t, const void *), const void *arg)
{
    nvs_handle_t runtime;
    esp_err_t err = nvs_open("node", NVS_READWRITE, &runtime);
    if (err != ESP_OK) {
        return err;
    }
    err = apply(runtime, arg);
    if (err == ESP_OK) {
        err = nvs_commit(runtime);
    }
    nvs_close(runtime);
    return err;
}

static esp_err_t apply_interval(nvs_handle_t handle, const void *arg)
{
    return nvs_set_u32(handle, "interval", *(const uint32_t *)arg);
}

esp_err_t config_set_interval(uint32_t seconds)
{
    esp_err_t err = with_runtime(apply_interval, &seconds);
    if (err == ESP_OK) {
        g_node.interval_s = seconds;
    }
    return err;
}

static esp_err_t apply_keepalive(nvs_handle_t handle, const void *arg)
{
    return nvs_set_u32(handle, "keepalive", *(const uint32_t *)arg);
}

esp_err_t config_set_keepalive(uint32_t seconds)
{
    esp_err_t err = with_runtime(apply_keepalive, &seconds);
    if (err == ESP_OK) {
        g_node.keepalive_s = seconds;
    }
    return err;
}

static esp_err_t apply_calibrated(nvs_handle_t handle, const void *arg)
{
    return nvs_set_u8(handle, "calibrated", *(const bool *)arg ? 1 : 0);
}

esp_err_t config_set_calibrated(bool calibrated)
{
    esp_err_t err = with_runtime(apply_calibrated, &calibrated);
    if (err == ESP_OK) {
        g_node.sensor_calibrated = calibrated;
    }
    return err;
}

typedef struct {
    const char *scenario;
    const char *firmware;
} boot_fault_args_t;

static esp_err_t apply_boot_fault(nvs_handle_t handle, const void *arg)
{
    const boot_fault_args_t *fault = arg;
    esp_err_t err = nvs_set_str(handle, "boot_fault", fault->scenario);
    if (err == ESP_OK) {
        err = nvs_set_str(handle, "fault_fw", fault->firmware);
    }
    if (err == ESP_OK) {
        err = nvs_set_u8(handle, "fault_set", 1);
    }
    return err;
}

esp_err_t config_set_boot_fault(const char *scenario, const char *firmware)
{
    boot_fault_args_t args = {.scenario = scenario, .firmware = firmware};
    esp_err_t err = with_runtime(apply_boot_fault, &args);
    if (err == ESP_OK) {
        strlcpy(g_node.boot_fault, scenario, sizeof(g_node.boot_fault));
        strlcpy(g_node.fault_firmware, firmware, sizeof(g_node.fault_firmware));
    }
    return err;
}

esp_err_t config_get_str(const char *key, char *out, size_t len)
{
    nvs_handle_t runtime;
    esp_err_t err = nvs_open("node", NVS_READONLY, &runtime);
    if (err != ESP_OK) {
        return err;
    }
    size_t size = len;
    err = nvs_get_str(runtime, key, out, &size);
    nvs_close(runtime);
    return err;
}

typedef struct {
    const char *key;
    const char *value;
} str_args_t;

static esp_err_t apply_str(nvs_handle_t handle, const void *arg)
{
    const str_args_t *pair = arg;
    return nvs_set_str(handle, pair->key, pair->value);
}

esp_err_t config_set_str(const char *key, const char *value)
{
    str_args_t args = {.key = key, .value = value};
    return with_runtime(apply_str, &args);
}
