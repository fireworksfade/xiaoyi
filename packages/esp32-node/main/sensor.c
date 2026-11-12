/*
 * Temperature sensor backends.
 *
 * - model (QEMU): QEMU emulates no sensor peripheral, so readings come from a
 *   small thermal model (baseline + slow daily-like swing + noise). It is
 *   reported as sensor_backend="model" and never presented as a real sensor.
 * - ntc_adc (Wokwi / real board): NTC thermistor divider on ADC1, read with
 *   the oneshot driver and ADC calibration when the eFuse data is available.
 */
#include <math.h>
#include <stdio.h>

#include "esp_log.h"
#include "esp_random.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "sdkconfig.h"

#if CONFIG_XIAOYI_SENSOR_NTC
#include "esp_adc/adc_cali.h"
#include "esp_adc/adc_cali_scheme.h"
#include "esp_adc/adc_oneshot.h"
#endif

#include "node.h"

static const char *TAG = "sensor";

static bool s_bus_fault;
static bool s_valid;
static SemaphoreHandle_t s_lock; /* report task reads while the command task may re-init */

void sensor_set_bus_fault(bool fault)
{
    s_bus_fault = fault;
}

bool sensor_valid(void)
{
    return s_valid;
}

#if CONFIG_XIAOYI_SENSOR_MODEL

const char *sensor_backend(void)
{
    return "model";
}

esp_err_t sensor_init(void)
{
    s_lock = xSemaphoreCreateMutex();
    ESP_LOGI(TAG, "thermal model sensor, baseline %.1f C (QEMU has no sensor peripheral)",
             g_node.temp_base_deci / 10.0);
    return ESP_OK;
}

static esp_err_t read_backend(float *celsius)
{
    const float base = g_node.temp_base_deci / 10.0f;
    const float swing = 0.8f * sinf(2.0f * (float)M_PI * (float)(uptime_s() % 600) / 600.0f);
    const float noise = ((float)(esp_random() % 61) - 30.0f) / 100.0f;
    *celsius = base + swing + noise;
    return ESP_OK;
}

static esp_err_t reinit_backend(void)
{
    return ESP_OK;
}

#else /* NTC on ADC1 */

static adc_oneshot_unit_handle_t s_adc;
static adc_cali_handle_t s_cali;

const char *sensor_backend(void)
{
    return "ntc_adc";
}

static esp_err_t open_adc(void)
{
    adc_oneshot_unit_init_cfg_t unit = {.unit_id = ADC_UNIT_1};
    esp_err_t err = adc_oneshot_new_unit(&unit, &s_adc);
    if (err != ESP_OK) {
        return err;
    }
    adc_oneshot_chan_cfg_t channel = {.atten = ADC_ATTEN_DB_12, .bitwidth = ADC_BITWIDTH_12};
    err = adc_oneshot_config_channel(s_adc, CONFIG_XIAOYI_NTC_ADC_CHANNEL, &channel);
    if (err != ESP_OK) {
        return err;
    }
    adc_cali_line_fitting_config_t cali = {
        .unit_id = ADC_UNIT_1,
        .atten = ADC_ATTEN_DB_12,
        .bitwidth = ADC_BITWIDTH_12,
        .default_vref = 1100,
    };
    err = adc_cali_create_scheme_line_fitting(&cali, &s_cali);
    if (err != ESP_OK) {
        s_cali = NULL;
        ESP_LOGW(TAG, "ADC calibration unavailable (%s), using the raw ratiometric reading",
                 esp_err_to_name(err));
    }
    return ESP_OK;
}

static void close_adc(void)
{
    if (s_cali != NULL) {
        adc_cali_delete_scheme_line_fitting(s_cali);
        s_cali = NULL;
    }
    if (s_adc != NULL) {
        adc_oneshot_del_unit(s_adc);
        s_adc = NULL;
    }
}

esp_err_t sensor_init(void)
{
    s_lock = xSemaphoreCreateMutex();
    esp_err_t err = open_adc();
    if (err == ESP_OK) {
        ESP_LOGI(TAG, "NTC thermistor on ADC1 channel %d, beta %d", CONFIG_XIAOYI_NTC_ADC_CHANNEL,
                 CONFIG_XIAOYI_NTC_BETA);
    } else {
        ESP_LOGE(TAG, "ADC init failed: %s", esp_err_to_name(err));
    }
    return err;
}

static esp_err_t read_backend(float *celsius)
{
    if (s_adc == NULL) {
        return ESP_ERR_INVALID_STATE;
    }
    int raw = 0;
    esp_err_t err = adc_oneshot_read(s_adc, CONFIG_XIAOYI_NTC_ADC_CHANNEL, &raw);
    if (err != ESP_OK) {
        return err;
    }
    if (raw <= 8 || raw >= 4087) {
        /* Rail-to-rail reading: divider open or shorted. */
        ESP_LOGW(TAG, "NTC reading at rail (raw=%d): open or short circuit", raw);
        return ESP_ERR_INVALID_RESPONSE;
    }
    const float beta = CONFIG_XIAOYI_NTC_BETA;
    *celsius = 1.0f / (logf(1.0f / (4095.0f / raw - 1.0f)) / beta + 1.0f / 298.15f) - 273.15f;
    return ESP_OK;
}

static esp_err_t reinit_backend(void)
{
    close_adc();
    return open_adc();
}

#endif

static esp_err_t read_locked(float *celsius)
{
    esp_err_t err = s_bus_fault ? ESP_ERR_TIMEOUT : read_backend(celsius);
    s_valid = err == ESP_OK;
    return err;
}

esp_err_t sensor_read(float *celsius)
{
    xSemaphoreTake(s_lock, portMAX_DELAY);
    esp_err_t err = read_locked(celsius);
    xSemaphoreGive(s_lock);
    return err;
}

esp_err_t sensor_calibrate(char *detail, size_t len)
{
    float celsius = 0;
    xSemaphoreTake(s_lock, portMAX_DELAY);
    s_bus_fault = false;
    esp_err_t err = reinit_backend();
    if (err == ESP_OK) {
        err = read_locked(&celsius);
    }
    xSemaphoreGive(s_lock);
    if (err != ESP_OK) {
        snprintf(detail, len, "重新初始化传感器后仍无法读取：%s", esp_err_to_name(err));
        return err;
    }
    err = config_set_calibrated(true);
    if (err != ESP_OK) {
        snprintf(detail, len, "读数已恢复，但校准记录写入 NVS 失败：%s", esp_err_to_name(err));
        return err;
    }
    snprintf(detail, len, "传感器已重新初始化并记录校准，当前读数 %.2f °C（%s）", celsius,
             sensor_backend());
    return ESP_OK;
}
