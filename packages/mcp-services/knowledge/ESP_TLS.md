来源：https://docs.espressif.com/projects/esp-idf/zh_CN/v5.5.4/esp32/api-reference/protocols/esp_tls.html

# ESP-TLS

## 概述

ESP-TLS 组件提供简化 API 接口，用于访问常用 TLS 功能，支持如 CA 认证验证、SNI、ALPN 协商和非阻塞连接等常见场景，相关配置可在数据结构体 `esp_tls_cfg_t` 中指定。配置完成后，使用以下 API 进行 TLS 通信：

- `esp_tls_init()`：初始化 TLS 连接句柄。

- `esp_tls_conn_new_sync()`：开启新的阻塞式 TLS 连接。

- `esp_tls_conn_new_async()`：开启新的非阻塞式 TLS 连接。

- `esp_tls_conn_read()`：读取 TLS 层之上的应用数据。

- `esp_tls_conn_write()`：将应用数据写入 TLS 连接。

- `esp_tls_conn_destroy()`：释放连接。

任何应用层协议，如 HTTP1、HTTP2 等，均可调用 ESP-TLS 组件接口实现。

## 应用示例

使用 ESP-TLS 建立安全套接字连接的 HTTPS 简单示例，请参阅 protocols/https_request。

## ESP-TLS 组件的树形结构

`
├── esp_tls.c
├── esp_tls.h
├── esp_tls_mbedtls.c
├── esp_tls_wolfssl.c
└── private_include
    ├── esp_tls_mbedtls.h
    └── esp_tls_wolfssl.h
`

ESP-TLS 组件文件 esp-tls/esp_tls.h 包含该组件的公共 API 头文件。在 ESP-TLS 组件内部，为了实现安全会话功能，会使用 MbedTLS 和 WolfSSL 两个 SSL/TLS 库中的其中一个进行安全会话的建立，与 MbedTLS 相关的 API 存放在 esp-tls/private_include/esp_tls_mbedtls.h，而与 WolfSSL 相关的 API 存放在 esp-tls/private_include/esp_tls_wolfssl.h。

## TLS 服务器验证

ESP-TLS 在客户端提供了多种验证 TLS 服务器的选项，如验证对端服务器的服务器证书、或使用预共享密钥验证服务器。用户应在 `esp_tls_cfg_t` 结构体中选择以下任一选项完成 TLS 服务器验证，若未做选择，则客户端默认在 TLS 连接创建时，会返回错误。

- cacert_buf 和 cacert_bytes：以缓冲区的形式向 `esp_tls_cfg_t` 结构体提供 CA 证书，ESP-TLS 将使用缓冲区中的 CA 证书验证服务器。注意，须在 `esp_tls_cfg_t` 结构体中设置以下变量：

  - `cacert_buf` - 指针，指向包含 CA 证书的缓冲区。

  - `cacert_bytes` - CA 证书大小（以字节为单位）。

- use_global_ca_store： `global_ca_store` 可一次性完成初始化及设置，并用于验证 ESP-TLS 连接的服务器，注意需要在这些服务器各自的 `esp_tls_cfg_t` 结构体中设置 `use_global_ca_store = true`。有关初始化和设置 `global_ca_store` 的不同 API，请参阅文末的 API 参考。

- crt_bundle_attach：ESP x509 证书包 API 提供了便捷的服务器验证方法，即打包一组自定义的 x509 根证书，用于 TLS 服务器验证，详情请参阅 ESP x509 证书包。

- psk_hint_key：要使用预共享密钥验证服务器，必须在 ESP-TLS menuconfig 中启用 CONFIG_ESP_TLS_PSK_VERIFICATION，然后向结构体 `esp_tls_cfg_t` 提供指向 PSK 提示和密钥的指针。若未选择有关服务器验证的其他选项，ESP-TLS 将仅用 PSK 验证服务器。

- 跳过服务器验证：该选项并不安全，仅供测试使用。在 ESP-TLS menuconfig 中启用 CONFIG_ESP_TLS_INSECURE 和 CONFIG_ESP_TLS_SKIP_SERVER_CERT_VERIFY 可启用该选项，此时，若未在 `esp_tls_cfg_t` 结构体选择其他服务器验证选项，ESP-TLS 将默认跳过服务器验证。

警告

启用 跳过服务器验证 选项存在潜在风险，若未通过 API 或 `ca_store` 等其他机制提供服务器证书，可能导致设备与伪造身份的服务器建立 TLS 连接。

## ESP-TLS 服务器证书选择回调

使用 MbedTLS 协议栈时，ESP-TLS 组件支持设置服务器证书选择回调函数。此时，在服务器握手期间可选择使用哪个服务器证书，该回调可获取客户端发送的 "Client Hello" 消息中提供的 TLS 扩展（ALPN、SPI 等），并基于此选择传输哪个服务器证书给客户端。要启用此功能，请在 ESP-TLS menuconfig 中启用 CONFIG_ESP_TLS_SERVER_CERT_SELECT_HOOK。

证书选择回调可在结构体 `esp_tls_cfg_t` 中配置，具体如下：

`
int cert_selection_callback(mbedtls_ssl_context *ssl)
{
    /* 回调应执行的代码 */
    return 0;
}

esp_tls_cfg_t cfg = {
    cert_select_cb = cert_section_callback,
};
`

## 底层 SSL/TLS 库选择

