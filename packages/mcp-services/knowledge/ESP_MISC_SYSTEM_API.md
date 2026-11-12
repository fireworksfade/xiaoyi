来源：https://docs.espressif.com/projects/esp-idf/zh_CN/v5.5.4/esp32/api-reference/system/misc_system_api.html

# 杂项系统 API

## 软件复位

函数 `esp_restart()` 用于执行芯片的软件复位。调用此函数时，程序停止执行，两个 CPU 均复位，应用程序由引导加载程序加载并重启。

函数 `esp_register_shutdown_handler()` 用于注册复位前会自动调用的例程（复位过程由 `esp_restart()` 函数触发），这与 `atexit` POSIX 函数的功能类似。

## 复位原因

ESP-IDF 应用程序启动或复位的原因有多种。调用 `esp_reset_reason()` 函数可获取最近一次复位的原因。复位的所有可能原因，请查看 `esp_reset_reason_t` 中的描述。

## 堆内存

ESP-IDF 中有两个与堆内存相关的函数：

- 函数 `esp_get_free_heap_size()` 用于查询当前可用的堆内存大小。

- 函数 `esp_get_minimum_free_heap_size()` 用于查询整个过程中可用的最小堆内存大小（例如应用程序生命周期内可用的最小堆内存大小）。

请注意，ESP-IDF 支持功能不同的的多个堆。上文中函数返回的堆内存大小可使用 `malloc` 函数族来进行分配。有关堆内存的更多信息，请参阅 堆内存分配。

## MAC 地址

以下 API 用于查询和自定义支持的网络接口（如 Wi-Fi、蓝牙、以太网）的 MAC 地址。

要获取特定接口（如 Wi-Fi、蓝牙、以太网）的 MAC 地址，请调用函数 `esp_read_mac()`。

在 ESP-IDF 中，各个网络接口的 MAC 地址是根据单个 基准 MAC 地址 (Base MAC address) 计算出来的。默认情况下使用乐鑫指定的基准 MAC 地址，该基准地址在产品生产过程中已预烧录至 ESP32 eFuse。

| 接口 | MAC 地址（默认 4 个全局地址） | MAC 地址（2 个全局地址） |
| --- | --- | --- |
| Wi-Fi Station | base_mac | base_mac |
| Wi-Fi SoftAP | base_mac 最后一组字节后加 1 | 本地 MAC （由 Wi-Fi Station MAC 生成） |
| 蓝牙 | base_mac 最后一组字节后加 2 | base_mac 最后一组字节后加 1 |
| 以太网 | base_mac 最后一组字节后加 3 | 本地 MAC （由蓝牙 MAC 生成） |

备注

配置选项 配置了乐鑫提供的全局 MAC 地址的数量。

### 自定义接口 MAC

有时用户可能需要自定义 MAC 地址，这些地址并不由基准 MAC 地址生成。如需设置自定义接口 MAC 地址，请使用 `esp_iface_mac_addr_set()` 函数。该函数用于覆盖由基准 MAC 地址设置（或尚未设置）的接口 MAC 地址。一旦设置某个接口 MAC 地址，即使更改基准 MAC 地址，也不会对其产生影响。

### 自定义基准 MAC

乐鑫已将默认的基准 MAC 地址预烧录至 eFuse BLK0 中。如需设置自定义基准 MAC 地址，请在初始化任一网络接口或调用 `esp_read_mac()` 函数前调用 `esp_base_mac_addr_set()` 函数。自定义基准 MAC 地址可以存储在任何支持的存储设备中（例如 flash、NVS）。

分配自定义基准 MAC 地址时，应避免 MAC 地址重叠。请根据上面的表格配置选项 CONFIG_ESP32_UNIVERSAL_MAC_ADDRESSES，设置可从自定义基准 MAC 地址生成的有效全局 MAC 地址。

备注

也可以调用函数 `esp_netif_set_mac()`，在网络初始化后设置网络接口使用的特定 MAC。但建议使用此处介绍的自定义基准 MAC 地址的方法，以避免原始 MAC 地址在更改前短暂出现在网络上。

#### eFuse 中的自定义 MAC 地址

ESP-IDF 提供了 `esp_efuse_mac_get_custom()` 函数，从 eFuse 读取自定义 MAC 地址时，调用该函数将从 eFuse BLK3 加载 MAC 地址。用户也可以调用 `esp_read_mac()` 函数，此时需使用 `ESP_MAC_EFUSE_CUSTOM` 参数。`esp_efuse_mac_get_custom()` 函数假定自定义基准 MAC 地址的存储格式如下：

