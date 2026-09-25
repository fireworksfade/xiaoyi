Source: https://docs.espressif.com/projects/esp-idf/zh_CN/latest/esp32/api-reference/system/esp_https_ota.html

API 参考

系统 API

ESP HTTPS OTA 升级

在 GitHub 上编辑

ESP HTTPS OTA 升级

[English]

概述

esp_https_ota 是现有 OTA（空中升级）API 的抽象层，其中提供了简化的 API，能够通过 HTTPS 升级固件。

esp_err_tdo_firmware_upgrade(){esp_http_client_config_tconfig={.url=CONFIG_FIRMWARE_UPGRADE_URL,.cert_pem=(char*)server_cert_pem_start,};esp_https_ota_config_tota_config={.http_config=&config,};esp_err_tret=esp_https_ota(&ota_config);if(ret==ESP_OK){esp_restart();}else{returnESP_FAIL;}returnESP_OK;}

服务器验证

验证服务器时，应将 PEM 格式的根证书提供给 esp_http_client_config_t::cert_pem 成员。如需了解有关服务器验证的更多信息，请参阅 TLS 服务器验证 。

备注

应使用服务器端点的 根 证书应用于验证，而不能使用证书链中的任何中间证书，因为根证书有效期最长，且通常长时间维持不变。用户还可以通过 esp_http_client_config_t::crt_bundle_attach 成员使用 ESP x509 证书包 功能进行验证，其中涵盖了大多数受信任的根证书。

通过 HTTPS 分段下载镜像

要使用分段镜像下载功能，需要：

启用组件级配置 ：在 menuconfig 中启用 CONFIG_ESP_HTTPS_OTA_ENABLE_PARTIAL_DOWNLOAD in menuconfig ( Component config → ESP HTTPS OTA → Enable partial HTTP download for OTA )

在应用程序中启用该功能 ：在 esp_https_ota_config_t 配置结构中设置 partial_http_download 字段

启用该配置后，固件镜像将通过多个指定大小的 HTTP 请求进行下载。通过将 max_http_request_size 设置为所需值，即可指定每个请求的最大内容长度。

在从 AWS S3 等服务获取镜像时，这一选项非常有用。在启用该选项时，可以将 mbedTLS Rx 的 buffer 大小（即 CONFIG_MBEDTLS_SSL_IN_CONTENT_LEN ）设置为较小的值。不启用此配置时，无法将其设置为较小值。

mbedTLS Rx buffer 的默认大小为 16 KB，但如果将 partial_http_download 的 max_http_request_size 设置为 4 KB，便能将 mbedTLS Rx 的 buffer 减小到 4 KB。使用这一配置方式预计可以节省约 12 KB 内存。

备注

如果服务器使用分块传输编码，则无法进行部分下载，因为无法预先获知总内容长度。

OTA 恢复

在 esp_https_ota_config_t 中启用 ota_resumption 配置，即可使用 OTA 恢复功能。启用此功能后，先前失败的 OTA 镜像下载便可以从中断处继续，无需重新开始整个 OTA 过程。此功能是基于 HTTP 的部分范围请求功能实现的。

要指定镜像下载的续传位置，需要在 esp_https_ota_config_t 中设置 ota_image_bytes_written 字段。此字段的值表示在上一次尝试过程中已写入到 OTA 分区的字节数。

如需了解更多，请参阅示例： system/ota/advanced_https_ota ，该示例演示了 OTA 恢复功能。在此示例中， OTA 的中断状态保存在 NVS 中，从而使 OTA 过程能够从上次保存的状态中无缝恢复，并继续下载。

签名验证

要进一步提升安全性，还可以验证 OTA 固件镜像的签名。更多内容请参考 没有安全启动的安全 OTA 升级 。

使用预加密固件进行 OTA 升级

预加密固件完全独立于 flash 加密 方案，主要原因如下：

flash 加密方案推荐各个设备使用在内部生成的唯一加密密钥，因此在 OTA 更新服务器上预加密固件并不可行。

flash 加密方案依赖 flash 偏移，会基于不同的 flash 偏移量生成不同的密文，因此根据分区槽（如 ota_0 、 ota_1 等）来管理不同的 OTA 更新镜像较为困难。

即使设备未启用 flash 加密，仍可能要求进行 OTA 的固件镜像保持加密。

