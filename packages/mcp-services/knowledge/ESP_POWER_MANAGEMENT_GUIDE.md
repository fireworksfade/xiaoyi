Source: https://docs.espressif.com/projects/esp-idf/zh_CN/latest/esp32/api-reference/system/power_management.html

API 参考

系统 API

电源管理

在 GitHub 上编辑

电源管理

[English]

概述

ESP-IDF 中集成的电源管理算法可以根据应用程序组件的需求，调整外围总线 (APB) 频率和 CPU 频率，并使芯片进入 Light-sleep 模式，尽可能减少运行应用程序的功耗。

应用程序组件可以通过创建和获取电源管理锁来控制功耗。

例如：

对于从 APB 获得时钟频率的外设，其驱动可以要求在使用该外设时，将 APB 频率设置为 80 MHz。

RTOS 可以要求 CPU 在有任务准备开始运行时以最高配置频率工作。

一些外设可能需要中断才能启用，因此其驱动也会要求禁用 Light-sleep 模式。

请求较高的 APB 频率或 CPU 频率以及禁用 Light-sleep 模式会增加功耗，因此请将组件使用的电源管理锁降到最少。

电源管理配置

编译时可使用 CONFIG_PM_ENABLE 选项启用电源管理功能。

启用电源管理功能将会增加中断延迟。额外延迟与多个因素有关，例如：CPU 频率、单/双核模式、是否需要进行频率切换等。CPU 频率为 240 MHz 且未启用频率调节时，最小额外延迟为 0.2 us；如果启用频率调节，且在中断入口将频率由 40 MHz 调节至 80 MHz，则最大额外延迟为 40 us。

通过调用 esp_pm_configure() 函数可以在应用程序中启用动态调频 (DFS) 功能和自动 Light-sleep 模式。此函数的参数 esp_pm_config_t 定义了频率调节的相关设置。在此参数结构中，需要初始化以下三个字段：

max_freq_mhz ：最大 CPU 频率 (MHz)，即获取 ESP_PM_CPU_FREQ_MAX 锁后所使用的频率。该字段通常设置为 CONFIG_ESP_DEFAULT_CPU_FREQ_MHZ 。

min_freq_mhz ：最小 CPU 频率 (MHz)，即未持有电源管理锁时所使用的频率。注意，10 MHz 是生成 1 MHz 的 REF_TICK 默认时钟所需的最小频率。

light_sleep_enable ：没有获取任何管理锁时，决定系统是否需要自动进入 Light-sleep 状态 ( true / false )。

如果在 menuconfig 中启用了 CONFIG_PM_DFS_INIT_AUTO 选项，最大 CPU 频率将由 CONFIG_ESP_DEFAULT_CPU_FREQ_MHZ 设置决定，最小 CPU 频率将锁定为 XTAL 频率。

备注

自动 Light-sleep 模式基于 FreeRTOS Tickless Idle 功能，因此如果在 menuconfig 中没有启用 CONFIG_FREERTOS_USE_TICKLESS_IDLE 选项，在请求自动 Light-sleep 时， esp_pm_configure() 将会返回 ESP_ERR_NOT_SUPPORTED 错误。

备注

Light-sleep 状态下，外设设有时钟门控，不会产生来自 GPIO 和内部外设的中断。 睡眠模式 文档中所提到的唤醒源可用于从 Light-sleep 状态触发唤醒。

警告

自动 Light-sleep 模式基于定时器唤醒实现，请勿手动配置定时器唤醒源。

例如，EXT0 和 EXT1 唤醒源可以通过 GPIO 唤醒芯片。

电源管理锁

应用程序可以通过获取或释放管理锁来控制电源管理算法。应用程序获取电源管理锁后，电源管理算法的操作将受到下面的限制。释放电源管理锁后，限制解除。

电源管理锁设有获取/释放计数器，如果已多次获取电源管理锁，则需要将电源管理锁释放相同次数以解除限制。

ESP32 支持下表中三种电源管理锁。

电源管理锁

描述

ESP_PM_CPU_FREQ_MAX

请求使用 esp_pm_configure() 将 CPU 频率设置为最大值。ESP32 可以将该值设置为 80 MHz, 160 MHz, or 240 MHz。

