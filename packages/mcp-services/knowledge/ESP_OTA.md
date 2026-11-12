来源：https://docs.espressif.com/projects/esp-idf/zh_CN/v5.5.4/esp32/api-reference/system/ota.html

# 空中升级 (OTA)

## OTA 流程概览

OTA 升级机制可以让设备在固件正常运行时根据接收数据（如通过 Wi-Fi、蓝牙或以太网）进行自我更新。

以下模式支持对特定分区进行 OTA 更新：

- 安全更新模式：可靠、稳定的分区更新，即使在更新期间断电，芯片仍能正常运行，并能够启动当前的应用程序。以下分区支持此模式：

  - 应用程序分区。要进行 OTA 更新，需在设备的 分区表 中配置至少两个 OTA 应用程序分区槽（例如 `ota_0` 和 `ota_1`）以及一个 OTA 数据分区。OTA 操作函数会将新的应用程序固件镜像写入当前未被选为启动分区的 OTA 应用程序分区槽。镜像验证通过后，OTA 数据分区将被更新，以指定在下次启动时使用该镜像。

- 非安全更新模式：此更新过程容易受到干扰，如果在更新过程中断电，可能会导致当前应用程序无法加载，甚至进入无法恢复的状态。在此模式下，新的镜像会先下载到临时分区，下载完成后复制到最终的目标分区。如果在最终复制过程中发生中断，可能会导致问题。以下分区支持此模式：

  - 引导加载程序

  - 分区表

  - 其他数据分区，如 NVS、FAT 等

## OTA 数据分区

所有使用 OTA 功能项目，其 分区表 必须包含一个 OTA 数据分区（类型为 `data`，子类型为 `ota`）。

工厂启动设置下，OTA 数据分区中应没有数据（所有字节擦写成 0xFF）。如果分区表中有工厂应用程序，ESP-IDF 二级引导加载程序会启动工厂应用程序。如果分区表中没有工厂应用程序，则启动第一个可用的 OTA 分区（通常是 `ota_0`）。

第一次 OTA 升级后，OTA 数据分区更新，指定下一次启动哪个 OTA 应用程序分区。

OTA 数据分区的容量是 2 个 flash 扇区的大小（0x2000 字节），防止写入时电源故障引发问题。两个扇区单独擦除、写入匹配数据，若存在不一致，则用计数器字段判定哪个扇区为最新数据。

## 应用程序回滚

应用程序回滚的主要目的是确保设备在更新后正常工作。如果新版应用程序出现严重错误，该功能可使设备回滚到之前正常运行的应用版本。在使能回滚并且 OTA 升级应用程序至新版本后，可能出现的结果如下：

- 应用程序运行正常，`esp_ota_mark_app_valid_cancel_rollback()` 将正在运行的应用程序状态标记为 `ESP_OTA_IMG_VALID`，启动此应用程序无限制。

- 应用程序出现严重错误，无法继续工作，必须回滚到此前的版本，`esp_ota_mark_app_invalid_rollback_and_reboot()` 将正在运行的版本标记为 `ESP_OTA_IMG_INVALID` 然后复位。引导加载程序不会选取此版本，而是启动此前正常运行的版本。

- 如果 CONFIG_BOOTLOADER_APP_ROLLBACK_ENABLE 使能，则无需调用函数便可复位，回滚至之前的应用版本。

可使用以下代码检测 OTA 更新后应用程序的首次启动。首次启动时，应用程序会检查其状态并执行检测。如果检测成功，应用程序调用 `esp_ota_mark_app_valid_cancel_rollback()` 函数，确认应用运行成功。如果检测失败，应用程序调用 `esp_ota_mark_app_invalid_rollback_and_reboot()` 函数，回滚至之前的应用版本。

如果应用程序由于中止、重启或掉电无法启动或运行上述代码，引导加载程序在下一次启动尝试中会将该应用程序的状态标记为 `ESP_OTA_IMG_INVALID`，并回滚至之前的应用版本。

`
const esp_partition_t *running = esp_ota_get_running_partition();
esp_ota_img_states_t ota_state;
if (esp_ota_get_state_partition(running, &ota_state) == ESP_OK) {
    if (ota_state == ESP_OTA_IMG_PENDING_VERIFY) {
        // run diagnostic function ...
        bool diagnostic_is_ok = diagnostic();
        if (diagnostic_is_ok) {
            ESP_LOGI(TAG, "Diagnostics completed successfully! Continuing execution ...");
            esp_ota_mark_app_valid_cancel_rollback();
        } else {
            ESP_LOGE(TAG, "Diagnostics failed! Start rollback to the previous version ...");
            esp_ota_mark_app_invalid_rollback_and_reboot();
        }
    }
}
`

请查看 system/ota/native_ota_example 获取包含上述代码片段的完整示例。

备注

应用程序的状态不是写到程序的二进制镜像，而是写到 `otadata` 分区。该分区有一个 `ota_seq` 计数器，该计数器是 OTA 应用分区的指针，指向下次启动时选取应用所在的分区 (`ota_0`, `ota_1`, ...)。

