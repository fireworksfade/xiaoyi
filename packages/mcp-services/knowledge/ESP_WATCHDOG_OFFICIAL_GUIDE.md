Source: https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-reference/system/wdts.html

Watchdogs
[中文]
The purpose of a watchdog timer is to monitor the system's operation and automatically recover from software or hardware faults by restarting the system if it becomes unresponsive.
Overview
ESP-IDF supports multiple types of watchdog timers:
Interrupt Watchdog Timer (IWDT)

Task Watchdog Timer (TWDT)

RTC/LP Watchdog Timer (RTC_WDT/LP_WDT)

The Interrupt Watchdog Timer (IWDT) is responsible for ensuring that ISRs (Interrupt Service Routines) are not blocked from running for a prolonged period of time, and prevents an ISR from getting stuck during execution.
The Task Watchdog Timer (TWDT) is responsible for detecting instances of tasks running without yielding for too long.
The RTC/LP Watchdog Timer (RTC_WDT) can be used to track the boot time from power-up until the user's main function. It can also be used during panic handling and in the low-power domain.
The various watchdog timers can be enabled by Editing the Configuration. However, the TWDT can also be enabled during runtime.

Hardware Watchdog Timers
The chips have two groups of watchdog timers:
Main System Watchdog Timer (MWDT_WDT) - used by Interrupt Watchdog Timer (IWDT) and Task Watchdog Timer (TWDT).

RTC Watchdog Timer (RTC_WDT) - used to track the boot time from power-up until the user's main function (by default RTC Watchdog is disabled immediately before the user's main function).

Refer to the Watchdog section to understand how watchdogs are utilized in the bootloader.
The app's behaviour can be adjusted so the RTC Watchdog remains enabled after app startup. The Watchdog would need to be explicitly reset (i.e., fed) or disabled by the app to avoid the chip reset. To do this, set the CONFIG_BOOTLOADER_WDT_DISABLE_IN_USER_CODE option, modify the app as needed, and then recompile the app. In this case, the following APIs should be used:
wdt_hal_disable(): see To Disable RTC_WDT

wdt_hal_feed(): see To Reset the RTC_WDT Counter

rtc_wdt_feed()

rtc_wdt_disable()

If RTC_WDT is not reset/disabled in time, the chip will be automatically reset. See RTC Watchdog Timeout for more information.

Interrupt Watchdog Timer (IWDT)
The purpose of the IWDT is to ensure that interrupt service routines (ISRs) are not blocked from running for a prolonged period of time (i.e., the IWDT timeout period). Preventing ISRs from running in a timely manner is undesirable as it can increase ISR latency, and also prevent task switching (as task switching is executed from an ISR). The things that can block ISRs from running include:
Disabling interrupts

Critical Sections (also disables interrupts)

Other same/higher priority ISRs which block same/lower priority ISRs from running

The IWDT utilizes the MWDT_WDT watchdog timer in Timer Group 1 as its underlying hardware timer and leverages the FreeRTOS tick interrupt on each CPU to feed the watchdog timer. If the tick interrupt on a particular CPU is not executed within the IWDT timeout period, it indicates that something is blocking ISRs from being run on that CPU (see the list of reasons above).
When the IWDT times out, the default action is to invoke the panic handler and display the panic reason as InterruptwdttimeoutonCPU0 or InterruptwdttimeoutonCPU1 (as applicable). Depending on the panic handler's configured behavior (see CONFIG_ESP_SYSTEM_PANIC), users can then debug the source of the IWDT timeout (via the backtrace, OpenOCD, gdbstub etc) or simply reset the chip (which may be preferred in a production environment).
If for whatever reason the panic handler is unable to run after an IWDT timeout, the IWDT has a second stage timeout that will hard-reset the chip (i.e., a system reset).
Configuration
The IWDT is enabled by default via the CONFIG_ESP_INT_WDT option.

