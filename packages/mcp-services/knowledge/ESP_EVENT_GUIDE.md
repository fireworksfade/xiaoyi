Source: https://docs.espressif.com/projects/esp-idf/zh_CN/latest/esp32/api-reference/system/esp_event.html

API 参考

系统 API

事件循环库

在 GitHub 上编辑

事件循环库

[English]

概述

事件循环库使组件能够声明事件，允许其他组件注册处理程序（即在事件发生时执行的代码片段）。此时，无需直接涉及应用程序，松散耦合组件也能够在其他组件状态变化时附加所需的行为。此外，通过将代码执行序列化，在指定的任务中运行事件循环库，可以简化事件处理程序，实现更高效的事件处理。

例如，当某个高级库要使用 Wi-Fi 库时，它可以直接订阅 ESP32 Wi-Fi 编程模型 ，对有关事件做出相应。

备注

蓝牙栈各模块通过调用专用回调函数向应用程序传递事件，而非通过事件循环库传递。

调用 esp_event API

使用事件循环库时应注意区分“事件”与“事件循环”。

事件表示重要的发生事件，如 Wi-Fi 成功连接到接入点。引用事件时应使用由两部分组成的标识符，详情请参阅 事件定义与事件声明 。事件循环是连接事件和事件处理程序之间的桥梁，事件源通过使用事件循环库提供的 API 将事件发布到事件循环中，注册到事件循环中的事件处理程序会响应特定类型的事件。

以下为事件循环库的使用流程：

定义一个函数，并在事件发布到事件循环中时运行该函数。此函数被称为事件处理程序，应具有与 esp_event_handler_t 同类型的签名。

调用 esp_event_loop_create() 创建事件循环，该函数输出类型为 esp_event_loop_handle_t 的循环句柄，使用此 API 创建的事件循环称为用户事件循环。另有一种特殊事件循环，请参阅 默认事件循环 。

调用 esp_event_handler_register_with() 将事件处理程序注册到循环中。处理程序可以注册到多个循环中，请参阅 注册处理程序注意事项 。

事件源调用 esp_event_post_to() 将事件发布到事件循环中。

调用 esp_event_handler_unregister_with() ，组件可以在事件循环中取消注册事件处理程序。

调用 esp_event_loop_delete() 删除不再需要的事件循环。

上述流程代码如下：

// 1. 定义事件处理程序voidrun_on_event(void*handler_arg,esp_event_base_tbase,int32_tid,void*event_data){// 事件处理程序逻辑}voidapp_main(){// 2. 用一个类型为 esp_event_loop_args_t 的配置结构体，指定所创建循环的属性。获取一个类型为 esp_event_loop_handle_t 的句柄，用于其他 API 引用循环、执行操作。esp_event_loop_args_tloop_args={.queue_size=...,.task_name=....task_priority=...,.task_stack_size=...,.task_core_id=...};esp_event_loop_handle_tloop_handle;esp_event_loop_create(&loop_args,&loop_handle);// 3. 注册在 (1) 中定义的事件处理程序。MY_EVENT_BASE 和 MY_EVENT_ID 指定了一个假设事件：将处理程序 run_on_event 发布到循环中时，执行该处理程序。esp_event_handler_register_with(loop_handle,MY_EVENT_BASE,MY_EVENT_ID,run_on_event,...);...// 4. 将事件发布到循环中。此时，事件排入事件循环队列，在某个时刻，事件循环会执行已注册到发布事件的事件处理程序，例如此处的 run_on_event。为简化过程，此示例从 app_main 调用 esp_event_post_to，实际应用中可从任何其他任务中发布事件。esp_event_post_to(loop_handle,MY_EVENT_BASE,MY_EVENT_ID,...);...// 5. 注销无用的处理程序。esp_event_handler_unregister_with(loop_handle,MY_EVENT_BASE,MY_EVENT_ID,run_on_event);...// 6. 删除无用的事件循环。esp_event_loop_delete(loop_handle);}

事件定义与事件声明

如前所述，事件标识符由两部分组成：事件根基和事件 ID。事件根基标识独立的事件组；事件 ID 标识组中的特定事件。可以将事件根基和事件 ID 类比为人的姓和名，姓表示一个家族，名表示家族中的某个人。

事件循环库提供了宏以便声明和定义事件根基。

声明事件根基：

ESP_EVENT_DECLARE_BASE(EVENT_BASE);

