来源：https://docs.espressif.com/projects/esp-idf/zh_CN/v5.5.4/esp32/api-reference/system/wdts.html

# 看门狗

## 概述

ESP-IDF 支持以下类型的看门狗定时器：

- 硬件看门狗定时器

- 中断看门狗定时器 (IWDT)

- 任务看门狗定时器 (TWDT)

中断看门狗负责确保 ISR（中断服务程序）不被长时间阻塞，TWDT 负责检测任务长时间运行而不让步的情况。

通过 Editing the Configuration 可启用各种看门狗定时器。其中，TWDT 也可以在程序运行时启用。

## 硬件看门狗定时器

芯片有两组看门狗定时器：

- 主系统看门狗定时器 (MWDT_WDT) - 用于中断看门狗定时器 (IWDT) 和任务看门狗定时器 (TWDT)。

- RTC 看门狗定时器 (RTC_WDT) - 用于跟踪从上电到执行用户主函数的启动时间（默认情况下，RTC 看门狗在执行用户主函数之前会被立即禁用）。

请参阅 看门狗 小节，了解如何在引导加载程序中使用看门狗。

用户可以调整应用程序行为，使 RTC 看门狗在应用程序启动后保持启用状态。应用程序需要显式重置（即喂狗）或禁用看门狗，以避免芯片重置。具体而言，用户可设置 CONFIG_BOOTLOADER_WDT_DISABLE_IN_USER_CODE 选项，根据需要修改应用程序并重新编译。此过程中应使用以下 API：

- `wdt_hal_disable()`：参考 禁用 RTC_WDT

- `wdt_hal_feed()`：参考 重置 RTC_WDT 计数器

- `rtc_wdt_feed()`

- `rtc_wdt_disable()`

如果未能及时重置或禁用 RTC_WDT，芯片将自动重置。请参阅 RTC 看门狗超时 了解更多信息。

## 中断看门狗定时器 (IWDT)

IWDT 的目的是，确保中断服务例程 (ISR) 运行不会受到长时间阻塞（即 IWDT 超时）。阻塞 ISR 及时运行会增加 ISR 延迟，也会阻止任务切换（因为任务切换是从 ISR 执行的）。阻止 ISR 运行的事项包括：

- 禁用中断

- 临界区（也会禁用中断）

- 其他相同或更高优先级的 ISR，在完成前会阻止相同或较低优先级的 ISR

IWDT 利用 定时器组 1 中的 MWDT_WDT 看门狗定时器作为其底层硬件定时器，并在每个 CPU 上使用 FreeRTOS 时钟滴答中断，即 tick 中断。如果某个 CPU 上的 tick 中断没有在 IWDT 超时前运行，就表明该 CPU 上的 ISR 运行受阻（参见上文原因列表）。

当 IWDT 超时后，默认操作是调用紧急处理程序 (Panic Handler)，并显示 出错原因（ `Interrupt wdt timeout on CPU0` 或 `Interrupt wdt timeout on CPU1`，视情况而定）。根据紧急处理程序的配置行为（参见 CONFIG_ESP_SYSTEM_PANIC），用户可通过回溯、OpenOCD、gdbstub 等来调试 IWDT 超时问题，也可以重置芯片（这在生产环境中可能是首选）。

如果出于某种原因，IWDT 超时后紧急处理程序无法运行，IWDT 还可以通过其二阶段超时来硬重置芯片（即系统重置）。

### 配置

- IWDT 默认通过 CONFIG_ESP_INT_WDT 选项启用。

- 通过 CONFIG_ESP_INT_WDT_TIMEOUT_MS 选项设置 IWDT 超时。

  - 注意，如果启用了 PSRAM 支持，那么默认的超时时间会更长，因为在某些情况下，临界区或中断例程访问大量 PSRAM 需要更长时间。

  - 超时时间至少应是 FreeRTOS tick 周期的两倍时长（参见 CONFIG_FREERTOS_HZ）。

### 调优

如果 IWDT 超时是中断或临界区运行超时导致的，可以考虑重写代码：

- 临界区应尽可能短。任何非关键的代码或计算都应放在临界区外。

- 中断处理程序也应尽可能减少计算量。考虑让 ISR 使用队列向任务推送数据，从而将计算推迟到任务中进行。