The IWDT's timeout is configured by setting the CONFIG_ESP_INT_WDT_TIMEOUT_MS option.
Note that the default timeout is higher if PSRAM support is enabled, as a critical section or interrupt routine that accesses a large amount of PSRAM takes longer to complete in some circumstances.

The configured timeout duration for IWDT should always be at least twice longer than the period between two FreeRTOS ticks, e.g., if two FreeRTOS ticks occur 10 ms apart, then IWDT timeout duration should at least be more than 20 ms (see CONFIG_FREERTOS_HZ).

Tuning
If you find the IWDT timeout is triggered because an interrupt or critical section is running longer than the timeout period, consider rewriting the code:
Critical sections should be made as short as possible. Any non-critical code/computation should be placed outside the critical section.

Interrupt handlers should also perform the minimum possible amount of computation. Users can consider deferring any computation to a task by having the ISR push data to a task using queues.

Neither critical sections or interrupt handlers should ever block waiting for another event to occur. If changing the code to reduce the processing time is not possible or desirable, it is possible to increase the CONFIG_ESP_INT_WDT_TIMEOUT_MS setting instead.

Task Watchdog Timer (TWDT)
The Task Watchdog Timer (TWDT) is used to monitor particular tasks, ensuring that they are able to execute within a given timeout period. By default the TWDT watches the Idle Tasks of each CPU, however any task can subscribe to be watched by the TWDT. By watching the Idle Tasks of each CPU, the TWDT can detect instances of tasks running for a prolonged period of time without yielding. This can be an indicator of poorly written code that spinloops on a peripheral, or a task that is stuck in an infinite loop.
The TWDT is built around the MWDT_WDT watchdog timer in Timer Group 0. When a timeout occurs, an interrupt is triggered.
Users can define the function esp_task_wdt_isr_user_handler in the user code, in order to receive the timeout event and extend the default behavior.
Usage
The following functions can be used to watch tasks using the TWDT:
esp_task_wdt_init() to initialize the TWDT and subscribe the idle tasks.

esp_task_wdt_add() subscribes other tasks to the TWDT.

Once subscribed, esp_task_wdt_reset() should be called from the task to feed the TWDT.

esp_task_wdt_delete() unsubscribes a previously subscribed task.

esp_task_wdt_deinit() unsubscribes the idle tasks and deinitializes the TWDT.

In the case where applications need to watch at a more granular level (i.e., ensure that a particular functions/stub/code-path is called), the TWDT allows subscription of users.
esp_task_wdt_add_user() to subscribe an arbitrary user of the TWDT. This function returns a user handle to the added user.

esp_task_wdt_reset_user() must be called using the user handle in order to prevent a TWDT timeout.

esp_task_wdt_delete_user() unsubscribes an arbitrary user of the TWDT.

Configuration
The default timeout period for the TWDT is set using config item CONFIG_ESP_TASK_WDT_TIMEOUT_S. This should be set to at least as long as you expect any single task needs to monopolize the CPU (for example, if you expect the app will do a long intensive calculation and should not yield to other tasks). It is also possible to change this timeout at runtime by calling esp_task_wdt_init().
Note
Erasing large flash areas can be time consuming and can cause a task to run continuously, thus triggering a TWDT timeout. The following two methods can be used to avoid this:
Increase CONFIG_ESP_TASK_WDT_TIMEOUT_S in menuconfig for a larger watchdog timeout period.

You can also call esp_task_wdt_init() again to increase the watchdog timeout period before erasing a large flash area.

For more information, you can refer to SPI Flash API.

The following config options control TWDT configuration. They are all enabled by default:
CONFIG_ESP_TASK_WDT_EN - enables TWDT feature. If this option is disabled, TWDT cannot be used, even if initialized at runtime.

CONFIG_ESP_TASK_WDT_INIT - initializes the TWDT automatically during startup. If this option is disabled, it is still possible to initialize the Task WDT at runtime by calling esp_task_wdt_init().

