来源：https://docs.espressif.com/projects/esp-idf/zh_CN/v5.5.4/esp32/api-reference/system/system_time.html

# 系统时间

## 概述

ESP32 使用两种硬件时钟源建立和保持系统时间。根据应用目的及对系统时间的精度要求，既可以仅使用其中一种时钟源，也可以同时使用两种时钟源。这两种硬件时钟源为：

- RTC 定时器：RTC 定时器在任何睡眠模式下及在任何复位后均可保持系统时间（上电复位除外，因为上电复位会重置 RTC 定时器）。时钟频率偏差取决于 RTC 定时器时钟源，该偏差只会在睡眠模式下影响时间精度。睡眠模式下，时间分辨率为 6.667 μs。

- 高分辨率定时器：高分辨率定时器在睡眠模式下及在复位后不可用，但其时间精度更高。该定时器使用 APB_CLK 时钟源（通常为 80 MHz），时钟频率偏差小于 ±10 ppm，时间分辨率为 1 μs。

可供选择的硬件时钟源组合如下所示：

- RTC 和高分辨率定时器（默认）

- RTC

- 高分辨率定时器

- 无

默认时钟源的时间精度最高，建议使用该配置。此外，你可以通过配置选项 CONFIG_LIBC_TIME_SYSCALL 来选择其他时钟源。

## RTC 定时器时钟源

RTC 定时器有以下时钟源：

- `内置 90～150 kHz（频率取决于芯片型号） 振荡器` （默认）：Deep-sleep 模式下电流消耗最低，不依赖任何外部元件。但由于温度波动会影响该时钟源的频率稳定性，在 Deep-sleep 和 Light-sleep 模式下都有可能发生时间偏移。

- `外置 32 kHz 晶振`：需要将一个 32 kHz 晶振连接到外置晶振管脚。频率稳定性更高，但在 Deep-sleep 模式下电流消耗略高（比默认模式高 1 μA）。管脚连接的相关信息请参考 技术规格书。

- `外置 32 kHz 振荡器`：允许使用由外部电路产生的 32 kHz 时钟。外部时钟信号必须连接到外置振荡器管脚。正弦波信号的振幅应小于 1.2 V，方波信号的振幅应小于 1 V。正常模式下，电压范围应为 0.1 < Vcm < 0.5 xVamp，其中 Vamp 代表信号振幅。管脚连接的相关信息请参考 技术规格书。

- `内置 8.5～17.5 MHz 振荡器（频率取决于芯片型号）的 256 分频时钟`：频率稳定性优于 `内置 90～150 kHz RC 振荡器`，同样无需外部元件，但 Deep-sleep 模式下电流消耗更高（比默认模式高 5 μA）。

时钟源的选择取决于系统时间精度要求和睡眠模式下的功耗要求。要修改 RTC 时钟源，请在项目配置中设置 CONFIG_RTC_CLK_SRC。

想要了解外置晶振或外置振荡器的更多布线要求，请参考 硬件设计指南。

## 获取当前时间

要获取当前时间，请使用 POSIX 函数 `gettimeofday()`。此外，也可以使用以下标准 C 库函数来获取时间并对其进行操作：

`
gettimeofday
time
asctime
clock
ctime
difftime
gmtime
localtime
mktime
strftime
adjtime*
`

如需立即更新当前时间，并暂停平滑时间校正，请使用 POSIX 函数 `settimeofday()`。

若要求时间的分辨率为 1 s，请使用以下代码片段：

`
time_t now;
char strftime_buf[64];
struct tm timeinfo;

time(&now);
// 将时区设置为中国标准时间
setenv("TZ", "CST-8", 1);
tzset();

localtime_r(&now, &timeinfo);
strftime(strftime_buf, sizeof(strftime_buf), "%c", &timeinfo);
ESP_LOGI(TAG, "The current date/time in Shanghai is: %s", strftime_buf);
`

若要求时间的分辨率为 1 μs，请使用以下代码片段：