| 字段 | 比特数 | 比特范围 | 说明 |
| --- | --- | --- | --- |
| Version | 8 | 191:184 | 0：无效；其他：有效 |
| Reserved | 128 | 183:56 |  |
| MAC address | 48 | 55:8 |  |
| MAC address CRC | 8 | 7:0 | CRC-8-CCITT，多项式 0x07 |

备注

如果启用了 3/4 编码方案，则必须同时烧写该块中的所有 eFuse 字段。

调用 `esp_efuse_mac_get_custom()` 或 `esp_read_mac()` 函数获得自定义 eFuse MAC 地址后，请将此 MAC 地址设置为基准 MAC 地址。有以下两种方法：

- 使用原有 API：调用 `esp_base_mac_addr_set()`。

- 使用新 API：调用 `esp_iface_mac_addr_set()`，此时需使用 `ESP_MAC_BASE` 参数。

### 本地 MAC 地址和全局 MAC 地址

在 ESP32 中，乐鑫已预烧录足够数量的有效乐鑫全局 MAC 地址，供所有内部接口使用。上文中的表格已经介绍了如何根据基准 MAC 地址计算出具体接口的 MAC 地址。

当使用自定义 MAC 地址时，可能并非所有接口都能被分配到一个全局 MAC 地址。此时，接口会被分配一个本地 MAC 地址。请注意，这些地址仅用于单个本地网络。

本地 MAC 地址和全局 MAC 地址的定义，请参见 此处。

内部调用函数 `esp_derive_local_mac()`，可从全局 MAC 地址生成本地 MAC 地址。具体流程如下：

- 在全局 MAC 地址的第一个字节组中设置 U/L 位（位值为 0x2），创建本地 MAC 地址。

- 如果该位已存在于全局 MAC 地址中（即现有的“全局”MAC 地址实际上已经是本地 MAC 地址），则本地 MAC 地址的第一个字节组与 0x4 异或。

## 芯片版本

`esp_chip_info()` 函数用于填充 `esp_chip_info_t` 结构体中的芯片信息，包括芯片版本、CPU 数量和芯片中已启用功能的位掩码。

## SDK 版本

调用函数 `esp_get_idf_version()` 可返回一个字符串，该字符串包含了用于编译应用程序的 ESP-IDF 版本，与构建系统中通过 `IDF_VER` 变量所获得的值相同。该版本字符串的格式即 `git describe` 命令的运行结果。

也有其它的版本宏可用于在构建过程中获取 ESP-IDF 版本，它们可根据 ESP-IDF 版本启用或禁用部分程序。

- `ESP_IDF_VERSION_MAJOR`、 `ESP_IDF_VERSION_MINOR` 和 `ESP_IDF_VERSION_PATCH` 分别被定义为代表主要版本、次要版本和补丁版本的整数。

- `ESP_IDF_VERSION_VAL` 和 `ESP_IDF_VERSION` 可在确认版本时使用：

`
#include "esp_idf_version.h"

#if ESP_IDF_VERSION >= ESP_IDF_VERSION_VAL(4, 0, 0)
    // 启用 ESP-IDF v4.0 中的功能
#endif
`

## 应用程序版本

应用程序版本存储在 `esp_app_desc_t` 结构体中。该结构体位于 DROM 扇区，有一个从二进制文件头部计算的固定偏移值。该结构体位于 `esp_image_header_t` 和 `esp_image_segment_header_t` 结构体之后。字段 Version 类型为字符串，最大长度为 32 字节。

若需手动设置版本，需要在项目的 `CMakeLists.txt` 文件中设置 `PROJECT_VER` 变量，即在 `CMakeLists.txt` 文件中，在包含 `project.cmake` 之前添加 `set(PROJECT_VER "0.1.0.1")`。

如果设置了 CONFIG_APP_PROJECT_VER_FROM_CONFIG 选项，则将使用 CONFIG_APP_PROJECT_VER 的值。否则，如果在项目中未设置 `PROJECT_VER` 变量，则该变量将从 `$(PROJECT_PATH)/version.txt` 文件（若有）中检索，或使用 git 命令 `git describe` 检索。如果两者都不可用，则 `PROJECT_VER` 将被设置为 “1”。应用程序可通过调用 `esp_app_get_description()` 或 `esp_ota_get_partition_description()` 函数来获取应用程序的版本信息。