CONFIG_ESP_TASK_WDT_CHECK_IDLE_TASK_CPU0 - subscribes CPU0 Idle task to the TWDT during startup. If this option is disabled, it is still possible to subscribe the idle task by calling esp_task_wdt_init() again, or by using esp_task_wdt_add() and passing the idle task handle obtained via xTaskGetIdleTaskHandleForCore().

CONFIG_ESP_TASK_WDT_CHECK_IDLE_TASK_CPU1 - Subscribes CPU1 Idle task to the TWDT during startup.

Note
On a TWDT timeout the default behaviour is to simply print a warning and a backtrace before continuing running the app. If you want a timeout to cause a panic and a system reset then this can be configured through CONFIG_ESP_TASK_WDT_PANIC.

Timeout Stages
Hardware watchdog timers in ESP-IDF have four timeout stages. If the WDT is not fed in the previous stage within the configured timeout duration of that stage, it will trigger the next stage. Each stage can be configured to take one of the actions listed below after the timeout duration:
Trigger an interrupt. When the stage expires, an interrupt is triggered.

Reset a CPU core. When the stage expires the designated CPU core will be reset.

Reset the main system. When the stage expires, the main system, including the MWDTs, will be reset. The main system includes the CPU and all peripherals. The RTC is an exception to this, and it will not be reset.

Reset the main system and RTC. When the stage expires the main system and the RTC will both be reset. This action is only available in the RTC_WDT.

Disabled. This stage will have no effects on the system.

The typical configuration of the stages can be done by having interrupt actions in the earlier stages and allowing stepwise handling up to a final system reset action in the later stages.
Stages can be configured via wdt_hal_config_stage() (or equivalent APIs), selecting actions per stage to match application behavior.

JTAG & Watchdogs
While debugging using OpenOCD, the CPUs are halted every time a breakpoint is reached. However if the watchdog timers continue to run when a breakpoint is encountered, they will eventually trigger a reset making it very difficult to debug code. Therefore OpenOCD will disable the hardware timers of both the interrupt and task watchdogs at every breakpoint. Moreover, OpenOCD will not re-enable them upon leaving the breakpoint. This means that interrupt watchdog and task watchdog functionality will essentially be disabled. No warnings or panics from either watchdogs will be generated when the ESP32 is connected to OpenOCD via JTAG.

Common Error Logs When WDT Triggers and Possible Resolutions
GuruMeditationError:Core0panic'ed(InterruptwdttimeoutonCPU0). followed by a backtrace: Indicates that the Interrupt Watchdog Timer (IWDT) has detected that interrupts have been blocked on CPU 0 for longer than the configured timeout period. This can be fixed by reducing the duration of long-running ISRs or critical sections, or by increasing the IWDT timeout period.

Taskwatchdoggottriggered.Thefollowingtasks/usersdidnotresetthewatchdogintime:-IDLE0(CPU0),Taskscurrentlyrunning:CPU0:main,CPU1:IDLE1: Indicates that the Task Watchdog Timer (TWDT) has detected that one or more tasks have not yielded within the configured timeout period, and hence the IDLE task couldn't feed the TWDT in time. This can be fixed by ensuring that tasks yield appropriately, reducing the duration of long-running tasks, or by increasing the TWDT timeout period. The user can also use esp_task_wdt_add(), esp_task_wdt_add_user() and esp_task_wdt_reset_user() APIs to find out which task and which code path inside that task is taking the longest time and causing the TWDT timeout.

CONFIG_BOOTLOADER_WDT_DISABLE_IN_USER_CODE is enabled and causes WDT timeout: Make sure RTC WDT is fed frequently enough from user code.

WDT Reset happens during boot-up: Ensure that a valid second stage bootloader is flashed correctly and investigate possible communication issues with external flash.

WDT Reset happens during operation: Try to identify when it happens, is it during a panic, a restart or enter/exit Light-sleep? If it happens during any of these system operations, it could point towards an issue inside ESP-IDF.

Application Examples
system/task_watchdog demonstrates how to initialize, subscribe and unsubscribe tasks and users to the task watchdog, and how tasks and users can reset (feed) the task watchdog.