ESP-TLS 组件支持以 MbedTLS 或 WolfSSL 作为其底层 SSL/TLS 库，默认仅使用 MbedTLS，WolfSSL 的 SSL/TLS 库可在 https://github.com/espressif/esp-wolfssl 上公开获取，该仓库提供二进制格式的 WolfSSL 组件，并提供了一些示例帮助用户了解相关 API。有关许可证和其他选项，请参阅仓库的 `README.md` 文件。下文介绍了在工程中使用 WolfSSL 的具体流程。

备注

库选项位于 ESP-TLS 内部，因此切换库不会更改工程的 ESP-TLS 特定代码。

## 在 ESP-IDF 使用 WolfSSL

要在工程中使用 WolfSSL，可采取以下两种方式：

- 将 WolfSSL 作为组件直接添加到工程中。用 cd 命令进入工程目录后，使用以下命令：

`
mkdir components
cd components
git clone --recursive https://github.com/espressif/esp-wolfssl.git
`

- 将 WolfSSL 作为额外组件添加到工程中。

  - 使用以下命令下载 WolfSSL：

`
git clone https://github.com/espressif/esp-wolfssl.git
`

  - 参照 wolfssl/examples 示例，在工程的 `CMakeLists.txt` 文件中设置 `EXTRA_COMPONENT_DIRS`，从而在 ESP-IDF 中包含 ESP-WolfSSL，详情请参阅 构建系统 中的 可选的项目变量 小节。

完成上述步骤后，可以在工程配置菜单中将 WolfSSL 作为底层 SSL/TLS 库，具体步骤如下：

`
idf.py menuconfig > ESP-TLS > SSL/TLS Library > Mbedtls/Wolfssl
`

## MbedTLS 与 WolfSSL 对比

下表是在使用 WolfSSL 和 MbedTLS 两种 SSL/TLS 库，并将所有相关配置设置为默认值时，运行具有服务器身份验证的 protocols/https_request 示例的比较结果。对于 MbedTLS，IN_CONTENT 长度和 OUT_CONTENT 长度分别设置为 16384 字节和 4096 字节。

| 属性 | WolfSSL | MbedTLS |
| --- | --- | --- |
| 总消耗堆空间 | ~ 19 KB | ~ 37 KB |
| 任务栈使用 | ~ 2.2 KB | ~ 3.6 KB |
| 二进制文件大小 | ~ 858 KB | ~ 736 KB |

备注

若配置选项不同或相应库的版本不同，得到的值可能与上表不同。

## ESP-TLS 中的 ATECC608A（安全元件）

ESP-TLS 支持在 ESP32 系列芯片上使用 ATECC608A 加密芯片，但必须将 MbedTLS 作为 ESP-TLS 的底层 SSL/TLS 协议栈。未经手动更改，ESP-TLS 默认以 MbedTLS 为其底层 TLS/SSL 协议栈。

备注

在 ESP32 系列上的 ATECC608A 芯片必须预先配置，详情请参阅 esp_cryptoauth_utility。

要启用安全元件支持，并将其应用于工程 TLS 连接，请遵循以下步骤：

- 在工程中添加 esp-cryptoauthlib，详情请参阅 如何在 ESP-IDF 中使用 esp-cryptoauthlib。

- 启用 menuconfig 选项 CONFIG_ESP_TLS_USE_SECURE_ELEMENT：

`
menuconfig > Component config > ESP-TLS > Use Secure Element (ATECC608A) with ESP-TLS
`

- 选择 ATECC608A 芯片类型：

`
menuconfig > Component config > esp-cryptoauthlib > Choose Type of ATECC608A chip
`

如需了解更多 ATECC608A 芯片类型，或需了解如何获取连接到特定 ESP 模块的 ATECC608A 芯片类型，请参阅 ATECC608A 芯片类型。

- 在 `esp_tls_cfg_t` 中提供以下配置，在 ESP-TLS 中启用 ATECC608A：

`
esp_tls_cfg_t cfg = {
    /* 其他配置选项 */
    .use_secure_element = true,
};
`

## TLS 加密套件

ESP-TLS 支持在客户端模式下设置加密套件列表，TLS 密码套件列表用于向服务器传递所支持的密码套件信息，用户可以根据自己需求增减加密套件，且适用于任何 TLS 协议栈配置。如果服务器支持列表中的任一密码套件，则 TLS 连接成功，反之连接失败。

连接客户端时，在 `esp_tls_cfg_t` 结构体中设置 `ciphersuites_list` 的步骤如下：

`
/* 加密套件列表必须以 0 结尾，并且在整个 TLS 连接期间，加密套件的内存地址空间有效 */
static const int ciphersuites_list[] = {MBEDTLS_TLS_ECDHE_ECDSA_WITH_AES_256_GCM_SHA384, MBEDTLS_TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384, 0};
esp_tls_cfg_t cfg = {
    .ciphersuites_list = ciphersuites_list,
};
`

ESP-TLS 不会检查 `ciphersuites_list` 的有效性，因此需调用 `esp_tls_get_ciphersuites_list()` 获取 TLS 协议栈中支持的加密套件列表，并检查设置的加密套件是否在支持的加密套件列表中。

备注

此功能仅在 MbedTLS 协议栈中有效。

## TLS 协议版本

ESP-TLS 能够为 TLS 连接设置相应的 TLS 协议版本，指定版本将用于建立专用 TLS 连接。也就是说，在运行时不同的 TLS 连接可以配置到 TLS 1.2、TLS 1.3 等不同协议版本。

备注

目前，仅在 MbedTLS 作为 ESP-TLS 的底层 SSL/TLS 协议栈时支持此功能。