## 应用示例

- system/base_mac_address 演示了如何从非易失性存储器中检索、设置和派生 ESP32 上每个网络接口的基准 MAC 地址，可以使用 eFuse 或外部存储。

## API 参考

### Header File

- components/esp_system/include/esp_system.h

- This header file can be included with:

`
#include "esp_system.h"
`

### Functions

esp_err_t esp_register_shutdown_handler(shutdown_handler_t handle)

Register shutdown handler.

This function allows you to register a handler that gets invoked before the application is restarted using esp_restart function.

参数:

handle -- function to execute on restart

返回:

- ESP_OK on success

- ESP_ERR_INVALID_STATE if the handler has already been registered

- ESP_ERR_NO_MEM if no more shutdown handler slots are available

esp_err_t esp_unregister_shutdown_handler(shutdown_handler_t handle)

Unregister shutdown handler.

This function allows you to unregister a handler which was previously registered using esp_register_shutdown_handler function.

- ESP_OK on success

- ESP_ERR_INVALID_STATE if the given handler hasn't been registered before

void esp_restart(void)

Restart PRO and APP CPUs.

This function can be called both from PRO and APP CPUs. After successful restart, CPU reset reason will be SW_CPU_RESET. Peripherals (except for Wi-Fi, BT, UART0, SPI1, and legacy timers) are not reset. This function does not return.

esp_reset_reason_t esp_reset_reason(void)

Get reason of last reset.

返回:

See description of esp_reset_reason_t for explanation of each value.

uint32_t esp_get_free_heap_size(void)

Get the size of available heap.

备注

Note that the returned value may be larger than the maximum contiguous block which can be allocated.

返回:

Available heap size, in bytes.

uint32_t esp_get_free_internal_heap_size(void)

Get the size of available internal heap.

备注

Note that the returned value may be larger than the maximum contiguous block which can be allocated.

返回:

Available internal heap size, in bytes.

uint32_t esp_get_minimum_free_heap_size(void)

Get the minimum heap that has ever been available.

返回:

Minimum free heap ever available

void esp_system_abort(const char *details)

Trigger a software abort.

参数:

details -- Details that will be displayed during panic handling.

### Type Definitions

typedef void (*shutdown_handler_t)(void)

Shutdown handler type

### Enumerations

enum esp_reset_reason_t

Reset reasons.

Values:

enumerator ESP_RST_UNKNOWN

Reset reason can not be determined.

enumerator ESP_RST_POWERON

Reset due to power-on event.

enumerator ESP_RST_EXT

Reset by external pin (not applicable for ESP32)

enumerator ESP_RST_SW

Software reset via esp_restart.

enumerator ESP_RST_PANIC

Software reset due to exception/panic.

enumerator ESP_RST_INT_WDT

Reset (software or hardware) due to interrupt watchdog.

enumerator ESP_RST_TASK_WDT

Reset due to task watchdog.

enumerator ESP_RST_WDT

Reset due to other watchdogs.

enumerator ESP_RST_DEEPSLEEP

Reset after exiting deep sleep mode.

enumerator ESP_RST_BROWNOUT

Brownout reset (software or hardware)

enumerator ESP_RST_SDIO

Reset over SDIO.

enumerator ESP_RST_USB

Reset by USB peripheral.

enumerator ESP_RST_JTAG

Reset by JTAG.

enumerator ESP_RST_EFUSE

Reset due to efuse error.

enumerator ESP_RST_PWR_GLITCH

Reset due to power glitch detected.

enumerator ESP_RST_CPU_LOCKUP

Reset due to CPU lock up (double exception)

### Header File

- components/esp_common/include/esp_idf_version.h

- This header file can be included with:

`
#include "esp_idf_version.h"
`

### Functions

const char *esp_get_idf_version(void)

Return full IDF version string, same as 'git describe' output.

备注

If you are printing the ESP-IDF version in a log file or other information, this function provides more information than using the numerical version macros. For example, numerical version macros don't differentiate between development, pre-release and release versions, but the output of this function does.

返回:

constant string from IDF_VER

### Macros

ESP_IDF_VERSION_MAJOR

Major version number (X.x.x)

ESP_IDF_VERSION_MINOR

Minor version number (x.X.x)

ESP_IDF_VERSION_PATCH

Patch version number (x.x.X)

ESP_IDF_VERSION_VAL(major, minor, patch)

Macro to convert IDF version number into an integer