API Reference
Header File
components/esp_system/include/esp_task_wdt.h

This header file can be included with:

#include"esp_task_wdt.h"

Functions
esp_err_tesp_task_wdt_init(constesp_task_wdt_config_t*config)
Initialize the Task Watchdog Timer (TWDT)
This function configures and initializes the TWDT. This function will subscribe the idle tasks if configured to do so. For other tasks, users can subscribe them using esp_task_wdt_add() or esp_task_wdt_add_user(). This function won't start the timer if no task have been registered yet.
Note
esp_task_wdt_init() must only be called after the scheduler is started. Moreover, it must not be called by multiple tasks simultaneously.

Parameters:config -- [in] Configuration structure
Returns:ESP_OK: Initialization was successful

ESP_ERR_INVALID_STATE: Already initialized

Other: Failed to initialize TWDT

esp_err_tesp_task_wdt_reconfigure(constesp_task_wdt_config_t*config)
Reconfigure the Task Watchdog Timer (TWDT)
The function reconfigures the running TWDT. It must already be initialized when this function is called.
Note
esp_task_wdt_reconfigure() must not be called by multiple tasks simultaneously.

Parameters:config -- [in] Configuration structure
Returns:ESP_OK: Reconfiguring was successful

ESP_ERR_INVALID_STATE: TWDT not initialized yet

Other: Failed to initialize TWDT

esp_err_tesp_task_wdt_deinit(void)
Deinitialize the Task Watchdog Timer (TWDT)
This function will deinitialize the TWDT, and unsubscribe any idle tasks. Calling this function whilst other tasks are still subscribed to the TWDT, or when the TWDT is already deinitialized, will result in an error code being returned.
Note
esp_task_wdt_deinit() must not be called by multiple tasks simultaneously.

Returns:ESP_OK: TWDT successfully deinitialized

Other: Failed to deinitialize TWDT

esp_err_tesp_task_wdt_add(TaskHandle_ttask_handle)
Subscribe a task to the Task Watchdog Timer (TWDT)
This function subscribes a task to the TWDT. Each subscribed task must periodically call esp_task_wdt_reset() to prevent the TWDT from elapsing its timeout period. Failure to do so will result in a TWDT timeout.
Parameters:task_handle -- Handle of the task. Input NULL to subscribe the current running task to the TWDT
Returns:ESP_OK: Successfully subscribed the task to the TWDT

Other: Failed to subscribe task

esp_err_tesp_task_wdt_add_user(constchar*user_name, esp_task_wdt_user_handle_t*user_handle_ret)
Subscribe a user to the Task Watchdog Timer (TWDT)
This function subscribes a user to the TWDT. A user of the TWDT is usually a function that needs to run periodically. Each subscribed user must periodically call esp_task_wdt_reset_user() to prevent the TWDT from elapsing its timeout period. Failure to do so will result in a TWDT timeout.
Parameters:user_name -- [in] String to identify the user

user_handle_ret -- [out] Handle of the user

Returns:ESP_OK: Successfully subscribed the user to the TWDT

Other: Failed to subscribe user

esp_err_tesp_task_wdt_reset(void)
Reset the Task Watchdog Timer (TWDT) on behalf of the currently running task.
This function will reset the TWDT on behalf of the currently running task. Each subscribed task must periodically call this function to prevent the TWDT from timing out. If one or more subscribed tasks fail to reset the TWDT on their own behalf, a TWDT timeout will occur.
Returns:ESP_OK: Successfully reset the TWDT on behalf of the currently running task

Other: Failed to reset

esp_err_tesp_task_wdt_reset_user(esp_task_wdt_user_handle_tuser_handle)
Reset the Task Watchdog Timer (TWDT) on behalf of a user.
This function will reset the TWDT on behalf of a user. Each subscribed user must periodically call this function to prevent the TWDT from timing out. If one or more subscribed users fail to reset the TWDT on their own behalf, a TWDT timeout will occur.
Parameters:user_handle -- [in] User handleESP_OK: Successfully reset the TWDT on behalf of the user