ESP_PM_APB_FREQ_MAX

请求将 APB 频率设置为最大值，ESP32 支持的最大频率为 80 MHz。

ESP_PM_NO_LIGHT_SLEEP

禁止自动切换至 Light-sleep 模式。

ESP32 电源管理算法

下表列出了启用动态调频时如何切换 CPU 频率和 APB 频率。可以使用 esp_pm_configure() 或 CONFIG_ESP_DEFAULT_CPU_FREQ_MHZ 指定 CPU 最大频率。

CPU 最高频率

电源管理锁获取情况

APB 频率和 CPU 频率

240

获取 ESP_PM_CPU_FREQ_MAX 或 ESP_PM_APB_FREQ_MAX

CPU: 240 MHz

APB: 80 MHz

无

使用 esp_pm_configure() 为二者设置最小值

160

获取 ESP_PM_CPU_FREQ_MAX

CPU: 160 MHz

APB: 80 MHz

获取 ESP_PM_APB_FREQ_MAX ，未获得 ESP_PM_CPU_FREQ_MAX

CPU: 80 MHz

APB: 80 MHz

无

使用 esp_pm_configure() 为二者设置最小值

80

获取 ESP_PM_CPU_FREQ_MAX 或 ESP_PM_APB_FREQ_MAX

CPU: 80 MHz

APB: 80 MHz

无

使用 esp_pm_configure() 为二者设置最小值

如果没有获取任何管理锁，调用 esp_pm_configure() 将启动 Light-sleep 模式。Light-sleep 模式持续时间由以下因素决定：

处于阻塞状态的 FreeRTOS 任务数（有限超时）

高分辨率定时器 API 注册的计数器数量

也可以设置 Light-sleep 模式在最近事件（任务解除阻塞，或计时器超时）之前的持续时间，在持续时间结束后再唤醒芯片。

为了跳过不必要的唤醒，可以将 skip_unhandled_events 选项设置为 true 来初始化 esp_timer 。带有此标志的定时器不会唤醒系统，有助于减少功耗。

自动 Light-sleep 时间补偿机制

ESP-IDF 使用预测性时间补偿机制来实现自动 Light-sleep。系统会在每次 Light-sleep 周期后测量实际的唤醒开销，并使用该测量值来预测下一次睡眠周期的唤醒开销。

系统根据下一个计划事件计算睡眠持续时间，并减去预测的唤醒开销（来自上一周期）来设置唤醒定时器。唤醒后，由于睡眠期间 FreeRTOS systick 中断被暂停，系统需要调用 vTaskStepTick() 来补偿睡眠期间经过的 tick 数，以保持 FreeRTOS tick 计数的准确性。同时，系统测量实际开销并记录，用于下次预测，形成自适应系统行为的反馈循环。

但实际开销可能因缓存未命中、CPU 频率变化、Flash 延迟变化或硬件状态恢复时间而有所不同。当实际开销超过预测值时，实际睡眠时间可能超过预期，导致 vTaskStepTick() 接收到的 tick 补偿值过大，触发断言失败。

CONFIG_PM_LIGHTSLEEP_TICK_OVERFLOW_PROTECTION 选项提供了一个安全机制，用于在唤醒开销超过预测时防止断言失败。启用后，系统会限制 tick 补偿值以防止溢出。

启用该选项时，系统对睡过超时情况的处理如下：
- 如果睡过超时在容忍范围内（可通过 CONFIG_PM_LIGHTSLEEP_TICK_OVERFLOW_TOLERANCE 配置，默认：2 个 tick），系统会静默地将 slept_ticks 限制为 xExpectedIdleTime ，防止断言失败
- 如果睡过超时超过容忍范围（可能存在 bug），系统不会限制 tick，会抛出错误日志，并触发断言失败
- 在极少数边缘场景下可能会丢失 tick，导致 FreeRTOS tick 计数（ xTickCount ）落后于真实时间（ esp_timer ），使用 vTaskDelay() 的任务可能比预期延迟稍长，FreeRTOS 软件定时器精度可能降低。