To be used in comparisons, such as ESP_IDF_VERSION >= ESP_IDF_VERSION_VAL(4, 0, 0)

ESP_IDF_VERSION

Current IDF version, as an integer

To be used in comparisons, such as ESP_IDF_VERSION >= ESP_IDF_VERSION_VAL(4, 0, 0)

### Header File

- components/esp_hw_support/include/esp_mac.h

- This header file can be included with:

`
#include "esp_mac.h"
`

### Functions

esp_err_t esp_base_mac_addr_set(const uint8_t *mac)

Set base MAC address with the MAC address which is stored in BLK3 of EFUSE or external storage e.g. flash and EEPROM.

Base MAC address is used to generate the MAC addresses used by network interfaces.

If using a custom base MAC address, call this API before initializing any network interfaces. Refer to the ESP-IDF Programming Guide for details about how the Base MAC is used.

备注

Base MAC must be a unicast MAC (least significant bit of first byte must be zero).

备注

If not using a valid OUI, set the "locally administered" bit (bit value 0x02 in the first byte) to avoid collisions.

参数:

mac -- base MAC address, length: 6 bytes. length: 6 bytes for MAC-48

返回:

ESP_OK on success ESP_ERR_INVALID_ARG If mac is NULL or is not a unicast MAC

esp_err_t esp_base_mac_addr_get(uint8_t *mac)

Return base MAC address which is set using esp_base_mac_addr_set.

备注

If no custom Base MAC has been set, this returns the pre-programmed Espressif base MAC address.

参数:

mac -- base MAC address, length: 6 bytes. length: 6 bytes for MAC-48

返回:

ESP_OK on success ESP_ERR_INVALID_ARG mac is NULL ESP_ERR_INVALID_MAC base MAC address has not been set

esp_err_t esp_efuse_mac_get_custom(uint8_t *mac)

Return base MAC address which was previously written to BLK3 of EFUSE.

Base MAC address is used to generate the MAC addresses used by the networking interfaces. This API returns the custom base MAC address which was previously written to EFUSE BLK3 in a specified format.

Writing this EFUSE allows setting of a different (non-Espressif) base MAC address. It is also possible to store a custom base MAC address elsewhere, see esp_base_mac_addr_set() for details.

备注

This function is currently only supported on ESP32.

参数:

mac -- base MAC address, length: 6 bytes/8 bytes. length: 6 bytes for MAC-48 8 bytes for EUI-64(used for IEEE 802.15.4, if CONFIG_SOC_IEEE802154_SUPPORTED=y)

返回:

ESP_OK on success ESP_ERR_INVALID_ARG mac is NULL ESP_ERR_INVALID_MAC CUSTOM_MAC address has not been set, all zeros (for esp32-xx) ESP_ERR_INVALID_VERSION An invalid MAC version field was read from BLK3 of EFUSE (for esp32) ESP_ERR_INVALID_CRC An invalid MAC CRC was read from BLK3 of EFUSE (for esp32)

esp_err_t esp_efuse_mac_get_default(uint8_t *mac)

Return base MAC address which is factory-programmed by Espressif in EFUSE.

参数:

mac -- base MAC address, length: 6 bytes/8 bytes. length: 6 bytes for MAC-48 8 bytes for EUI-64(used for IEEE 802.15.4, if CONFIG_SOC_IEEE802154_SUPPORTED=y)

返回:

ESP_OK on success ESP_ERR_INVALID_ARG mac is NULL

esp_err_t esp_read_mac(uint8_t *mac, esp_mac_type_t type)

Read base MAC address and set MAC address of the interface.

This function first get base MAC address using esp_base_mac_addr_get(). Then calculates the MAC address of the specific interface requested, refer to ESP-IDF Programming Guide for the algorithm.

The MAC address set by the esp_iface_mac_addr_set() function will not depend on the base MAC address.

参数:

- mac -- base MAC address, length: 6 bytes/8 bytes. length: 6 bytes for MAC-48 8 bytes for EUI-64(used for IEEE 802.15.4, if CONFIG_SOC_IEEE802154_SUPPORTED=y)

- type -- Type of MAC address to return

返回:

ESP_OK on success

esp_err_t esp_derive_local_mac(uint8_t *local_mac, const uint8_t *universal_mac)

Derive local MAC address from universal MAC address.

This function copies a universal MAC address and then sets the "locally

administered" bit (bit 0x2) in the first octet, creating a locally administered MAC address.