Other: Failed to reset

esp_err_tesp_task_wdt_delete(TaskHandle_ttask_handle)
Unsubscribes a task from the Task Watchdog Timer (TWDT)
This function will unsubscribe a task from the TWDT. After being unsubscribed, the task should no longer call esp_task_wdt_reset().
Parameters:task_handle -- [in] Handle of the task. Input NULL to unsubscribe the current running task.
Returns:ESP_OK: Successfully unsubscribed the task from the TWDT

Other: Failed to unsubscribe task

esp_err_tesp_task_wdt_delete_user(esp_task_wdt_user_handle_tuser_handle)
Unsubscribes a user from the Task Watchdog Timer (TWDT)
This function will unsubscribe a user from the TWDT. After being unsubscribed, the user should no longer call esp_task_wdt_reset_user().
Parameters:user_handle -- [in] User handle
Returns:ESP_OK: Successfully unsubscribed the user from the TWDT

Other: Failed to unsubscribe user

esp_err_tesp_task_wdt_status(TaskHandle_ttask_handle)
Query whether a task is subscribed to the Task Watchdog Timer (TWDT)
This function will query whether a task is currently subscribed to the TWDT, or whether the TWDT is initialized.
Parameters:task_handle -- [in] Handle of the task. Input NULL to query the current running task.
Returns::ESP_OK: The task is currently subscribed to the TWDT

ESP_ERR_NOT_FOUND: The task is not subscribed

ESP_ERR_INVALID_STATE: TWDT was never initialized

voidesp_task_wdt_isr_user_handler(void)
User ISR callback placeholder.
This function is called by task_wdt_isr function (ISR for when TWDT times out). It can be defined in user code to handle TWDT events.
Note
It has the same limitations as the interrupt function. Do not use ESP_LOGx functions inside.

esp_err_tesp_task_wdt_print_triggered_tasks(task_wdt_msg_handlermsg_handler, void*opaque, int*cpus_fail)
Prints or retrieves information about tasks/users that triggered the Task Watchdog Timeout.
This function provides various operations to handle tasks/users that did not reset the Task Watchdog in time. It can print detailed information about these tasks/users, such as their names, associated CPUs, and whether they have been reset. Additionally, it can retrieve the total length of the printed information or the CPU affinity of the failing tasks.
Note
If msg_handler is not provided, the information will be printed to console using ESP_EARLY_LOGE.

If msg_handler is provided, the function will send the printed information to the provided message handler function.

If cpus_fail is provided, the function will store the CPU affinity of the failing tasks in the provided integer.

During the execution of this function, logging is allowed in critical sections, as TWDT timeouts are considered fatal errors.

Parameters:msg_handler -- [in] Optional message handler function that will be called for each printed line.

opaque -- [in] Optional pointer to opaque data that will be passed to the message handler function.

cpus_fail -- [out] Optional pointer to an integer where the CPU affinity of the failing tasks will be stored.

Returns:ESP_OK: The function executed successfully.

ESP_FAIL: No triggered tasks were found, and thus no information was printed or retrieved.

Structures
structesp_task_wdt_config_t
Task Watchdog Timer (TWDT) configuration structure.
Public Members
uint32_ttimeout_ms
TWDT timeout duration in milliseconds
uint32_tidle_core_mask
Bitmask of the core whose idle task should be subscribed on initialization where 1 << i means that core i's idle task will be monitored by the TWDT
booltrigger_panic
Trigger panic when timeout occurs

Type Definitions
typedefstructesp_task_wdt_user_handle_s*esp_task_wdt_user_handle_t
Task Watchdog Timer (TWDT) user handle.
typedefvoid(*task_wdt_msg_handler)(void*opaque,constchar*msg)

Was this page helpful?

Thank you! We received your feedback.
If you have any comments, fill in Espressif Documentation Feedback Form.

We value your feedback.
Let us know how we can improve this page by filling in Espressif Documentation Feedback Form.