要在 ESP-TLS 中设置 TLS 协议版本，请设置 `esp_tls_cfg_t::tls_version`，从 `esp_tls_proto_ver_t` 中选择所需版本。如未指定协议版本字段，将默认根据服务器要求建立 TLS 连接。

ESP-TLS 连接的协议版本可按如下方式配置：

`
#include "esp_tls.h"
esp_tls_cfg_t cfg = {
    .tls_version = ESP_TLS_VER_TLS_1_2,
};
`

## API 参考

### Header File

- components/esp-tls/esp_tls.h

- This header file can be included with:

`
#include "esp_tls.h"
`

- This header file is a part of the API provided by the `esp-tls` component. To declare that your component depends on `esp-tls`, add the following to your CMakeLists.txt:

`
REQUIRES esp-tls
`

or

`
PRIV_REQUIRES esp-tls
`

### Functions

esp_err_t esp_tls_cfg_server_session_tickets_init(esp_tls_cfg_server_t *cfg)

Initialize the server side TLS session ticket context.

This function initializes the server side tls session ticket context which holds all necessary data structures to enable tls session tickets according to RFC5077. Use esp_tls_cfg_server_session_tickets_free to free the data.

参数:

cfg -- [in] server configuration as esp_tls_cfg_server_t

返回:

ESP_OK if setup succeeded ESP_ERR_INVALID_ARG if context is already initialized ESP_ERR_NO_MEM if memory allocation failed ESP_ERR_NOT_SUPPORTED if session tickets are not available due to build configuration ESP_FAIL if setup failed

void esp_tls_cfg_server_session_tickets_free(esp_tls_cfg_server_t *cfg)

Free the server side TLS session ticket context.

参数:

cfg -- server configuration as esp_tls_cfg_server_t

esp_tls_t *esp_tls_init(void)

Create TLS connection.

This function allocates and initializes esp-tls structure handle.

返回:

tls Pointer to esp-tls as esp-tls handle if successfully initialized, NULL if allocation error

esp_tls_t *esp_tls_conn_http_new(const char *url, const esp_tls_cfg_t *cfg)

Create a new blocking TLS/SSL connection with a given "HTTP" url.

Note: This API is present for backward compatibility reasons. Alternative function with the same functionality is `esp_tls_conn_http_new_sync` (and its asynchronous version `esp_tls_conn_http_new_async`)

参数:

- url -- [in] url of host.

- cfg -- [in] TLS configuration as esp_tls_cfg_t. If you wish to open non-TLS connection, keep this NULL. For TLS connection, a pass pointer to 'esp_tls_cfg_t'. At a minimum, this structure should be zero-initialized.

返回:

pointer to esp_tls_t, or NULL if connection couldn't be opened.

int esp_tls_conn_new_sync(const char *hostname, int hostlen, int port, const esp_tls_cfg_t *cfg, esp_tls_t *tls)

Create a new blocking TLS/SSL connection.

This function establishes a TLS/SSL connection with the specified host in blocking manner.

参数:

- hostname -- [in] Hostname of the host.

- hostlen -- [in] Length of hostname.

- port -- [in] Port number of the host.

- cfg -- [in] TLS configuration as esp_tls_cfg_t. For a TLS connection, pass a pointer to a esp_tls_cfg_t. For a plain TCP connection, pass a pointer to a esp_tls_cfg_t with is_plain_tcp set to true. At a minimum, this pointer should be not NULL and the structure should be zero-initialized

- tls -- [in] Pointer to esp-tls as esp-tls handle.

返回:

- -1 If connection establishment fails.

- 1 If connection establishment is successful.

- 0 If connection state is in progress.

int esp_tls_conn_http_new_sync(const char *url, const esp_tls_cfg_t *cfg, esp_tls_t *tls)

Create a new blocking TLS/SSL connection with a given "HTTP" url.

The behaviour is same as esp_tls_conn_new_sync() API. However this API accepts host's url.

参数:

- url -- [in] url of host.

- cfg -- [in] TLS configuration as esp_tls_cfg_t. If you wish to open non-TLS connection, keep this NULL. For TLS connection, a pass pointer to 'esp_tls_cfg_t'. At a minimum, this structure should be zero-initialized.

- tls -- [in] Pointer to esp-tls as esp-tls handle.

返回:

- -1 If connection establishment fails.

- 1 If connection establishment is successful.

- 0 If connection state is in progress.

int esp_tls_conn_new_async(const char *hostname, int hostlen, int port, const esp_tls_cfg_t *cfg, esp_tls_t *tls)

Create a new non-blocking TLS/SSL connection.

This function initiates a non-blocking TLS/SSL connection with the specified host, but due to its non-blocking nature, it doesn't wait for the connection to get established.

参数:

- hostname -- [in] Hostname of the host.

- hostlen -- [in] Length of hostname.

- port -- [in] Port number of the host.

- cfg -- [in] TLS configuration as esp_tls_cfg_t. `non_block` member of this structure should be set to be true.

- tls -- [in] pointer to esp-tls as esp-tls handle.

返回:

- -1 If connection establishment fails.

- 0 If connection establishment is in progress.

- 1 If connection establishment is successful.

int esp_tls_conn_http_new_async(const char *url, const esp_tls_cfg_t *cfg, esp_tls_t *tls)

Create a new non-blocking TLS/SSL connection with a given "HTTP" url.

The behaviour is same as esp_tls_conn_new_async() API. However this API accepts host's url.

参数:

- url -- [in] url of host.

- cfg -- [in] TLS configuration as esp_tls_cfg_t.

- tls -- [in] pointer to esp-tls as esp-tls handle.

返回:

- -1 If connection establishment fails.

