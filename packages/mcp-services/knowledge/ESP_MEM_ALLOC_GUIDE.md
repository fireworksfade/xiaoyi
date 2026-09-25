Source: https://docs.espressif.com/projects/esp-idf/zh_CN/latest/esp32/api-reference/system/mem_alloc.html

API 参考

系统 API

堆内存分配

在 GitHub 上编辑

堆内存分配

[English]

栈 (stack) 和堆 (heap) 的区别

ESP-IDF 应用程序使用常见的计算机架构模式：由程序控制流动态分配的内存（即 栈 ）、由函数调用动态分配的内存（即 堆 ）以及在编译时分配的 静态内存 。

由于 ESP-IDF 是一个多线程 RTOS 环境，因此每个 RTOS 任务都有自己的栈，这些栈默认在创建任务时从堆中分配。有关栈静态分配的方法，请参阅 xTaskCreateStatic() 。

ESP32 使用多种类型的 RAM，因此具备不同属性的堆，即基于属性的内存分配器允许应用程序按不同目的进行堆分配。

多数情况下，可直接使用 C 标准函数库中的 malloc() 和 free() 函数实现堆分配。为充分利用各种内存类型及其特性，ESP-IDF 还具有基于内存属性的堆内存分配器。要配备具有特定属性的内存，如 DMA 存储器 或可执行内存，可以创建具备所需属性的 OR 掩码，将其传递给 heap_caps_malloc() 。

内存属性

ESP32 包含多种类型的 RAM：

DRAM（数据 RAM）是连接到 CPU 数据总线上的内存，用于存储数据。这是作为堆访问最常见的一种内存。

IRAM（指令 RAM）是连接到 CPU 指令总线上的内存，通常仅用于存储可执行数据（即指令）。如果作为通用内存访问，则所有访问必须为 32 位可访问内存 。

D/IRAM 是连接到 CPU 数据总线和指令总线的 RAM，因此可用作指令 RAM 或数据 RAM。

有关内存类型的详细信息，请参阅 存储器类型 。

也可将外部 SPI RAM 连接到 ESP32。通过缓存将 片外 RAM 集成到 ESP32 的内存映射中，访问方式与 DRAM 类似。

所有的 DRAM 内存都可以单字节访问，因此所有的 DRAM 堆都具有 MALLOC_CAP_8BIT 属性。要获取所有 DRAM 堆的剩余空间大小，请调用 heap_caps_get_free_size(MALLOC_CAP_8BIT) 。

如果占用了所有的 MALLOC_CAP_8BIT 堆空间，则可以用 MALLOC_CAP_IRAM_8BIT 代替。此时，若只以 32 位对齐的方式访问 IRAM 内存，或者启用了 CONFIG_ESP32_IRAM_AS_8BIT_ACCESSIBLE_MEMORY ，则仍然可以将 IRAM 用作内部内存的“储备池”。

备注

此选项仅在单核 ESP32 配置（ CONFIG_FREERTOS_UNICORE=y ）下可用。与普通内存相比， CONFIG_ESP32_IRAM_AS_8BIT_ACCESSIBLE_MEMORY 选项有一个显著的缺点：对 MALLOC_CAP_IRAM_8BIT 内存的每次字节、半字或任意非对齐访问都会触发 LoadStore 或 Alignment 异常。虽然这些异常会通过软件处理以确保读写值的正确性，但每次访问都会产生约 167 个 CPU 周期的开销，如果频繁访问，可能导致严重的性能下降。因此，应避免在注重性能的代码段（如 ISR 例程或紧凑循环）中使用此类内存。建议重构代码，改用 32 位对齐（ uint32_t ）的访问方式。

调用 malloc() 时，ESP-IDF malloc() 内部调用 heap_caps_malloc_default(size) ，使用属性 MALLOC_CAP_DEFAULT 分配内存。该属性可实现字节寻址功能，即存储空间的最小编址单位为字节。

MALLOC_CAP_DEFAULT 描述的是内存能力，而不是精确的分配策略。特别是， heap_caps_malloc(size, MALLOC_CAP_DEFAULT) 不一定遵循与 malloc() 相同的放置策略。

例如，当 片外 RAM 被添加到基于能力的堆分配器后， heap_caps_malloc(size, MALLOC_CAP_DEFAULT) 可能返回片外 RAM，而 malloc() 是否优先或仅使用内部 RAM 则取决于具体配置。

malloc() 使用基于属性的分配系统，所以使用 heap_caps_malloc() 分配的内存可以通过调用标准的 free() 函数释放。

可用堆空间

DRAM

启动时，DRAM 堆包含应用程序未静态分配的所有数据内存，减少静态分配的 buffer 将增加可用的空闲堆空间。

调用命令 idf.py size 可查找静态分配内存大小。

备注

有关 DRAM 使用限制的详细信息，请参阅 DRAM（数据 RAM） 。

备注

运行时可用的 DRAM 堆空间可能少于编译时计算的大小，因为启动时会在运行 FreeRTOS 调度程序之前从堆中分配部分内存，包括初始 FreeRTOS 任务的栈内存。