### 应用程序 OTA 状态

状态控制了选取启动应用程序的过程：

| 状态 | 引导加载程序选取启动应用程序的限制 |
| --- | --- |
| ESP_OTA_IMG_VALID | 没有限制，可以选取。 |
| ESP_OTA_IMG_UNDEFINED | 没有限制，可以选取。 |
| ESP_OTA_IMG_INVALID | 不会选取。 |
| ESP_OTA_IMG_ABORTED | 不会选取。 |
| ESP_OTA_IMG_NEW | 如使能 CONFIG_BOOTLOADER_APP_ROLLBACK_ENABLE， 则仅会选取一次。在引导加载程序中，状态立即变为 `ESP_OTA_IMG_PENDING_VERIFY`。 |
| ESP_OTA_IMG_PENDING_VERIFY | 如使能 CONFIG_BOOTLOADER_APP_ROLLBACK_ENABLE， 则不会选取，状态变为 `ESP_OTA_IMG_ABORTED`。 |

如果 CONFIG_BOOTLOADER_APP_ROLLBACK_ENABLE 没有使能（默认情况），则 `esp_ota_mark_app_valid_cancel_rollback()` 和 `esp_ota_mark_app_invalid_rollback_and_reboot()` 为可选功能，`ESP_OTA_IMG_NEW` 和 `ESP_OTA_IMG_PENDING_VERIFY` 不会使用。

Kconfig 中的 CONFIG_BOOTLOADER_APP_ROLLBACK_ENABLE 可以帮助用户追踪新版应用程序的第一次启动。应用程序需调用 `esp_ota_mark_app_valid_cancel_rollback()` 函数确认可以运行，否则将会在重启时回滚至旧版本。该功能可让用户在启动阶段控制应用程序的可操作性。新版应用程序仅有一次机会尝试是否能成功启动。

### 回滚过程

CONFIG_BOOTLOADER_APP_ROLLBACK_ENABLE 使能时，回滚过程如下：

- 新版应用程序下载成功，`esp_ota_set_boot_partition()` 函数将分区设为可启动，状态设为 `ESP_OTA_IMG_NEW`。该状态表示应用程序为新版本，第一次启动需要监测。

- 重新启动 `esp_restart()`。

- 引导加载程序检查 `ESP_OTA_IMG_PENDING_VERIFY` 状态，如有设置，则将其写入 `ESP_OTA_IMG_ABORTED`。

- 引导加载程序选取一个新版应用程序来引导，这样应用程序状态就不会设置为 `ESP_OTA_IMG_INVALID` 或 `ESP_OTA_IMG_ABORTED`。

- 引导加载程序检查所选取的新版应用程序，若状态设置为 `ESP_OTA_IMG_NEW`，则写入 `ESP_OTA_IMG_PENDING_VERIFY`。该状态表示，需确认应用程序的可操作性，如不确认，发生重启，则状态会重写为 `ESP_OTA_IMG_ABORTED` （见上文），该应用程序不可再启动，将回滚至上一版本。

- 新版应用程序启动，应进行自测。

- 若通过自测，则必须调用函数 `esp_ota_mark_app_valid_cancel_rollback()`，因为新版应用程序在等待确认其可操作性（`ESP_OTA_IMG_PENDING_VERIFY` 状态）。

- 若未通过自测，则调用函数 `esp_ota_mark_app_invalid_rollback_and_reboot()`，回滚至之前能正常工作的应用程序版本，同时将无效的新版本应用程序设置为 `ESP_OTA_IMG_INVALID`。

- 如果新版应用程序可操作性没有确认，则状态一直为 `ESP_OTA_IMG_PENDING_VERIFY`。下一次启动时，状态变更为 `ESP_OTA_IMG_ABORTED`，阻止其再次启动，之后回滚到之前的版本。

### 意外复位

如果在新版应用第一次启动时发生断电或意外崩溃，则会回滚至之前正常运行的版本。

建议：尽快完成自测，防止因断电回滚。

只有 `OTA` 分区可以回滚。工厂分区不会回滚。

### 启动无效/中止的应用程序

用户可以启动此前设置为 `ESP_OTA_IMG_INVALID` 或 `ESP_OTA_IMG_ABORTED` 的应用程序：

- 获取最后一个无效应用分区 `esp_ota_get_last_invalid_partition()`。

- 将获取的分区传递给 `esp_ota_set_boot_partition()`，更新 `otadata`。

- 重启 `esp_restart()`。引导加载程序会启动指定应用程序。

要确定是否在应用程序启动时进行自测，可以调用 `esp_ota_get_state_partition()` 函数。如果结果为 `ESP_OTA_IMG_PENDING_VERIFY`，则需要自测，后续确认应用程序的可操作性。

### 如何设置状态

下文简单描述了如何设置应用程序状态：

- `ESP_OTA_IMG_VALID` 由函数 `esp_ota_mark_app_valid_cancel_rollback()` 设置。