- 0 If connection establishment is in progress.

- 1 If connection establishment is successful.

ssize_t esp_tls_conn_write(esp_tls_t *tls, const void *data, size_t datalen)

Write from buffer 'data' into specified tls connection.

参数:

- tls -- [in] pointer to esp-tls as esp-tls handle.

- data -- [in] Buffer from which data will be written.

- datalen -- [in] Length of data buffer.

返回:

- >=0 if write operation was successful, the return value is the number of bytes actually written to the TLS/SSL connection.

- <0 if write operation was not successful, because either an error occurred or an action must be taken by the calling process.

- ESP_TLS_ERR_SSL_WANT_READ/ ESP_TLS_ERR_SSL_WANT_WRITE. if the handshake is incomplete and waiting for data to be available for reading. In this case this functions needs to be called again when the underlying transport is ready for operation.

ssize_t esp_tls_conn_read(esp_tls_t *tls, void *data, size_t datalen)

Read from specified tls connection into the buffer 'data'.

参数:

- tls -- [in] pointer to esp-tls as esp-tls handle.

- data -- [in] Buffer to hold read data.

- datalen -- [in] Length of data buffer.

返回:

- >0 if read operation was successful, the return value is the number of bytes actually read from the TLS/SSL connection.

- 0 if read operation was not successful. The underlying connection was closed.

- <0 if read operation was not successful, because either an error occurred or an action must be taken by the calling process.

int esp_tls_conn_destroy(esp_tls_t *tls)

Close the TLS/SSL connection and free any allocated resources.

This function should be called to close each tls connection opened with esp_tls_conn_new_sync() (or esp_tls_conn_http_new_sync()) and esp_tls_conn_new_async() (or esp_tls_conn_http_new_async()) APIs.

参数:

tls -- [in] pointer to esp-tls as esp-tls handle.

返回:

- 0 on success

- -1 if socket error or an invalid argument

ssize_t esp_tls_get_bytes_avail(esp_tls_t *tls)

Return the number of application data bytes remaining to be read from the current record.

This API is a wrapper over mbedtls's mbedtls_ssl_get_bytes_avail() API.

参数:

tls -- [in] pointer to esp-tls as esp-tls handle.

返回:

- -1 in case of invalid arg

- bytes available in the application data record read buffer

esp_err_t esp_tls_get_conn_sockfd(esp_tls_t *tls, int *sockfd)

Returns the connection socket file descriptor from esp_tls session.

参数:

- tls -- [in] handle to esp_tls context

- sockfd -- [out] int pointer to sockfd value.

返回:

- ESP_OK on success and value of sockfd will be updated with socket file descriptor for connection

- ESP_ERR_INVALID_ARG if (tls == NULL || sockfd == NULL)

esp_err_t esp_tls_set_conn_sockfd(esp_tls_t *tls, int sockfd)

Sets the connection socket file descriptor for the esp_tls session.

参数:

- tls -- [in] handle to esp_tls context

- sockfd -- [in] sockfd value to set.

返回:

- ESP_OK on success and value of sockfd for the tls connection shall updated with the provided value

- ESP_ERR_INVALID_ARG if (tls == NULL || sockfd < 0)

esp_err_t esp_tls_get_conn_state(esp_tls_t *tls, esp_tls_conn_state_t *conn_state)

Gets the connection state for the esp_tls session.

参数:

- tls -- [in] handle to esp_tls context

- conn_state -- [out] pointer to the connection state value.

返回:

- ESP_OK on success and value of sockfd for the tls connection shall updated with the provided value

- ESP_ERR_INVALID_ARG (Invalid arguments)

esp_err_t esp_tls_set_conn_state(esp_tls_t *tls, esp_tls_conn_state_t conn_state)

Sets the connection state for the esp_tls session.

参数:

- tls -- [in] handle to esp_tls context

- conn_state -- [in] connection state value to set.

返回:

- ESP_OK on success and value of sockfd for the tls connection shall updated with the provided value

- ESP_ERR_INVALID_ARG (Invalid arguments)

void *esp_tls_get_ssl_context(esp_tls_t *tls)

Returns the ssl context.

参数:

tls -- [in] handle to esp_tls context

返回:

- ssl_ctx pointer to ssl context of underlying TLS layer on success

- NULL in case of error

esp_err_t esp_tls_init_global_ca_store(void)

Create a global CA store, initially empty.

This function should be called if the application wants to use the same CA store for multiple connections. This function initialises the global CA store which can be then set by calling esp_tls_set_global_ca_store(). To be effective, this function must be called before any call to esp_tls_set_global_ca_store().

返回:

- ESP_OK if creating global CA store was successful.

- ESP_ERR_NO_MEM if an error occurred when allocating the mbedTLS resources.

esp_err_t esp_tls_set_global_ca_store(const unsigned char *cacert_pem_buf, const unsigned int cacert_pem_bytes)

Set the global CA store with the buffer provided in pem format.

This function should be called if the application wants to set the global CA store for multiple connections i.e. to add the certificates in the provided buffer to the certificate chain. This function implicitly calls esp_tls_init_global_ca_store() if it has not already been called. The application must call this function before calling esp_tls_conn_new().

参数:

- cacert_pem_buf -- [in] Buffer which has certificates in pem format. This buffer is used for creating a global CA store, which can be used by other tls connections.

- cacert_pem_bytes -- [in] Length of the buffer.

返回:

- ESP_OK if adding certificates was successful.

- Other if an error occurred or an action must be taken by the calling process.

void esp_tls_free_global_ca_store(void)

Free the global CA store currently being used.

