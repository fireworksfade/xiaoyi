来源：https://docs.espressif.com/projects/esp-idf/zh_CN/v5.5.4/esp32/api-reference/error-codes.html

# 错误代码参考

本节列出了 ESP-IDF 中定义的各种错误代码常量。

有关 ESP-IDF 中出错处理的通用信息，请参见 错误处理。

`ESP_FAIL` (-1): Generic esp_err_t code indicating failure

`ESP_OK` (0): esp_err_t value indicating success (no error)

`ESP_ERR_NO_MEM` (0x101): Out of memory

`ESP_ERR_INVALID_ARG` (0x102): Invalid argument

`ESP_ERR_INVALID_STATE` (0x103): Invalid state

`ESP_ERR_INVALID_SIZE` (0x104): Invalid size

`ESP_ERR_NOT_FOUND` (0x105): Requested resource not found

`ESP_ERR_NOT_SUPPORTED` (0x106): Operation or feature not supported

`ESP_ERR_TIMEOUT` (0x107): Operation timed out

`ESP_ERR_INVALID_RESPONSE` (0x108): Received response was invalid

`ESP_ERR_INVALID_CRC` (0x109): CRC or checksum was invalid

`ESP_ERR_INVALID_VERSION` (0x10a): Version was invalid

`ESP_ERR_INVALID_MAC` (0x10b): MAC address was invalid

`ESP_ERR_NOT_FINISHED` (0x10c): Operation has not fully completed

`ESP_ERR_NOT_ALLOWED` (0x10d): Operation is not allowed

`ESP_ERR_NVS_BASE` (0x1100): Starting number of error codes

`ESP_ERR_NVS_NOT_INITIALIZED` (0x1101): The storage driver is not initialized

`ESP_ERR_NVS_NOT_FOUND` (0x1102): A requested entry couldn't be found or namespace doesn’t exist yet and mode is NVS_READONLY

`ESP_ERR_NVS_TYPE_MISMATCH` (0x1103): The type of set or get operation doesn't match the type of value stored in NVS

`ESP_ERR_NVS_READ_ONLY` (0x1104): Storage handle was opened as read only

`ESP_ERR_NVS_NOT_ENOUGH_SPACE` (0x1105): There is not enough space in the underlying storage to save the value

`ESP_ERR_NVS_INVALID_NAME` (0x1106): Namespace name doesn’t satisfy constraints

`ESP_ERR_NVS_INVALID_HANDLE` (0x1107): Handle has been closed or is NULL

`ESP_ERR_NVS_REMOVE_FAILED` (0x1108): The value wasn’t updated because flash write operation has failed. The value was written however, and update will be finished after re-initialization of nvs, provided that flash operation doesn’t fail again.

`ESP_ERR_NVS_KEY_TOO_LONG` (0x1109): Key name is too long

`ESP_ERR_NVS_PAGE_FULL` (0x110a): Internal error; never returned by nvs API functions

`ESP_ERR_NVS_INVALID_STATE` (0x110b): NVS is in an inconsistent state due to a previous error. Call nvs_flash_init and nvs_open again, then retry.

`ESP_ERR_NVS_INVALID_LENGTH` (0x110c): String or blob length is not sufficient to store data

`ESP_ERR_NVS_NO_FREE_PAGES` (0x110d): NVS partition doesn't contain any empty pages. This may happen if NVS partition was truncated. Erase the whole partition and call nvs_flash_init again.

`ESP_ERR_NVS_VALUE_TOO_LONG` (0x110e): Value doesn't fit into the entry or string or blob length is longer than supported by the implementation

`ESP_ERR_NVS_PART_NOT_FOUND` (0x110f): Partition with specified name is not found in the partition table

`ESP_ERR_NVS_NEW_VERSION_FOUND` (0x1110): NVS partition contains data in new format and cannot be recognized by this version of code

`ESP_ERR_NVS_XTS_ENCR_FAILED` (0x1111): XTS encryption failed while writing NVS entry

`ESP_ERR_NVS_XTS_DECR_FAILED` (0x1112): XTS decryption failed while reading NVS entry

`ESP_ERR_NVS_XTS_CFG_FAILED` (0x1113): XTS configuration setting failed

`ESP_ERR_NVS_XTS_CFG_NOT_FOUND` (0x1114): XTS configuration not found

`ESP_ERR_NVS_ENCR_NOT_SUPPORTED` (0x1115): NVS encryption is not supported in this version