IRAM

启动时，IRAM 堆包含所有应用程序可执行代码未使用的指令内存。

调用命令 idf.py size 查找应用程序使用的 IRAM 量。

D/IRAM

一些内存在 ESP32 中可用作 DRAM 或 IRAM。如果从 D/IRAM 区域分配内存，则两种类型的内存的可用堆空间都会减少。

堆空间大小

启动时，所有 ESP-IDF 应用程序都会记录全部堆地址（和空间大小）的摘要，级别为 Info：

I (252) heap_init: Initializing. RAM available for dynamic allocation:
I (259) heap_init: At 3FFAE6E0 len 00001920 (6 KiB): DRAM
I (265) heap_init: At 3FFB2EC8 len 0002D138 (180 KiB): DRAM
I (272) heap_init: At 3FFE0440 len 00003AE0 (14 KiB): D/IRAM
I (278) heap_init: At 3FFE4350 len 0001BCB0 (111 KiB): D/IRAM
I (284) heap_init: At 4008944C len 00016BB4 (90 KiB): IRAM

查找可用堆

请参阅 堆内存信息 。

特殊用途

DMA 存储器

使用 MALLOC_CAP_DMA 标志分配适合与硬件 DMA 引擎（如 SPI 和 I2S）配合使用的内存，此属性标志不包括外部 PSRAM。

32 位可访问内存

如果某个内存结构体仅以 32 位为单位寻址，例如一个整数或指针数组，则可以使用 MALLOC_CAP_32BIT 标志分配。通过这一方式，分配器能够在无法调用 malloc() 的情况下提供 IRAM 内存，从而充分利用 ESP32 中的所有可用内存。

请注意，在 ESP32 系列芯片上，不可使用 MALLOC_CAP_32BIT 存储浮点变量。因为 MALLOC_CAP_32BIT 可能返回指令 RAM，而 ESP32 上的浮点汇编指令无法访问指令 RAM。

请注意，使用 MALLOC_CAP_32BIT 分配的内存 只能 通过 32 位读写访问，其他类型的访问将导致 LoadStoreError 异常。

外部 SPI 内存

当启用 片外 RAM 时，可以根据配置调用标准 malloc 或通过 heap_caps_malloc(MALLOC_CAP_SPIRAM) 分配外部 SPI RAM，详情请参阅 配置片外 RAM 。

在 ESP32 上，只有不超过 4 MiB 的外部 SPI RAM 可以通过上述方式分配。要使用超过 4 MiB 限制的区域，可以使用 himem API 。

线程安全性

堆函数是线程安全的，因此可不受限制，在不同任务中同时调用多个堆函数。

从中断处理程序 (ISR) 上下文中调用 malloc 、 free 和相关函数虽然在技术层面可行（请参阅 从 ISR 调用堆相关函数 ），但不建议使用此种方法，因为调用堆函数可能会延迟其他中断。建议重构应用程序，将 ISR 使用的任何 buffer 预先分配到 ISR 之外。之后可能会删除从 ISR 调用堆函数的功能。

从 ISR 调用堆相关函数

堆组件中的以下函数可以在中断处理程序 (ISR) 中调用：

heap_caps_malloc()

heap_caps_malloc_default()

heap_caps_realloc_default()

heap_caps_malloc_prefer()

heap_caps_realloc_prefer()

heap_caps_calloc_prefer()

heap_caps_free()

heap_caps_realloc()

heap_caps_calloc()

heap_caps_aligned_alloc()

heap_caps_aligned_free()

备注

不建议使用此种方法。

堆跟踪及调试

以下功能介绍详见 堆内存调试 ：

堆信息 （释放内存空间等）

堆分配与释放函数挂钩

堆损坏检测

堆跟踪 （检测、监控内存泄漏等）

实现说明

堆属性分配器对芯片内存区域的了解源于 SoC 组件，该组件包含芯片的内存布局信息以及每个区域的不同属性。各区域的功能为首要考虑因素，如会优先使用 DRAM 和 IRAM 特定区域而非用途更广的 D/IRAM 区域来分配内存。

每个连续的内存区域都包含其自己的内存堆，由 multi_heap 函数创建。 multi_heap 允许将任何连续的内存区域作为堆使用。

堆属性分配器通过对内存区域的了解初始化每个单独的堆，堆属性 API 中的分配函数将基于所需的属性、可用空间和每个区域使用的首选项为分配函数找到最合适的堆，随后为位于特定内存区域的堆调用 multi_heap_malloc() 。

调用 free() 查找对应释放地址的特定堆，随后在特定的 multi_heap 实例上调用 multi_heap_free() 。

API 参考 - 堆分配

Header File

components/heap/include/esp_heap_caps.h

This header file can be included with:

#include"esp_heap_caps.h"

Functions

esp_err_t heap_caps_register_failed_alloc_callback ( esp_alloc_failed_hook_t callback )

registers a callback function to be invoked if a memory allocation operation fails