The memory being used by the global CA store to store all the parsed certificates is freed up. The application can call this API if it no longer needs the global CA store.

esp_err_t esp_tls_get_and_clear_last_error(esp_tls_error_handle_t h, int *esp_tls_code, int *esp_tls_flags)

Returns last error in esp_tls with detailed mbedtls related error codes. The error information is cleared internally upon return.

参数:

- h -- [in] esp-tls error handle.

- esp_tls_code -- [out] last error code returned from mbedtls api (set to zero if none) This pointer could be NULL if caller does not care about esp_tls_code

- esp_tls_flags -- [out] last certification verification flags (set to zero if none) This pointer could be NULL if caller does not care about esp_tls_code

返回:

- ESP_ERR_INVALID_STATE if invalid parameters

- ESP_OK (0) if no error occurred

- specific error code (based on ESP_ERR_ESP_TLS_BASE) otherwise

esp_err_t esp_tls_get_and_clear_error_type(esp_tls_error_handle_t h, esp_tls_error_type_t err_type, int *error_code)

Returns the last error captured in esp_tls of a specific type The error information is cleared internally upon return.

参数:

- h -- [in] esp-tls error handle.

- err_type -- [in] specific error type

- error_code -- [out] last error code returned from mbedtls api (set to zero if none) This pointer could be NULL if caller does not care about esp_tls_code

返回:

- ESP_ERR_INVALID_STATE if invalid parameters

- ESP_OK if a valid error returned and was cleared

esp_err_t esp_tls_get_error_handle(esp_tls_t *tls, esp_tls_error_handle_t *error_handle)

Returns the ESP-TLS error_handle.

参数:

- tls -- [in] handle to esp_tls context

- error_handle -- [out] pointer to the error handle.

返回:

- ESP_OK on success and error_handle will be updated with the ESP-TLS error handle.

- ESP_ERR_INVALID_ARG if (tls == NULL || error_handle == NULL)

mbedtls_x509_crt *esp_tls_get_global_ca_store(void)

Get the pointer to the global CA store currently being used.

The application must first call esp_tls_set_global_ca_store(). Then the same CA store could be used by the application for APIs other than esp_tls.

备注

Modifying the pointer might cause a failure in verifying the certificates.

返回:

- Pointer to the global CA store currently being used if successful.

- NULL if there is no global CA store set.

const int *esp_tls_get_ciphersuites_list(void)

Get supported TLS ciphersuites list.

See https://www.iana.org/assignments/tls-parameters/tls-parameters.xhtml#tls-parameters-4 for the list of ciphersuites

返回:

Pointer to a zero-terminated array of IANA identifiers of TLS ciphersuites.

esp_err_t esp_tls_server_session_init(esp_tls_cfg_server_t *cfg, int sockfd, esp_tls_t *tls)

Initialize server side TLS/SSL connection.

This function should be used to initialize the server side TLS/SSL connection when the application wants to handle the TLS/SSL connection asynchronously with the help of esp_tls_server_session_continue_async() function.

参数:

- cfg -- [in] Pointer to esp_tls_cfg_server_t

- sockfd -- [in] FD of accepted connection

- tls -- [out] Pointer to allocated esp_tls_t

返回:

- ESP_OK if successful

- ESP_ERR_INVALID_ARG if invalid arguments

- ESP_FAIL if server session setup failed

int esp_tls_server_session_continue_async(esp_tls_t *tls)

Asynchronous continue of esp_tls_server_session_init.

This function should be called in a loop by the user until it returns 0. If this functions returns something other than 0, ESP_TLS_ERR_SSL_WANT_READ or ESP_TLS_ERR_SSL_WANT_WRITE, the esp-tls context must not be used and should be freed using esp_tls_conn_destroy();

参数:

tls -- [in] pointer to esp_tls_t

返回:

- 0 if successful

- <0 in case of error

- ESP_TLS_ERR_SSL_WANT_READ/ESP_TLS_ERR_SSL_WANT_WRITE if the handshake is incomplete and waiting for data to be available for reading.

int esp_tls_server_session_create(esp_tls_cfg_server_t *cfg, int sockfd, esp_tls_t *tls)

Create TLS/SSL server session.

This function creates a TLS/SSL server context for already accepted client connection and performs TLS/SSL handshake with the client

参数:

- cfg -- [in] Pointer to esp_tls_cfg_server_t

- sockfd -- [in] FD of accepted connection

- tls -- [out] Pointer to allocated esp_tls_t

返回:

- 0 if successful

- <0 in case of error

void esp_tls_server_session_delete(esp_tls_t *tls)

Close the server side TLS/SSL connection and free any allocated resources.

This function should be called to close each tls connection opened with esp_tls_server_session_create()

参数:

tls -- [in] pointer to esp_tls_t

esp_err_t esp_tls_plain_tcp_connect(const char *host, int hostlen, int port, const esp_tls_cfg_t *cfg, esp_tls_error_handle_t error_handle, int *sockfd)

Creates a plain TCP connection, returning a valid socket fd on success or an error handle.

参数:

- host -- [in] Hostname of the host.

- hostlen -- [in] Length of hostname.

- port -- [in] Port number of the host.

- cfg -- [in] ESP-TLS configuration as esp_tls_cfg_t.

- error_handle -- [out] ESP-TLS error handle holding potential errors occurred during connection

- sockfd -- [out] Socket descriptor if successfully connected on TCP layer

返回:

ESP_OK on success ESP_ERR_INVALID_ARG if invalid output parameters ESP-TLS based error codes on failure

### Structures

struct psk_key_hint