定义事件根基：

ESP_EVENT_DEFINE_BASE(EVENT_BASE);

备注

在 ESP-IDF 中，系统事件的根基标识符为大写字母，并以 _EVENT 结尾。例如，Wi-Fi 事件的根基声明为 WIFI_EVENT ，以太网的事件根基声明为 ETHERNET_EVENT 等。这样一来，事件根基与常量类似（尽管根据宏 ESP_EVENT_DECLARE_BASE 和 ESP_EVENT_DEFINE_BASE 的定义，它们属于全局变量）。

建议以枚举类型声明事件 ID，它们通常放在公共头文件中。

事件 ID：

enum{EVENT_ID_1,EVENT_ID_2,EVENT_ID_3,...}

默认事件循环

默认事件循环是一种特殊循环，用于处理系统事件（如 Wi-Fi 事件）。用户无法使用该循环的句柄，创建、删除、注册/注销处理程序以及事件发布均通过用户事件循环 API 的变体完成，下表列出了这些变体及其对应用户事件循环。

用户事件循环

默认事件循环

esp_event_loop_create()

esp_event_loop_create_default()

esp_event_loop_delete()

esp_event_loop_delete_default()

esp_event_handler_register_with()

esp_event_handler_register()

esp_event_handler_unregister_with()

esp_event_handler_unregister()

esp_event_post_to()

esp_event_post()

比较二者签名可知，它们大部分是相似的，唯一区别在于默认事件循环的 API 不需要指定循环句柄。

除了 API 的差异和用于系统事件的特殊分类外，默认事件循环和用户事件循环的行为并无差异。实际上，用户甚至可以将自己的事件发布到默认事件循环中，以节省内存而无需创建自己的循环。

注册处理程序注意事项

通过重复调用 esp_event_handler_register_with() ，可以将单个处理程序独立注册到多个事件中，且每次调用均可指定处理程序应执行的具体事件根基和事件 ID。

然而，在某些情况下，你可能希望处理程序在以下情况时执行：

所有发布到循环的事件

特定基本标识符的所有事件

为此，可调用特殊的事件根基标识符 ESP_EVENT_ANY_BASE 和特殊的事件 ESP_EVENT_ANY_ID 实现，这些特殊标识符可以作为 esp_event_handler_register_with() 的事件根基和事件 ID 参数传递。

因此 esp_event_handler_register_with() 的有效参数为：

<event base>, <event ID> - 根基为 <event base> 且 ID 为 <event ID> 的事件发布到循环中时，执行处理程序。

<event base>, ESP_EVENT_ANY_ID - 任何根基为 <event base> 的事件发布到循环中时，执行处理程序。

ESP_EVENT_ANY_BASE, ESP_EVENT_ANY_ID - 任何事件发布到循环中时，执行处理程序。

例如，如果注册了以下处理程序：

esp_event_handler_register_with(loop_handle,MY_EVENT_BASE,MY_EVENT_ID,run_on_event_1,...);esp_event_handler_register_with(loop_handle,MY_EVENT_BASE,ESP_EVENT_ANY_ID,run_on_event_2,...);esp_event_handler_register_with(loop_handle,ESP_EVENT_ANY_BASE,ESP_EVENT_ANY_ID,run_on_event_3,...);

如果假设事件由 MY_EVENT_BASE 和 MY_EVENT_ID 组成，则三个处理程序 run_on_event_1 、 run_on_event_2 和 run_on_event_3 都会执行。

如果假设事件由 MY_EVENT_BASE 和 MY_OTHER_EVENT_ID 组成，则仅执行处理程序 run_on_event_2 和 run_on_event_3 。

如果假设事件由 MY_OTHER_EVENT_BASE 和 MY_OTHER_EVENT_ID 组成，则仅执行处理程序 run_on_event_3 。

处理程序自行注销

通常情况下，由事件循环运行的事件处理程序 不允许在该事件循环上执行任何注册/注销活动 ，但允许处理程序自行注销。例如，可以执行以下操作：