- 如果 CONFIG_BOOTLOADER_APP_ROLLBACK_ENABLE 没有使能，`ESP_OTA_IMG_UNDEFINED` 由函数 `esp_ota_set_boot_partition()` 设置。

- 如果 CONFIG_BOOTLOADER_APP_ROLLBACK_ENABLE 使能，`ESP_OTA_IMG_NEW` 由函数 `esp_ota_set_boot_partition()` 设置。

- `ESP_OTA_IMG_INVALID` 由函数 `esp_ota_mark_app_invalid_rollback()` 或 `esp_ota_mark_app_invalid_rollback_and_reboot()` 设置。

- 如果应用程序的可操作性无法确认，发生重启（CONFIG_BOOTLOADER_APP_ROLLBACK_ENABLE 使能），则设置 `ESP_OTA_IMG_ABORTED`。

- 如果 CONFIG_BOOTLOADER_APP_ROLLBACK_ENABLE 使能，选取的应用程序状态为 `ESP_OTA_IMG_NEW`，则在引导加载程序中设置 `ESP_OTA_IMG_PENDING_VERIFY`。

## 防回滚

防回滚机制可以防止回滚到安全版本号低于芯片 eFuse 中烧录程序的应用程序版本。

设置 CONFIG_BOOTLOADER_APP_ANTI_ROLLBACK，启动防回滚机制。在引导加载程序中选取可启动的应用程序，会额外检查芯片和应用程序镜像的安全版本号。可启动固件中的应用安全版本号必须等于或高于芯片中的应用安全版本号。

CONFIG_BOOTLOADER_APP_ANTI_ROLLBACK 和 CONFIG_BOOTLOADER_APP_ROLLBACK_ENABLE 一起使用。此时，只有安全版本号等于或高于芯片中的应用安全版本号时才会回滚。

### 典型的防回滚机制

- 新发布的固件解决了此前版本的安全问题。

- 开发者在确保固件可以运行之后，增加安全版本号，发布固件。

- 下载新版应用程序。

- 运行函数 `esp_ota_set_boot_partition()`，将新版应用程序设为可启动。如果新版应用程序的安全版本号低于芯片中的应用安全版本号，新版应用程序会被擦除，无法更新到新固件。

- 重新启动。

- 在引导加载程序中选取安全版本号等于或高于芯片中应用安全版本号的应用程序。如果 otadata 处于初始阶段，通过串行通道加载了安全版本号高于芯片中应用安全版本号的固件，则引导加载程序中 eFuse 的安全版本号会立即更新。

- 新版应用程序启动，之后进行可操作性检测，如果通过检测，则调用函数 `esp_ota_mark_app_valid_cancel_rollback()`，将应用程序标记为 `ESP_OTA_IMG_VALID`，更新芯片中应用程序的安全版本号。注意，如果调用了函数 `esp_ota_mark_app_invalid_rollback()` 或 `esp_ota_mark_app_invalid_rollback_with_reboot()`，也可能会因为设备中没有可启动的应用程序而回滚失败，返回 `ESP_ERR_OTA_ROLLBACK_FAILED` 错误，应用程序状态一直处于 `ESP_OTA_IMG_PENDING_VERIFY` 状态。

- 如果运行的应用程序处于 `ESP_OTA_IMG_VALID` 状态，则可再次更新。

建议：

如果想避免因服务器应用程序的安全版本号低于运行的应用程序，造成不必要的下载和擦除，必须从镜像的第一个包中获取 `new_app_info.secure_version`，和 eFuse 的安全版本号比较。如果 `esp_efuse_check_secure_version(new_app_info.secure_version)` 函数为真，则下载继续，反之则中断。

`
....
bool image_header_was_checked = false;
while (1) {
    int data_read = esp_http_client_read(client, ota_write_data, BUFFSIZE);
    ...
    if (data_read > 0) {
        if (image_header_was_checked == false) {
            esp_app_desc_t new_app_info;
            if (data_read > sizeof(esp_image_header_t) + sizeof(esp_image_segment_header_t) + sizeof(esp_app_desc_t)) {
                // check current version with downloading
                if (esp_efuse_check_secure_version(new_app_info.secure_version) == false) {
                  ESP_LOGE(TAG, "This a new app can not be downloaded due to a secure version is lower than stored in efuse.");
                  http_cleanup(client);
                  task_fatal_error();
                }

                image_header_was_checked = true;

                esp_ota_begin(update_partition, OTA_SIZE_UNKNOWN, &update_handle);
            }
        }
        esp_ota_write( update_handle, (const void *)ota_write_data, data_read);
    }
}
...
`

限制：

- `secure_version` 字段最多有 32 位。也就是说，防回滚最多可以做 32 次。用户可以使用 CONFIG_BOOTLOADER_APP_SEC_VER_SIZE_EFUSE_FIELD 减少该 eFuse 字段的长度。

- 防回滚仅在 eFuse 编码机制设置为 `NONE` 时生效。

- 防回滚不支持工厂和测试分区，因此分区表中不应有设置为 `工厂` 或 `测试` 的分区。