ESP-TLS preshared key and hint structure.

Public Members

const uint8_t *key

key in PSK authentication mode in binary format

size_t key_size

length of the key

const char *hint

hint in PSK authentication mode in string format

struct tls_keep_alive_cfg

esp-tls client session ticket ctx

Keep alive parameters structure

Public Members

bool keep_alive_enable

Enable keep-alive timeout

int keep_alive_idle

Keep-alive idle time (second)

int keep_alive_interval

Keep-alive interval time (second)

int keep_alive_count

Keep-alive packet retry send count

struct esp_tls_cfg

ESP-TLS configuration parameters.

备注

Note about format of certificates:

- This structure includes certificates of a Certificate Authority, of client or server as well as private keys, which may be of PEM or DER format. In case of PEM format, the buffer must be NULL terminated (with NULL character included in certificate size).

- Certificate Authority's certificate may be a chain of certificates in case of PEM format, but could be only one certificate in case of DER format

- Variables names of certificates and private key buffers and sizes are defined as unions providing backward compatibility for legacy *_pem_buf and *_pem_bytes names which suggested only PEM format was supported. It is encouraged to use generic names such as cacert_buf and cacert_bytes.

Public Members

const char **alpn_protos

Application protocols required for HTTP2. If HTTP2/ALPN support is required, a list of protocols that should be negotiated. The format is length followed by protocol name. For the most common cases the following is ok: const char **alpn_protos = { "h2", NULL };

- where 'h2' is the protocol name

const unsigned char *cacert_buf

Certificate Authority's certificate in a buffer. Format may be PEM or DER, depending on mbedtls-support This buffer should be NULL terminated in case of PEM

const unsigned char *cacert_pem_buf

CA certificate buffer legacy name

unsigned int cacert_bytes

Size of Certificate Authority certificate pointed to by cacert_buf (including NULL-terminator in case of PEM format)

unsigned int cacert_pem_bytes

Size of Certificate Authority certificate legacy name

const unsigned char *clientcert_buf

Client certificate in a buffer Format may be PEM or DER, depending on mbedtls-support This buffer should be NULL terminated in case of PEM

const unsigned char *clientcert_pem_buf

Client certificate legacy name

unsigned int clientcert_bytes

Size of client certificate pointed to by clientcert_pem_buf (including NULL-terminator in case of PEM format)

unsigned int clientcert_pem_bytes

Size of client certificate legacy name

const unsigned char *clientkey_buf

Client key in a buffer Format may be PEM or DER, depending on mbedtls-support This buffer should be NULL terminated in case of PEM

const unsigned char *clientkey_pem_buf

Client key legacy name

unsigned int clientkey_bytes

Size of client key pointed to by clientkey_pem_buf (including NULL-terminator in case of PEM format)

unsigned int clientkey_pem_bytes

Size of client key legacy name

const unsigned char *clientkey_password

Client key decryption password string

unsigned int clientkey_password_len

String length of the password pointed to by clientkey_password

bool use_ecdsa_peripheral

Use the ECDSA peripheral for the private key operations

uint8_t ecdsa_key_efuse_blk

The efuse block where ECDSA key is stored. For SECP384R1 curve, if two blocks are used, set this to the low block and use ecdsa_key_efuse_blk_high for the high block.

uint8_t ecdsa_key_efuse_blk_high

The high efuse block for ECDSA key (used only for SECP384R1 curve). If not set (0), only ecdsa_key_efuse_blk is used.

esp_tls_ecdsa_curve_t ecdsa_curve

ECDSA curve to use (SECP256R1 or SECP384R1)

bool non_block

Configure non-blocking mode. If set to true the underneath socket will be configured in non blocking mode after tls session is established

bool use_secure_element

Enable this option to use secure element or atecc608a chip

int timeout_ms

Network timeout in milliseconds. Note: If this value is not set, by default the timeout is set to 10 seconds. If you wish that the session should wait indefinitely then please use a larger value e.g., INT32_MAX

bool use_global_ca_store

Use a global ca_store for all the connections in which this bool is set.

const char *common_name

If non-NULL, server certificate CN must match this name. If NULL, server certificate CN must match hostname.

bool skip_common_name

Skip any validation of server certificate CN field

tls_keep_alive_cfg_t *keep_alive_cfg

Enable TCP keep-alive timeout for SSL connection

esp_err_t (*crt_bundle_attach)(void *conf)

Function pointer to esp_crt_bundle_attach. Enables the use of certification bundle for server verification, must be enabled in menuconfig

void *ds_data

Pointer for digital signature peripheral context

bool is_plain_tcp

Use non-TLS connection: When set to true, the esp-tls uses plain TCP transport rather then TLS/SSL connection. Note, that it is possible to connect using a plain tcp transport directly with esp_tls_plain_tcp_connect() API

struct ifreq *if_name

The name of interface for data to go through. Use the default interface without setting

esp_tls_addr_family_t addr_family

The address family to use when connecting to a host.

const int *ciphersuites_list

Pointer to a zero-terminated array of IANA identifiers of TLS ciphersuites. Please check the list validity by esp_tls_get_ciphersuites_list() API

esp_tls_proto_ver_t tls_version

TLS protocol version of the connection, e.g., TLS 1.2, TLS 1.3 (default - no preference)

struct esp_tls_cfg_server

ESP-TLS Server configuration parameters.

Public Members

const char **alpn_protos

Application protocols required for HTTP2. If HTTP2/ALPN support is required, a list of protocols that should be negotiated. The format is length followed by protocol name. For the most common cases the following is ok: const char **alpn_protos = { "h2", NULL };