voidrun_on_event(void*handler_arg,esp_event_base_tbase,int32_tid,void*event_data){esp_event_loop_handle_t*loop_handle=(esp_event_loop_handle_t*)handler_arg;esp_event_handler_unregister_with(*loop_handle,MY_EVENT_BASE,MY_EVENT_ID,run_on_event);}voidapp_main(void){esp_event_loop_handle_tloop_handle;esp_event_loop_create(&loop_args,&loop_handle);esp_event_handler_register_with(loop_handle,MY_EVENT_BASE,MY_EVENT_ID,run_on_event,&loop_handle);// ... 发布事件 MY_EVENT_BASE 和 MY_EVENT_ID，并在某些时候运行循环}

注册处理程序及处理程序调度顺序

一般而言，对于在调度期间与某个已发布事件匹配的处理程序，先注册的也会先执行。在所有注册均使用单个任务执行的情况下，可以通过在其他处理程序注册前注册目标处理程序，控制处理程序的执行顺序。如果计划利用这一规则，在有多个任务注册处理程序的情况下要多加小心。此时，虽然“先注册，先执行”的规则仍然成立，但率先执行的任务也会率先注册其处理程序，而由单个任务连续注册的处理函数仍然按相对顺序调度。但如果该任务在注册期间被另一个任务抢占，而该任务还注册了处理程序，则在调度期间，那些处理程序也将在处理其他任务时执行。

事件循环性能分析

要启动数据收集，统计所有已创建事件循环的数据，请激活配置选项 CONFIG_ESP_EVENT_LOOP_PROFILING ，函数 esp_event_dump() 可将收集的统计数据输出到文件流中。有关转储信息的更多详情，请参阅 esp_event_dump() API 参考。

应用示例

system/esp_event/default_event_loop 演示了如何使用 ESP32 的默认事件循环系统来发布和处理事件，包括声明和定义事件、创建默认事件循环、将事件发布到循环中，以及注册/注销事件处理程序。

system/esp_event/user_event_loops 演示了如何在 ESP32 上创建和使用用户事件循环，包括创建和运行事件循环、注册和注销处理程序、以及发布事件，能够处理超出默认事件循环的不同示例。

API 参考

Header File

components/esp_event/include/esp_event.h

This header file can be included with:

#include"esp_event.h"

This header file is a part of the API provided by the esp_event component. To declare that your component depends on esp_event , add the following to your CMakeLists.txt:

REQUIRES esp_event

or

PRIV_REQUIRES esp_event

Functions

esp_err_t esp_event_loop_create ( const esp_event_loop_args_t * event_loop_args , esp_event_loop_handle_t * event_loop )

Create a new event loop.

参数 :

event_loop_args -- [in] configuration structure for the event loop to create

event_loop -- [out] handle to the created event loop

返回 :

ESP_OK: Success

ESP_ERR_INVALID_ARG: event_loop_args or event_loop was NULL

ESP_ERR_NO_MEM: Cannot allocate memory for event loops list

ESP_FAIL: Failed to create task loop

Others: Fail

esp_err_t esp_event_loop_delete ( esp_event_loop_handle_t event_loop )

Delete an existing event loop.

参数 :

event_loop -- [in] event loop to delete, must not be NULL

返回 :

ESP_OK: Success

Others: Fail

esp_err_t esp_event_loop_create_default ( void )

Create default event loop.

返回 :

ESP_OK: Success

ESP_ERR_NO_MEM: Cannot allocate memory for event loops list

ESP_ERR_INVALID_STATE: Default event loop has already been created

ESP_FAIL: Failed to create task loop

Others: Fail

esp_err_t esp_event_loop_delete_default ( void )

Delete the default event loop.

返回 :

ESP_OK: Success

Others: Fail

esp_err_t esp_event_loop_run ( esp_event_loop_handle_t event_loop , TickType_t ticks_to_run )

Dispatch events posted to an event loop.

This function is used to dispatch events posted to a loop with no dedicated task, i.e. task name was set to NULL in event_loop_args argument during loop creation. This function includes an argument to limit the amount of time it runs, returning control to the caller when that time expires (or some time afterwards). There is no guarantee that a call to this function will exit at exactly the time of expiry. There is also no guarantee that events have been dispatched during the call, as the function might have spent all the allotted time waiting on the event queue. Once an event has been dequeued, however, it is guaranteed to be dispatched. This guarantee contributes to not being able to exit exactly at time of expiry as (1) blocking on internal mutexes is necessary for dispatching the dequeued event, and (2) during dispatch of the dequeued event there is no way to control the time occupied by handler code execution. The guaranteed time of exit is therefore the allotted time + amount of time required to dispatch the last dequeued event.

In cases where waiting on the queue times out, ESP_OK is returned and not ESP_ERR_TIMEOUT, since it is normal behavior.

备注

encountering an unknown event that has been posted to the loop will only generate a warning, not an error.

参数 :

event_loop -- [in] event loop to dispatch posted events from, must not be NULL

ticks_to_run -- [in] number of ticks to run the loop

返回 :

ESP_OK: Success

Others: Fail

esp_err_t esp_event_handler_register ( esp_event_base_t event_base , int32_t event_id , esp_event_handler_t event_handler , void * event_handler_arg )

Register an event handler to the system event loop (legacy).

This function can be used to register a handler for either: (1) specific events, (2) all events of a certain event base, or (3) all events known by the system event loop.

specific events: specify exact event_base and event_id

all events of a certain base: specify exact event_base and use ESP_EVENT_ANY_ID as the event_id

all events known by the loop: use ESP_EVENT_ANY_BASE for event_base and ESP_EVENT_ANY_ID as the event_id

Registering multiple handlers to events is possible. Registering a single handler to multiple events is also possible. However, registering the same handler to the same event multiple times would cause the overwriting of the event_handler_arg but the handler will be kept at the same position in the list associated with the event that triggers it. It means that the call order of registered handlers for that event will remain the same.

备注

the event loop library does not maintain a copy of event_handler_arg, therefore the user should ensure that event_handler_arg still points to a valid location by the time the handler gets called

参数 :

event_base -- [in] the base ID of the event to register the handler for

event_id -- [in] the ID of the event to register the handler for

event_handler -- [in] the handler function which gets called when the event is dispatched

event_handler_arg -- [in] data, aside from event data, that is passed to the handler when it is called

返回 :

ESP_OK: Success

ESP_ERR_NO_MEM: Cannot allocate memory for the handler

ESP_ERR_INVALID_ARG: Invalid combination of event base and event ID

Others: Fail

esp_err_t esp_event_handler_register_with ( esp_event_loop_handle_t event_loop , esp_event_base_t event_base , int32_t event_id , esp_event_handler_t event_handler , void * event_handler_arg )

Register an event handler to a specific loop (legacy).

This function behaves in the same manner as esp_event_handler_register, except the additional specification of the event loop to register the handler to.

备注

the event loop library does not maintain a copy of event_handler_arg, therefore the user should ensure that event_handler_arg still points to a valid location by the time the handler gets called

参数 :

event_loop -- [in] the event loop to register this handler function to, must not be NULL

event_base -- [in] the base ID of the event to register the handler for

event_id -- [in] the ID of the event to register the handler for

event_handler -- [in] the handler function which gets called when the event is dispatched

event_handler_arg -- [in] data, aside from event data, that is passed to the handler when it is called

返回 :

ESP_OK: Success

ESP_ERR_NO_MEM: Cannot allocate memory for the handler

ESP_ERR_INVALID_ARG: Invalid combination of event base and event ID

Others: Fail

esp_err_t esp_event_handler_instance_register_with ( esp_event_loop_handle_t event_loop , esp_event_base_t event_base , int32_t event_id , esp_event_handler_t event_handler , void * event_handler_arg , esp_event_handler_instance_t * instance )

Register an instance of event handler to a specific loop.

This function can be used to register a handler for either: (1) specific events, (2) all events of a certain event base, or (3) all events known by the system event loop.

specific events: specify exact event_base and event_id

all events of a certain base: specify exact event_base and use ESP_EVENT_ANY_ID as the event_id

all events known by the loop: use ESP_EVENT_ANY_BASE for event_base and ESP_EVENT_ANY_ID as the event_id

Besides the error, the function returns an instance object as output parameter to identify each registration. This is necessary to remove (unregister) the registration before the event loop is deleted.

Registering multiple handlers to events, registering a single handler to multiple events as well as registering the same handler to the same event multiple times is possible. Each registration yields a distinct instance object which identifies it over the registration lifetime.

备注

the event loop library does not maintain a copy of event_handler_arg, therefore the user should ensure that event_handler_arg still points to a valid location by the time the handler gets called

备注

Calling this function with instance set to NULL is equivalent to calling esp_event_handler_register_with.

参数 :

event_loop -- [in] the event loop to register this handler function to, must not be NULL

event_base -- [in] the base ID of the event to register the handler for

event_id -- [in] the ID of the event to register the handler for

event_handler -- [in] the handler function which gets called when the event is dispatched

event_handler_arg -- [in] data, aside from event data, that is passed to the handler when it is called

instance -- [out] An event handler instance object related to the registered event handler and data, can be NULL. This needs to be kept if the specific callback instance should be unregistered before deleting the whole event loop. Registering the same event handler multiple times is possible and yields distinct instance objects. The data can be the same for all registrations. If no unregistration is needed, but the handler should be deleted when the event loop is deleted, instance can be NULL.

返回 :

ESP_OK: Success

ESP_ERR_NO_MEM: Cannot allocate memory for the handler

ESP_ERR_INVALID_ARG: Invalid combination of event base and event ID or instance is NULL

Others: Fail

esp_err_t esp_event_handler_instance_register ( esp_event_base_t event_base , int32_t event_id , esp_event_handler_t event_handler , void * event_handler_arg , esp_event_handler_instance_t * instance )

Register an instance of event handler to the default loop.

This function does the same as esp_event_handler_instance_register_with, except that it registers the handler to the default event loop.

备注

the event loop library does not maintain a copy of event_handler_arg, therefore the user should ensure that event_handler_arg still points to a valid location by the time the handler gets called

备注

Calling this function with instance set to NULL is equivalent to calling esp_event_handler_register.

参数 :

event_base -- [in] the base ID of the event to register the handler for

event_id -- [in] the ID of the event to register the handler for

event_handler -- [in] the handler function which gets called when the event is dispatched

event_handler_arg -- [in] data, aside from event data, that is passed to the handler when it is called

instance -- [out] An event handler instance object related to the registered event handler and data, can be NULL. This needs to be kept if the specific callback instance should be unregistered before deleting the whole event loop. Registering the same event handler multiple times is possible and yields distinct instance objects. The data can be the same for all registrations. If no unregistration is needed, but the handler should be deleted when the event loop is deleted, instance can be NULL.

返回 :

ESP_OK: Success

ESP_ERR_NO_MEM: Cannot allocate memory for the handler

ESP_ERR_INVALID_ARG: Invalid combination of event base and event ID or instance is NULL

Others: Fail

esp_err_t esp_event_handler_unregister ( esp_event_base_t event_base , int32_t event_id , esp_event_handler_t event_handler )

Unregister a handler with the system event loop (legacy).

Unregisters a handler, so it will no longer be called during dispatch. Handlers can be unregistered for any combination of event_base and event_id which were previously registered. To unregister a handler, the event_base and event_id arguments must match exactly the arguments passed to esp_event_handler_register() when that handler was registered. Passing ESP_EVENT_ANY_BASE and/or ESP_EVENT_ANY_ID will only unregister handlers that were registered with the same wildcard arguments.

备注

When using ESP_EVENT_ANY_ID, handlers registered to specific event IDs using the same base will not be unregistered. When using ESP_EVENT_ANY_BASE, events registered to specific bases will also not be unregistered. This avoids accidental unregistration of handlers registered by other users or components.

参数 :

event_base -- [in] the base of the event with which to unregister the handler

event_id -- [in] the ID of the event with which to unregister the handler

event_handler -- [in] the handler to unregister

返回 :

ESP_OK success

返回 :

ESP_ERR_INVALID_ARG invalid combination of event base and event ID

返回 :

others fail

esp_err_t esp_event_handler_unregister_with ( esp_event_loop_handle_t event_loop , esp_event_base_t event_base , int32_t event_id , esp_event_handler_t event_handler )

Unregister a handler from a specific event loop (legacy).

This function behaves in the same manner as esp_event_handler_unregister, except the additional specification of the event loop to unregister the handler with.

参数 :

event_loop -- [in] the event loop with which to unregister this handler function, must not be NULL

event_base -- [in] the base of the event with which to unregister the handler

event_id -- [in] the ID of the event with which to unregister the handler

event_handler -- [in] the handler to unregister

返回 :

ESP_OK: Success

ESP_ERR_INVALID_ARG: Invalid combination of event base and event ID

Others: Fail

esp_err_t esp_event_handler_instance_unregister_with ( esp_event_loop_handle_t event_loop , esp_event_base_t event_base , int32_t event_id , esp_event_handler_instance_t instance )

Unregister a handler instance from a specific event loop.

Unregisters a handler instance, so it will no longer be called during dispatch. Handler instances can be unregistered for any combination of event_base and event_id which were previously registered. To unregister a handler instance, the event_base and event_id arguments must match exactly the arguments passed to esp_event_handler_instance_register() when that handler instance was registered. Passing ESP_EVENT_ANY_BASE and/or ESP_EVENT_ANY_ID will only unregister handler instances that were registered with the same wildcard arguments.

备注

When using ESP_EVENT_ANY_ID, handlers registered to specific event IDs using the same base will not be unregistered. When using ESP_EVENT_ANY_BASE, events registered to specific bases will also not be unregistered. This avoids accidental unregistration of handlers registered by other users or components.

参数 :

event_loop -- [in] the event loop with which to unregister this handler function, must not be NULL

event_base -- [in] the base of the event with which to unregister the handler

event_id -- [in] the ID of the event with which to unregister the handler

instance -- [in] the instance object of the registration to be unregistered

返回 :

ESP_OK: Success

ESP_ERR_INVALID_ARG: Invalid combination of event base and event ID

Others: Fail

esp_err_t esp_event_handler_instance_unregister ( esp_event_base_t event_base , int32_t event_id , esp_event_handler_instance_t instance )

Unregister a handler from the system event loop.

This function does the same as esp_event_handler_instance_unregister_with, except that it unregisters the handler instance from the default event loop.

参数 :

event_base -- [in] the base of the event with which to unregister the handler

event_id -- [in] the ID of the event with which to unregister the handler

instance -- [in] the instance object of the registration to be unregistered

返回 :

ESP_OK: Success

ESP_ERR_INVALID_ARG: Invalid combination of event base and event ID

Others: Fail

esp_err_t esp_event_post ( esp_event_base_t event_base , int32_t event_id , const void * event_data , size_t event_data_size , TickType_t ticks_to_wait )

Posts an event to the system default event loop. The event loop library keeps a copy of event_data and manages the copy's lifetime automatically (allocation + deletion); this ensures that the data the handler receives is always valid.

参数 :

event_base -- [in] the event base that identifies the event

event_id -- [in] the event ID that identifies the event

event_data -- [in] the data, specific to the event occurrence, that gets passed to the handler

event_data_size -- [in] the size of the event data

ticks_to_wait -- [in] number of ticks to block on a full event queue

返回 :

ESP_OK: Success

ESP_ERR_TIMEOUT: Time to wait for event queue to unblock expired, queue full when posting from ISR

ESP_ERR_INVALID_ARG: Invalid combination of event base and event ID

Others: Fail

esp_err_t esp_event_post_to ( esp_event_loop_handle_t event_loop , esp_event_base_t event_base , int32_t event_id , const void * event_data , size_t event_data_size , TickType_t ticks_to_wait )

Posts an event to the specified event loop. The event loop library keeps a copy of event_data and manages the copy's lifetime automatically (allocation + deletion); this ensures that the data the handler receives is always valid.

This function behaves in the same manner as esp_event_post, except the additional specification of the event loop to post the event to.

参数 :

event_loop -- [in] the event loop to post to, must not be NULL

event_base -- [in] the event base that identifies the event

event_id -- [in] the event ID that identifies the event

event_data -- [in] the data, specific to the event occurrence, that gets passed to the handler

event_data_size -- [in] the size of the event data

ticks_to_wait -- [in] number of ticks to block on a full event queue

返回 :

ESP_OK: Success

ESP_ERR_TIMEOUT: Time to wait for event queue to unblock expired, queue full when posting from ISR

ESP_ERR_INVALID_ARG: Invalid combination of event base and event ID

Others: Fail

esp_err_t esp_event_isr_post ( esp_event_base_t event_base , int32_t event_id , const void * event_data , size_t event_data_size , BaseType_t * task_unblocked )

Special variant of esp_event_post for posting events from interrupt handlers.

备注

this function is only available when CONFIG_ESP_EVENT_POST_FROM_ISR is enabled

备注

when this function is called from an interrupt handler placed in IRAM, this function should be placed in IRAM as well by enabling CONFIG_ESP_EVENT_POST_FROM_IRAM_ISR

参数 :

event_base -- [in] the event base that identifies the event

event_id -- [in] the event ID that identifies the event

event_data -- [in] the data, specific to the event occurrence, that gets passed to the handler

event_data_size -- [in] the size of the event data; max is 4 bytes

task_unblocked -- [out] an optional parameter (can be NULL) which indicates that an event task with higher priority than currently running task has been unblocked by the posted event; a context switch should be requested before the interrupt is existed.

返回 :

ESP_OK: Success

ESP_FAIL: Event queue for the default event loop full

ESP_ERR_INVALID_ARG: Invalid combination of event base and event ID, data size of more than 4 bytes

Others: Fail

esp_err_t esp_event_isr_post_to ( esp_event_loop_handle_t event_loop , esp_event_base_t event_base , int32_t event_id , const void * event_data , size_t event_data_size , BaseType_t * task_unblocked )

Special variant of esp_event_post_to for posting events from interrupt handlers.

备注

this function is only available when CONFIG_ESP_EVENT_POST_FROM_ISR is enabled

备注

when this function is called from an interrupt handler placed in IRAM, this function should be placed in IRAM as well by enabling CONFIG_ESP_EVENT_POST_FROM_IRAM_ISR

参数 :

event_loop -- [in] the event loop to post to, must not be NULL

event_base -- [in] the event base that identifies the event

event_id -- [in] the event ID that identifies the event

event_data -- [in] the data, specific to the event occurrence, that gets passed to the handler

event_data_size -- [in] the size of the event data

task_unblocked -- [out] an optional parameter (can be NULL) which indicates that an event task with higher priority than currently running task has been unblocked by the posted event; a context switch should be requested before the interrupt is existed.

返回 :

ESP_OK: Success

ESP_FAIL: Event queue for the loop full

ESP_ERR_INVALID_ARG: Invalid combination of event base and event ID, data size of more than 4 bytes

Others: Fail

esp_err_t esp_event_dump ( FILE * file )

Dumps statistics of all event loops.

Dumps event loop info in the format:

eventloophandlerhandler...eventloophandlerhandler...where:eventloopformat:address,namerx:total_receiveddr:total_droppedwhere:address-memoryaddressoftheeventloopname-nameoftheeventloop,'none'ifnodedicatedtasktotal_received-numberofsuccessfullypostedeventstotal_dropped-numberofeventsunsuccessfullypostedduetoqueuebeingfullhandlerformat:addressev:base,idinv:total_invokedrun:total_runtimewhere:address-addressofthehandlerfunctionbase,id-theeventspecifiedbyeventbaseandIDthishandlerexecutestotal_invoked-numberoftimesthishandlerhasbeeninvokedtotal_runtime-totalamountoftimeusedforinvokingthishandler

备注

this function is a noop when CONFIG_ESP_EVENT_LOOP_PROFILING is disabled

参数 :

file -- [in] the file stream to output to

返回 :

ESP_OK: Success

ESP_ERR_NO_MEM: Cannot allocate memory for event loops list

Others: Fail

Structures

struct esp_event_loop_args_t

Configuration for creating event loops.

Public Members

int32_t queue_size

size of the event loop queue

const char * task_name

name of the event loop task; if NULL, a dedicated task is not created for event loop

UBaseType_t task_priority

priority of the event loop task, ignored if task name is NULL

uint32_t task_stack_size

stack size of the event loop task, ignored if task name is NULL

BaseType_t task_core_id

core to which the event loop task is pinned to, ignored if task name is NULL

Header File

components/esp_event/include/esp_event_base.h

This header file can be included with:

#include"esp_event_base.h"

This header file is a part of the API provided by the esp_event component. To declare that your component depends on esp_event , add the following to your CMakeLists.txt:

REQUIRES esp_event

or

PRIV_REQUIRES esp_event

Macros

ESP_EVENT_DECLARE_BASE ( id )

ESP_EVENT_DEFINE_BASE ( id )

ESP_EVENT_ANY_BASE

register handler for any event base

ESP_EVENT_ANY_ID

register handler for any event id

Type Definitions

typedef const char * esp_event_base_t

unique pointer to a subsystem that exposes events

typedef void * esp_event_loop_handle_t

a number that identifies an event with respect to a base

typedef void ( * esp_event_handler_t ) ( void * event_handler_arg , esp_event_base_t event_base , int32_t event_id , void * event_data )

function called when an event is posted to the queue

typedef void * esp_event_handler_instance_t

context identifying an instance of a registered event handler

相关文档

此文档对您有帮助吗？

反馈已收到，谢谢！

如果您有其他意见，欢迎填写 乐鑫文档反馈表 。

我们重视您的反馈。

您可以填写 乐鑫文档反馈表 告诉我们如何改进该文档。