禁用该选项时（默认），可以获得准确的 tick 补偿，对时间关键应用具有更好的精度。在边缘情况下, 如果唤醒开销估算不足导致 Light-sleep 睡过超时时，可能会触发断言失败导致系统崩溃。

建议默认保持禁用状态以维持 tick 精度。仅在遇到与 vTaskStepTick() 相关的断言失败，且可以接受 RTOS tick 时间相较于真实时间轻微不准时启用。

调试和性能分析

电源管理子系统提供了几个函数来帮助调试和分析应用程序中的电源管理锁使用情况：

esp_pm_dump_locks() - 将所有当前创建的锁列表转储到指定流，显示其类型、名称和当前获取状态。

esp_pm_get_lock_stats_all() - 获取所有 PM 锁类型的统计信息，包括创建的锁数量和当前持有数。

esp_pm_lock_get_stats() - 获取特定锁实例的详细统计信息，包括获取计数（如果启用性能分析）和总占用时间。

这些函数特别适用于：

识别获取但从未释放的锁导致的泄漏

了解哪些组件阻止了节能

通过分析锁使用模式来优化功耗

调试与应用程序中锁管理相关的问题

要启用性能分析功能（单个锁的计时信息），请在 menuconfig 中启用 CONFIG_PM_PROFILING 选项。

应用示例

lowpower/power_management 示例演示了动态调频、自动 Light-sleep 与电源管理锁。

动态调频和外设驱动

启用动态调频后，APB 频率可在一个 RTOS 滴答周期内多次更改。有些外设不受 APB 频率变更的影响，但有些外设可能会出现问题。例如，Timer Group 外设定时器会继续计数，但定时器计数的速度将随 APB 频率的变更而变更。

时钟频率不受 APB 频率影响的外设时钟源通常有 REF_TICK , XTAL , RC_FAST (i.e., RTC_8M )。因此，为了保证外设在 DFS 期间的所有行为一致，建议在上述时钟中选择其一作为外设的时钟源。如果想要了解更多详情可以浏览每个外设 ”API 参考 > 外设 API“ 页面的 “电源管理” 章节。

目前以下外设驱动程序可感知动态调频，并在调频期间使用 ESP_PM_APB_FREQ_MAX 锁：

SPI master

I2C

I2S

SDMMC

启用以下驱动程序时，将占用 ESP_PM_APB_FREQ_MAX 锁：

SPI slave ：从调用 spi_slave_initialize() 至 spi_slave_free() 期间。

GPTimer ：从调用 gptimer_enable() 至 gptimer_disable() 期间。

Ethernet ：从调用 esp_eth_driver_install() 至 esp_eth_driver_uninstall() 期间。

WiFi ：从调用 esp_wifi_start() 至 esp_wifi_stop() 期间。如果启用了调制解调器睡眠模式，广播关闭时将释放此管理锁。

TWAI ：从调用 twai_driver_install() 至 twai_driver_uninstall() 期间 (只有在 TWAI 时钟源选择为 TWAI_CLK_SRC_APB 的时候生效)。

Bluetooth ：从调用 esp_bt_controller_enable() 至 esp_bt_controller_disable() 期间。如果启用了蓝牙调制解调器，广播关闭时将释放此管理锁。但依然占用 ESP_PM_NO_LIGHT_SLEEP 锁，除非将 CONFIG_BTDM_CTRL_LOW_POWER_CLOCK 选项设置为 “外部 32 kHz 晶振”。

PCNT ：从调用 pcnt_unit_enable() 至 pcnt_unit_disable() 期间。

Sigma-delta ：从调用 sdm_channel_enable() 至 sdm_channel_disable() 期间。

MCPWM : 从调用 mcpwm_timer_enable() 至 mcpwm_timer_disable() 期间，以及调用 mcpwm_capture_timer_enable() 至 mcpwm_capture_timer_disable() 期间。

API 参考

Header File

components/esp_pm/include/esp_pm.h

This header file can be included with:

#include"esp_pm.h"

This header file is a part of the API provided by the esp_pm component. To declare that your component depends on esp_pm , add the following to your CMakeLists.txt:

REQUIRES esp_pm