临界区或中断处理程序都不应阻塞其他事件。如果不能或不希望通过更改代码减少处理时间，可以通过设置 CONFIG_ESP_INT_WDT_TIMEOUT_MS 延长超时时间。

## 任务看门狗定时器 (TWDT)

任务看门狗定时器 (TWDT) 用于监视特定任务，确保任务在配置的超时时间内执行。TWDT 主要监视每个 CPU 的空闲任务，但其他任务也可以订阅 TWDT 监视。通过监视每个 CPU 的空闲任务，TWDT 可以检测到任务长时间运行没有让出的情况。这可能表明代码编写不当，在外设上自旋循环，或者任务陷入了无限循环。

TWDT 是基于定时器组 0 中的 MWDT_WDT 看门狗定时器构建的。超时发生时会触发中断。

可以在用户代码中定义函数 `esp_task_wdt_isr_user_handler` 来接收超时事件，并扩展默认行为。

### 使用

调用以下函数，用 TWDT 监视任务：

- `esp_task_wdt_init()` 初始化 TWDT 并订阅空闲任务。

- `esp_task_wdt_add()` 为其他任务订阅 TWDT。

- 订阅后，应从任务中调用 `esp_task_wdt_reset()` 来喂 TWDT。

- `esp_task_wdt_delete()` 可以取消之前订阅的任务。

- `esp_task_wdt_deinit()` 取消订阅空闲任务并反初始化 TWDT。

在需要更细粒度级别监视的情况下（即确保调用特定的函数、存根、代码路径），TWDT 允许订阅 `users`。

- `esp_task_wdt_add_user()` 订阅 TWDT 的任意用户。此函数返回添加用户的用户句柄。

- 必须使用用户句柄调用 `esp_task_wdt_reset_user()`，防止 TWDT 超时。

- `esp_task_wdt_delete_user()` 取消订阅 TWDT 的任意用户。

### 配置

TWDT 的默认超时时间可以通过 CONFIG_ESP_TASK_WDT_TIMEOUT_S 配置项进行设置，并应至少设置为任何单个任务预计需要独占 CPU 的时长，例如某应用程序将进行长时间的密集计算且不让位给其他任务时的预计时长。也可以调用 `esp_task_wdt_init()`，在运行时更改此时间。

备注

擦除较大的 flash 区域可能会非常耗时，并可能导致任务连续运行，触发 TWDT 超时。以下两种方法可以避免这种情况：

- 在 menuconfig 中增加 CONFIG_ESP_TASK_WDT_TIMEOUT_S，延长看门狗超时时间。

- 在擦除 flash 区域前，调用 `esp_task_wdt_init()` 增加看门狗超时时间。

如需了解更多信息，请参考 SPI flash API。

以下配置选项控制 TWDT 配置，默认情况下全部启用：

- CONFIG_ESP_TASK_WDT_EN - 启用 TWDT 功能。如果禁用此选项， TWDT 即使运行时已初始化也无法使用。

- CONFIG_ESP_TASK_WDT_INIT - TWDT 在启动期间自动初始化。禁用此选项时，仍可以调用 `esp_task_wdt_init()` 在运行时初始化 TWDT。

- CONFIG_ESP_TASK_WDT_CHECK_IDLE_TASK_CPU0 - CPU0 空闲任务在启动时订阅了 TWDT。如果此选项被禁用，仍可以调用 `esp_task_wdt_init()` 再次订阅。

- CONFIG_ESP_TASK_WDT_CHECK_IDLE_TASK_CPU1 - CPU1 空闲任务在启动时订阅了 TWDT。

备注

如果 TWDT 超时，会默认在继续运行应用程序前打印警告和回溯。如希望超时触发系统严重错误和系统重置，可以通过 CONFIG_ESP_TASK_WDT_PANIC 进行配置。

## JTAG & 看门狗

在使用 OpenOCD 进行调试时，CPU 会在每次达到断点时停止运行。然而，如果遇到断点后看门狗定时器继续运行，就会最终触发复位，为调试代码带来巨大的困难。因此， OpenOCD 会在每个断点处禁用中断和任务的看门狗的硬件定时器。此外，在离开断点时，OpenOCD 也不会重新启用定时器，也就是说，中断看门狗和任务看门狗实际上被禁用。当 ESP32 通过 JTAG 连接到 OpenOCD 时，看门狗不会打印任何警告或出现严重错误。