`ESP_ERR_NVS_KEYS_NOT_INITIALIZED` (0x1116): NVS key partition is uninitialized

`ESP_ERR_NVS_CORRUPT_KEY_PART` (0x1117): NVS key partition is corrupt

`ESP_ERR_NVS_CONTENT_DIFFERS` (0x1118): Internal error; never returned by nvs API functions. NVS key is different in comparison

`ESP_ERR_NVS_WRONG_ENCRYPTION` (0x1119): NVS partition is marked as encrypted with generic flash encryption. This is forbidden since the NVS encryption works differently.

`ESP_ERR_ULP_BASE` (0x1200): Offset for ULP-related error codes

`ESP_ERR_ULP_SIZE_TOO_BIG` (0x1201): Program doesn't fit into RTC memory reserved for the ULP

`ESP_ERR_ULP_INVALID_LOAD_ADDR` (0x1202): Load address is outside of RTC memory reserved for the ULP

`ESP_ERR_ULP_DUPLICATE_LABEL` (0x1203): More than one label with the same number was defined

`ESP_ERR_ULP_UNDEFINED_LABEL` (0x1204): Branch instructions references an undefined label

`ESP_ERR_ULP_BRANCH_OUT_OF_RANGE` (0x1205): Branch target is out of range of B instruction (try replacing with BX)

`ESP_ERR_OTA_BASE` (0x1500): Base error code for ota_ops api

`ESP_ERR_OTA_PARTITION_CONFLICT` (0x1501): Error if request was to write or erase the current running partition

`ESP_ERR_OTA_SELECT_INFO_INVALID` (0x1502): Error if OTA data partition contains invalid content

`ESP_ERR_OTA_VALIDATE_FAILED` (0x1503): Error if OTA app image is invalid

`ESP_ERR_OTA_SMALL_SEC_VER` (0x1504): Error if the firmware has a secure version less than the running firmware.

`ESP_ERR_OTA_ROLLBACK_FAILED` (0x1505): Error if flash does not have valid firmware in passive partition and hence rollback is not possible

`ESP_ERR_OTA_ROLLBACK_INVALID_STATE` (0x1506): Error if current active firmware is still marked in pending validation state (ESP_OTA_IMG_PENDING_VERIFY), essentially first boot of firmware image post upgrade and hence firmware upgrade is not possible

`ESP_ERR_EFUSE` (0x1600): Base error code for efuse api.

`ESP_OK_EFUSE_CNT` (0x1601): OK the required number of bits is set.

`ESP_ERR_EFUSE_CNT_IS_FULL` (0x1602): Error field is full.

`ESP_ERR_EFUSE_REPEATED_PROG` (0x1603): Error repeated programming of programmed bits is strictly forbidden.

`ESP_ERR_CODING` (0x1604): Error while a encoding operation.

`ESP_ERR_NOT_ENOUGH_UNUSED_KEY_BLOCKS` (0x1605): Error not enough unused key blocks available

`ESP_ERR_DAMAGED_READING` (0x1606): Error. Burn or reset was done during a reading operation leads to damage read data. This error is internal to the efuse component and not returned by any public API.

`ESP_ERR_IMAGE_BASE` (0x2000)

`ESP_ERR_IMAGE_FLASH_FAIL` (0x2001)

`ESP_ERR_IMAGE_INVALID` (0x2002)

`ESP_ERR_WIFI_BASE` (0x3000): Starting number of WiFi error codes

`ESP_ERR_WIFI_NOT_INIT` (0x3001): WiFi driver was not installed by esp_wifi_init

`ESP_ERR_WIFI_NOT_STARTED` (0x3002): WiFi driver was not started by esp_wifi_start

`ESP_ERR_WIFI_NOT_STOPPED` (0x3003): WiFi driver was not stopped by esp_wifi_stop

`ESP_ERR_WIFI_IF` (0x3004): WiFi interface error

`ESP_ERR_WIFI_MODE` (0x3005): WiFi mode error

`ESP_ERR_WIFI_STATE` (0x3006): WiFi internal state error

`ESP_ERR_WIFI_CONN` (0x3007): WiFi internal control block of station or soft-AP error

`ESP_ERR_WIFI_NVS` (0x3008): WiFi internal NVS module error

`ESP_ERR_WIFI_MAC` (0x3009): MAC address is invalid

`ESP_ERR_WIFI_SSID` (0x300a): SSID is invalid