- where 'h2' is the protocol name

const unsigned char *cacert_buf

Client CA certificate in a buffer. This buffer should be NULL terminated

const unsigned char *cacert_pem_buf

Client CA certificate legacy name

unsigned int cacert_bytes

Size of client CA certificate pointed to by cacert_pem_buf

unsigned int cacert_pem_bytes

Size of client CA certificate legacy name

const unsigned char *servercert_buf

Server certificate in a buffer This buffer should be NULL terminated

const unsigned char *servercert_pem_buf

Server certificate legacy name

unsigned int servercert_bytes

Size of server certificate pointed to by servercert_pem_buf

unsigned int servercert_pem_bytes

Size of server certificate legacy name

const unsigned char *serverkey_buf

Server key in a buffer This buffer should be NULL terminated

const unsigned char *serverkey_pem_buf

Server key legacy name

unsigned int serverkey_bytes

Size of server key pointed to by serverkey_pem_buf

unsigned int serverkey_pem_bytes

Size of server key legacy name

const unsigned char *serverkey_password

Server key decryption password string

unsigned int serverkey_password_len

String length of the password pointed to by serverkey_password

bool use_ecdsa_peripheral

Use ECDSA peripheral to use private key

uint8_t ecdsa_key_efuse_blk

The efuse block where ECDSA key is stored. For SECP384R1 curve, if two blocks are used, set this to the low block and use ecdsa_key_efuse_blk_high for the high block.

uint8_t ecdsa_key_efuse_blk_high

The high efuse block for ECDSA key (used only for SECP384R1 curve). If not set (0), only ecdsa_key_efuse_blk is used.

esp_tls_ecdsa_curve_t ecdsa_curve

ECDSA curve to use (SECP256R1 or SECP384R1)

bool use_secure_element

Enable this option to use secure element or atecc608a chip

uint32_t tls_handshake_timeout_ms

TLS handshake timeout in milliseconds. Note: If this value is not set, by default the timeout is set to 10 seconds. If you wish that the session should wait indefinitely then please use a larger value e.g., INT32_MAX

void *userdata

User data to be added to the ssl context. Can be retrieved by callbacks

### Type Definitions

typedef enum esp_tls_conn_state esp_tls_conn_state_t

ESP-TLS Connection State.

typedef enum esp_tls_role esp_tls_role_t

typedef struct psk_key_hint psk_hint_key_t

ESP-TLS preshared key and hint structure.

typedef struct tls_keep_alive_cfg tls_keep_alive_cfg_t

esp-tls client session ticket ctx

Keep alive parameters structure

typedef enum esp_tls_addr_family esp_tls_addr_family_t

typedef struct esp_tls_cfg esp_tls_cfg_t

ESP-TLS configuration parameters.

备注

Note about format of certificates:

- This structure includes certificates of a Certificate Authority, of client or server as well as private keys, which may be of PEM or DER format. In case of PEM format, the buffer must be NULL terminated (with NULL character included in certificate size).

- Certificate Authority's certificate may be a chain of certificates in case of PEM format, but could be only one certificate in case of DER format

- Variables names of certificates and private key buffers and sizes are defined as unions providing backward compatibility for legacy *_pem_buf and *_pem_bytes names which suggested only PEM format was supported. It is encouraged to use generic names such as cacert_buf and cacert_bytes.

typedef void *esp_tls_handshake_callback

typedef struct esp_tls_cfg_server esp_tls_cfg_server_t

ESP-TLS Server configuration parameters.

typedef struct esp_tls esp_tls_t

### Enumerations

enum esp_tls_conn_state

ESP-TLS Connection State.

Values:

enumerator ESP_TLS_INIT

enumerator ESP_TLS_CONNECTING

enumerator ESP_TLS_HANDSHAKE

enumerator ESP_TLS_FAIL

enumerator ESP_TLS_DONE

enum esp_tls_role

Values:

enumerator ESP_TLS_CLIENT

enumerator ESP_TLS_SERVER

enum esp_tls_addr_family

Values:

enumerator ESP_TLS_AF_UNSPEC

Unspecified address family.

enumerator ESP_TLS_AF_INET

IPv4 address family.

enumerator ESP_TLS_AF_INET6

IPv6 address family.

enum esp_tls_proto_ver_t

Values:

enumerator ESP_TLS_VER_ANY

enumerator ESP_TLS_VER_TLS_1_2

enumerator ESP_TLS_VER_TLS_1_3

enumerator ESP_TLS_VER_TLS_MAX

enum esp_tls_dyn_buf_strategy_t

Values:

enumerator ESP_TLS_DYN_BUF_RX_STATIC

Strategy to disable dynamic RX buffer allocations and convert to static allocation post-handshake, reducing memory fragmentation

enumerator ESP_TLS_DYN_BUF_STRATEGY_MAX

to indicate max

enum esp_tls_ecdsa_curve_t

ECDSA curve options for TLS connections.

Values:

enumerator ESP_TLS_ECDSA_CURVE_SECP256R1

Use SECP256R1 curve

enumerator ESP_TLS_ECDSA_CURVE_MAX

to indicate max

### Header File

- components/esp-tls/esp_tls_errors.h

- This header file can be included with:

`
#include "esp_tls_errors.h"
`

- This header file is a part of the API provided by the `esp-tls` component. To declare that your component depends on `esp-tls`, add the following to your CMakeLists.txt:

`
REQUIRES esp-tls
`

or

`
PRIV_REQUIRES esp-tls
`

### Structures

struct esp_tls_last_error

Error structure containing relevant errors in case tls error occurred.

