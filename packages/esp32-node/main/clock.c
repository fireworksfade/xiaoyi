#include <stdio.h>
#include <string.h>
#include <sys/time.h>
#include <time.h>

#include "esp_log.h"
#include "esp_netif_sntp.h"
#include "esp_timer.h"
#include "sdkconfig.h"

#include "node.h"

static const char *TAG = "clock";

/* Anything before 2023-11 means SNTP has not run yet (the RTC starts at 1970). */
#define CLOCK_VALID_AFTER 1700000000LL

static void on_time_sync(struct timeval *tv)
{
    char now[40];
    clock_format_ms((int64_t)tv->tv_sec * 1000 + tv->tv_usec / 1000, now, sizeof(now));
    ESP_LOGI(TAG, "clock synchronised via SNTP: %s", now);
}

void clock_start(void)
{
    setenv("TZ", "UTC0", 1);
    tzset();
    /* One unreachable or lossy server must not leave the clock unsynced for minutes:
     * lwIP moves on to the next server on each timeout. */
    esp_sntp_config_t config = ESP_NETIF_SNTP_DEFAULT_CONFIG_MULTIPLE(
        3, ESP_SNTP_SERVER_LIST(CONFIG_XIAOYI_SNTP_SERVER, CONFIG_XIAOYI_SNTP_SERVER_2,
                                CONFIG_XIAOYI_SNTP_SERVER_3));
    config.sync_cb = on_time_sync;
    esp_err_t err = esp_netif_sntp_init(&config);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "SNTP start failed: %s; timestamps will be omitted", esp_err_to_name(err));
    }
}

bool clock_synced(void)
{
    return time(NULL) > CLOCK_VALID_AFTER;
}

int64_t clock_epoch_ms(void)
{
    struct timeval tv;
    gettimeofday(&tv, NULL);
    if (tv.tv_sec <= CLOCK_VALID_AFTER) {
        return 0;
    }
    return (int64_t)tv.tv_sec * 1000 + tv.tv_usec / 1000;
}

void clock_format_ms(int64_t epoch_ms, char *out, size_t len)
{
    time_t seconds = (time_t)(epoch_ms / 1000);
    struct tm tm;
    gmtime_r(&seconds, &tm);
    size_t used = strftime(out, len, "%Y-%m-%dT%H:%M:%S", &tm);
    snprintf(out + used, len - used, ".%03d+00:00", (int)(epoch_ms % 1000));
}

bool clock_iso_now(char *out, size_t len)
{
    int64_t now = clock_epoch_ms();
    if (now == 0) {
        return false;
    }
    clock_format_ms(now, out, len);
    return true;
}

static int64_t days_from_civil(int year, int month, int day)
{
    year -= month <= 2;
    const int64_t era = (year >= 0 ? year : year - 399) / 400;
    const int yoe = (int)(year - era * 400);
    const int doy = (153 * (month + (month > 2 ? -3 : 9)) + 2) / 5 + day - 1;
    const int doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
    return era * 146097 + doe - 719468;
}

bool clock_parse_iso(const char *text, int64_t *epoch_s)
{
    int year, month, day, hour, minute, second;
    if (text == NULL || strlen(text) < 19 ||
        sscanf(text, "%4d-%2d-%2dT%2d:%2d:%2d", &year, &month, &day, &hour, &minute, &second) != 6) {
        return false;
    }
    const char *rest = text + 19;
    if (*rest == '.') {
        rest++;
        while (*rest >= '0' && *rest <= '9') {
            rest++;
        }
    }
    int offset = 0;
    if (*rest == '+' || *rest == '-') {
        int hours = 0;
        int minutes = 0;
        if (sscanf(rest + 1, "%2d:%2d", &hours, &minutes) < 1) {
            return false;
        }
        offset = (hours * 3600 + minutes * 60) * (*rest == '-' ? -1 : 1);
    } else if (*rest != 'Z' && *rest != '\0') {
        return false;
    }
    *epoch_s = days_from_civil(year, month, day) * 86400 + hour * 3600 + minute * 60 + second - offset;
    return true;
}

uint32_t uptime_s(void)
{
    return (uint32_t)(esp_timer_get_time() / 1000000);
}

uint32_t uptime_ms(void)
{
    return (uint32_t)(esp_timer_get_time() / 1000);
}