`security_version`:

- 存储在应用程序镜像中的 `esp_app_desc` 里。版本号用 CONFIG_BOOTLOADER_APP_SECURE_VERSION 设置。

- ESP32 中版本号存储在 eFuse 的 `EFUSE_BLK3_RDATA4_REG` 里（若 eFuse 的位烧写为 1，则永远无法恢复为 0）。寄存器设置了多少位，应用程序的安全版本号就为多少。

## 没有安全启动的安全 OTA 升级

即便硬件安全启动没有使能，也可验证已签名的 OTA 升级。可通过设置 CONFIG_SECURE_SIGNED_APPS_NO_SECURE_BOOT 和 CONFIG_SECURE_SIGNED_ON_UPDATE_NO_SECURE_BOOT 实现。

具体可参考 在未启用硬件安全启动时验证已签名的应用程序。

## OTA 性能调优

- 在写操作时，与按默认机制逐块顺序擦除相比，一次性擦除更新分区可能有助于减少固件升级所需的时间。要启用此功能，请在 `esp_https_ota_config_t` 结构体中将 `esp_https_ota_config_t::bulk_flash_erase` 设置为 true。如果要擦除的分区过大，可能会触发任务看门狗。建议在这种情况下增加看门狗超时时间。

`
esp_https_ota_config_t ota_config = {
    .bulk_flash_erase = true,
}
`

- 调整 `esp_https_ota_config_t::http_config::buffer_size` 也有助于 OTA 性能调优。

- `esp_https_ota_config_t` 结构体中有一个成员 `esp_https_ota_config_t::buffer_caps`，可以用来指定在为 OTA 缓冲区分配内存时使用的内存类型。当启用 SPIRAM 时，将该值配置为 MALLOC_CAP_INTERNAL 可能有助于 OTA 性能调优。

- 请参阅 速度优化 中的 提高网络速度 小节获取详细信息。

## OTA 工具 `otatool.py`

`app_update` 组件中有 app_update/otatool.py 工具，用于在目标设备上完成下列 OTA 分区相关操作：

- 读取 otadata 分区 (read_otadata)

- 擦除 otadata 分区，将设备复位至工厂应用程序 (erase_otadata)

- 切换 OTA 分区 (switch_ota_partition)

- 擦除 OTA 分区 (erase_ota_partition)

- 写入 OTA 分区 (write_ota_partition)

- 读取 OTA 分区 (read_ota_partition)

用户若想通过编程方式完成相关操作，可从另一个 Python 脚本导入并使用该 OTA 工具，或者从 Shell 脚本调用该 OTA 工具。前者可使用工具的 Python API，后者可使用命令行界面。

### Python API

首先，确保已导入 `otatool` 模块。

`
import sys
import os

idf_path = os.environ["IDF_PATH"]  # 从环境中获取 IDF_PATH 的值
otatool_dir = os.path.join(idf_path, "components", "app_update")  # otatool.py 位于 $IDF_PATH/components/app_update 下

sys.path.append(otatool_dir)  # 使能 Python 寻找 otatool 模块
from otatool import *  # 导入 otatool 模块内的所有名称
`

要使用 OTA 工具的 Python API，第一步是创建 OtatoolTarget 对象：

`
# 创建 parttool.py 的目标设备，并将目标设备连接到串行端口 /dev/ttyUSB1
target = OtatoolTarget("/dev/ttyUSB1")
`

现在，可使用创建的 OtatoolTarget 在目标设备上完成操作：

`
# 擦除 otadata，将设备复位至工厂应用程序
target.erase_otadata()

# 擦除 OTA 应用程序分区 0
target.erase_ota_partition(0)

# 将启动分区切换至 OTA 应用程序分区 1
target.switch_ota_partition(1)

# 读取 OTA 分区 'ota_3'，将内容保存至文件 'ota_3.bin'
target.read_ota_partition("ota_3", "ota_3.bin")
`

要操作的 OTA 分区通过应用程序分区序号或分区名称指定。

更多关于 Python API 的信息，请查看 OTA 工具的代码注释。

### 命令行界面

`otatool.py` 的命令行界面具有如下结构体：

`
otatool.py [command-args] [subcommand] [subcommand-args]

- command-args - 执行主命令 (otatool.py) 所需的实际参数，多与目标设备有关
- subcommand - 要执行的操作
- subcommand-args - 所选操作的实际参数
`

`
# 擦除 otadata，将设备复位至工厂应用程序
otatool.py --port "/dev/ttyUSB1" erase_otadata

# 擦除 OTA 应用程序分区 0
otatool.py --port "/dev/ttyUSB1" erase_ota_partition --slot 0

# 将启动分区切换至 OTA 应用程序分区 1
otatool.py --port "/dev/ttyUSB1" switch_ota_partition --slot 1

# 读取 OTA 分区 'ota_3'，将内容保存至文件 'ota_3.bin'
otatool.py --port "/dev/ttyUSB1" read_ota_partition --name=ota_3 --output=ota_3.bin
`