参数 :

callback -- caller defined callback to be invoked

返回 :

ESP_OK if callback was registered.

void * heap_caps_malloc ( size_t size , uint32_t caps )

Allocate a chunk of memory which has the given capabilities.

Equivalent semantics to libc malloc(), for capability-aware memory.

参数 :

size -- Size, in bytes, of the amount of memory to allocate

caps -- Bitwise OR of MALLOC_CAP_* flags indicating the type of memory to be returned

返回 :

A pointer to the memory allocated on success, NULL on failure

void heap_caps_free ( void * ptr )

Free memory previously allocated via heap_caps_malloc() or heap_caps_realloc().

Equivalent semantics to libc free(), for capability-aware memory.

In IDF, free(p) is equivalent to heap_caps_free(p) .

参数 :

ptr -- Pointer to memory previously returned from heap_caps_malloc() or heap_caps_realloc(). Can be NULL.

void * heap_caps_realloc ( void * ptr , size_t size , uint32_t caps )

Reallocate memory previously allocated via heap_caps_malloc() or heap_caps_realloc().

Equivalent semantics to libc realloc(), for capability-aware memory.

In IDF, realloc(p, s) is equivalent to heap_caps_realloc(p, s, MALLOC_CAP_8BIT) .

'caps' parameter can be different to the capabilities that any original 'ptr' was allocated with. In this way, realloc can be used to "move" a buffer if necessary to ensure it meets a new set of capabilities.

参数 :

ptr -- Pointer to previously allocated memory, or NULL for a new allocation.

size -- Size of the new buffer requested, or 0 to free the buffer.

caps -- Bitwise OR of MALLOC_CAP_* flags indicating the type of memory desired for the new allocation.

返回 :

Pointer to a new buffer of size 'size' with capabilities 'caps', or NULL if allocation failed.

void * heap_caps_aligned_alloc ( size_t alignment , size_t size , uint32_t caps )

Allocate an aligned chunk of memory which has the given capabilities.

Equivalent semantics to libc aligned_alloc(), for capability-aware memory.

参数 :

alignment -- How the pointer received needs to be aligned must be a power of two

size -- Size, in bytes, of the amount of memory to allocate

caps -- Bitwise OR of MALLOC_CAP_* flags indicating the type of memory to be returned

返回 :

A pointer to the memory allocated on success, NULL on failure

void heap_caps_aligned_free ( void * ptr )

Used to deallocate memory previously allocated with heap_caps_aligned_alloc.

备注

This function is deprecated, please consider using heap_caps_free() instead

参数 :

ptr -- Pointer to the memory allocated

void * heap_caps_aligned_calloc ( size_t alignment , size_t n , size_t size , uint32_t caps )

Allocate an aligned chunk of memory which has the given capabilities. The initialized value in the memory is set to zero.

参数 :

alignment -- How the pointer received needs to be aligned must be a power of two

n -- Number of continuing chunks of memory to allocate

size -- Size, in bytes, of a chunk of memory to allocate

caps -- Bitwise OR of MALLOC_CAP_* flags indicating the type of memory to be returned

返回 :

A pointer to the memory allocated on success, NULL on failure

void * heap_caps_calloc ( size_t n , size_t size , uint32_t caps )

Allocate a chunk of memory which has the given capabilities. The initialized value in the memory is set to zero.

Equivalent semantics to libc calloc(), for capability-aware memory.

In IDF, calloc(p) is equivalent to heap_caps_calloc(p, MALLOC_CAP_8BIT) .

参数 :

n -- Number of continuing chunks of memory to allocate

size -- Size, in bytes, of a chunk of memory to allocate

caps -- Bitwise OR of MALLOC_CAP_* flags indicating the type of memory to be returned

返回 :

A pointer to the memory allocated on success, NULL on failure

size_t heap_caps_get_total_size ( uint32_t caps )

Get the total size of all the regions that have the given capabilities.

This function takes all regions capable of having the given capabilities allocated in them and adds up the total space they have.

参数 :

caps -- Bitwise OR of MALLOC_CAP_* flags indicating the type of memory

返回 :

total size in bytes

size_t heap_caps_get_free_size ( uint32_t caps )

Get the total free size of all the regions that have the given capabilities.

This function takes all regions capable of having the given capabilities allocated in them and adds up the free space they have.

备注

Note that because of heap fragmentation it is probably not possible to allocate a single block of memory of this size. Use heap_caps_get_largest_free_block() for this purpose.

参数 :

caps -- Bitwise OR of MALLOC_CAP_* flags indicating the type of memory

返回 :

Amount of free bytes in the regions

size_t heap_caps_get_minimum_free_size ( uint32_t caps )

Get the total minimum free memory of all regions with the given capabilities.

This adds all the low watermarks of the regions capable of delivering the memory with the given capabilities.

备注

Note the result may be less than the global all-time minimum available heap of this kind, as "low watermarks" are tracked per-region. Individual regions' heaps may have reached their "low watermarks" at different points in time. However, this result still gives a "worst case" indication for all-time minimum free heap.