If the universal MAC address argument is already a locally administered MAC address, then the first octet is XORed with 0x4 in order to create a different locally administered MAC address.

参数:

- local_mac -- base MAC address, length: 6 bytes. length: 6 bytes for MAC-48

- universal_mac -- Source universal MAC address, length: 6 bytes.

返回:

ESP_OK on success

esp_err_t esp_iface_mac_addr_set(const uint8_t *mac, esp_mac_type_t type)

Set custom MAC address of the interface. This function allows you to overwrite the MAC addresses of the interfaces set by the base MAC address.

参数:

- mac -- MAC address, length: 6 bytes/8 bytes. length: 6 bytes for MAC-48 8 bytes for EUI-64(used for ESP_MAC_IEEE802154 type, if CONFIG_SOC_IEEE802154_SUPPORTED=y)

- type -- Type of MAC address

返回:

ESP_OK on success

size_t esp_mac_addr_len_get(esp_mac_type_t type)

Return the size of the MAC type in bytes.

If CONFIG_SOC_IEEE802154_SUPPORTED is set then for these types:

- ESP_MAC_IEEE802154 is 8 bytes.

- ESP_MAC_BASE, ESP_MAC_EFUSE_FACTORY and ESP_MAC_EFUSE_CUSTOM the MAC size is 6 bytes.

- ESP_MAC_EFUSE_EXT is 2 bytes. If CONFIG_SOC_IEEE802154_SUPPORTED is not set then for all types it returns 6 bytes.

参数:

type -- Type of MAC address

返回:

0 MAC type not found (not supported) 6 bytes for MAC-48. 8 bytes for EUI-64.

### Macros

MAC2STR(a)

MACSTR

### Enumerations

enum esp_mac_type_t

Values:

enumerator ESP_MAC_WIFI_STA

MAC for WiFi Station (6 bytes)

enumerator ESP_MAC_WIFI_SOFTAP

MAC for WiFi Soft-AP (6 bytes)

enumerator ESP_MAC_BT

MAC for Bluetooth (6 bytes)

enumerator ESP_MAC_ETH

MAC for Ethernet (6 bytes)

enumerator ESP_MAC_IEEE802154

if CONFIG_SOC_IEEE802154_SUPPORTED=y, MAC for IEEE802154 (8 bytes)

enumerator ESP_MAC_BASE

Base MAC for that used for other MAC types (6 bytes)

enumerator ESP_MAC_EFUSE_FACTORY

MAC_FACTORY eFuse which was burned by Espressif in production (6 bytes)

enumerator ESP_MAC_EFUSE_CUSTOM

MAC_CUSTOM eFuse which was can be burned by customer (6 bytes)

enumerator ESP_MAC_EFUSE_EXT

if CONFIG_SOC_IEEE802154_SUPPORTED=y, MAC_EXT eFuse which is used as an extender for IEEE802154 MAC (2 bytes)

### Header File

- components/esp_hw_support/include/esp_chip_info.h

- This header file can be included with:

`
#include "esp_chip_info.h"
`

### Functions

void esp_chip_info(esp_chip_info_t *out_info)

Fill an esp_chip_info_t structure with information about the chip.

参数:

out_info -- [out] structure to be filled

### Structures

struct esp_chip_info_t

The structure represents information about the chip.

Public Members

esp_chip_model_t model

chip model, one of esp_chip_model_t

uint32_t features

bit mask of CHIP_FEATURE_x feature flags

uint16_t revision

chip revision number (in format MXX; where M - wafer major version, XX - wafer minor version)

uint8_t cores

number of CPU cores

### Macros

CHIP_FEATURE_EMB_FLASH

Chip has embedded flash memory.

CHIP_FEATURE_WIFI_BGN

Chip has 2.4GHz WiFi.

CHIP_FEATURE_BLE

Chip has Bluetooth LE.

CHIP_FEATURE_BT

Chip has Bluetooth Classic.

CHIP_FEATURE_IEEE802154

Chip has IEEE 802.15.4.

CHIP_FEATURE_EMB_PSRAM

Chip has embedded psram.

### Enumerations

enum esp_chip_model_t

Chip models.

Values:

enumerator CHIP_ESP32

ESP32.

enumerator CHIP_ESP32S2

ESP32-S2.

enumerator CHIP_ESP32S3

ESP32-S3.

enumerator CHIP_ESP32C3

ESP32-C3.

enumerator CHIP_ESP32C2

ESP32-C2.