更多信息可用 `--help` 指令查看：

`
# 显示可用的子命令和主命令描述
otatool.py --help

# 显示子命令的描述
otatool.py [subcommand] --help
`

## 相关文档

- 分区表

- 分区 API

- SPI flash API

- ESP HTTPS OTA 升级

## 应用示例

- system/ota/native_ota_example 演示了如何在 ESP32 上使用 app_update 组件的 API 进行原生空中升级 (OTA)。适用的 SoC 请参阅 system/ota/native_ota_example/README.md。

- system/ota/otatool 演示了如何使用 OTA 工具执行读取、写入和擦除 OTA 分区、切换启动分区以及切换到工厂分区等操作。详情请参阅 system/ota/otatool/README.md。

## API 参考

### Header File

- components/app_update/include/esp_ota_ops.h

- This header file can be included with:

`
#include "esp_ota_ops.h"
`

- This header file is a part of the API provided by the `app_update` component. To declare that your component depends on `app_update`, add the following to your CMakeLists.txt:

`
REQUIRES app_update
`

or

`
PRIV_REQUIRES app_update
`

### Functions

const esp_app_desc_t *esp_ota_get_app_description(void)

Return esp_app_desc structure. This structure includes app version.

Return description for running app.

备注

This API is present for backward compatibility reasons. Alternative function with the same functionality is `esp_app_get_description`

返回:

Pointer to esp_app_desc structure.

int esp_ota_get_app_elf_sha256(char *dst, size_t size)

Fill the provided buffer with SHA256 of the ELF file, formatted as hexadecimal, null-terminated. If the buffer size is not sufficient to fit the entire SHA256 in hex plus a null terminator, the largest possible number of bytes will be written followed by a null.

备注

This API is present for backward compatibility reasons. Alternative function with the same functionality is `esp_app_get_elf_sha256`

参数:

- dst -- Destination buffer

- size -- Size of the buffer

返回:

Number of bytes written to dst (including null terminator)

esp_err_t esp_ota_begin(const esp_partition_t *partition, size_t image_size, esp_ota_handle_t *out_handle)

Commence an OTA update writing to the specified partition.

The specified partition is erased to the specified image size.

If image size is not yet known, pass OTA_SIZE_UNKNOWN which will cause the entire partition to be erased.

On success, this function allocates memory that remains in use until esp_ota_end() is called with the returned handle.

Note: If the rollback option is enabled and the running application has the ESP_OTA_IMG_PENDING_VERIFY state then it will lead to the ESP_ERR_OTA_ROLLBACK_INVALID_STATE error. Confirm the running app before to run download a new app, use esp_ota_mark_app_valid_cancel_rollback() function for it (this should be done as early as possible when you first download a new application).

Note: Rollback is applicable only for app type partitions. Note: For Rollback - The OTA data slot corresponding to the last boot application partition will be invalidated.

参数:

- partition -- Pointer to info for partition which will receive the OTA update. Required. This is considered as the staging partition (where OTA is downloaded), be default this also considered as the final partition which supposed to be updated. The final partition can be overwritten using esp_ota_set_final_partition() after calling esp_ota_begin() to relocate contents to the final destination partition.

- image_size -- Size of new OTA app image. Partition will be erased in order to receive this size of image. If 0 or OTA_SIZE_UNKNOWN, the entire partition is erased.

- out_handle -- On success, returns a handle which should be used for subsequent esp_ota_write() and esp_ota_end() calls.

返回:

- ESP_OK: OTA operation commenced successfully.

- ESP_ERR_INVALID_ARG: partition or out_handle arguments were NULL, or partition doesn't point to an OTA app partition.

- ESP_ERR_NO_MEM: Cannot allocate memory for OTA operation.

- ESP_ERR_OTA_PARTITION_CONFLICT: Partition holds the currently running firmware, cannot update in place.

- ESP_ERR_NOT_FOUND: Partition argument not found in partition table.

- ESP_ERR_OTA_SELECT_INFO_INVALID: The OTA data partition contains invalid data.

- ESP_ERR_INVALID_SIZE: Partition doesn't fit in configured flash size.

- ESP_ERR_FLASH_OP_TIMEOUT or ESP_ERR_FLASH_OP_FAIL: Flash write failed.

- ESP_ERR_OTA_ROLLBACK_INVALID_STATE: If the running app has not confirmed state. Before performing an update, the application must be valid.

esp_err_t esp_ota_resume(const esp_partition_t *partition, const size_t erase_size, const size_t image_offset, esp_ota_handle_t *out_handle)

Resume an interrupted OTA update by continuing to write to the specified partition.

This function is used when an OTA update was previously started and needs to be resumed after an interruption. It continues the OTA process from the specified offset within the partition.

Unlike esp_ota_begin(), this function does not erase the partition which receives the OTA update, but rather expects that part of the image has already been written correctly, and it resumes writing from the given offset.

参数:

- partition -- Pointer to info for the partition which is receiving the OTA update. Required.