备注

Heaps added at runtime using heap_caps_add_region_with_caps() (i.e., from app_main onwards) are not taken into account in the minimum free size calculation.

参数 :

caps -- Bitwise OR of MALLOC_CAP_* flags indicating the type of memory

返回 :

Amount of free bytes in the regions

size_t heap_caps_get_largest_free_block ( uint32_t caps )

Get the largest free block of memory able to be allocated with the given capabilities.

Returns the largest value of s for which heap_caps_malloc(s, caps) will succeed.

参数 :

caps -- Bitwise OR of MALLOC_CAP_* flags indicating the type of memory

返回 :

Size of the largest free block in bytes.

esp_err_t heap_caps_monitor_local_minimum_free_size_start ( void )

Start monitoring the value of minimum_free_bytes from the moment this function is called instead of from startup.

备注

This allows to detect local lows of the minimum_free_bytes value that wouldn't be detected otherwise.

返回 :

esp_err_t ESP_OK if the function executed properly ESP_FAIL if called when monitoring already active

esp_err_t heap_caps_monitor_local_minimum_free_size_stop ( void )

Stop monitoring the value of minimum_free_bytes. After this call the minimum_free_bytes value calculated from startup will be returned in heap_caps_get_info and heap_caps_get_minimum_free_size.

返回 :

esp_err_t ESP_OK if the function executed properly ESP_FAIL if called when monitoring not active

void heap_caps_get_info ( multi_heap_info_t * info , uint32_t caps )

Get heap info for all regions with the given capabilities.

Calls multi_heap_info() on all heaps which share the given capabilities. The information returned is an aggregate across all matching heaps. The meanings of fields are the same as defined for multi_heap_info_t , except that minimum_free_bytes has the same caveats described in heap_caps_get_minimum_free_size().

参数 :

info -- Pointer to a structure which will be filled with relevant heap metadata.

caps -- Bitwise OR of MALLOC_CAP_* flags indicating the type of memory

void heap_caps_print_heap_info ( uint32_t caps )

Print a summary of all memory with the given capabilities.

Calls multi_heap_info on all heaps which share the given capabilities, and prints a two-line summary for each, then a total summary.

参数 :

caps -- Bitwise OR of MALLOC_CAP_* flags indicating the type of memory

bool heap_caps_check_integrity_all ( bool print_errors )

Check integrity of all heap memory in the system.

Calls multi_heap_check on all heaps. Optionally print errors if heaps are corrupt.

Calling this function is equivalent to calling heap_caps_check_integrity with the caps argument set to MALLOC_CAP_INVALID.

备注

Please increase the value of CONFIG_ESP_INT_WDT_TIMEOUT_MS when using this API with PSRAM enabled.

参数 :

print_errors -- Print specific errors if heap corruption is found.

返回 :

True if all heaps are valid, False if at least one heap is corrupt.

bool heap_caps_check_integrity ( uint32_t caps , bool print_errors )

Check integrity of all heaps with the given capabilities.

Calls multi_heap_check on all heaps which share the given capabilities. Optionally print errors if the heaps are corrupt.

See also heap_caps_check_integrity_all to check all heap memory in the system and heap_caps_check_integrity_addr to check memory around a single address.

备注

Please increase the value of CONFIG_ESP_INT_WDT_TIMEOUT_MS when using this API with PSRAM capability flag.

参数 :

caps -- Bitwise OR of MALLOC_CAP_* flags indicating the type of memory

print_errors -- Print specific errors if heap corruption is found.

返回 :

True if all heaps are valid, False if at least one heap is corrupt.

bool heap_caps_check_integrity_addr ( intptr_t addr , bool print_errors )

Check integrity of heap memory around a given address.

This function can be used to check the integrity of a single region of heap memory, which contains the given address.

This can be useful if debugging heap integrity for corruption at a known address, as it has a lower overhead than checking all heap regions. Note that if the corrupt address moves around between runs (due to timing or other factors) then this approach won't work, and you should call heap_caps_check_integrity or heap_caps_check_integrity_all instead.

备注

The entire heap region around the address is checked, not only the adjacent heap blocks.

参数 :

addr -- Address in memory. Check for corruption in region containing this address.

print_errors -- Print specific errors if heap corruption is found.

返回 :

True if the heap containing the specified address is valid, False if at least one heap is corrupt or the address doesn't belong to a heap region.

void heap_caps_malloc_extmem_enable ( size_t limit )

Enable malloc() in external memory and set limit below which malloc() attempts are placed in internal memory.

When external memory is in use, the allocation strategy is to initially try to satisfy smaller allocation requests with internal memory and larger requests with external memory. This sets the limit between the two, as well as generally enabling allocation in external memory.

参数 :

limit -- Limit, in bytes.

void * heap_caps_malloc_prefer ( size_t size , size_t num , ... )

Allocate a chunk of memory as preference in decreasing order.

Attention