or

PRIV_REQUIRES esp_pm

Functions

esp_err_t esp_pm_configure ( const void * config )

Set implementation-specific power management configuration.

参数 :

config -- pointer to implementation-specific configuration structure (e.g. esp_pm_config_esp32)

返回 :

ESP_OK on success

ESP_ERR_INVALID_ARG if the configuration values are not correct

ESP_ERR_NOT_SUPPORTED if certain combination of values is not supported, or if CONFIG_PM_ENABLE is not enabled in sdkconfig

esp_err_t esp_pm_get_configuration ( void * config )

Get implementation-specific power management configuration.

参数 :

config -- pointer to implementation-specific configuration structure (e.g. esp_pm_config_esp32)

返回 :

ESP_OK on success

ESP_ERR_INVALID_ARG if the pointer is null

esp_err_t esp_pm_lock_create ( esp_pm_lock_type_t lock_type , int arg , const char * name , esp_pm_lock_handle_t * out_handle )

Initialize a lock handle for certain power management parameter.

When lock is created, initially it is not taken. Call esp_pm_lock_acquire to take the lock.

This function must not be called from an ISR.

备注

If the lock_type argument is not valid, it will cause an abort.

参数 :

lock_type -- Power management constraint which the lock should control

arg -- argument, value depends on lock_type, see esp_pm_lock_type_t

name -- arbitrary string identifying the lock (e.g. "wifi" or "spi"). Used by the esp_pm_dump_locks function to list existing locks. May be set to NULL. If not set to NULL, must point to a string which is valid for the lifetime of the lock.

out_handle -- [out] handle returned from this function. Use this handle when calling esp_pm_lock_delete, esp_pm_lock_acquire, esp_pm_lock_release. Must not be NULL.

返回 :

ESP_OK on success

ESP_ERR_NO_MEM if the lock structure can not be allocated

ESP_ERR_INVALID_ARG if out_handle is NULL

ESP_ERR_NOT_SUPPORTED if CONFIG_PM_ENABLE is not enabled in sdkconfig

esp_err_t esp_pm_lock_acquire ( esp_pm_lock_handle_t handle )

Take a power management lock.

Once the lock is taken, power management algorithm will not switch to the mode specified in a call to esp_pm_lock_create, or any of the lower power modes (higher numeric values of 'mode').

The lock is recursive, in the sense that if esp_pm_lock_acquire is called a number of times, esp_pm_lock_release has to be called the same number of times in order to release the lock.

This function may be called from an ISR.

This function is not thread-safe w.r.t. calls to other esp_pm_lock_* functions for the same handle.

参数 :

handle -- handle obtained from esp_pm_lock_create function

返回 :

ESP_OK on success

ESP_ERR_INVALID_ARG if the handle is invalid

ESP_ERR_NOT_SUPPORTED if CONFIG_PM_ENABLE is not enabled in sdkconfig

esp_err_t esp_pm_lock_release ( esp_pm_lock_handle_t handle )

Release the lock taken using esp_pm_lock_acquire.

Call to this functions removes power management restrictions placed when taking the lock.

Locks are recursive, so if esp_pm_lock_acquire is called a number of times, esp_pm_lock_release has to be called the same number of times in order to actually release the lock.

This function may be called from an ISR.

This function is not thread-safe w.r.t. calls to other esp_pm_lock_* functions for the same handle.

参数 :

handle -- handle obtained from esp_pm_lock_create function

返回 :

ESP_OK on success

ESP_ERR_INVALID_ARG if the handle is invalid

ESP_ERR_INVALID_STATE if lock is not acquired

ESP_ERR_NOT_SUPPORTED if CONFIG_PM_ENABLE is not enabled in sdkconfig

esp_err_t esp_pm_lock_delete ( esp_pm_lock_handle_t handle )

Delete a lock created using esp_pm_lock.

The lock must be released before calling this function.

This function must not be called from an ISR.

参数 :

handle -- handle obtained from esp_pm_lock_create function

返回 :

ESP_OK on success

ESP_ERR_INVALID_ARG if the handle argument is NULL

ESP_ERR_INVALID_STATE if the lock is still acquired