`ESP_ERR_WIFI_PASSWORD` (0x300b): Password is invalid

`ESP_ERR_WIFI_TIMEOUT` (0x300c): Timeout error

`ESP_ERR_WIFI_WAKE_FAIL` (0x300d): WiFi is in sleep state(RF closed) and wakeup fail

`ESP_ERR_WIFI_WOULD_BLOCK` (0x300e): The caller would block

`ESP_ERR_WIFI_NOT_CONNECT` (0x300f): Station still in disconnect status

`ESP_ERR_WIFI_POST` (0x3012): Failed to post the event to WiFi task

`ESP_ERR_WIFI_INIT_STATE` (0x3013): Invalid WiFi state when init/deinit is called

`ESP_ERR_WIFI_STOP_STATE` (0x3014): Returned when WiFi is stopping

`ESP_ERR_WIFI_NOT_ASSOC` (0x3015): The WiFi connection is not associated

`ESP_ERR_WIFI_TX_DISALLOW` (0x3016): The WiFi TX is disallowed

`ESP_ERR_WIFI_TWT_FULL` (0x3017): no available flow id

`ESP_ERR_WIFI_TWT_SETUP_TIMEOUT` (0x3018): Timeout of receiving twt setup response frame, timeout times can be set during twt setup

`ESP_ERR_WIFI_TWT_SETUP_TXFAIL` (0x3019): TWT setup frame tx failed

`ESP_ERR_WIFI_TWT_SETUP_REJECT` (0x301a): The twt setup request was rejected by the AP

`ESP_ERR_WIFI_DISCARD` (0x301b): Discard frame

`ESP_ERR_WIFI_ROC_IN_PROGRESS` (0x301c): ROC op is in progress

`ESP_ERR_WIFI_REGISTRAR` (0x3033): WPS registrar is not supported

`ESP_ERR_WIFI_WPS_TYPE` (0x3034): WPS type error

`ESP_ERR_WIFI_WPS_SM` (0x3035): WPS state machine is not initialized

`ESP_ERR_ESPNOW_BASE` (0x3064): ESPNOW error number base.

`ESP_ERR_ESPNOW_NOT_INIT` (0x3065): ESPNOW is not initialized.

`ESP_ERR_ESPNOW_ARG` (0x3066): Invalid argument

`ESP_ERR_ESPNOW_NO_MEM` (0x3067): Out of memory

`ESP_ERR_ESPNOW_FULL` (0x3068): ESPNOW peer list is full

`ESP_ERR_ESPNOW_NOT_FOUND` (0x3069): ESPNOW peer is not found

`ESP_ERR_ESPNOW_INTERNAL` (0x306a): Internal error

`ESP_ERR_ESPNOW_EXIST` (0x306b): ESPNOW peer has existed

`ESP_ERR_ESPNOW_IF` (0x306c): Interface error

`ESP_ERR_ESPNOW_CHAN` (0x306d): Channel error

`ESP_ERR_DPP_FAILURE` (0x3097): Generic failure during DPP Operation

`ESP_ERR_DPP_TX_FAILURE` (0x3098): DPP Frame Tx failed OR not Acked

`ESP_ERR_DPP_INVALID_ATTR` (0x3099): Encountered invalid DPP Attribute

`ESP_ERR_DPP_AUTH_TIMEOUT` (0x309a): DPP Auth response was not received in time

`ESP_ERR_DPP_INVALID_LIST` (0x309b): Channel list given in esp_supp_dpp_bootstrap_gen() is not valid or too big

`ESP_ERR_DPP_CONF_TIMEOUT` (0x309c): DPP Configuration was not received in time

`ESP_ERR_MESH_BASE` (0x4000): Starting number of MESH error codes

`ESP_ERR_MESH_WIFI_NOT_START` (0x4001)

`ESP_ERR_MESH_NOT_INIT` (0x4002)

`ESP_ERR_MESH_NOT_CONFIG` (0x4003)

`ESP_ERR_MESH_NOT_START` (0x4004)

`ESP_ERR_MESH_NOT_SUPPORT` (0x4005)

`ESP_ERR_MESH_NOT_ALLOWED` (0x4006)

`ESP_ERR_MESH_NO_MEMORY` (0x4007)

`ESP_ERR_MESH_ARGUMENT` (0x4008)

`ESP_ERR_MESH_EXCEED_MTU` (0x4009)