无论底层传输安全性如何，预加密固件的分发都能确保固件镜像在从服务器到设备的 传输过程中 保持加密状态。首先，预加密软件层在设备上通过网络接收并解密固件，然后使用平台 flash 加密（如果已启用）重新加密内容，最后写入 flash。

设计

预加密固件是一种 传输安全方案 ，用于确保固件镜像在从 OTA 服务器传输到设备的过程中始终处于加密状态（与底层传输安全无关）。这种方案与 flash 加密 在多个关键方面有所不同：

密钥管理 ：使用外部管理的加密密钥，而不是每个设备内部生成的唯一密钥

独立于 flash 偏移 ：无论固件烧录在哪个 flash 分区（ ota_0 、 ota_1 等），生成的密文内容一致

传输保护 ：在固件传输过程中提供加密保护，不涉及设备本地存储安全

重要安全提示 ：预加密固件本身不提供设备级安全保护。固件被接收后在设备上解密，并按设备的 flash 加密配置存储。如需设备级安全措施，需另外启用 flash 加密功能。

该功能由 esp_encrypted_img 组件实现，该组件通过解密回调 ( esp_https_ota_config_t::decrypt_cb ) 机制集成在 OTA 更新框架中。

有关镜像格式、密钥生成及实现细节的详细信息，请参阅 esp_encrypted_img 组件文档 。

OTA 系统事件

ESP HTTPS OTA 过程中可能发生各种系统事件。当特定事件发生时，会由 事件循环库 触发处理程序。此处理程序必须使用 esp_event_handler_register() 注册。这有助于 ESP HTTPS OTA 进行事件处理。

esp_https_ota_event_t 中包含了使用 ESP HTTPS OTA 升级时可能发生的所有事件。

事件处理程序示例

/* 用于捕获系统事件的事件处理程序 */staticvoidevent_handler(void*arg,esp_event_base_tevent_base,int32_tevent_id,void*event_data){if(event_base==ESP_HTTPS_OTA_EVENT){switch(event_id){caseESP_HTTPS_OTA_START:ESP_LOGI(TAG,"OTA started");break;caseESP_HTTPS_OTA_CONNECTED:ESP_LOGI(TAG,"Connected to server");break;caseESP_HTTPS_OTA_GET_IMG_DESC:ESP_LOGI(TAG,"Reading Image Description");break;caseESP_HTTPS_OTA_VERIFY_CHIP_ID:ESP_LOGI(TAG,"Verifying chip id of new image: %d",*(esp_chip_id_t*)event_data);break;caseESP_HTTPS_OTA_VERIFY_CHIP_REVISION:ESP_LOGI(TAG,"Verifying chip revision of new image: %d",*(uint16_t*)event_data);break;caseESP_HTTPS_OTA_DECRYPT_CB:ESP_LOGI(TAG,"Callback to decrypt function");break;caseESP_HTTPS_OTA_WRITE_FLASH:ESP_LOGD(TAG,"Writing to flash: %d written",*(int*)event_data);break;caseESP_HTTPS_OTA_UPDATE_BOOT_PARTITION:ESP_LOGI(TAG,"Boot partition updated. Next Partition: %d",*(esp_partition_subtype_t*)event_data);break;caseESP_HTTPS_OTA_FINISH:ESP_LOGI(TAG,"OTA finish");break;caseESP_HTTPS_OTA_ABORT:ESP_LOGI(TAG,"OTA abort");break;}}}

系统事件循环中，不同 ESP HTTPS OTA 事件的预期数据类型如下所示：

ESP_HTTPS_OTA_START : NULL

ESP_HTTPS_OTA_CONNECTED : NULL

ESP_HTTPS_OTA_GET_IMG_DESC : NULL

ESP_HTTPS_OTA_VERIFY_CHIP_ID : esp_chip_id_t

ESP_HTTPS_OTA_VERIFY_CHIP_REVISION : uint16_t

ESP_HTTPS_OTA_DECRYPT_CB : NULL

ESP_HTTPS_OTA_WRITE_FLASH : int

ESP_HTTPS_OTA_UPDATE_BOOT_PARTITION : esp_partition_subtype_t

ESP_HTTPS_OTA_FINISH : NULL

ESP_HTTPS_OTA_ABORT : NULL

应用示例

system/ota/advanced_https_ota 演示了如何在 ESP32 上使用 esp_https_ota 组件的 API 来使用 HTTPS OTA 更新功能。关于该示例适用的芯片，请参考 system/ota/advanced_https_ota/README.md 。