`
struct timeval tv_now;
gettimeofday(&tv_now, NULL);
int64_t time_us = (int64_t)tv_now.tv_sec * 1000000L + (int64_t)tv_now.tv_usec;
`

## SNTP 时间同步

要设置当前时间，可以使用 POSIX 函数 `settimeofday()` 和 `adjtime()`。lwIP 中的 SNTP 库会在收到 NTP 服务器的响应报文后，调用这两个函数以更新当前的系统时间。当然，用户可以在 lwIP SNTP 库之外独立地使用这两个函数。

包括 SNTP 函数在内的一些 lwIP API 并非线程安全，因此建议在与 SNTP 模块交互时使用 esp_netif component。

要初始化特定的 SNTP 服务器并启动 SNTP 服务，只需创建有特定服务器名称的默认 SNTP 服务器配置，然后调用 `esp_netif_sntp_init()` 注册该服务器并启动 SNTP 服务。

`
esp_sntp_config_t config = ESP_NETIF_SNTP_DEFAULT_CONFIG("pool.ntp.org");
esp_netif_sntp_init(&config);
`

一旦收到 SNTP 服务器的响应，此代码会自动执行时间同步。有时等待时间同步很有意义，调用 `esp_netif_sntp_sync_wait()` 可实现此目的：

`
if (esp_netif_sntp_sync_wait(pdMS_TO_TICKS(10000)) != ESP_OK) {
    printf("Failed to update system time within 10s timeout");
}
`

要配置多个 NTP 服务器（或使用更高级的设置，例如 DHCP 提供的 NTP 服务器），请参考 esp_netif 文档 SNTP Service 中的详细说明。

lwIP SNTP 库可在下列任一同步模式下工作：

- `SNTP_SYNC_MODE_IMMED` （默认）：使用 `settimeofday()`，收到 SNTP 服务器响应后立即更新系统时间。

- `SNTP_SYNC_MODE_SMOOTH`：使用函数 `adjtime()` 逐渐减少时间误差以平滑更新时间。如果 SNTP 响应时间和系统时间之差超过 35 分钟，请立即使用 `settimeofday()` 更新系统时间。

如要选择 `SNTP_SYNC_MODE_SMOOTH` 模式，请将 SNTP 配置结构体中的 `esp_sntp_config::smooth` 设置为 `true`，否则将默认使用 `SNTP_SYNC_MODE_IMMED` 模式。

设置时间同步时的回调函数，请使用配置结构体中的 `esp_sntp_config::sync_cb` 字段。

添加此初始化代码后，应用程序将定期同步时间。时间同步周期由 CONFIG_LWIP_SNTP_UPDATE_DELAY 设置（默认为一小时）。如需修改，请在项目配置中设置 CONFIG_LWIP_SNTP_UPDATE_DELAY。

如需查看示例代码，请前往 protocols/sntp 目录。该目录下的示例展示了如何基于 lwIP SNTP 库实现时间同步。

也可以直接使用 lwIP API，但请务必注意线程安全。线程安全的 API 如下：

- `sntp_set_time_sync_notification_cb()` 用于设置通知时间同步过程的回调函数。

- `sntp_get_sync_status()` 和 `sntp_set_sync_status()` 用于获取/设置时间同步状态。

- `sntp_set_sync_mode()` 用于设置同步模式。

- `esp_sntp_setoperatingmode()` 用于设置首选操作模式。`ESP_SNTP_OPMODE_POLL` 和 `esp_sntp_init()` 可初始化 SNTP 模块。

- `esp_sntp_setservername()` 用于配置特定 SNTP 服务器。

## 时区

要设置本地时区，请使用以下 POSIX 函数：

- 调用 `setenv()`，将 `TZ` 环境变量根据设备位置设置为正确的值。时间字符串的格式与 GNU libc 文档 中描述的相同（但实现方式不同）。

- 调用 `tzset()`，为新的时区更新 C 库的运行数据。

完成上述步骤后，请调用标准 C 库函数 `localtime()`。该函数将返回排除时区偏差和夏令时干扰后的准确本地时间。