The variable parameters are bitwise OR of MALLOC_CAP_* flags indicating the type of memory. This API prefers to allocate memory with the first parameter. If failed, allocate memory with the next parameter. It will try in this order until allocating a chunk of memory successfully or fail to allocate memories with any of the parameters.

参数 :

size -- Size, in bytes, of the amount of memory to allocate

num -- Number of variable parameters

返回 :

A pointer to the memory allocated on success, NULL on failure

void * heap_caps_realloc_prefer ( void * ptr , size_t size , size_t num , ... )

Reallocate a chunk of memory as preference in decreasing order.

参数 :

ptr -- Pointer to previously allocated memory, or NULL for a new allocation.

size -- Size of the new buffer requested, or 0 to free the buffer.

num -- Number of variable parameters

返回 :

Pointer to a new buffer of size 'size', or NULL if allocation failed.

void * heap_caps_calloc_prefer ( size_t n , size_t size , size_t num , ... )

Allocate a chunk of memory as preference in decreasing order.

参数 :

n -- Number of continuing chunks of memory to allocate

size -- Size, in bytes, of a chunk of memory to allocate

num -- Number of variable parameters

返回 :

A pointer to the memory allocated on success, NULL on failure

void heap_caps_dump ( uint32_t caps )

Dump the full structure of all heaps with matching capabilities.

Prints a large amount of output to serial (because of locking limitations, the output bypasses stdout/stderr). For each (variable sized) block in each matching heap, the following output is printed on a single line:

Block address (the data buffer returned by malloc is 4 bytes after this if heap debugging is set to Basic, or 8 bytes otherwise).

Data size (the data size may be larger than the size requested by malloc, either due to heap fragmentation or because of heap debugging level).

Address of next block in the heap.

If the block is free, the address of the next free block is also printed.

参数 :

caps -- Bitwise OR of MALLOC_CAP_* flags indicating the type of memory

void heap_caps_dump_all ( void )

Dump the full structure of all heaps.

Covers all registered heaps. Prints a large amount of output to serial.

Output is the same as for heap_caps_dump.

size_t heap_caps_get_allocated_size ( void * ptr )

Return the size that a particular pointer was allocated with.

备注

The app will crash with an assertion failure if the pointer is not valid.

参数 :

ptr -- Pointer to currently allocated heap memory. Must be a pointer value previously returned by heap_caps_malloc, malloc, calloc, etc. and not yet freed.

返回 :

Size of the memory allocated at this block.

size_t heap_caps_get_containing_block_size ( void * ptr )

Return the size of the block containing the pointer passed as parameter.

备注

The app will crash with an assertion failure if the pointer is invalid.

参数 :

ptr -- Pointer to currently allocated heap memory. The pointer value must be within the allocated memory and the memory must not be freed.

返回 :

Size of the containing block allocated.

void heap_caps_walk ( uint32_t caps , heap_caps_walker_cb_t walker_func , void * user_data )

Function called to walk through the heaps with the given set of capabilities.

参数 :

caps -- The set of capabilities assigned to the heaps to walk through

walker_func -- Callback called for each block of the heaps being traversed

user_data -- Opaque pointer to user defined data

void heap_caps_walk_all ( heap_caps_walker_cb_t walker_func , void * user_data )

Function called to walk through all heaps defined by the heap component.

参数 :

walker_func -- Callback called for each block of the heaps being traversed

user_data -- Opaque pointer to user defined data

Structures

struct walker_heap_info

Structure used to store heap related data passed to the walker callback function.

Public Members

intptr_t start

Start address of the heap in which the block is located.

intptr_t end

End address of the heap in which the block is located.

struct walker_block_info

Structure used to store block related data passed to the walker callback function.

Public Members

void * ptr

Pointer to the block data.

size_t size

The size of the block.

bool used

Block status. True: used, False: free.

Macros

HEAP_IRAM_ATTR

MALLOC_CAP_EXEC

Flags to indicate the capabilities of the various memory systems.

Memory must be able to run executable code

MALLOC_CAP_32BIT

Memory must allow for aligned 32-bit data accesses.

MALLOC_CAP_8BIT

Memory must allow for 8/16/...-bit data accesses.

MALLOC_CAP_DMA

Memory must be able to accessed by DMA.

MALLOC_CAP_PID2

Memory must be mapped to PID2 memory space (PIDs are not currently used)

MALLOC_CAP_PID3

Memory must be mapped to PID3 memory space (PIDs are not currently used)

MALLOC_CAP_PID4

Memory must be mapped to PID4 memory space (PIDs are not currently used)

MALLOC_CAP_PID5

Memory must be mapped to PID5 memory space (PIDs are not currently used)

MALLOC_CAP_PID6

Memory must be mapped to PID6 memory space (PIDs are not currently used)

MALLOC_CAP_PID7

Memory must be mapped to PID7 memory space (PIDs are not currently used)

MALLOC_CAP_SPIRAM

Memory must be in SPI RAM.

MALLOC_CAP_INTERNAL

Memory must be internal; specifically it should not disappear when flash/spiram cache is switched off.