system/ota/partitions_ota 演示了如何使用 esp_https_ota 组件的 API 对多个分区（应用、引导加载程序、分区表、存储）进行 OTA 更新。

system/ota/simple_ota_example 演示了如何使用 esp_https_ota 组件的 API，通过特定的网络接口，如以太网或 Wi-Fi Station，在 ESP32 上进行固件升级。关于该示例适用的芯片，请参考 system/ota/simple_ota_example/README.md 。

API 参考

Header File

components/esp_https_ota/include/esp_https_ota.h

This header file can be included with:

#include"esp_https_ota.h"

This header file is a part of the API provided by the esp_https_ota component. To declare that your component depends on esp_https_ota , add the following to your CMakeLists.txt:

REQUIRES esp_https_ota

or

PRIV_REQUIRES esp_https_ota

Functions

esp_err_t esp_https_ota ( const esp_https_ota_config_t * ota_config )

HTTPS OTA Firmware upgrade.

This function allocates HTTPS OTA Firmware upgrade context, establishes HTTPS connection, reads image data from HTTP stream and writes it to OTA partition and finishes HTTPS OTA Firmware upgrade operation. This API supports URL redirection, but if CA cert of URLs differ then it should be appended to cert_pem member of ota_config->http_config .

备注

This API handles the entire OTA operation, so if this API is being used then no other APIs from esp_https_ota component should be called. If more information and control is needed during the HTTPS OTA process, then one can use esp_https_ota_begin and subsequent APIs. If this API returns successfully, esp_restart() must be called to boot from the new firmware image.

参数 :

ota_config -- [in] pointer to esp_https_ota_config_t structure.

返回 :

ESP_OK: OTA data updated, next reboot will use specified partition.

ESP_FAIL: For generic failure.

ESP_ERR_INVALID_ARG: Invalid argument

ESP_ERR_OTA_VALIDATE_FAILED: Invalid app image

ESP_ERR_NO_MEM: Cannot allocate memory for OTA operation.

ESP_ERR_FLASH_OP_TIMEOUT or ESP_ERR_FLASH_OP_FAIL: Flash write failed.

ESP_ERR_HTTP_NOT_MODIFIED: OTA image is not modified on server side

For other return codes, refer OTA documentation in esp-idf's app_update component.

esp_err_t esp_https_ota_begin ( const esp_https_ota_config_t * ota_config , esp_https_ota_handle_t * handle )

Start HTTPS OTA Firmware upgrade.

This function initializes ESP HTTPS OTA context and establishes HTTPS connection. This function must be invoked first. If this function returns successfully, then esp_https_ota_perform should be called to continue with the OTA process and there should be a call to esp_https_ota_finish on completion of OTA operation or on failure in subsequent operations. This API supports URL redirection, but if CA cert of URLs differ then it should be appended to cert_pem member of http_config , which is a part of ota_config . In case of error, this API explicitly sets handle to NULL.

备注

This API is blocking, so setting is_async member of http_config structure will result in an error.

参数 :

ota_config -- [in] pointer to esp_https_ota_config_t structure

handle -- [out] pointer to an allocated data of type esp_https_ota_handle_t which will be initialised in this function

返回 :

ESP_OK: HTTPS OTA Firmware upgrade context initialised and HTTPS connection established

ESP_FAIL: For generic failure.

ESP_ERR_INVALID_ARG: Invalid argument (missing/incorrect config, certificate, etc.)

ESP_ERR_HTTP_NOT_MODIFIED: OTA image is not modified on server side

For other return codes, refer documentation in app_update component and esp_http_client component in esp-idf.

esp_err_t esp_https_ota_perform ( esp_https_ota_handle_t https_ota_handle )

Read image data from HTTP stream and write it to OTA partition.

This function reads image data from HTTP stream and writes it to OTA partition. This function must be called only if esp_https_ota_begin() returns successfully. This function must be called in a loop since it returns after every HTTP read operation thus giving you the flexibility to stop OTA operation midway.

参数 :

https_ota_handle -- [in] pointer to esp_https_ota_handle_t structure

返回 :

ESP_ERR_HTTPS_OTA_IN_PROGRESS: OTA update is in progress, call this API again to continue.

ESP_OK: OTA update was successful

ESP_FAIL: OTA update failed