`ESP_ERR_MESH_TIMEOUT` (0x400a)

`ESP_ERR_MESH_DISCONNECTED` (0x400b)

`ESP_ERR_MESH_QUEUE_FAIL` (0x400c)

`ESP_ERR_MESH_QUEUE_FULL` (0x400d)

`ESP_ERR_MESH_NO_PARENT_FOUND` (0x400e)

`ESP_ERR_MESH_NO_ROUTE_FOUND` (0x400f)

`ESP_ERR_MESH_OPTION_NULL` (0x4010)

`ESP_ERR_MESH_OPTION_UNKNOWN` (0x4011)

`ESP_ERR_MESH_XON_NO_WINDOW` (0x4012)

`ESP_ERR_MESH_INTERFACE` (0x4013)

`ESP_ERR_MESH_DISCARD_DUPLICATE` (0x4014)

`ESP_ERR_MESH_DISCARD` (0x4015)

`ESP_ERR_MESH_VOTING` (0x4016)

`ESP_ERR_MESH_XMIT` (0x4017)

`ESP_ERR_MESH_QUEUE_READ` (0x4018)

`ESP_ERR_MESH_PS` (0x4019)

`ESP_ERR_MESH_RECV_RELEASE` (0x401a)

`ESP_ERR_ESP_NETIF_BASE` (0x5000)

`ESP_ERR_ESP_NETIF_INVALID_PARAMS` (0x5001)

`ESP_ERR_ESP_NETIF_IF_NOT_READY` (0x5002)

`ESP_ERR_ESP_NETIF_DHCPC_START_FAILED` (0x5003)

`ESP_ERR_ESP_NETIF_DHCP_ALREADY_STARTED` (0x5004)

`ESP_ERR_ESP_NETIF_DHCP_ALREADY_STOPPED` (0x5005)

`ESP_ERR_ESP_NETIF_NO_MEM` (0x5006)

`ESP_ERR_ESP_NETIF_DHCP_NOT_STOPPED` (0x5007)

`ESP_ERR_ESP_NETIF_DRIVER_ATTACH_FAILED` (0x5008)

`ESP_ERR_ESP_NETIF_INIT_FAILED` (0x5009)

`ESP_ERR_ESP_NETIF_DNS_NOT_CONFIGURED` (0x500a)

`ESP_ERR_ESP_NETIF_MLD6_FAILED` (0x500b)

`ESP_ERR_ESP_NETIF_IP6_ADDR_FAILED` (0x500c)

`ESP_ERR_ESP_NETIF_DHCPS_START_FAILED` (0x500d)

`ESP_ERR_ESP_NETIF_TX_FAILED` (0x500e)

`ESP_ERR_FLASH_BASE` (0x6000): Starting number of flash error codes

`ESP_ERR_FLASH_OP_FAIL` (0x6001)

`ESP_ERR_FLASH_OP_TIMEOUT` (0x6002)

`ESP_ERR_FLASH_NOT_INITIALISED` (0x6003)

`ESP_ERR_FLASH_UNSUPPORTED_HOST` (0x6004)

`ESP_ERR_FLASH_UNSUPPORTED_CHIP` (0x6005)

`ESP_ERR_FLASH_PROTECTED` (0x6006)

`ESP_ERR_HTTP_BASE` (0x7000): Starting number of HTTP error codes

`ESP_ERR_HTTP_MAX_REDIRECT` (0x7001): The error exceeds the number of HTTP redirects

`ESP_ERR_HTTP_CONNECT` (0x7002): Error open the HTTP connection

`ESP_ERR_HTTP_WRITE_DATA` (0x7003): Error write HTTP data

`ESP_ERR_HTTP_FETCH_HEADER` (0x7004): Error read HTTP header from server

`ESP_ERR_HTTP_INVALID_TRANSPORT` (0x7005): There are no transport support for the input scheme

`ESP_ERR_HTTP_CONNECTING` (0x7006): HTTP connection hasn't been established yet

`ESP_ERR_HTTP_EAGAIN` (0x7007): Mapping of errno EAGAIN to esp_err_t

`ESP_ERR_HTTP_CONNECTION_CLOSED` (0x7008): Read FIN from peer and the connection closed

`ESP_ERR_HTTP_NOT_MODIFIED` (0x7009): HTTP 304 Not Modified, no update available

`ESP_ERR_HTTP_RANGE_NOT_SATISFIABLE` (0x700a): HTTP 416 Range Not Satisfiable, requested range in header is incorrect