## 应用示例

- system/task_watchdog 演示了如何初始化、订阅和取消订阅任务看门狗的任务和用户，以及任务和用户如何重置任务看门狗。

## API 参考

### Header File

- components/esp_system/include/esp_task_wdt.h

- This header file can be included with:

`
#include "esp_task_wdt.h"
`

### Functions

esp_err_t esp_task_wdt_init(const esp_task_wdt_config_t *config)

Initialize the Task Watchdog Timer (TWDT)

This function configures and initializes the TWDT. This function will subscribe the idle tasks if configured to do so. For other tasks, users can subscribe them using esp_task_wdt_add() or esp_task_wdt_add_user(). This function won't start the timer if no task have been registered yet.

备注

esp_task_wdt_init() must only be called after the scheduler is started. Moreover, it must not be called by multiple tasks simultaneously.

参数:

config -- [in] Configuration structure

返回:

- ESP_OK: Initialization was successful

- ESP_ERR_INVALID_STATE: Already initialized

- Other: Failed to initialize TWDT

esp_err_t esp_task_wdt_reconfigure(const esp_task_wdt_config_t *config)

Reconfigure the Task Watchdog Timer (TWDT)

The function reconfigures the running TWDT. It must already be initialized when this function is called.

备注

esp_task_wdt_reconfigure() must not be called by multiple tasks simultaneously.

参数:

config -- [in] Configuration structure

返回:

- ESP_OK: Reconfiguring was successful

- ESP_ERR_INVALID_STATE: TWDT not initialized yet

- Other: Failed to initialize TWDT

esp_err_t esp_task_wdt_deinit(void)

Deinitialize the Task Watchdog Timer (TWDT)

This function will deinitialize the TWDT, and unsubscribe any idle tasks. Calling this function whilst other tasks are still subscribed to the TWDT, or when the TWDT is already deinitialized, will result in an error code being returned.

备注

esp_task_wdt_deinit() must not be called by multiple tasks simultaneously.

返回:

- ESP_OK: TWDT successfully deinitialized

- Other: Failed to deinitialize TWDT

esp_err_t esp_task_wdt_add(TaskHandle_t task_handle)

Subscribe a task to the Task Watchdog Timer (TWDT)

This function subscribes a task to the TWDT. Each subscribed task must periodically call esp_task_wdt_reset() to prevent the TWDT from elapsing its timeout period. Failure to do so will result in a TWDT timeout.

参数:

task_handle -- Handle of the task. Input NULL to subscribe the current running task to the TWDT

返回:

- ESP_OK: Successfully subscribed the task to the TWDT

- Other: Failed to subscribe task

esp_err_t esp_task_wdt_add_user(const char *user_name, esp_task_wdt_user_handle_t *user_handle_ret)

Subscribe a user to the Task Watchdog Timer (TWDT)

This function subscribes a user to the TWDT. A user of the TWDT is usually a function that needs to run periodically. Each subscribed user must periodically call esp_task_wdt_reset_user() to prevent the TWDT from elapsing its timeout period. Failure to do so will result in a TWDT timeout.

参数:

- user_name -- [in] String to identify the user

- user_handle_ret -- [out] Handle of the user

返回:

- ESP_OK: Successfully subscribed the user to the TWDT

- Other: Failed to subscribe user

esp_err_t esp_task_wdt_reset(void)

Reset the Task Watchdog Timer (TWDT) on behalf of the currently running task.

This function will reset the TWDT on behalf of the currently running task. Each subscribed task must periodically call this function to prevent the TWDT from timing out. If one or more subscribed tasks fail to reset the TWDT on their own behalf, a TWDT timeout will occur.

返回:

- ESP_OK: Successfully reset the TWDT on behalf of the currently running task

- Other: Failed to reset

esp_err_t esp_task_wdt_reset_user(esp_task_wdt_user_handle_t user_handle)

Reset the Task Watchdog Timer (TWDT) on behalf of a user.