- erase_size -- Specifies how much flash memory to erase before resuming OTA, depending on whether a sequential write or a bulk erase is being used.

- image_offset -- Offset from where to resume the OTA process. Should be set to the number of bytes already written.

- out_handle -- On success, returns a handle that should be used for subsequent esp_ota_write() and esp_ota_end() calls.

返回:

- ESP_OK: OTA operation resumed successfully.

- ESP_ERR_INVALID_ARG: partition, out_handle were NULL or image_offset arguments is negative, or partition doesn't point to an OTA app partition.

- ESP_ERR_NO_MEM: Cannot allocate memory for OTA operation.

- ESP_ERR_OTA_PARTITION_CONFLICT: Partition holds the currently running firmware, cannot update in place.

- ESP_ERR_NOT_FOUND: Partition argument not found in partition table.

- ESP_ERR_OTA_SELECT_INFO_INVALID: The OTA data partition contains invalid data.

- ESP_ERR_INVALID_SIZE: Partition doesn't fit in configured flash size.

- ESP_ERR_FLASH_OP_TIMEOUT or ESP_ERR_FLASH_OP_FAIL: Flash write failed.

esp_err_t esp_ota_set_final_partition(esp_ota_handle_t handle, const esp_partition_t *final, bool finalize_with_copy)

Set the final destination partition for OTA update.

This function configures the specified final partition as the destination for the OTA update. It also allows setting a flag to indicate if the image should be copied from the staging partition to the final partition after the OTA update completes. Otherwise, copying will need to be handled by custom code using esp_partition_copy().

备注

This can be called after esp_ota_begin() and before the OTA update has started (before esp_ota_write()).

参数:

- handle -- OTA update handle obtained from esp_ota_begin().

- final -- Pointer to the final destination partition where the new image will be verified and potentially finalized. This partition must not be NULL.

- finalize_with_copy -- Boolean flag indicating if the downloaded image should be copied from the staging partition to the final partition upon completion. Set to False if you intend to perform the final copy process manually later.

返回:

- ESP_OK: final destination partition set successfully.

- ESP_ERR_INVALID_STATE: Once the OTA update has started, changing the final destination partition is prohibited.

- ESP_ERR_INVALID_ARG: Invalid arguments were passed (e.g., final partition is NULL).

- ESP_ERR_NOT_FOUND: OTA handle not found or final partition verification failed.

esp_err_t esp_ota_write(esp_ota_handle_t handle, const void *data, size_t size)

Write OTA update data to partition.

This function can be called multiple times as data is received during the OTA operation. Data is written sequentially to the partition.

参数:

- handle -- Handle obtained from esp_ota_begin

- data -- Data buffer to write

- size -- Size of data buffer in bytes.

返回:

- ESP_OK: Data was written to flash successfully, or size = 0

- ESP_ERR_INVALID_ARG: handle is invalid.

- ESP_ERR_OTA_VALIDATE_FAILED: First byte of image contains invalid image magic byte.

- ESP_ERR_FLASH_OP_TIMEOUT or ESP_ERR_FLASH_OP_FAIL: Flash write failed.

- ESP_ERR_INVALID_SIZE: if write would go out of bounds of the partition

- or one of error codes from lower-level flash driver.

esp_err_t esp_ota_write_with_offset(esp_ota_handle_t handle, const void *data, size_t size, uint32_t offset)

Write OTA update data to partition at an offset.

This function can write data in non-contiguous manner. If flash encryption is enabled, data should be 16 bytes aligned.

备注

While performing OTA, if the packets arrive out of order, esp_ota_write_with_offset() can be used to write data in non-contiguous manner. Use of esp_ota_write_with_offset() in combination with esp_ota_write() is not recommended.

参数:

- handle -- Handle obtained from esp_ota_begin

- data -- Data buffer to write

- size -- Size of data buffer in bytes

- offset -- Offset in flash partition

返回:

- ESP_OK: Data was written to flash successfully.

- ESP_ERR_INVALID_ARG: handle is invalid.

- ESP_ERR_FLASH_OP_TIMEOUT or ESP_ERR_FLASH_OP_FAIL: Flash write failed.

esp_err_t esp_ota_end(esp_ota_handle_t handle)

Finish OTA update and validate newly written app image.

If the finalize_with_copy option is set, the staging partition will be copied to the final partition at the end of this function. Otherwise, copying will need to be handled by custom code using esp_partition_copy().

备注

After calling esp_ota_end(), the handle is no longer valid and any memory associated with it is freed (regardless of result).

备注

If either the final or staging partitions were for the bootloader, then at the end of this function, the bootloader is reset to its default offset: esp_image_bootloader_offset_set(ESP_PRIMARY_BOOTLOADER_OFFSET)

参数:

handle -- Handle obtained from esp_ota_begin().

返回:

- ESP_OK: Newly written OTA app image is valid.

- ESP_ERR_NOT_FOUND: OTA handle was not found.

- ESP_ERR_INVALID_ARG: Handle was never written to.

- ESP_ERR_OTA_VALIDATE_FAILED: OTA image is invalid (either not a valid app image, or - if secure boot is enabled - signature failed to verify.)