`ESP_ERR_HTTP_READ_TIMEOUT` (0x700b): HTTP data read timeout

`ESP_ERR_HTTP_INCOMPLETE_DATA` (0x700c): Incomplete data received, less than Content-Length or last chunk

`ESP_ERR_ESP_TLS_BASE` (0x8000): Starting number of ESP-TLS error codes

`ESP_ERR_ESP_TLS_CANNOT_RESOLVE_HOSTNAME` (0x8001): Error if hostname couldn't be resolved upon tls connection

`ESP_ERR_ESP_TLS_CANNOT_CREATE_SOCKET` (0x8002): Failed to create socket

`ESP_ERR_ESP_TLS_UNSUPPORTED_PROTOCOL_FAMILY` (0x8003): Unsupported protocol family

`ESP_ERR_ESP_TLS_FAILED_CONNECT_TO_HOST` (0x8004): Failed to connect to host

`ESP_ERR_ESP_TLS_SOCKET_SETOPT_FAILED` (0x8005): failed to set/get socket option

`ESP_ERR_ESP_TLS_CONNECTION_TIMEOUT` (0x8006): new connection in esp_tls_low_level_conn connection timeouted

`ESP_ERR_ESP_TLS_SE_FAILED` (0x8007)

`ESP_ERR_ESP_TLS_TCP_CLOSED_FIN` (0x8008)

`ESP_ERR_ESP_TLS_SERVER_HANDSHAKE_TIMEOUT` (0x8009): TLS handshake timeout

`ESP_ERR_MBEDTLS_CERT_PARTLY_OK` (0x8010): mbedtls parse certificates was partly successful

`ESP_ERR_MBEDTLS_CTR_DRBG_SEED_FAILED` (0x8011): mbedtls api returned error

`ESP_ERR_MBEDTLS_SSL_SET_HOSTNAME_FAILED` (0x8012): mbedtls api returned error

`ESP_ERR_MBEDTLS_SSL_CONFIG_DEFAULTS_FAILED` (0x8013): mbedtls api returned error

`ESP_ERR_MBEDTLS_SSL_CONF_ALPN_PROTOCOLS_FAILED` (0x8014): mbedtls api returned error

`ESP_ERR_MBEDTLS_X509_CRT_PARSE_FAILED` (0x8015): mbedtls api returned error

`ESP_ERR_MBEDTLS_SSL_CONF_OWN_CERT_FAILED` (0x8016): mbedtls api returned error

`ESP_ERR_MBEDTLS_SSL_SETUP_FAILED` (0x8017): mbedtls api returned error

`ESP_ERR_MBEDTLS_SSL_WRITE_FAILED` (0x8018): mbedtls api returned error

`ESP_ERR_MBEDTLS_PK_PARSE_KEY_FAILED` (0x8019): mbedtls api returned failed

`ESP_ERR_MBEDTLS_SSL_HANDSHAKE_FAILED` (0x801a): mbedtls api returned failed

`ESP_ERR_MBEDTLS_SSL_CONF_PSK_FAILED` (0x801b): mbedtls api returned failed

`ESP_ERR_MBEDTLS_SSL_TICKET_SETUP_FAILED` (0x801c): mbedtls api returned failed

`ESP_ERR_MBEDTLS_SSL_READ_FAILED` (0x801d): mbedtls api returned failed

`ESP_ERR_WOLFSSL_SSL_SET_HOSTNAME_FAILED` (0x8031): wolfSSL api returned error

`ESP_ERR_WOLFSSL_SSL_CONF_ALPN_PROTOCOLS_FAILED` (0x8032): wolfSSL api returned error

`ESP_ERR_WOLFSSL_CERT_VERIFY_SETUP_FAILED` (0x8033): wolfSSL api returned error

`ESP_ERR_WOLFSSL_KEY_VERIFY_SETUP_FAILED` (0x8034): wolfSSL api returned error

`ESP_ERR_WOLFSSL_SSL_HANDSHAKE_FAILED` (0x8035): wolfSSL api returned failed

`ESP_ERR_WOLFSSL_CTX_SETUP_FAILED` (0x8036): wolfSSL api returned failed

`ESP_ERR_WOLFSSL_SSL_SETUP_FAILED` (0x8037): wolfSSL api returned failed

`ESP_ERR_WOLFSSL_SSL_WRITE_FAILED` (0x8038): wolfSSL api returned failed

