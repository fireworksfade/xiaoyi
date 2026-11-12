#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "cJSON.h"
#include "esp_err.h"

/* ---- configuration (config.c) ------------------------------------------ */

typedef struct {
    char device_id[64];
    char name[96];
    char broker_uri[128];
    char ota_base_url[128];
    char boot_fault[24];      /* drill applied on every boot of fault_firmware */
    char fault_firmware[32];
    uint32_t interval_s;
    int32_t temp_base_deci;
    uint32_t keepalive_s;
    uint32_t boot_count;
    bool sensor_calibrated;
} node_config_t;

extern node_config_t g_node;

esp_err_t config_load(void);
esp_err_t config_set_interval(uint32_t seconds);
esp_err_t config_set_keepalive(uint32_t seconds);
esp_err_t config_set_calibrated(bool calibrated);
esp_err_t config_set_boot_fault(const char *scenario, const char *firmware);
esp_err_t config_get_str(const char *key, char *out, size_t len);
esp_err_t config_set_str(const char *key, const char *value);

/* ---- wall clock (clock.c) ---------------------------------------------- */

void clock_start(void);
bool clock_synced(void);
int64_t clock_epoch_ms(void); /* 0 until SNTP has synchronised */
void clock_format_ms(int64_t epoch_ms, char *out, size_t len);
bool clock_iso_now(char *out, size_t len);
bool clock_parse_iso(const char *text, int64_t *epoch_s);
uint32_t uptime_s(void);
uint32_t uptime_ms(void);

/* ---- network link (net.c) ---------------------------------------------- */

esp_err_t net_start(void);
bool net_wait_ip(uint32_t timeout_ms);
esp_err_t net_reconnect(uint32_t timeout_ms);
bool net_is_wifi(void);
bool net_has_ip(void);
bool net_rssi(int *rssi);

/* ---- MQTT session (link.c) --------------------------------------------- */

void link_init(void);
esp_err_t link_start(void);
bool link_connected(void);
bool link_wait_connected(uint32_t timeout_ms);
esp_err_t link_reconnect(uint32_t timeout_ms);
esp_err_t link_set_keepalive(uint32_t seconds, uint32_t timeout_ms);
void link_shutdown(const char *reason);
int link_publish(const char *suffix, const char *payload, int qos, bool retain);
int link_publish_json(const char *suffix, const cJSON *payload, int qos, bool retain);
uint32_t link_reconnects(void);

/* ---- log forwarding (log_forward.c) ------------------------------------ */

/* Longest message one log/fault entry carries, NUL included. */
#define LOGFWD_MESSAGE_LEN 320

void logfwd_init(void);
void logfwd_start(void);
void logfwd_fault(const char *fault_type, const char *message);

/* ---- status reporting (report.c) --------------------------------------- */

void report_boot_evidence(void);
const char *report_reset_reason(void);
cJSON *report_status(void);
void report_start(void);
void report_now(void);
void report_birth(void);

/* ---- commands and OTA (commands.c, ota.c) ------------------------------ */

void commands_start(void);
void commands_enqueue(const char *data, int len);
esp_err_t ota_update(const char *version, char *detail, size_t len);
void ota_confirm_running_image(void);
/* Version held by the other OTA slot if the bootloader may start it, else NULL. */
const char *ota_rollback_version(void);
void ota_record_running_slot(void);
esp_err_t ota_select_previous(char *detail, size_t len);

/* ---- sensor (sensor.c) ------------------------------------------------- */

esp_err_t sensor_init(void);
esp_err_t sensor_read(float *celsius);
esp_err_t sensor_calibrate(char *detail, size_t len);
bool sensor_valid(void);
const char *sensor_backend(void);
void sensor_set_bus_fault(bool fault);

/* ---- fault drills (drills.c) ------------------------------------------- */

esp_err_t drill_start(const char *scenario, char *detail, size_t len);
void drill_apply_boot_fault(void);