- ESP_ERR_INVALID_STATE: If flash encryption is enabled, this result indicates an internal error writing the final encrypted bytes to flash.

esp_err_t esp_ota_abort(esp_ota_handle_t handle)

Abort OTA update, free the handle and memory associated with it.

参数:

handle -- obtained from esp_ota_begin().

返回:

- ESP_OK: Handle and its associated memory is freed successfully.

- ESP_ERR_NOT_FOUND: OTA handle was not found.

esp_err_t esp_ota_set_boot_partition(const esp_partition_t *partition)

Configure OTA data for a new boot partition.

备注

If this function returns ESP_OK, calling esp_restart() will boot the newly configured app partition.

参数:

partition -- Pointer to info for partition containing app image to boot.

返回:

- ESP_OK: OTA data updated, next reboot will use specified partition.

- ESP_ERR_INVALID_ARG: partition argument was NULL or didn't point to a valid OTA partition of type "app".

- ESP_ERR_OTA_VALIDATE_FAILED: Partition contained invalid app image. Also returned if secure boot is enabled and signature validation failed.

- ESP_ERR_NOT_FOUND: OTA data partition not found.

- ESP_ERR_FLASH_OP_TIMEOUT or ESP_ERR_FLASH_OP_FAIL: Flash erase or write failed.

const esp_partition_t *esp_ota_get_boot_partition(void)

Get partition info of currently configured boot app.

If esp_ota_set_boot_partition() has been called, the partition which was set by that function will be returned.

If esp_ota_set_boot_partition() has not been called, the result is usually the same as esp_ota_get_running_partition(). The two results are not equal if the configured boot partition does not contain a valid app (meaning that the running partition will be an app that the bootloader chose via fallback).

If the OTA data partition is not present or not valid then the result is the first app partition found in the partition table. In priority order, this means: the factory app, the first OTA app slot, or the test app partition.

Note that there is no guarantee the returned partition is a valid app. Use esp_image_verify(ESP_IMAGE_VERIFY, ...) to verify if the returned partition contains a bootable image.

返回:

Pointer to info for partition structure, or NULL if partition table is invalid or a flash read operation failed. Any returned pointer is valid for the lifetime of the application.

const esp_partition_t *esp_ota_get_running_partition(void)

Get partition info of currently running app.

This function is different to esp_ota_get_boot_partition() in that it ignores any change of selected boot partition caused by esp_ota_set_boot_partition(). Only the app whose code is currently running will have its partition information returned.

The partition returned by this function may also differ from esp_ota_get_boot_partition() if the configured boot partition is somehow invalid, and the bootloader fell back to a different app partition at boot.

返回:

Pointer to info for partition structure, or NULL if no partition is found or flash read operation failed. Returned pointer is valid for the lifetime of the application.

const esp_partition_t *esp_ota_get_next_update_partition(const esp_partition_t *start_from)

Return the next OTA app partition which should be written with a new firmware.

Call this function to find an OTA app partition which can be passed to esp_ota_begin().

Finds next partition round-robin, starting from the current running partition.

参数:

start_from -- If set, treat this partition info as describing the current running partition. Can be NULL, in which case esp_ota_get_running_partition() is used to find the currently running partition. The result of this function is never the same as this argument.

返回:

Pointer to info for partition which should be updated next. NULL result indicates invalid OTA data partition, or that no eligible OTA app slot partition was found.

esp_err_t esp_ota_get_partition_description(const esp_partition_t *partition, esp_app_desc_t *app_desc)

Returns esp_app_desc structure for app partition. This structure includes app version.

Returns a description for the requested app partition.

参数:

- partition -- [in] Pointer to app partition. (only app partition)

- app_desc -- [out] Structure of info about app.

返回:

- ESP_OK Successful.

- ESP_ERR_NOT_FOUND app_desc structure is not found. Magic word is incorrect.

- ESP_ERR_NOT_SUPPORTED Partition is not application.

- ESP_ERR_INVALID_ARG Arguments is NULL or if partition's offset exceeds partition size.

- ESP_ERR_INVALID_SIZE Read would go out of bounds of the partition.

- or one of error codes from lower-level flash driver.

esp_err_t esp_ota_get_bootloader_description(const esp_partition_t *bootloader_partition, esp_bootloader_desc_t *desc)

Returns the description structure of the bootloader.

参数:

- bootloader_partition -- [in] Pointer to bootloader partition. If NULL, then the PRIMARY bootloader is used (the default location). offset = CONFIG_BOOTLOADER_OFFSET_IN_FLASH, size = CONFIG_PARTITION_TABLE_OFFSET - CONFIG_BOOTLOADER_OFFSET_IN_FLASH,

- desc -- [out] Structure of info about bootloader.

返回:

- ESP_OK Successful.

- ESP_ERR_NOT_FOUND Description structure is not found in the bootloader image. Magic byte is incorrect.

- ESP_ERR_INVALID_ARG Arguments is NULL.