enumerator CHIP_ESP32C6

ESP32-C6.

enumerator CHIP_ESP32H2

ESP32-H2.

enumerator CHIP_ESP32P4

ESP32-P4.

enumerator CHIP_ESP32C61

ESP32-C61.

enumerator CHIP_ESP32C5

ESP32-C5.

enumerator CHIP_ESP32H21

ESP32-H21.

enumerator CHIP_ESP32H4

ESP32-H4.

enumerator CHIP_POSIX_LINUX

The code is running on POSIX/Linux simulator.

### Header File

- components/esp_hw_support/include/esp_cpu.h

- This header file can be included with:

`
#include "esp_cpu.h"
`

### Functions

void esp_cpu_stall(int core_id)

Stall a CPU core.

参数:

core_id -- The core's ID

void esp_cpu_unstall(int core_id)

Resume a previously stalled CPU core.

参数:

core_id -- The core's ID

void esp_cpu_reset(int core_id)

Reset a CPU core.

参数:

core_id -- The core's ID

void esp_cpu_wait_for_intr(void)

Wait for Interrupt.

This function causes the current CPU core to execute its Wait For Interrupt (WFI or equivalent) instruction. After executing this function, the CPU core will stop execution until an interrupt occurs.

int esp_cpu_get_core_id(void)

Get the current core's ID.

This function will return the ID of the current CPU (i.e., the CPU that calls this function).

返回:

The current core's ID [0..SOC_CPU_CORES_NUM - 1]

int esp_cpu_get_curr_privilege_level(void)

Get the current [RISC-V] CPU core's privilege level.

This function returns the current privilege level of the CPU core executing this function.

返回:

The current CPU core's privilege level, -1 if not supported.

void *esp_cpu_get_sp(void)

Read the current stack pointer address.

返回:

Stack pointer address

esp_cpu_cycle_count_t esp_cpu_get_cycle_count(void)

Get the current CPU core's cycle count.

Each CPU core maintains an internal counter (i.e., cycle count) that increments every CPU clock cycle.

返回:

Current CPU's cycle count, 0 if not supported.

void esp_cpu_set_cycle_count(esp_cpu_cycle_count_t cycle_count)

Set the current CPU core's cycle count.

Set the given value into the internal counter that increments every CPU clock cycle.

参数:

cycle_count -- CPU cycle count

void *esp_cpu_pc_to_addr(uint32_t pc)

Convert a program counter (PC) value to address.

If the architecture does not store the true virtual address in the CPU's PC or return addresses, this function will convert the PC value to a virtual address. Otherwise, the PC is just returned

参数:

pc -- PC value

返回:

Virtual address

void esp_cpu_set_threadptr(void *threadptr)

Set the current CPU core's thread pointer.

Sets the thread pointer register to the given value.

参数:

threadptr -- Pointer to the thread-local storage area

void *esp_cpu_get_threadptr(void)

Get the current CPU core's thread pointer.

返回:

thread pointer register value

void esp_cpu_intr_get_desc(int core_id, int intr_num, esp_cpu_intr_desc_t *intr_desc_ret)

Get a CPU interrupt's descriptor.

Each CPU interrupt has a descriptor describing the interrupt's capabilities and restrictions. This function gets the descriptor of a particular interrupt on a particular CPU.

参数:

- core_id -- [in] The core's ID

- intr_num -- [in] Interrupt number

- intr_desc_ret -- [out] The interrupt's descriptor

void esp_cpu_intr_set_ivt_addr(const void *ivt_addr)

Set the base address of the current CPU's Interrupt Vector Table (IVT)

参数:

ivt_addr -- Interrupt Vector Table's base address

bool esp_cpu_intr_has_handler(int intr_num)

Check if a particular interrupt already has a handler function.

Check if a particular interrupt on the current CPU already has a handler function assigned.

备注

This function simply checks if the IVT of the current CPU already has a handler assigned.

参数:

intr_num -- Interrupt number (from 0 to 31)

返回:

True if the interrupt has a handler function, false otherwise.

void esp_cpu_intr_set_handler(int intr_num, esp_cpu_intr_handler_t handler, void *handler_arg)

Set the handler function of a particular interrupt.

Assign a handler function (i.e., ISR) to a particular interrupt on the current CPU.

备注

This function simply sets the handler function (in the IVT) and does not actually enable the interrupt.

参数:

- intr_num -- Interrupt number (from 0 to 31)

- handler -- Handler function

- handler_arg -- Argument passed to the handler function