## 2036 年和 2038 年溢出问题

### SNTP/NTP 2036 年溢出问题

SNTP/NTP 时间戳为 64 位无符号定点数，其中前 32 位表示整数部分，后 32 位表示小数部分。该 64 位无符号定点数代表从 1900 年 1 月 1 日 00:00 起经过的秒数，因此 SNTP/NTP 时间将在 2036 年溢出。

为了解决这一问题，可以使用整数部分的 MSB（惯例为位 0）来表示 1968 年到 2104 年之间的时间范围（查看 RFC2030 了解更多信息），这一惯例将使得 SNTP/NTP 时间戳的生命周期延长。该惯例会在 lwIP 库的 SNTP 模块中实现，因此 ESP-IDF 中 SNTP 相关功能在 2104 年之前能够经受住时间的考验。

### Unix 时间 2038 年溢出问题

Unix 时间（类型 `time_t`）此前为有符号的 32 位整数，因此将于 2038 年溢出（即 Y2K38 问题）。为了解决 Y2K38 问题，ESP-IDF 从 v5.0 版本起开始使用有符号的 64 位整数来表示 `time_t`，从而将 `time_t` 溢出推迟 2920 亿年。

## API 参考

### Header File

- components/lwip/include/apps/esp_sntp.h

- This header file can be included with:

`
#include "esp_sntp.h"
`

- This header file is a part of the API provided by the `lwip` component. To declare that your component depends on `lwip`, add the following to your CMakeLists.txt:

`
REQUIRES lwip
`

or

`
PRIV_REQUIRES lwip
`

### Functions

void sntp_sync_time(struct timeval *tv)

This function updates the system time.

This is a weak-linked function. It is possible to replace all SNTP update functionality by placing a sntp_sync_time() function in the app firmware source. If the default implementation is used, calling sntp_set_sync_mode() allows the time synchronization mode to be changed to instant or smooth. If a callback function is registered via sntp_set_time_sync_notification_cb(), it will be called following time synchronization.

参数:

tv -- Time received from SNTP server.

void sntp_set_sync_mode(sntp_sync_mode_t sync_mode)

Set the sync mode.

Modes allowed: SNTP_SYNC_MODE_IMMED and SNTP_SYNC_MODE_SMOOTH.

参数:

sync_mode -- Sync mode.

sntp_sync_mode_t sntp_get_sync_mode(void)

Get set sync mode.

返回:

SNTP_SYNC_MODE_IMMED: Update time immediately. SNTP_SYNC_MODE_SMOOTH: Smooth time updating.

sntp_sync_status_t sntp_get_sync_status(void)

Get status of time sync.

After the update is completed, the status will be returned as SNTP_SYNC_STATUS_COMPLETED. After that, the status will be reset to SNTP_SYNC_STATUS_RESET. If the update operation is not completed yet, the status will be SNTP_SYNC_STATUS_RESET. If a smooth mode was chosen and the synchronization is still continuing (adjtime works), then it will be SNTP_SYNC_STATUS_IN_PROGRESS.

返回:

SNTP_SYNC_STATUS_RESET: Reset status. SNTP_SYNC_STATUS_COMPLETED: Time is synchronized. SNTP_SYNC_STATUS_IN_PROGRESS: Smooth time sync in progress.

void sntp_set_sync_status(sntp_sync_status_t sync_status)

Set status of time sync.

参数:

sync_status -- status of time sync (see sntp_sync_status_t)

void sntp_set_time_sync_notification_cb(sntp_sync_time_cb_t callback)

Set a callback function for time synchronization notification.

参数:

callback -- a callback function

void sntp_set_sync_interval(uint32_t interval_ms)

Set the sync interval of SNTP operation.

Note: SNTPv4 RFC 4330 enforces a minimum sync interval of 15 seconds. This sync interval will be used in the next attempt update time throught SNTP. To apply the new sync interval call the sntp_restart() function, otherwise, it will be applied after the last interval expired.

参数:

interval_ms -- The sync interval in ms. It cannot be lower than 15 seconds, otherwise 15 seconds will be set.