ESP_ERR_INVALID_ARG: Invalid argument

ESP_ERR_INVALID_VERSION: Invalid chip revision in image header

ESP_ERR_OTA_VALIDATE_FAILED: Invalid app image

ESP_ERR_NO_MEM: Cannot allocate memory for OTA operation.

ESP_ERR_FLASH_OP_TIMEOUT or ESP_ERR_FLASH_OP_FAIL: Flash write failed.

For other return codes, refer OTA documentation in esp-idf's app_update component.

bool esp_https_ota_is_complete_data_received ( esp_https_ota_handle_t https_ota_handle )

Checks if complete data was received or not.

备注

This API can be called just before esp_https_ota_finish() to validate if the complete image was indeed received.

参数 :

https_ota_handle -- [in] pointer to esp_https_ota_handle_t structure

返回 :

false

true

esp_err_t esp_https_ota_finish ( esp_https_ota_handle_t https_ota_handle )

Clean-up HTTPS OTA Firmware upgrade and close HTTPS connection.

This function closes the HTTP connection and frees the ESP HTTPS OTA context. This function switches the boot partition to the OTA partition containing the new firmware image.

备注

If this API returns successfully, esp_restart() must be called to boot from the new firmware image esp_https_ota_finish should not be called after calling esp_https_ota_abort

参数 :

https_ota_handle -- [in] pointer to esp_https_ota_handle_t structure

返回 :

ESP_OK: Clean-up successful

ESP_ERR_INVALID_STATE

ESP_ERR_INVALID_ARG: Invalid argument

ESP_ERR_OTA_VALIDATE_FAILED: Invalid app image

esp_err_t esp_https_ota_abort ( esp_https_ota_handle_t https_ota_handle )

Clean-up HTTPS OTA Firmware upgrade and close HTTPS connection.

This function closes the HTTP connection and frees the ESP HTTPS OTA context.

备注

esp_https_ota_abort should not be called after calling esp_https_ota_finish

参数 :

https_ota_handle -- [in] pointer to esp_https_ota_handle_t structure

返回 :

ESP_OK: Clean-up successful

ESP_ERR_INVALID_STATE: Invalid ESP HTTPS OTA state

ESP_FAIL: OTA not started

ESP_ERR_NOT_FOUND: OTA handle not found

ESP_ERR_INVALID_ARG: Invalid argument

esp_err_t esp_https_ota_get_img_desc ( esp_https_ota_handle_t https_ota_handle , esp_app_desc_t * new_app_info )

Reads app description from image header. The app description provides information like the "Firmware version" of the image.

备注

This API can be called only after esp_https_ota_begin() and before esp_https_ota_perform(). Calling this API is not mandatory.

参数 :

https_ota_handle -- [in] pointer to esp_https_ota_handle_t structure

new_app_info -- [out] pointer to an allocated esp_app_desc_t structure

返回 :

ESP_ERR_INVALID_ARG: Invalid arguments

ESP_ERR_INVALID_STATE: Invalid state to call this API. esp_https_ota_begin() not called yet.

ESP_FAIL: Failed to read image descriptor

ESP_OK: Successfully read image descriptor

esp_err_t esp_https_ota_get_bootloader_img_desc ( esp_https_ota_handle_t https_ota_handle , esp_bootloader_desc_t * new_img_info )

Reads bootloader description from image header. The bootloader description provides information like the "Bootloader version" of the image.

备注

This API can be called only after esp_https_ota_begin() and before esp_https_ota_perform(). Calling this API is not mandatory.

参数 :

https_ota_handle -- [in] pointer to esp_https_ota_handle_t structure

new_img_info -- [out] pointer to an allocated esp_bootloader_desc_t structure

返回 :

ESP_ERR_INVALID_ARG: Invalid arguments

ESP_ERR_INVALID_STATE: Invalid state to call this API. esp_https_ota_begin() not called yet.

ESP_FAIL: Failed to read image descriptor

ESP_OK: Successfully read image descriptor

int esp_https_ota_get_image_len_read ( esp_https_ota_handle_t https_ota_handle )

This function returns OTA image data read so far.

备注

This API should be called only if esp_https_ota_perform() has been called at least once or if esp_https_ota_get_img_desc has been called before.

参数 :

https_ota_handle -- [in] pointer to esp_https_ota_handle_t structure

返回 :

-1 On failure

total bytes read so far