void *esp_cpu_intr_get_handler_arg(int intr_num)

Get a handler function's argument of.

Get the argument of a previously assigned handler function on the current CPU.

参数:

intr_num -- Interrupt number (from 0 to 31)

返回:

The the argument passed to the handler function

void esp_cpu_intr_enable(uint32_t intr_mask)

Enable particular interrupts on the current CPU.

参数:

intr_mask -- Bit mask of the interrupts to enable

void esp_cpu_intr_disable(uint32_t intr_mask)

Disable particular interrupts on the current CPU.

参数:

intr_mask -- Bit mask of the interrupts to disable

uint32_t esp_cpu_intr_get_enabled_mask(void)

Get the enabled interrupts on the current CPU.

返回:

Bit mask of the enabled interrupts

void esp_cpu_intr_edge_ack(int intr_num)

Acknowledge an edge interrupt.

参数:

intr_num -- Interrupt number (from 0 to 31)

void esp_cpu_configure_region_protection(void)

Configure the CPU to disable access to invalid memory regions.

esp_err_t esp_cpu_set_breakpoint(int bp_num, const void *bp_addr)

Set and enable a hardware breakpoint on the current CPU.

备注

This function is meant to be called by the panic handler to set a breakpoint for an attached debugger during a panic.

备注

Overwrites previously set breakpoint with same breakpoint number.

参数:

- bp_num -- Hardware breakpoint number [0..SOC_CPU_BREAKPOINTS_NUM - 1]

- bp_addr -- Address to set a breakpoint on

返回:

ESP_OK if breakpoint is set. Failure otherwise

esp_err_t esp_cpu_clear_breakpoint(int bp_num)

Clear a hardware breakpoint on the current CPU.

备注

Clears a breakpoint regardless of whether it was previously set

参数:

bp_num -- Hardware breakpoint number [0..SOC_CPU_BREAKPOINTS_NUM - 1]

返回:

ESP_OK if breakpoint is cleared. Failure otherwise

esp_err_t esp_cpu_set_watchpoint(int wp_num, const void *wp_addr, size_t size, esp_cpu_watchpoint_trigger_t trigger)

Set and enable a hardware watchpoint on the current CPU.

Set and enable a hardware watchpoint on the current CPU, specifying the memory range and trigger operation. Watchpoints will break/panic the CPU when the CPU accesses (according to the trigger type) on a certain memory range.

备注

Overwrites previously set watchpoint with same watchpoint number. On RISC-V chips, this API uses method0(Exact matching) and method1(NAPOT matching) according to the riscv-debug-spec-0.13 specification for address matching. If the watch region size is 1byte, it uses exact matching (method 0). If the watch region size is larger than 1byte, it uses NAPOT matching (method 1). This mode requires the watching region start address to be aligned to the watching region size.

参数:

- wp_num -- Hardware watchpoint number [0..SOC_CPU_WATCHPOINTS_NUM - 1]

- wp_addr -- Watchpoint's base address, must be naturally aligned to the size of the region

- size -- Size of the region to watch. Must be one of 2^n and in the range of [1 ... SOC_CPU_WATCHPOINT_MAX_REGION_SIZE]

- trigger -- Trigger type

返回:

ESP_ERR_INVALID_ARG on invalid arg, ESP_OK otherwise

esp_err_t esp_cpu_clear_watchpoint(int wp_num)

Clear a hardware watchpoint on the current CPU.

备注

Clears a watchpoint regardless of whether it was previously set

参数:

wp_num -- Hardware watchpoint number [0..SOC_CPU_WATCHPOINTS_NUM - 1]

返回:

ESP_OK if watchpoint was cleared. Failure otherwise.

bool esp_cpu_dbgr_is_attached(void)

Check if the current CPU has a debugger attached.

返回:

True if debugger is attached, false otherwise

void esp_cpu_dbgr_break(void)

Trigger a call to the current CPU's attached debugger.

intptr_t esp_cpu_get_call_addr(intptr_t return_address)

Given the return address, calculate the address of the preceding call instruction This is typically used to answer the question "where was the function called from?".

参数:

return_address -- The value of the return address register. Typically set to the value of __builtin_return_address(0).

返回:

Address of the call instruction preceding the return address.

bool esp_cpu_compare_and_set(volatile uint32_t *addr, uint32_t compare_value, uint32_t new_value)

Atomic compare-and-set operation.

参数:

- addr -- Address of atomic variable