Public Members

esp_err_t last_error

error code (based on ESP_ERR_ESP_TLS_BASE) of the last occurred error

int esp_tls_error_code

esp_tls error code from last esp_tls failed api

int esp_tls_flags

last certification verification flags

### Macros

ESP_ERR_ESP_TLS_BASE

Starting number of ESP-TLS error codes

ESP_ERR_ESP_TLS_CANNOT_RESOLVE_HOSTNAME

Error if hostname couldn't be resolved upon tls connection

ESP_ERR_ESP_TLS_CANNOT_CREATE_SOCKET

Failed to create socket

ESP_ERR_ESP_TLS_UNSUPPORTED_PROTOCOL_FAMILY

Unsupported protocol family

ESP_ERR_ESP_TLS_FAILED_CONNECT_TO_HOST

Failed to connect to host

ESP_ERR_ESP_TLS_SOCKET_SETOPT_FAILED

failed to set/get socket option

ESP_ERR_ESP_TLS_CONNECTION_TIMEOUT

new connection in esp_tls_low_level_conn connection timeouted

ESP_ERR_ESP_TLS_SE_FAILED

ESP_ERR_ESP_TLS_TCP_CLOSED_FIN

ESP_ERR_ESP_TLS_SERVER_HANDSHAKE_TIMEOUT

TLS handshake timeout

ESP_ERR_MBEDTLS_CERT_PARTLY_OK

mbedtls parse certificates was partly successful

ESP_ERR_MBEDTLS_CTR_DRBG_SEED_FAILED

mbedtls api returned error

ESP_ERR_MBEDTLS_SSL_SET_HOSTNAME_FAILED

mbedtls api returned error

ESP_ERR_MBEDTLS_SSL_CONFIG_DEFAULTS_FAILED

mbedtls api returned error

ESP_ERR_MBEDTLS_SSL_CONF_ALPN_PROTOCOLS_FAILED

mbedtls api returned error

ESP_ERR_MBEDTLS_X509_CRT_PARSE_FAILED

mbedtls api returned error

ESP_ERR_MBEDTLS_SSL_CONF_OWN_CERT_FAILED

mbedtls api returned error

ESP_ERR_MBEDTLS_SSL_SETUP_FAILED

mbedtls api returned error

ESP_ERR_MBEDTLS_SSL_WRITE_FAILED

mbedtls api returned error

ESP_ERR_MBEDTLS_PK_PARSE_KEY_FAILED

mbedtls api returned failed

ESP_ERR_MBEDTLS_SSL_HANDSHAKE_FAILED

mbedtls api returned failed

ESP_ERR_MBEDTLS_SSL_CONF_PSK_FAILED

mbedtls api returned failed

ESP_ERR_MBEDTLS_SSL_TICKET_SETUP_FAILED

mbedtls api returned failed

ESP_ERR_MBEDTLS_SSL_READ_FAILED

mbedtls api returned failed

ESP_ERR_WOLFSSL_SSL_SET_HOSTNAME_FAILED

wolfSSL api returned error

ESP_ERR_WOLFSSL_SSL_CONF_ALPN_PROTOCOLS_FAILED

wolfSSL api returned error

ESP_ERR_WOLFSSL_CERT_VERIFY_SETUP_FAILED

wolfSSL api returned error

ESP_ERR_WOLFSSL_KEY_VERIFY_SETUP_FAILED

wolfSSL api returned error

ESP_ERR_WOLFSSL_SSL_HANDSHAKE_FAILED

wolfSSL api returned failed

ESP_ERR_WOLFSSL_CTX_SETUP_FAILED

wolfSSL api returned failed

ESP_ERR_WOLFSSL_SSL_SETUP_FAILED

wolfSSL api returned failed

ESP_ERR_WOLFSSL_SSL_WRITE_FAILED

wolfSSL api returned failed

ESP_TLS_ERR_SSL_WANT_READ

Definition of errors reported from IO API (potentially non-blocking) in case of error:

- esp_tls_conn_read()

- esp_tls_conn_write()

ESP_TLS_ERR_SSL_WANT_WRITE

ESP_TLS_ERR_SSL_TIMEOUT

### Type Definitions

typedef struct esp_tls_last_error *esp_tls_error_handle_t

typedef struct esp_tls_last_error esp_tls_last_error_t

Error structure containing relevant errors in case tls error occurred.

### Enumerations

enum esp_tls_error_type_t

Definition of different types/sources of error codes reported from different components

Values:

enumerator ESP_TLS_ERR_TYPE_UNKNOWN

enumerator ESP_TLS_ERR_TYPE_SYSTEM

System error – errno

enumerator ESP_TLS_ERR_TYPE_MBEDTLS

Error code from mbedTLS library

enumerator ESP_TLS_ERR_TYPE_MBEDTLS_CERT_FLAGS

Certificate flags defined in mbedTLS

enumerator ESP_TLS_ERR_TYPE_ESP

ESP-IDF error type – esp_err_t

enumerator ESP_TLS_ERR_TYPE_WOLFSSL

Error code from wolfSSL library

enumerator ESP_TLS_ERR_TYPE_WOLFSSL_CERT_FLAGS

Certificate flags defined in wolfSSL

enumerator ESP_TLS_ERR_TYPE_MAX

Last err type – invalid entry

此文档对您有帮助吗？

- 反馈已收到，谢谢！

- 如果您有其他意见，欢迎填写乐鑫文档反馈表。

- 我们重视您的反馈。

- 您可以填写乐鑫文档反馈表告诉我们如何改进该文档。