`ESP_ERR_HTTPS_OTA_BASE` (0x9000)

`ESP_ERR_HTTPS_OTA_IN_PROGRESS` (0x9001)

`ESP_ERR_PING_BASE` (0xa000)

`ESP_ERR_PING_INVALID_PARAMS` (0xa001)

`ESP_ERR_PING_NO_MEM` (0xa002)

`ESP_ERR_HTTPD_BASE` (0xb000): Starting number of HTTPD error codes

`ESP_ERR_HTTPD_HANDLERS_FULL` (0xb001): All slots for registering URI handlers have been consumed

`ESP_ERR_HTTPD_HANDLER_EXISTS` (0xb002): URI handler with same method and target URI already registered

`ESP_ERR_HTTPD_INVALID_REQ` (0xb003): Invalid request pointer

`ESP_ERR_HTTPD_RESULT_TRUNC` (0xb004): Result string truncated

`ESP_ERR_HTTPD_RESP_HDR` (0xb005): Response header field larger than supported

`ESP_ERR_HTTPD_RESP_SEND` (0xb006): Error occurred while sending response packet

`ESP_ERR_HTTPD_ALLOC_MEM` (0xb007): Failed to dynamically allocate memory for resource

`ESP_ERR_HTTPD_TASK` (0xb008): Failed to launch server task/thread

`ESP_ERR_HW_CRYPTO_BASE` (0xc000): Starting number of HW cryptography module error codes

`ESP_ERR_HW_CRYPTO_DS_HMAC_FAIL` (0xc001): HMAC peripheral problem

`ESP_ERR_HW_CRYPTO_DS_INVALID_KEY` (0xc002)

`ESP_ERR_HW_CRYPTO_DS_INVALID_DIGEST` (0xc004)

`ESP_ERR_HW_CRYPTO_DS_INVALID_PADDING` (0xc005)

`ESP_ERR_MEMPROT_BASE` (0xd000): Starting number of Memory Protection API error codes

`ESP_ERR_MEMPROT_MEMORY_TYPE_INVALID` (0xd001)

`ESP_ERR_MEMPROT_SPLIT_ADDR_INVALID` (0xd002)

`ESP_ERR_MEMPROT_SPLIT_ADDR_OUT_OF_RANGE` (0xd003)

`ESP_ERR_MEMPROT_SPLIT_ADDR_UNALIGNED` (0xd004)

`ESP_ERR_MEMPROT_UNIMGMT_BLOCK_INVALID` (0xd005)

`ESP_ERR_MEMPROT_WORLD_INVALID` (0xd006)

`ESP_ERR_MEMPROT_AREA_INVALID` (0xd007)

`ESP_ERR_MEMPROT_CPUID_INVALID` (0xd008)

`ESP_ERR_TCP_TRANSPORT_BASE` (0xe000): Starting number of TCP Transport error codes

`ESP_ERR_TCP_TRANSPORT_CONNECTION_TIMEOUT` (0xe001): Connection has timed out

`ESP_ERR_TCP_TRANSPORT_CONNECTION_CLOSED_BY_FIN` (0xe002): Read FIN from peer and the connection has closed (in a clean way)

`ESP_ERR_TCP_TRANSPORT_CONNECTION_FAILED` (0xe003): Failed to connect to the peer

`ESP_ERR_TCP_TRANSPORT_NO_MEM` (0xe004): Memory allocation failed

`ESP_ERR_NVS_SEC_BASE` (0xf000): Starting number of error codes

`ESP_ERR_NVS_SEC_HMAC_KEY_NOT_FOUND` (0xf001): HMAC Key required to generate the NVS encryption keys not found

`ESP_ERR_NVS_SEC_HMAC_KEY_BLK_ALREADY_USED` (0xf002): Provided eFuse block for HMAC key generation is already in use

`ESP_ERR_NVS_SEC_HMAC_KEY_GENERATION_FAILED` (0xf003): Failed to generate/write the HMAC key to eFuse

`ESP_ERR_NVS_SEC_HMAC_XTS_KEYS_DERIV_FAILED` (0xf004): Failed to derive the NVS encryption keys based on the HMAC-based scheme

此文档对您有帮助吗？

- 反馈已收到，谢谢！

- 如果您有其他意见，欢迎填写乐鑫文档反馈表。

- 我们重视您的反馈。

- 您可以填写乐鑫文档反馈表告诉我们如何改进该文档。