uint32_t sntp_get_sync_interval(void)

Get the sync interval of SNTP operation.

返回:

the sync interval

bool sntp_restart(void)

Restart SNTP.

返回:

True - Restart False - SNTP was not initialized yet

void esp_sntp_setoperatingmode(esp_sntp_operatingmode_t operating_mode)

Sets SNTP operating mode. The mode has to be set before init.

参数:

operating_mode -- Desired operating mode

void esp_sntp_init(void)

Init and start SNTP service.

void esp_sntp_stop(void)

Stops SNTP service.

void esp_sntp_setserver(u8_t idx, const ip_addr_t *addr)

Sets SNTP server address.

参数:

- idx -- Index of the server

- addr -- IP address of the server

void esp_sntp_setservername(u8_t idx, const char *server)

Sets SNTP hostname.

参数:

- idx -- Index of the server

- server -- Name of the server

const char *esp_sntp_getservername(u8_t idx)

Gets SNTP server name.

参数:

idx -- Index of the server

返回:

Name of the server

const ip_addr_t *esp_sntp_getserver(u8_t idx)

Get SNTP server IP.

参数:

idx -- Index of the server

返回:

IP address of the server

bool esp_sntp_enabled(void)

Checks if sntp is enabled.

返回:

true if sntp module is enabled

uint8_t esp_sntp_getreachability(uint8_t idx)

Gets the server reachability shift register as described in RFC 5905.

参数:

idx -- Index of the SNTP server

返回:

reachability shift register

esp_sntp_operatingmode_t esp_sntp_getoperatingmode(void)

Get the configured operating mode.

返回:

operating mode enum

static inline void sntp_setoperatingmode(u8_t operating_mode)

if not build within lwip, provide translating inlines, that will warn about thread safety

static inline void sntp_servermode_dhcp(int set_servers_from_dhcp)

static inline void sntp_setservername(u8_t idx, const char *server)

static inline void sntp_init(void)

static inline const char *sntp_getservername(u8_t idx)

static inline const ip_addr_t *sntp_getserver(u8_t idx)

static inline uint8_t sntp_getreachability(uint8_t idx)

static inline esp_sntp_operatingmode_t sntp_getoperatingmode(void)

### Macros

esp_sntp_sync_time

Aliases for esp_sntp prefixed API (inherently thread safe)

esp_sntp_set_sync_mode

esp_sntp_get_sync_mode

esp_sntp_get_sync_status

esp_sntp_set_sync_status

esp_sntp_set_time_sync_notification_cb

esp_sntp_set_sync_interval

esp_sntp_get_sync_interval

esp_sntp_restart

SNTP_OPMODE_POLL

### Type Definitions

typedef void (*sntp_sync_time_cb_t)(struct timeval *tv)

SNTP callback function for notifying about time sync event.

Param tv:

Time received from SNTP server.

### Enumerations

enum sntp_sync_mode_t

SNTP time update mode.

Values:

enumerator SNTP_SYNC_MODE_IMMED

Update system time immediately when receiving a response from the SNTP server.

enumerator SNTP_SYNC_MODE_SMOOTH

Smooth time updating. Time error is gradually reduced using adjtime function. If the difference between SNTP response time and system time is large (more than 35 minutes) then update immediately.

enum sntp_sync_status_t

SNTP sync status.

Values:

enumerator SNTP_SYNC_STATUS_RESET

enumerator SNTP_SYNC_STATUS_COMPLETED

enumerator SNTP_SYNC_STATUS_IN_PROGRESS

enum esp_sntp_operatingmode_t

SNTP operating modes per lwip SNTP module.

Values:

enumerator ESP_SNTP_OPMODE_POLL

enumerator ESP_SNTP_OPMODE_LISTENONLY

此文档对您有帮助吗？

- 反馈已收到，谢谢！

- 如果您有其他意见，欢迎填写乐鑫文档反馈表。

- 我们重视您的反馈。

- 您可以填写乐鑫文档反馈表告诉我们如何改进该文档。
