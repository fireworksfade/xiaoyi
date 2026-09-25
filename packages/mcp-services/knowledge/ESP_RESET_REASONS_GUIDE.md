Source: https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-reference/system/misc_system_api.html

Miscellaneous System APIs
[中文]
Software Reset
To perform software reset of the chip, the esp_restart() function is provided. When the function is called, execution of the program stops, both CPUs are reset, the application is loaded by the bootloader and starts execution again.
Additionally, the esp_register_shutdown_handler() function can register a routine that will be automatically called before a restart (that is triggered by esp_restart()) occurs. This is similar to the functionality of atexit POSIX function.

Reset Reason
ESP-IDF applications can be started or restarted due to a variety of reasons. To get the last reset reason, call esp_reset_reason() function. See description of esp_reset_reason_t for the list of possible reset reasons.

Heap Memory
Two heap-memory-related functions are provided:
esp_get_free_heap_size() returns the current size of free heap memory.

esp_get_minimum_free_heap_size() returns the minimum size of free heap memory that has ever been available (i.e., the smallest size of free heap memory in the application's lifetime).

Note that ESP-IDF supports multiple heaps with different capabilities. The functions mentioned in this section return the size of heap memory that can be allocated using the malloc family of functions. For further information about heap memory, see Heap Memory Allocation.

MAC Address
These APIs allow querying and customizing MAC addresses for different supported network interfaces (e.g., Wi-Fi, Bluetooth, Ethernet).
To fetch the MAC address for a specific network interface (e.g., Wi-Fi, Bluetooth, Ethernet), call the function esp_read_mac().
In ESP-IDF, the MAC addresses for the various network interfaces are calculated from a single base MAC address. By default, the Espressif base MAC address is used. This base MAC address is pre-programmed into the ESP32 eFuse in the factory during production.
Interface
MAC Address (4 universally administered, default)
MAC Address (2 universally administered)

Wi-Fi Station
base_mac
base_mac

Wi-Fi SoftAP
base_mac, +1 to the last octet
Local MAC (derived from Wi-Fi Station MAC)

Bluetooth
base_mac, +2 to the last octet
base_mac, +1 to the last octet

Ethernet
base_mac, +3 to the last octet
Local MAC (derived from Bluetooth MAC)

Note
The configuration configures the number of universally administered MAC addresses that are provided by Espressif.

Custom Interface MAC
Sometimes you may need to define custom MAC addresses that are not generated from the base MAC address. To set a custom interface MAC address, use the esp_iface_mac_addr_set() function. This function allows you to overwrite the MAC addresses of interfaces set (or not yet set) by the base MAC address. Once a MAC address has been set for a particular interface, it will not be affected when the base MAC address is changed.

Custom Base MAC
The default base MAC is pre-programmed by Espressif in eFuse BLK0. To set a custom base MAC instead, call the function esp_iface_mac_addr_set() with the ESP_MAC_BASE argument (or esp_base_mac_addr_set()) before initializing any network interfaces or calling the esp_read_mac() function. The custom MAC address can be stored in any supported storage device (e.g., flash, NVS).
The custom base MAC addresses should be allocated such that derived MAC addresses will not overlap. Based on the table above, users can configure the option CONFIG_ESP32_UNIVERSAL_MAC_ADDRESSES to set the number of valid universal MAC addresses that can be derived from the custom base MAC.
Note
It is also possible to call the function esp_netif_set_mac() to set the specific MAC used by a network interface after network initialization. But it is recommended to use the base MAC approach documented here to avoid the possibility of the original MAC address briefly appearing on the network before being changed.

Custom MAC Address in eFuse
When reading custom MAC addresses from eFuse, ESP-IDF provides a helper function esp_efuse_mac_get_custom(). Users can also use esp_read_mac() with the ESP_MAC_EFUSE_CUSTOM argument. This loads the MAC address from eFuse BLK3. The esp_efuse_mac_get_custom() function assumes that the custom base MAC address is stored in the following format:
Field
# of bits
Range of bits
Notes

Version
8
191:184
0: invalid, others — valid

Reserved
128
183:56

MAC address
48
55:8

MAC address CRC
8
7:0
CRC-8-CCITT, polynomial 0x07

Note
If the 3/4 coding scheme is enabled, all eFuse fields in this block must be burnt at the same time.

Once custom eFuse MAC address has been obtained (using esp_efuse_mac_get_custom() or esp_read_mac()), you need to set it as the base MAC address. There are two ways to do it:
Use an old API: call esp_base_mac_addr_set().

Use a new API: call esp_iface_mac_addr_set() with the ESP_MAC_BASE argument.

Local Versus Universal MAC Addresses
ESP32 comes pre-programmed with enough valid Espressif universally administered MAC addresses for all internal interfaces. The table above shows how to calculate and derive the MAC address for a specific interface according to the base MAC address.
When using a custom MAC address scheme, it is possible that not all interfaces can be assigned with a universally administered MAC address. In these cases, a locally administered MAC address is assigned. Note that these addresses are intended for use on a single local network only.
See this article for the definition of locally and universally administered MAC addresses.
Function esp_derive_local_mac() is called internally to derive a local MAC address from a universal MAC address. The process is as follows:
The U/L bit (bit value 0x2) is set in the first octet of the universal MAC address, creating a local MAC address.

If this bit is already set in the supplied universal MAC address (i.e., the supplied "universal" MAC address was in fact already a local MAC address), then the first octet of the local MAC address is XORed with 0x4.

Chip Version
esp_chip_info() function fills esp_chip_info_t structure with information about the chip. This includes the chip revision, number of CPU cores, and a bit mask of features enabled in the chip.

SDK Version
esp_get_idf_version() returns a string describing the ESP-IDF version which is used to compile the application. This is the same value as the one available through IDF_VER variable of the build system. The version string generally has the format of gitdescribe output.
To get the version at build time, additional version macros are provided. They can be used to enable or disable parts of the program depending on the ESP-IDF version.
ESP_IDF_VERSION_MAJOR, ESP_IDF_VERSION_MINOR, ESP_IDF_VERSION_PATCH are defined to integers representing major, minor, and patch version.

ESP_IDF_VERSION_VAL and ESP_IDF_VERSION can be used when implementing version checks:

#include"esp_idf_version.h"#if ESP_IDF_VERSION >= ESP_IDF_VERSION_VAL(4, 0, 0)// enable functionality present in ESP-IDF v4.0#endif

Debug Helpers
The debug helper APIs in esp_debug_helpers.h provide utilities for run-time debugging and stack backtrace output.
esp_backtrace_print() prints the current stack backtrace.

esp_backtrace_print_all_tasks() prints backtraces for all tasks.

esp_backtrace_get_start() and esp_backtrace_get_next_frame() allow manual iteration over backtrace frames.

These APIs are useful when diagnosing crashes, watchdog timeouts, or unexpected control flow.

App Version
The application version is stored in esp_app_desc_t structure. It is located in DROM sector and has a fixed offset from the beginning of the binary file. The structure is located after esp_image_header_t and esp_image_segment_header_t structures. The type of the field version is string and it has a maximum length of 32 chars.
To set the version in your project manually, you need to set the PROJECT_VER variable in the CMakeLists.txt of your project. In application CMakeLists.txt, put set(PROJECT_VER"0.1.0.1") before including project.cmake.
If the CONFIG_APP_PROJECT_VER_FROM_CONFIG option is set, the value of CONFIG_APP_PROJECT_VER will be used. Otherwise, if the PROJECT_VER variable is not set in the project, it will be retrieved either from the $(PROJECT_PATH)/version.txt file (if present) or using git command gitdescribe. If neither is available, PROJECT_VER will be set to "1". Application can make use of this by calling esp_app_get_description() or esp_ota_get_partition_description() functions.

Application Examples
system/base_mac_address demonstrates how to retrieve, set, and derive the base MAC address for each network interface on ESP32 from non-volatile memory, using either the eFuse blocks or external storage.

API Reference
Header File
components/esp_system/include/esp_system.h

This header file can be included with:

#include"esp_system.h"

Functions
esp_err_tesp_register_shutdown_handler(shutdown_handler_thandle)
Register shutdown handler.
This function allows you to register a handler that gets invoked before the application is restarted using esp_restart function.
Parameters:handle -- function to execute on restart
Returns:ESP_OK on success

ESP_ERR_INVALID_STATE if the handler has already been registered

ESP_ERR_NO_MEM if no more shutdown handler slots are available

esp_err_tesp_unregister_shutdown_handler(shutdown_handler_thandle)
Unregister shutdown handler.
This function allows you to unregister a handler which was previously registered using esp_register_shutdown_handler function.ESP_OK on success

ESP_ERR_INVALID_STATE if the given handler hasn't been registered before

voidesp_restart(void)
Restart PRO and APP CPUs.
This function can be called both from PRO and APP CPUs. After successful restart, CPU reset reason will be SW_CPU_RESET. Peripherals (except for Wi-Fi, BT, UART0, SPI1, and legacy timers) are not reset. This function does not return.
esp_reset_reason_tesp_reset_reason(void)
Get reason of last reset.
Returns:See description of esp_reset_reason_t for explanation of each value.
uint32_tesp_get_free_heap_size(void)
Get the size of available heap.
Note
Note that the returned value may be larger than the maximum contiguous block which can be allocated.

Returns:Available heap size, in bytes.
uint32_tesp_get_free_internal_heap_size(void)
Get the size of available internal heap.
Note
Note that the returned value may be larger than the maximum contiguous block which can be allocated.

Returns:Available internal heap size, in bytes.
uint32_tesp_get_minimum_free_heap_size(void)
Get the minimum heap that has ever been available.
Returns:Minimum free heap ever available
voidesp_system_abort(constchar*details)
Trigger a software abort.
Parameters:details -- Details that will be displayed during panic handling.

Type Definitions
typedefvoid(*shutdown_handler_t)(void)
Shutdown handler type

Enumerations
enumesp_reset_reason_t
Reset reasons.
Values:
enumeratorESP_RST_UNKNOWN
Reset reason can not be determined.
enumeratorESP_RST_POWERON
Reset due to power-on event.
enumeratorESP_RST_EXT
Reset by external pin (not applicable for ESP32)
enumeratorESP_RST_SW
Software reset via esp_restart.
enumeratorESP_RST_PANIC
Software reset due to exception/panic.
enumeratorESP_RST_INT_WDT
Reset (software or hardware) due to interrupt watchdog.
enumeratorESP_RST_TASK_WDT
Reset due to task watchdog.
enumeratorESP_RST_WDT
Reset due to other watchdogs.
enumeratorESP_RST_DEEPSLEEP
Reset after exiting deep sleep mode.
enumeratorESP_RST_BROWNOUT
Brownout reset (software or hardware)
enumeratorESP_RST_SDIO
Reset over SDIO.
enumeratorESP_RST_USB
Reset by USB peripheral.
enumeratorESP_RST_JTAG
Reset by JTAG.
enumeratorESP_RST_EFUSE
Reset due to efuse error.
enumeratorESP_RST_PWR_GLITCH
Reset due to power glitch detected.
enumeratorESP_RST_CPU_LOCKUP
Reset due to CPU lock up (double exception)

Header File
components/esp_common/include/esp_idf_version.h

This header file can be included with:

#include"esp_idf_version.h"

Functions
constchar*esp_get_idf_version(void)
Return full IDF version string, same as 'git describe' output.
Note
If you are printing the ESP-IDF version in a log file or other information, this function provides more information than using the numerical version macros. For example, numerical version macros don't differentiate between development, pre-release and release versions, but the output of this function does.

Returns:constant string from IDF_VER

Macros
ESP_IDF_VERSION_MAJOR
Major version number (X.x.x)
ESP_IDF_VERSION_MINOR
Minor version number (x.X.x)
ESP_IDF_VERSION_PATCH
Patch version number (x.x.X)
ESP_IDF_VERSION_VAL(major, minor, patch)
Macro to convert IDF version number into an integer
To be used in comparisons, such as ESP_IDF_VERSION >= ESP_IDF_VERSION_VAL(4, 0, 0)
ESP_IDF_VERSION
Current IDF version, as an integer
To be used in comparisons, such as ESP_IDF_VERSION >= ESP_IDF_VERSION_VAL(4, 0, 0)

Header File
components/esp_hw_support/include/esp_mac.h

This header file can be included with:

#include"esp_mac.h"

Functions
esp_err_tesp_base_mac_addr_set(constuint8_t*mac)
Set base MAC address with the MAC address which is stored in BLK3 of EFUSE or external storage e.g. flash and EEPROM.
Base MAC address is used to generate the MAC addresses used by network interfaces.
If using a custom base MAC address, call this API before initializing any network interfaces. Refer to the ESP-IDF Programming Guide for details about how the Base MAC is used.
Note
Base MAC must be a unicast MAC (least significant bit of first byte must be zero).

Note
If not using a valid OUI, set the "locally administered" bit (bit value 0x02 in the first byte) to avoid collisions.

Parameters:mac -- base MAC address, length: 6 bytes. length: 6 bytes for MAC-48
Returns:ESP_OK on success ESP_ERR_INVALID_ARG If mac is NULL or is not a unicast MAC
esp_err_tesp_base_mac_addr_get(uint8_t*mac)
Return base MAC address which is set using esp_base_mac_addr_set.
Note
If no custom Base MAC has been set, this returns the pre-programmed Espressif base MAC address.

Parameters:mac -- base MAC address, length: 6 bytes. length: 6 bytes for MAC-48
Returns:ESP_OK on success ESP_ERR_INVALID_ARG mac is NULL ESP_ERR_INVALID_MAC base MAC address has not been set
esp_err_tesp_efuse_mac_get_custom(uint8_t*mac)
Return base MAC address which was previously written to BLK3 of EFUSE.
Base MAC address is used to generate the MAC addresses used by the networking interfaces. This API returns the custom base MAC address which was previously written to EFUSE BLK3 in a specified format.
Writing this EFUSE allows setting of a different (non-Espressif) base MAC address. It is also possible to store a custom base MAC address elsewhere, see esp_base_mac_addr_set() for details.
Note
This function is currently only supported on ESP32.

Parameters:mac -- base MAC address, length: 6 bytes/8 bytes. length: 6 bytes for MAC-48 8 bytes for EUI-64(used for IEEE 802.15.4, if CONFIG_SOC_IEEE802154_SUPPORTED=y)
Returns:ESP_OK on success ESP_ERR_INVALID_ARG mac is NULL ESP_ERR_INVALID_MAC CUSTOM_MAC address has not been set, all zeros (for esp32-xx) ESP_ERR_INVALID_VERSION An invalid MAC version field was read from BLK3 of EFUSE (for esp32) ESP_ERR_INVALID_CRC An invalid MAC CRC was read from BLK3 of EFUSE (for esp32)
esp_err_tesp_efuse_mac_get_default(uint8_t*mac)
Return base MAC address which is factory-programmed by Espressif in EFUSE.
Parameters:mac -- base MAC address, length: 6 bytes/8 bytes. length: 6 bytes for MAC-48 8 bytes for EUI-64(used for IEEE 802.15.4, if CONFIG_SOC_IEEE802154_SUPPORTED=y)
Returns:ESP_OK on success ESP_ERR_INVALID_ARG mac is NULL
esp_err_tesp_read_mac(uint8_t*mac, esp_mac_type_ttype)
Read base MAC address and set MAC address of the interface.
This function first get base MAC address using esp_base_mac_addr_get(). Then calculates the MAC address of the specific interface requested, refer to ESP-IDF Programming Guide for the algorithm.

The MAC address set by the esp_iface_mac_addr_set() function will not depend on the base MAC address.
Note
This function reads MAC address directly from efuse(and might be different from MAC address read using esp_wifi_get_mac() API).

Parameters:mac -- base MAC address, length: 6 bytes/8 bytes. length: 6 bytes for MAC-48 8 bytes for EUI-64(used for IEEE 802.15.4, if CONFIG_SOC_IEEE802154_SUPPORTED=y)

type -- Type of MAC address to return

Returns:ESP_OK on success
esp_err_tesp_derive_local_mac(uint8_t*local_mac, constuint8_t*universal_mac)
Derive local MAC address from universal MAC address.
This function copies a universal MAC address and then sets the "locally
administered" bit (bit 0x2) in the first octet, creating a locally administered MAC address.

If the universal MAC address argument is already a locally administered MAC address, then the first octet is XORed with 0x4 in order to create a different locally administered MAC address.
Parameters:local_mac -- base MAC address, length: 6 bytes. length: 6 bytes for MAC-48

universal_mac -- Source universal MAC address, length: 6 bytes.

Returns:ESP_OK on success
esp_err_tesp_iface_mac_addr_set(constuint8_t*mac, esp_mac_type_ttype)
Set custom MAC address of the interface. This function allows you to overwrite the MAC addresses of the interfaces set by the base MAC address.
Parameters:mac -- MAC address, length: 6 bytes/8 bytes. length: 6 bytes for MAC-48 8 bytes for EUI-64(used for ESP_MAC_IEEE802154 type, if CONFIG_SOC_IEEE802154_SUPPORTED=y)

type -- Type of MAC address

Returns:ESP_OK on success
size_tesp_mac_addr_len_get(esp_mac_type_ttype)
Return the size of the MAC type in bytes.
If CONFIG_SOC_IEEE802154_SUPPORTED is set then for these types:ESP_MAC_IEEE802154 is 8 bytes.

ESP_MAC_BASE, ESP_MAC_EFUSE_FACTORY and ESP_MAC_EFUSE_CUSTOM the MAC size is 6 bytes.

ESP_MAC_EFUSE_EXT is 2 bytes. If CONFIG_SOC_IEEE802154_SUPPORTED is not set then for all types it returns 6 bytes.

Parameters:type -- Type of MAC address
Returns:0 MAC type not found (not supported) 6 bytes for MAC-48. 8 bytes for EUI-64.

Macros
MAC2STR(a)
MACSTR

Enumerations
enumesp_mac_type_t
Values:
enumeratorESP_MAC_WIFI_STA
MAC for WiFi Station (6 bytes)
enumeratorESP_MAC_WIFI_SOFTAP
MAC for WiFi Soft-AP (6 bytes)
enumeratorESP_MAC_BT
MAC for Bluetooth (6 bytes)
enumeratorESP_MAC_ETH
MAC for Ethernet (6 bytes)
enumeratorESP_MAC_IEEE802154
if CONFIG_SOC_IEEE802154_SUPPORTED=y, MAC for IEEE802154 (8 bytes)
enumeratorESP_MAC_BASE
Base MAC for that used for other MAC types (6 bytes)
enumeratorESP_MAC_EFUSE_FACTORY
MAC_FACTORY eFuse which was burned by Espressif in production (6 bytes)
enumeratorESP_MAC_EFUSE_CUSTOM
MAC_CUSTOM eFuse which was can be burned by customer (6 bytes)
enumeratorESP_MAC_EFUSE_EXT
if CONFIG_SOC_IEEE802154_SUPPORTED=y, MAC_EXT eFuse which is used as an extender for IEEE802154 MAC (2 bytes)

Header File
components/esp_hw_support/include/esp_chip_info.h

This header file can be included with:

#include"esp_chip_info.h"

Functions
voidesp_chip_info(esp_chip_info_t*out_info)
Fill an esp_chip_info_t structure with information about the chip.
Parameters:out_info -- [out] structure to be filled

Structures
structesp_chip_info_t
The structure represents information about the chip.
Public Members
esp_chip_model_tmodel
chip model, one of esp_chip_model_t
uint32_tfeatures
bit mask of CHIP_FEATURE_x feature flags
uint16_trevision
chip revision number (in format MXX; where M - wafer major version, XX - wafer minor version)
uint8_tcores
number of CPU cores

Macros
CHIP_FEATURE_EMB_FLASH
Chip has embedded flash memory.
CHIP_FEATURE_WIFI_BGN
Chip has 2.4GHz WiFi.
CHIP_FEATURE_BLE
Chip has Bluetooth LE.
CHIP_FEATURE_BT
Chip has Bluetooth Classic.
CHIP_FEATURE_IEEE802154
Chip has IEEE 802.15.4.
CHIP_FEATURE_EMB_PSRAM
Chip has embedded psram.

Enumerations
enumesp_chip_model_t
Chip models.
Values:
enumeratorCHIP_ESP32
ESP32.
enumeratorCHIP_ESP32S2
ESP32-S2.
enumeratorCHIP_ESP32S3
ESP32-S3.
enumeratorCHIP_ESP32C3
ESP32-C3.
enumeratorCHIP_ESP32C2
ESP32-C2.
enumeratorCHIP_ESP32C6
ESP32-C6.
enumeratorCHIP_ESP32H2
ESP32-H2.
enumeratorCHIP_ESP32P4
ESP32-P4.
enumeratorCHIP_ESP32C61
ESP32-C61.
enumeratorCHIP_ESP32C5
ESP32-C5.
enumeratorCHIP_ESP32H21
ESP32-H21.
enumeratorCHIP_ESP32H4
ESP32-H4.
enumeratorCHIP_ESP32S31
ESP32-S31.
enumeratorCHIP_POSIX_LINUX
The code is running on POSIX/Linux simulator.

Header File
components/esp_hw_support/include/esp_cpu.h

This header file can be included with:

#include"esp_cpu.h"

Functions
voidesp_cpu_stall(intcore_id)
Stall a CPU core.
Parameters:core_id -- The core's ID
voidesp_cpu_unstall(intcore_id)
Resume a previously stalled CPU core.
Parameters:core_id -- The core's ID
voidesp_cpu_reset(intcore_id)
Reset a CPU core.
Parameters:core_id -- The core's ID
voidesp_cpu_wait_for_intr(void)
Wait for Interrupt.
This function causes the current CPU core to execute its Wait For Interrupt (WFI or equivalent) instruction. After executing this function, the CPU core will stop execution until an interrupt occurs.
Note
On some RISC-V targets, if a debugger is attached while the hardware wait mode is disabled, this function may return immediately instead of entering WFI. This keeps debugger memory access working.

intesp_cpu_get_core_id(void)
Get the current core's ID.
This function will return the ID of the current CPU (i.e., the CPU that calls this function).
Returns:The current core's ID [0..SOC_CPU_CORES_NUM - 1]
intesp_cpu_get_curr_privilege_level(void)
Get the current [RISC-V] CPU core's privilege level.
This function returns the current privilege level of the CPU core executing this function.
Returns:The current CPU core's privilege level, -1 if not supported.
void*esp_cpu_get_sp(void)
Read the current stack pointer address.
Returns:Stack pointer address
esp_cpu_cycle_count_tesp_cpu_get_cycle_count(void)
Get the current CPU core's cycle count.
Each CPU core maintains an internal counter (i.e., cycle count) that increments every CPU clock cycle.
Returns:Current CPU's cycle count, 0 if not supported.
voidesp_cpu_set_cycle_count(esp_cpu_cycle_count_tcycle_count)
Set the current CPU core's cycle count.
Set the given value into the internal counter that increments every CPU clock cycle.
Parameters:cycle_count -- CPU cycle count
void*esp_cpu_pc_to_addr(uint32_tpc)
Convert a program counter (PC) value to address.
If the architecture does not store the true virtual address in the CPU's PC or return addresses, this function will convert the PC value to a virtual address. Otherwise, the PC is just returned
Parameters:pc -- PC value
Returns:Virtual address
voidesp_cpu_set_threadptr(void*threadptr)
Set the current CPU core's thread pointer.
Sets the thread pointer register to the given value.
Parameters:threadptr -- Pointer to the thread-local storage area
void*esp_cpu_get_threadptr(void)
Get the current CPU core's thread pointer.
Returns:thread pointer register value
voidesp_cpu_intr_get_desc(intcore_id, intintr_num, esp_cpu_intr_desc_t*intr_desc_ret)
Get a CPU interrupt's descriptor.
Each CPU interrupt has a descriptor describing the interrupt's capabilities and restrictions. This function gets the descriptor of a particular interrupt on a particular CPU.
Parameters:core_id -- [in] The core's ID

intr_num -- [in] Interrupt number

intr_desc_ret -- [out] The interrupt's descriptor

voidesp_cpu_intr_set_ivt_addr(constvoid*ivt_addr)
Set the base address of the current CPU's Interrupt Vector Table (IVT)
Parameters:ivt_addr -- Interrupt Vector Table's base address
boolesp_cpu_intr_has_handler(intintr_num)
Check if a particular interrupt already has a handler function.
Check if a particular interrupt on the current CPU already has a handler function assigned.
Note
This function simply checks if the IVT of the current CPU already has a handler assigned.

Parameters:intr_num -- Interrupt number (from 0 to 31)
Returns:True if the interrupt has a handler function, false otherwise.
voidesp_cpu_intr_set_handler(intintr_num, esp_cpu_intr_handler_thandler, void*handler_arg)
Set the handler function of a particular interrupt.
Assign a handler function (i.e., ISR) to a particular interrupt on the current CPU.
Note
This function simply sets the handler function (in the IVT) and does not actually enable the interrupt.

Parameters:intr_num -- Interrupt number (from 0 to 31)

handler -- Handler function

handler_arg -- Argument passed to the handler function

void*esp_cpu_intr_get_handler_arg(intintr_num)
Get a handler function's argument.
Get the argument of a previously assigned handler function on the current CPU.
Parameters:intr_num -- Interrupt number (from 0 to 31)
Returns:The argument passed to the handler function
voidesp_cpu_intr_enable(uint32_tintr_mask)
Enable particular interrupts on the current CPU.
Parameters:intr_mask -- Bit mask of the interrupts to enable
voidesp_cpu_intr_disable(uint32_tintr_mask)
Disable particular interrupts on the current CPU.
Parameters:intr_mask -- Bit mask of the interrupts to disable
uint32_tesp_cpu_intr_get_enabled_mask(void)
Get the enabled interrupts on the current CPU.
Returns:Bit mask of the enabled interrupts
voidesp_cpu_intr_edge_ack(intintr_num)
Acknowledge an edge interrupt.
Parameters:intr_num -- Interrupt number (from 0 to 31)
voidesp_cpu_configure_region_protection(void)
Configure the CPU to disable access to invalid memory regions.
esp_err_tesp_cpu_set_breakpoint(intbp_num, constvoid*bp_addr)
Set and enable a hardware breakpoint on the current CPU.
Note
This function is meant to be called by the panic handler to set a breakpoint for an attached debugger during a panic.

Note
Overwrites previously set breakpoint with same breakpoint number.

Parameters:bp_num -- Hardware breakpoint number [0..SOC_CPU_BREAKPOINTS_NUM - 1]

bp_addr -- Address to set a breakpoint on

Returns:ESP_OK if the breakpoint is set

ESP_ERR_INVALID_ARG if bp_num is out of range

ESP_ERR_INVALID_RESPONSE if setting the breakpoint via semihosting fails

esp_err_tesp_cpu_clear_breakpoint(intbp_num)
Clear a hardware breakpoint on the current CPU.
Note
Clears a breakpoint regardless of whether it was previously set

Parameters:bp_num -- Hardware breakpoint number [0..SOC_CPU_BREAKPOINTS_NUM - 1]
Returns:ESP_OK if the breakpoint is cleared

ESP_ERR_INVALID_ARG if bp_num is out of range

ESP_ERR_INVALID_RESPONSE if clearing the breakpoint via semihosting fails

esp_err_tesp_cpu_set_watchpoint(intwp_num, constvoid*wp_addr, size_tsize, esp_cpu_watchpoint_trigger_ttrigger)
Set and enable a hardware watchpoint on the current CPU.
Set and enable a hardware watchpoint on the current CPU, specifying the memory range and trigger operation. Watchpoints will break/panic the CPU when the CPU accesses (according to the trigger type) on a certain memory range.
Note
Overwrites previously set watchpoint with same watchpoint number. On RISC-V chips, this API uses method0(Exact matching) and method1(NAPOT matching) according to the riscv-debug-spec-0.13 specification for address matching. If the watch region size is 1byte, it uses exact matching (method 0). If the watch region size is larger than 1byte, it uses NAPOT matching (method 1). This mode requires the watching region start address to be aligned to the watching region size.

Parameters:wp_num -- Hardware watchpoint number [0..SOC_CPU_WATCHPOINTS_NUM - 1]

wp_addr -- Watchpoint's base address, must be naturally aligned to the size of the region

size -- Size of the region to watch. Must be one of 2^n and in the range of [1 ... SOC_CPU_WATCHPOINT_MAX_REGION_SIZE]

trigger -- Trigger type

Returns:ESP_OK if the watchpoint is set

ESP_ERR_INVALID_ARG if wp_num, wp_addr, or size is invalid

ESP_ERR_INVALID_RESPONSE if setting the watchpoint via semihosting fails

esp_err_tesp_cpu_clear_watchpoint(intwp_num)
Clear a hardware watchpoint on the current CPU.
Note
Clears a watchpoint regardless of whether it was previously set

Parameters:wp_num -- Hardware watchpoint number [0..SOC_CPU_WATCHPOINTS_NUM - 1]
Returns:ESP_OK if the watchpoint is cleared

ESP_ERR_INVALID_ARG if wp_num is out of range

ESP_ERR_INVALID_RESPONSE if clearing the watchpoint via semihosting fails

boolesp_cpu_dbgr_is_attached(void)
Check if the current CPU has a debugger attached.
Returns:True if debugger is attached, false otherwise
voidesp_cpu_dbgr_break(void)
Trigger a call to the current CPU's attached debugger.
intptr_tesp_cpu_get_call_addr(intptr_treturn_address)
Given the return address, calculate the address of the preceding call instruction This is typically used to answer the question "where was the function called from?".
Parameters:return_address -- The value of the return address register. Typically set to the value of __builtin_return_address(0).
Returns:Address of the call instruction preceding the return address.
boolesp_cpu_compare_and_set(volatileuint32_t*addr, uint32_tcompare_value, uint32_tnew_value)
Atomic compare-and-set operation.
Parameters:addr -- Address of atomic variable

compare_value -- Value to compare the atomic variable to

new_value -- New value to set the atomic variable to

Returns:Whether the atomic variable was set or not

Structures
structesp_cpu_intr_desc_t
CPU interrupt descriptor.
Each particular CPU interrupt has an associated descriptor describing that particular interrupt's characteristics. Call esp_cpu_intr_get_desc() to get the descriptors of a particular interrupt.
Public Members
intpriority
Priority of the interrupt if it has a fixed priority, (-1) if the priority is configurable.
esp_cpu_intr_type_ttype
Whether the interrupt is an edge or level type interrupt, ESP_CPU_INTR_TYPE_NA if the type is configurable.
uint32_tflags
Flags indicating extra details.

Macros
ESP_CPU_INTR_DESC_FLAG_SPECIAL
Interrupt descriptor flags of esp_cpu_intr_desc_t.
The interrupt is a special interrupt (e.g., a CPU timer interrupt)
ESP_CPU_INTR_DESC_FLAG_RESVD
The interrupt is reserved for internal use

Type Definitions
typedefuint32_tesp_cpu_cycle_count_t
CPU cycle count type.
This data type represents the CPU's clock cycle count
typedefvoid(*esp_cpu_intr_handler_t)(void*arg)
CPU interrupt handler type.

Enumerations
enumesp_cpu_intr_type_t
CPU interrupt type.
Values:
enumeratorESP_CPU_INTR_TYPE_LEVEL
enumeratorESP_CPU_INTR_TYPE_EDGE
enumeratorESP_CPU_INTR_TYPE_NA
enumesp_cpu_watchpoint_trigger_t
CPU watchpoint trigger type.
Values:
enumeratorESP_CPU_WATCHPOINT_LOAD
enumeratorESP_CPU_WATCHPOINT_STORE
enumeratorESP_CPU_WATCHPOINT_ACCESS

Header File
components/esp_system/include/esp_debug_helpers.h

This header file can be included with:

#include"esp_debug_helpers.h"

Functions
voidesp_set_breakpoint_if_jtag(void*fn)
If an OCD is connected over JTAG. set breakpoint 0 to the given function address. Do nothing otherwise.
Parameters:fn -- Pointer to the target breakpoint position
voidesp_backtrace_get_start(uint32_t*pc, uint32_t*sp, uint32_t*next_pc)
Get the first frame of the current stack's backtrace
Given the following function call flow (B -> A -> X -> esp_backtrace_get_start), this function will do the following.Flush CPU registers and window frames onto the current stack

Return PC and SP of function A (i.e. start of the stack's backtrace)

Return PC of function B (i.e. next_pc)

Note
This function is implemented in assembly

Parameters:pc -- [out] PC of the first frame in the backtrace

sp -- [out] SP of the first frame in the backtrace

next_pc -- [out] PC of the first frame's caller

boolesp_backtrace_get_next_frame(esp_backtrace_frame_t*frame)
Get the next frame on a stack for backtracing
Given a stack frame(i), this function will obtain the next stack frame(i-1) on the same call stack (i.e. the caller of frame(i)). This function is meant to be called iteratively when doing a backtrace.
Entry Conditions: Frame structure containing valid SP and next_pc Exit Conditions:Frame structure updated with SP and PC of frame(i-1). next_pc now points to frame(i-2).

If a next_pc of 0 is returned, it indicates that frame(i-1) is last frame on the stack

Parameters:frame -- [inout] Pointer to frame structure
Returns:True if the SP and PC of the next frame(i-1) are sane

False otherwise

esp_err_tesp_backtrace_print_from_frame(intdepth, constesp_backtrace_frame_t*frame, boolpanic)
Print the backtrace from specified frame.
Note
On the ESP32, users must call esp_backtrace_get_start() first to flush the stack.

Note
If a esp_backtrace_frame_t* frame is obtained though a call to esp_backtrace_get_start() from some example function func_a(), then frame is only valid within the frame/scope of func_a(). Users should not attempt to pass/use frame other frames within the same stack of different stacks.

Parameters:depth -- The maximum number of stack frames to print (should be > 0)

frame -- Starting frame to print from

panic -- Indicator if backtrace print is during a system panic

Returns:ESP_OK Backtrace successfully printed to completion or to depth limit

ESP_FAIL Backtrace is corrupted

esp_err_tesp_backtrace_print(intdepth)
Print the backtrace of the current stack.
Note
On RISC-V targets printing backtrace at run-time is only available if CONFIG_ESP_SYSTEM_USE_EH_FRAME is selected. Otherwise we simply print a register dump. Function assumes it is called in a context where the calling task will not migrate to another core, e.g. interrupts disabled/panic handler.

Parameters:depth -- The maximum number of stack frames to print (should be > 0)
Returns:ESP_OK Backtrace successfully printed to completion or to depth limit

ESP_FAIL Backtrace is corrupted

esp_err_tesp_backtrace_print_all_tasks(intdepth)
Print the backtrace of all tasks.
Note
Users must ensure that no tasks are created or deleted while this function is running.

Note
This function must be called from a task context.

Parameters:depth -- The maximum number of stack frames to print (must be > 0)
Returns:ESP_OK All backtraces successfully printed to completion or to depth limit

ESP_FAIL One or more backtraces are corrupt

staticinlineesp_err_tesp_set_watchpoint(intno, void*adr, intsize, intflags)
Set a watchpoint to break/panic when a certain memory range is accessed. Superseded by esp_cpu_set_watchpoint in esp_cpu.h.
staticinlinevoidesp_clear_watchpoint(intno)
Set a watchpoint to break/panic when a certain memory range is accessed. Superseded by esp_cpu_clear_watchpoint in esp_cpu.h.

Structures
structesp_backtrace_frame_t
Structure used for backtracing.
This structure stores the backtrace information of a particular stack frame (i.e. the PC and SP). This structure is used iteratively with the esp_cpu_get_next_backtrace_frame() function to traverse each frame within a single stack. The next_pc represents the PC of the current frame's caller, thus a next_pc of 0 indicates that the current frame is the last frame on the stack.
Note
Call esp_backtrace_get_start() to obtain initialization values for this structure.

Public Members
uint32_tpc
PC of the current frame
uint32_tsp
SP of the current frame
uint32_tnext_pc
PC of the current frame's caller
constvoid*exc_frame
Pointer to the full frame data structure, if applicable

Header File
components/esp_app_format/include/esp_app_desc.h

This header file can be included with:

#include"esp_app_desc.h"

This header file is a part of the API provided by the esp_app_format component. To declare that your component depends on esp_app_format, add the following to your CMakeLists.txt:

REQUIRES esp_app_format

or

PRIV_REQUIRES esp_app_format

Functions
constesp_app_desc_t*esp_app_get_description(void)
Return esp_app_desc structure. This structure includes app version.
Return description for running app.
Returns:Pointer to esp_app_desc structure.
intesp_app_get_elf_sha256(char*dst, size_tsize)
Fill the provided buffer with SHA256 of the ELF file, formatted as hexadecimal, null-terminated. If the buffer size is not sufficient to fit the entire SHA256 in hex plus a null terminator, the largest possible number of bytes will be written followed by a null.
Parameters:dst -- Destination buffer

size -- Size of the buffer

Returns:Number of bytes written to dst (including null terminator)
char*esp_app_get_elf_sha256_str(void)
Return SHA256 of the ELF file which is already formatted as hexadecimal, null-terminated included. Can be used in panic handler or core dump during when cache is disabled. The length is defined by CONFIG_APP_RETRIEVE_LEN_ELF_SHA option.
Returns:Hexadecimal SHA256 string

Structures
structesp_app_desc_t
Description about application.
Public Members
uint32_tmagic_word
Magic word ESP_APP_DESC_MAGIC_WORD
uint32_tsecure_version
Secure version
uint32_treserv1[2]
reserv1
charversion[32]
Application version
charproject_name[32]
Project name
chartime[16]
Compile time
chardate[16]
Compile date
charidf_ver[32]
Version IDF
uint8_tapp_elf_sha256[32]
sha256 of elf file
uint16_tmin_efuse_blk_rev_full
Minimal eFuse block revision supported by image, in format: major * 100 + minor
uint16_tmax_efuse_blk_rev_full
Maximal eFuse block revision supported by image, in format: major * 100 + minor
uint8_tmmu_page_size
MMU page size in log base 2 format
uint8_tspi_flash_mode
SPI flash mode as per CONFIG_ESPTOOLPY_FLASHMODE_VAL for compatibility check during OTA
uint8_treserv3[2]
reserv3
uint32_treserv2[18]
reserv2

Macros
ESP_APP_DESC_MAGIC_WORD
The magic word for the esp_app_desc structure that is in DROM.

Was this page helpful?

Thank you! We received your feedback.
If you have any comments, fill in Espressif Documentation Feedback Form.

We value your feedback.
Let us know how we can improve this page by filling in Espressif Documentation Feedback Form.