MALLOC_CAP_DEFAULT

Memory can be returned in a non-capability-specific memory allocation (e.g. malloc(), calloc()) call.

MALLOC_CAP_IRAM_8BIT

Memory must be in IRAM and allow unaligned access.

MALLOC_CAP_RETENTION

Memory must be able to accessed by retention DMA.

MALLOC_CAP_RTCRAM

Memory must be in RTC fast memory.

MALLOC_CAP_SPM

Memory must be in SPM memory.

MALLOC_CAP_TCM

MALLOC_CAP_DMA_DESC_AHB

Memory must be capable of containing AHB DMA descriptors.

MALLOC_CAP_DMA_DESC_AXI

Memory must be capable of containing AXI DMA descriptors.

MALLOC_CAP_CACHE_ALIGNED

Memory must be aligned to the cache line size of any intermediate caches.

MALLOC_CAP_SIMD

Memory must be capable of being used for SIMD instructions (i.e. allow for SIMD-specific-bit data accesses)

MALLOC_CAP_SPIRAM_NO_ENC

Memory must be in the PSRAM region exempt from flash encryption (plaintext in PSRAM; see CONFIG_SPIRAM_ENC_EXEMPT)

MALLOC_CAP_INVALID

Memory can't be used / list end marker.

Type Definitions

typedef void ( * esp_alloc_failed_hook_t ) ( size_t size , uint32_t caps , const char * function_name )

callback called when an allocation operation fails, if registered

Param size :

in bytes of failed allocation

Param caps :

capabilities requested of failed allocation

Param function_name :

function which generated the failure

typedef struct walker_heap_info walker_heap_into_t

Structure used to store heap related data passed to the walker callback function.

typedef struct walker_block_info walker_block_info_t

Structure used to store block related data passed to the walker callback function.

typedef bool ( * heap_caps_walker_cb_t ) ( walker_heap_into_t heap_info , walker_block_info_t block_info , void * user_data )

Function callback used to get information of memory block during calls to heap_caps_walk or heap_caps_walk_all.

Param heap_info :

See walker_heap_into_t

Param block_info :

See walker_block_info_t

Param user_data :

Opaque pointer to user defined data

Return :

True to proceed with the heap traversal False to stop the traversal of the current heap and continue with the traversal of the next heap (if any)

API 参考 - 初始化

Header File

components/heap/include/esp_heap_caps_init.h

This header file can be included with:

#include"esp_heap_caps_init.h"

Functions

void heap_caps_init ( void )

Initialize the capability-aware heap allocator.

This is called once in the IDF startup code. Do not call it at other times.

void heap_caps_enable_nonos_stack_heaps ( void )

Enable heap(s) in memory regions where the startup stacks are located.

On startup, the pro/app CPUs have a certain memory region they use as stack, so we cannot do allocations in the regions these stack frames are. When FreeRTOS is completely started, they do not use that memory anymore and heap(s) there can be enabled.

esp_err_t heap_caps_add_region ( intptr_t start , intptr_t end )

Add a region of memory to the collection of heaps at runtime.

Most memory regions are defined in soc_memory_layout.c for the SoC, and are registered via heap_caps_init(). Some regions can't be used immediately and are later enabled via heap_caps_enable_nonos_stack_heaps().

Call this function to add a region of memory to the heap at some later time.

This function does not consider any of the "reserved" regions or other data in soc_memory_layout, caller needs to consider this themselves.

All memory within the region specified by start & end parameters must be otherwise unused.

The capabilities of the newly registered memory will be determined by the start address, as looked up in the regions specified in soc_memory_layout.c.

Use heap_caps_add_region_with_caps() to register a region with custom capabilities.

备注

Please refer to following example for memory regions allowed for addition to heap based on an existing region (address range for demonstration purpose only):

Existingregion:0x1000<->0x3000Newregion:0x1000<->0x3000(Allowed)Newregion:0x1000<->0x2000(Allowed)Newregion:0x0000<->0x1000(Allowed)Newregion:0x3000<->0x4000(Allowed)Newregion:0x0000<->0x2000(NOTAllowed)Newregion:0x0000<->0x4000(NOTAllowed)Newregion:0x1000<->0x4000(NOTAllowed)Newregion:0x2000<->0x4000(NOTAllowed)

参数 :

start -- Start address of new region.

end -- End address of new region.

返回 :

ESP_OK on success, ESP_ERR_INVALID_ARG if a parameter is invalid, ESP_ERR_NOT_FOUND if the specified start address doesn't reside in a known region, or any error returned by heap_caps_add_region_with_caps().

esp_err_t heap_caps_add_region_with_caps ( const uint32_t caps [ ] , intptr_t start , intptr_t end )

Add a region of memory to the collection of heaps at runtime, with custom capabilities.

Similar to heap_caps_add_region(), only custom memory capabilities are specified by the caller.

备注

Please refer to following example for memory regions allowed for addition to heap based on an existing region (address range for demonstration purpose only):