This function will reset the TWDT on behalf of a user. Each subscribed user must periodically call this function to prevent the TWDT from timing out. If one or more subscribed users fail to reset the TWDT on their own behalf, a TWDT timeout will occur.

参数:

user_handle -- [in] User handle

- ESP_OK: Successfully reset the TWDT on behalf of the user

- Other: Failed to reset

esp_err_t esp_task_wdt_delete(TaskHandle_t task_handle)

Unsubscribes a task from the Task Watchdog Timer (TWDT)

This function will unsubscribe a task from the TWDT. After being unsubscribed, the task should no longer call esp_task_wdt_reset().

参数:

task_handle -- [in] Handle of the task. Input NULL to unsubscribe the current running task.

返回:

- ESP_OK: Successfully unsubscribed the task from the TWDT

- Other: Failed to unsubscribe task

esp_err_t esp_task_wdt_delete_user(esp_task_wdt_user_handle_t user_handle)

Unsubscribes a user from the Task Watchdog Timer (TWDT)

This function will unsubscribe a user from the TWDT. After being unsubscribed, the user should no longer call esp_task_wdt_reset_user().

参数:

user_handle -- [in] User handle

返回:

- ESP_OK: Successfully unsubscribed the user from the TWDT

- Other: Failed to unsubscribe user

esp_err_t esp_task_wdt_status(TaskHandle_t task_handle)

Query whether a task is subscribed to the Task Watchdog Timer (TWDT)

This function will query whether a task is currently subscribed to the TWDT, or whether the TWDT is initialized.

参数:

task_handle -- [in] Handle of the task. Input NULL to query the current running task.

返回:

:

- ESP_OK: The task is currently subscribed to the TWDT

- ESP_ERR_NOT_FOUND: The task is not subscribed

- ESP_ERR_INVALID_STATE: TWDT was never initialized

void esp_task_wdt_isr_user_handler(void)

User ISR callback placeholder.

This function is called by task_wdt_isr function (ISR for when TWDT times out). It can be defined in user code to handle TWDT events.

备注

It has the same limitations as the interrupt function. Do not use ESP_LOGx functions inside.

esp_err_t esp_task_wdt_print_triggered_tasks(task_wdt_msg_handler msg_handler, void *opaque, int *cpus_fail)

Prints or retrieves information about tasks/users that triggered the Task Watchdog Timeout.

This function provides various operations to handle tasks/users that did not reset the Task Watchdog in time. It can print detailed information about these tasks/users, such as their names, associated CPUs, and whether they have been reset. Additionally, it can retrieve the total length of the printed information or the CPU affinity of the failing tasks.

备注

- If `msg_handler` is not provided, the information will be printed to console using ESP_EARLY_LOGE.

- If `msg_handler` is provided, the function will send the printed information to the provided message handler function.

- If `cpus_fail` is provided, the function will store the CPU affinity of the failing tasks in the provided integer.

- During the execution of this function, logging is allowed in critical sections, as TWDT timeouts are considered fatal errors.

参数:

- msg_handler -- [in] Optional message handler function that will be called for each printed line.

- opaque -- [in] Optional pointer to opaque data that will be passed to the message handler function.

- cpus_fail -- [out] Optional pointer to an integer where the CPU affinity of the failing tasks will be stored.

返回:

- ESP_OK: The function executed successfully.

- ESP_FAIL: No triggered tasks were found, and thus no information was printed or retrieved.

### Structures

struct esp_task_wdt_config_t

Task Watchdog Timer (TWDT) configuration structure.

Public Members

uint32_t timeout_ms

TWDT timeout duration in milliseconds

uint32_t idle_core_mask

Bitmask of the core whose idle task should be subscribed on initialization where 1 << i means that core i's idle task will be monitored by the TWDT

bool trigger_panic

Trigger panic when timeout occurs

### Type Definitions

typedef struct esp_task_wdt_user_handle_s *esp_task_wdt_user_handle_t

Task Watchdog Timer (TWDT) user handle.

typedef void (*task_wdt_msg_handler)(void *opaque, const char *msg)

此文档对您有帮助吗？

- 反馈已收到，谢谢！

- 如果您有其他意见，欢迎填写乐鑫文档反馈表。

- 我们重视您的反馈。

- 您可以填写乐鑫文档反馈表告诉我们如何改进该文档。