ESP_ERR_NOT_SUPPORTED if CONFIG_PM_ENABLE is not enabled in sdkconfig

esp_err_t esp_pm_dump_locks ( FILE * stream )

Dump the list of all locks to stderr

This function dumps debugging information about locks created using esp_pm_lock_create to an output stream.

This function must not be called from an ISR. If esp_pm_lock_acquire/release are called while this function is running, inconsistent results may be reported.

参数 :

stream -- stream to print information to; use stdout or stderr to print to the console; use fmemopen/open_memstream to print to a string buffer.

返回 :

ESP_OK on success

ESP_ERR_NOT_SUPPORTED if CONFIG_PM_ENABLE is not enabled in sdkconfig

esp_err_t esp_pm_get_lock_stats_all ( esp_pm_lock_stats_t stats [ ESP_PM_LOCK_MAX ] )

Get statistics for all PM lock types.

This function returns the number of locks created for each lock type and the total number of times locks of each type have been acquired.

参数 :

stats -- pointer to array of esp_pm_lock_stats_t with ESP_PM_LOCK_MAX elements

返回 :

ESP_OK on success

ESP_ERR_INVALID_ARG if stats pointer is invalid

ESP_ERR_NOT_SUPPORTED if CONFIG_PM_ENABLE is not enabled in sdkconfig

esp_err_t esp_pm_lock_get_stats ( esp_pm_lock_handle_t handle , esp_pm_lock_instance_stats_t * stats )

Get statistics for a single PM lock instance.

This function returns statistics for a specific lock instance, including the number of times it has been acquired and released.

参数 :

handle -- handle of the lock to get statistics for

stats -- pointer to esp_pm_lock_instance_stats_t structure to fill

返回 :

ESP_OK on success

ESP_ERR_INVALID_ARG if handle or stats pointer is invalid

ESP_ERR_NOT_SUPPORTED if CONFIG_PM_ENABLE is not enabled in sdkconfig

Structures

struct esp_pm_config_t

Power management config.

Pass a pointer to this structure as an argument to esp_pm_configure function.

Public Members

int max_freq_mhz

Maximum CPU frequency, in MHz

int min_freq_mhz

Minimum CPU frequency to use when no locks are taken, in MHz

bool light_sleep_enable

Enter light sleep when no locks are taken

struct esp_pm_lock_stats_t

Structure to store PM lock statistics for each lock type.

Public Members

size_t created

Number of locks of this type that have been created

size_t acquired

Total number of times locks of this type have been acquired

struct esp_pm_lock_instance_stats_t

Structure to store statistics for a single PM lock instance.

Public Members

size_t acquired

Current reference count of the lock (number of times it has been acquired without corresponding release)

Type Definitions

typedef esp_pm_config_t esp_pm_config_esp32_t

backward compatibility newer chips no longer require this typedef

typedef esp_pm_config_t esp_pm_config_esp32s2_t

typedef esp_pm_config_t esp_pm_config_esp32s3_t

typedef esp_pm_config_t esp_pm_config_esp32c3_t

typedef esp_pm_config_t esp_pm_config_esp32c2_t

typedef esp_pm_config_t esp_pm_config_esp32c6_t

typedef struct esp_pm_lock * esp_pm_lock_handle_t

Opaque handle to the power management lock.

Enumerations

enum esp_pm_lock_type_t

Power management constraints.

Values:

enumerator ESP_PM_CPU_FREQ_MAX

Require CPU frequency to be at the maximum value set via esp_pm_configure. Argument is unused and should be set to 0.

enumerator ESP_PM_APB_FREQ_MAX

Require APB frequency to be at the maximum value supported by the chip. Argument is unused and should be set to 0.

enumerator ESP_PM_NO_LIGHT_SLEEP

Prevent the system from going into light sleep. Argument is unused and should be set to 0.

enumerator ESP_PM_LOCK_MAX

此文档对您有帮助吗？

反馈已收到，谢谢！

如果您有其他意见，欢迎填写 乐鑫文档反馈表 。

我们重视您的反馈。

您可以填写 乐鑫文档反馈表 告诉我们如何改进该文档。