Existingregion:0x1000<->0x3000Newregion:0x1000<->0x3000(Allowed)Newregion:0x1000<->0x2000(Allowed)Newregion:0x0000<->0x1000(Allowed)Newregion:0x3000<->0x4000(Allowed)Newregion:0x0000<->0x2000(NOTAllowed)Newregion:0x0000<->0x4000(NOTAllowed)Newregion:0x1000<->0x4000(NOTAllowed)Newregion:0x2000<->0x4000(NOTAllowed)

参数 :

caps -- Ordered array of capability masks for the new region, in order of priority. Must have length SOC_MEMORY_TYPE_NO_PRIOS. Does not need to remain valid after the call returns.

start -- Start address of new region.

end -- End address of new region.

返回 :

ESP_OK on success

ESP_ERR_INVALID_ARG if a parameter is invalid

ESP_ERR_NO_MEM if no memory to register new heap.

ESP_ERR_INVALID_SIZE if the memory region is too small to fit a heap

ESP_FAIL if region overlaps the start and/or end of an existing region

API 参考 - 多堆 API

（注意：堆属性分配器在内部使用多堆 API，而多数 IDF 程序不需要直接调用此 API。）

Header File

components/heap/include/multi_heap.h

This header file can be included with:

#include"multi_heap.h"

Functions

void * multi_heap_aligned_alloc ( multi_heap_handle_t heap , size_t size , size_t alignment )

allocate a chunk of memory with specific alignment

参数 :

heap -- Handle to a registered heap.

size -- size in bytes of memory chunk

alignment -- how the memory must be aligned

返回 :

pointer to the memory allocated, NULL on failure

void * multi_heap_malloc ( multi_heap_handle_t heap , size_t size )

malloc() a buffer in a given heap

Semantics are the same as standard malloc(), only the returned buffer will be allocated in the specified heap.

参数 :

heap -- Handle to a registered heap.

size -- Size of desired buffer.

返回 :

Pointer to new memory, or NULL if allocation fails.

void multi_heap_aligned_free ( multi_heap_handle_t heap , void * p )

free() a buffer aligned in a given heap.

备注

This function is deprecated, consider using multi_heap_free() instead

参数 :

heap -- Handle to a registered heap.

p -- NULL, or a pointer previously returned from multi_heap_aligned_alloc() for the same heap.

void multi_heap_free ( multi_heap_handle_t heap , void * p )

free() a buffer in a given heap.

Semantics are the same as standard free(), only the argument 'p' must be NULL or have been allocated in the specified heap.

参数 :

heap -- Handle to a registered heap.

p -- NULL, or a pointer previously returned from multi_heap_malloc() or multi_heap_realloc() for the same heap.

void * multi_heap_realloc ( multi_heap_handle_t heap , void * p , size_t size )

realloc() a buffer in a given heap.

Semantics are the same as standard realloc(), only the argument 'p' must be NULL or have been allocated in the specified heap.

参数 :

heap -- Handle to a registered heap.

p -- NULL, or a pointer previously returned from multi_heap_malloc() or multi_heap_realloc() for the same heap.

size -- Desired new size for buffer.

返回 :

New buffer of 'size' containing contents of 'p', or NULL if reallocation failed.

size_t multi_heap_get_allocated_size ( multi_heap_handle_t heap , void * p )

Return the size that a particular pointer was allocated with.

参数 :

heap -- Handle to a registered heap.

p -- Pointer, must have been previously returned from multi_heap_malloc() or multi_heap_realloc() for the same heap.

返回 :

Size of the memory allocated at this block. May be more than the original size argument, due to padding and minimum block sizes.

multi_heap_handle_t multi_heap_register ( void * start , size_t size )

Register a new heap for use.

This function initialises a heap at the specified address, and returns a handle for future heap operations.

There is no equivalent function for deregistering a heap - if all blocks in the heap are free, you can immediately start using the memory for other purposes.

参数 :

start -- Start address of the memory to use for a new heap.

size -- Size (in bytes) of the new heap.

返回 :

Handle of a new heap ready for use, or NULL if the heap region was too small to be initialised.

void multi_heap_set_lock ( multi_heap_handle_t heap , void * lock )

Associate a private lock pointer with a heap.

The lock argument is supplied to the MULTI_HEAP_LOCK() and MULTI_HEAP_UNLOCK() macros, defined in multi_heap_platform.h.

The lock in question must be recursive.

When the heap is first registered, the associated lock is NULL.

参数 :

heap -- Handle to a registered heap.

lock -- Optional pointer to a locking structure to associate with this heap.

void multi_heap_dump ( multi_heap_handle_t heap )

Dump heap information to stdout.

For debugging purposes, this function dumps information about every block in the heap to stdout.

参数 :

heap -- Handle to a registered heap.

bool multi_heap_check ( multi_heap_handle_t heap , bool print_errors )

Check heap integrity.

Walks the heap and checks all heap data structures are valid. If any errors are detected, an error-specific message can be optionally printed to stderr. Print behaviour can be overridden at compile time by defining MULTI_CHECK_FAIL_PRINTF in multi_heap_platform.h.