- compare_value -- Value to compare the atomic variable to

- new_value -- New value to set the atomic variable to

返回:

Whether the atomic variable was set or not

### Structures

struct esp_cpu_intr_desc_t

CPU interrupt descriptor.

Each particular CPU interrupt has an associated descriptor describing that particular interrupt's characteristics. Call esp_cpu_intr_get_desc() to get the descriptors of a particular interrupt.

Public Members

int priority

Priority of the interrupt if it has a fixed priority, (-1) if the priority is configurable.

esp_cpu_intr_type_t type

Whether the interrupt is an edge or level type interrupt, ESP_CPU_INTR_TYPE_NA if the type is configurable.

uint32_t flags

Flags indicating extra details.

### Macros

ESP_CPU_INTR_DESC_FLAG_SPECIAL

Interrupt descriptor flags of esp_cpu_intr_desc_t.

The interrupt is a special interrupt (e.g., a CPU timer interrupt)

ESP_CPU_INTR_DESC_FLAG_RESVD

The interrupt is reserved for internal use

### Type Definitions

typedef uint32_t esp_cpu_cycle_count_t

CPU cycle count type.

This data type represents the CPU's clock cycle count

typedef void (*esp_cpu_intr_handler_t)(void *arg)

CPU interrupt handler type.

### Enumerations

enum esp_cpu_intr_type_t

CPU interrupt type.

Values:

enumerator ESP_CPU_INTR_TYPE_LEVEL

enumerator ESP_CPU_INTR_TYPE_EDGE

enumerator ESP_CPU_INTR_TYPE_NA

enum esp_cpu_watchpoint_trigger_t

CPU watchpoint trigger type.

Values:

enumerator ESP_CPU_WATCHPOINT_LOAD

enumerator ESP_CPU_WATCHPOINT_STORE

enumerator ESP_CPU_WATCHPOINT_ACCESS

### Header File

- components/esp_app_format/include/esp_app_desc.h

- This header file can be included with:

`
#include "esp_app_desc.h"
`

- This header file is a part of the API provided by the `esp_app_format` component. To declare that your component depends on `esp_app_format`, add the following to your CMakeLists.txt:

`
REQUIRES esp_app_format
`

or

`
PRIV_REQUIRES esp_app_format
`

### Functions

const esp_app_desc_t *esp_app_get_description(void)

Return esp_app_desc structure. This structure includes app version.

Return description for running app.

返回:

Pointer to esp_app_desc structure.

int esp_app_get_elf_sha256(char *dst, size_t size)

Fill the provided buffer with SHA256 of the ELF file, formatted as hexadecimal, null-terminated. If the buffer size is not sufficient to fit the entire SHA256 in hex plus a null terminator, the largest possible number of bytes will be written followed by a null.

参数:

- dst -- Destination buffer

- size -- Size of the buffer

返回:

Number of bytes written to dst (including null terminator)

char *esp_app_get_elf_sha256_str(void)

Return SHA256 of the ELF file which is already formatted as hexadecimal, null-terminated included. Can be used in panic handler or core dump during when cache is disabled. The length is defined by CONFIG_APP_RETRIEVE_LEN_ELF_SHA option.

返回:

Hexadecimal SHA256 string

### Structures

struct esp_app_desc_t

Description about application.

Public Members

uint32_t magic_word

Magic word ESP_APP_DESC_MAGIC_WORD

uint32_t secure_version

Secure version

uint32_t reserv1[2]

reserv1

char version[32]

Application version

char project_name[32]

Project name

char time[16]

Compile time

char date[16]

Compile date

char idf_ver[32]

Version IDF

uint8_t app_elf_sha256[32]

sha256 of elf file

uint16_t min_efuse_blk_rev_full

Minimal eFuse block revision supported by image, in format: major * 100 + minor

uint16_t max_efuse_blk_rev_full

Maximal eFuse block revision supported by image, in format: major * 100 + minor

uint8_t mmu_page_size

MMU page size in log base 2 format

uint8_t reserv3[3]

reserv3

uint32_t reserv2[18]

reserv2

### Macros

ESP_APP_DESC_MAGIC_WORD

The magic word for the esp_app_desc structure that is in DROM.

此文档对您有帮助吗？

- 反馈已收到，谢谢！

- 如果您有其他意见，欢迎填写乐鑫文档反馈表。

- 我们重视您的反馈。

- 您可以填写乐鑫文档反馈表告诉我们如何改进该文档。