int esp_https_ota_get_status_code ( esp_https_ota_handle_t https_ota_handle )

This function returns the HTTP status code of the last HTTP response.

备注

This API should be called only after esp_https_ota_begin() has been called. This can be used to check the HTTP status code of the OTA download process.

参数 :

https_ota_handle -- [in] pointer to esp_https_ota_handle_t structure

返回 :

-1 On failure

HTTP status code

int esp_https_ota_get_image_size ( esp_https_ota_handle_t https_ota_handle )

This function returns OTA image total size.

备注

This API should be called after esp_https_ota_begin() has been already called. This can be used to create some sort of progress indication (in combination with esp_https_ota_get_image_len_read())

参数 :

https_ota_handle -- [in] pointer to esp_https_ota_handle_t structure

返回 :

-1 On failure or chunked encoding

total bytes of image

Structures

struct decrypt_cb_arg_t

ESP HTTPS OTA decrypt callback args.

Public Members

const char * data_in

Pointer to data to be decrypted

size_t data_in_len

Input data length

char * data_out

Pointer to data decrypted using callback, this will be freed after data is written to flash

size_t data_out_len

Output data length

struct esp_https_ota_config_t

ESP HTTPS OTA configuration.

Public Members

const esp_http_client_config_t * http_config

ESP HTTP client configuration

http_client_init_cb_t http_client_init_cb

Callback after ESP HTTP client is initialised

bool bulk_flash_erase

Erase entire flash partition during initialization. By default flash partition is erased during write operation and in chunk of 4K sector size

bool partial_http_download

Enable Firmware image to be downloaded over multiple HTTP requests

int max_http_request_size

Maximum request size for partial HTTP download

uint32_t buffer_caps

The memory capability to use when allocating the buffer for OTA update. Default capability is MALLOC_CAP_DEFAULT

bool ota_resumption

Enable resumption in downloading of OTA image between reboots

size_t ota_image_bytes_written

Number of OTA image bytes written to flash so far, updated by the application when OTA data is written successfully in the target OTA partition.

decrypt_cb_t decrypt_cb

Callback for external decryption layer

void * decrypt_user_ctx

User context for external decryption layer

uint16_t enc_img_header_size

Header size of pre-encrypted ota image header

const esp_partition_t * staging

< Details of staging and final partitions for OTA update New image will be downloaded in this staging partition. If NULL then a free app partition (passive app partition) is selected as the staging partition.

const esp_partition_t * final

Final destination partition. Its type/subtype will be used for verification. If set to NULL, staging partition shall be set as the final partition.

bool finalize_with_copy

Flag to copy the staging image to the final partition at the end of OTA update

struct esp_https_ota_config_t partition

Struct containing details about the staging and final partitions for OTA update.

Macros

ESP_ERR_HTTPS_OTA_BASE

ESP_ERR_HTTPS_OTA_IN_PROGRESS

Type Definitions

typedef void * esp_https_ota_handle_t

typedef esp_err_t ( * http_client_init_cb_t ) ( esp_http_client_handle_t )

typedef esp_err_t ( * decrypt_cb_t ) ( decrypt_cb_arg_t * args , void * user_ctx )

Enumerations

enum esp_https_ota_event_t

Events generated by OTA process.

Values:

enumerator ESP_HTTPS_OTA_START

OTA started

enumerator ESP_HTTPS_OTA_CONNECTED

Connected to server

enumerator ESP_HTTPS_OTA_GET_IMG_DESC

Read app/bootloader description from image header

enumerator ESP_HTTPS_OTA_VERIFY_CHIP_ID

Verify chip id of new image

enumerator ESP_HTTPS_OTA_VERIFY_CHIP_REVISION

Verify chip revision of new image

enumerator ESP_HTTPS_OTA_DECRYPT_CB

Callback to decrypt function

enumerator ESP_HTTPS_OTA_WRITE_FLASH

Flash write operation

enumerator ESP_HTTPS_OTA_UPDATE_BOOT_PARTITION

Boot partition update after successful ota update

enumerator ESP_HTTPS_OTA_FINISH

OTA finished

enumerator ESP_HTTPS_OTA_ABORT

OTA aborted

此文档对您有帮助吗？

反馈已收到，谢谢！

如果您有其他意见，欢迎填写 乐鑫文档反馈表 。

我们重视您的反馈。

您可以填写 乐鑫文档反馈表 告诉我们如何改进该文档。