备注

This function is not thread-safe as it sets a global variable with the value of print_errors.

参数 :

heap -- Handle to a registered heap.

print_errors -- If true, errors will be printed to stderr.

返回 :

true if heap is valid, false otherwise.

size_t multi_heap_free_size ( multi_heap_handle_t heap )

Return free heap size.

Returns the number of bytes available in the heap.

Equivalent to the total_free_bytes member returned by multi_heap_get_heap_info().

Note that the heap may be fragmented, so the actual maximum size for a single malloc() may be lower. To know this size, see the largest_free_block member returned by multi_heap_get_heap_info().

参数 :

heap -- Handle to a registered heap.

返回 :

Number of free bytes.

size_t multi_heap_minimum_free_size ( multi_heap_handle_t heap )

Return the lifetime minimum free heap size.

Equivalent to the minimum_free_bytes member returned by multi_heap_get_info().

Returns the lifetime "low watermark" of possible values returned from multi_free_heap_size(), for the specified heap.

参数 :

heap -- Handle to a registered heap.

返回 :

Number of free bytes.

void multi_heap_get_info ( multi_heap_handle_t heap , multi_heap_info_t * info )

Return metadata about a given heap.

Fills a multi_heap_info_t structure with information about the specified heap.

参数 :

heap -- Handle to a registered heap.

info -- Pointer to a structure to fill with heap metadata.

void * multi_heap_aligned_alloc_offs ( multi_heap_handle_t heap , size_t size , size_t alignment , size_t offset )

Perform an aligned allocation from the provided offset.

参数 :

heap -- The heap in which to perform the allocation

size -- The size of the allocation

alignment -- How the memory must be aligned

offset -- The offset at which the alignment should start

返回 :

void* The ptr to the allocated memory

size_t multi_heap_reset_minimum_free_bytes ( multi_heap_handle_t heap )

Reset the minimum_free_bytes value (setting it to free_bytes) and return the former value.

参数 :

heap -- The heap in which the reset is taking place

返回 :

size_t the value of minimum_free_bytes before it is reset

void multi_heap_restore_minimum_free_bytes ( multi_heap_handle_t heap , const size_t new_minimum_free_bytes_value )

Set the value of minimum_free_bytes to new_minimum_free_bytes_value or keep the current value of minimum_free_bytes if it is smaller than new_minimum_free_bytes_value.

参数 :

heap -- The heap in which the restore is taking place

new_minimum_free_bytes_value -- The value to restore the minimum_free_bytes to

void multi_heap_walk ( multi_heap_handle_t heap , multi_heap_walker_cb_t walker_func , void * user_data )

Call the tlsf_walk_pool function of the heap given as parameter with the walker function passed as parameter.

参数 :

heap -- The heap to traverse

walker_func -- The walker to trigger on each block of the heap

user_data -- Opaque pointer to user defined data

size_t multi_heap_get_full_block_size ( multi_heap_handle_t heap , void * p )

void * multi_heap_find_containing_block ( multi_heap_handle_t heap , void * ptr )

Function walking through a given heap and returning the pointer to the allocated block containing the pointer passed as parameter.

备注

The heap parameter must be valid and the pointer parameter must belong to a block of allocated memory. The app will crash with an assertion failure if at least one of the parameter is invalid.

参数 :

heap -- The heap to walk through

ptr -- The pointer to find the allocated block of

返回 :

Pointer to the allocated block containing the pointer ptr

Structures

struct multi_heap_info_t

Structure to access heap metadata via multi_heap_get_info.

Public Members

size_t total_free_bytes

Total free bytes in the heap. Equivalent to multi_free_heap_size().

size_t total_allocated_bytes

Total bytes allocated to data in the heap.

size_t largest_free_block

Size of the largest free block in the heap. This is the largest malloc-able size.

size_t minimum_free_bytes

Lifetime minimum free heap size. Equivalent to multi_minimum_free_heap_size().

size_t allocated_blocks

Number of (variable size) blocks allocated in the heap.

size_t free_blocks

Number of (variable size) free blocks in the heap.

size_t total_blocks

Total number of (variable size) blocks in the heap.

Type Definitions

typedef struct multi_heap_info * multi_heap_handle_t

Opaque handle to a registered heap.

typedef bool ( * multi_heap_walker_cb_t ) ( void * block_ptr , size_t block_size , int block_used , void * user_data )

Callback called when walking the given heap blocks of memory.

Param block_ptr :

Pointer to the block data

Param block_size :

The size of the block

Param block_used :

Block status. 0: free, 1: allocated

Param user_data :

Opaque pointer to user defined data

Return :

True if the walker is expected to continue the heap traversal False if the walker is expected to stop the traversal of the heap

此文档对您有帮助吗？

反馈已收到，谢谢！

如果您有其他意见，欢迎填写 乐鑫文档反馈表 。

我们重视您的反馈。

您可以填写 乐鑫文档反馈表 告诉我们如何改进该文档。