- ESP_ERR_INVALID_SIZE Read would go out of bounds of the partition.

- or one of error codes from lower-level flash driver.

esp_err_t esp_ota_invalidate_inactive_ota_data_slot(void)

Invalidate the OTA data slot associated with the last boot application partition.

This function erases the OTA data slot corresponding to the last boot application partition, making the partition invalid for booting in future. The application partition itself is not erased, preserving its contents.

返回:

- ESP_OK: Successfully invalidated the OTA data slot.

- ESP_FAIL: Failed to invalidate the OTA data slot (e.g., invalid parameters, no OTA data partition, or other errors).

- Other error codes from `esp_partition_erase_range`.

uint8_t esp_ota_get_app_partition_count(void)

Returns number of ota partitions provided in partition table.

返回:

- Number of OTA partitions

esp_err_t esp_ota_mark_app_valid_cancel_rollback(void)

This function is called to indicate that the running app is working well.

返回:

- ESP_OK: if successful.

esp_err_t esp_ota_mark_app_invalid_rollback(void)

This function is called to roll back to the previously workable app without reboot.

Checks applications on a flash drive that can be booted in case of rollback. If the flash does not have at least one app (except the running app) then rollback is not possible.

返回:

- ESP_OK: if successful.

- ESP_FAIL: if not successful.

- ESP_ERR_OTA_ROLLBACK_FAILED: The rollback is not possible because the available OTA partitions on the flash do not contain a valid application.

esp_err_t esp_ota_mark_app_invalid_rollback_and_reboot(void)

This function is called to roll back to the previously workable app with reboot.

Equivalent to calling esp_ota_mark_app_invalid_rollback(), and, if successful, followed by esp_restart().

返回:

- ESP_FAIL: if not successful.

- ESP_ERR_OTA_ROLLBACK_FAILED: The rollback is not possible due to flash does not have any apps.

const esp_partition_t *esp_ota_get_last_invalid_partition(void)

Returns last partition with invalid state (ESP_OTA_IMG_INVALID or ESP_OTA_IMG_ABORTED).

返回:

partition.

esp_err_t esp_ota_get_state_partition(const esp_partition_t *partition, esp_ota_img_states_t *ota_state)

Returns state for given partition.

参数:

- partition -- [in] Pointer to partition.

- ota_state -- [out] state of partition (if this partition has a record in otadata).

返回:

- ESP_OK: Successful.

- ESP_ERR_INVALID_ARG: partition or ota_state arguments were NULL.

- ESP_ERR_NOT_SUPPORTED: partition is not ota.

- ESP_ERR_NOT_FOUND: Partition table does not have otadata or state was not found for given partition.

esp_err_t esp_ota_erase_last_boot_app_partition(void)

Erase previous boot app partition and corresponding otadata select for this partition.

When current app is marked to as valid then you can erase previous app partition.

返回:

- ESP_OK: Successful, otherwise ESP_ERR.

bool esp_ota_check_rollback_is_possible(void)

Checks applications on the slots which can be booted in case of rollback.

These applications should be valid (marked in otadata as not UNDEFINED, INVALID or ABORTED and crc is good) and be able booted, and secure_version of app >= secure_version of efuse (if anti-rollback is enabled).

返回:

- True: Returns true if the slots have at least one app (except the running app).

- False: The rollback is not possible.

### Macros

OTA_SIZE_UNKNOWN

Used for esp_ota_begin() if new image size is unknown

OTA_WITH_SEQUENTIAL_WRITES

Used for esp_ota_begin() if new image size is unknown and erase can be done in incremental manner (assuming write operation is in continuous sequence)

ESP_ERR_OTA_BASE

Base error code for ota_ops api

ESP_ERR_OTA_PARTITION_CONFLICT

Error if request was to write or erase the current running partition

ESP_ERR_OTA_SELECT_INFO_INVALID

Error if OTA data partition contains invalid content

ESP_ERR_OTA_VALIDATE_FAILED

Error if OTA app image is invalid

ESP_ERR_OTA_SMALL_SEC_VER

Error if the firmware has a secure version less than the running firmware.

ESP_ERR_OTA_ROLLBACK_FAILED

Error if flash does not have valid firmware in passive partition and hence rollback is not possible

ESP_ERR_OTA_ROLLBACK_INVALID_STATE

Error if current active firmware is still marked in pending validation state (ESP_OTA_IMG_PENDING_VERIFY), essentially first boot of firmware image post upgrade and hence firmware upgrade is not possible

### Type Definitions

typedef uint32_t esp_ota_handle_t

Opaque handle for an application OTA update.

esp_ota_begin() returns a handle which is then used for subsequent calls to esp_ota_write() and esp_ota_end().

## OTA 升级失败排查

OTA 升级失败时如何排查（点击放大）

此文档对您有帮助吗？

- 反馈已收到，谢谢！

- 如果您有其他意见，欢迎填写乐鑫文档反馈表。

- 我们重视您的反馈。

- 您可以填写乐鑫文档反馈表告诉我们如何改进该文档。
