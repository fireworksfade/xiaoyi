来源：https://docs.espressif.com/projects/esp-idf/zh_CN/v5.5.4/esp32/api-reference/protocols/mqtt.html

# ESP-MQTT

## 概述

ESP-MQTT 是 MQTT 协议客户端的实现，MQTT 是一种基于发布/订阅模式的轻量级消息传输协议。ESP-MQTT 当前支持 MQTT v5.0。

## 特性

- 支持基于 TCP 的 MQTT、基于 Mbed TLS 的 SSL、基于 WebSocket 的 MQTT 以及基于 WebSocket Secure 的 MQTT

- 通过 URI 简化配置流程

- 多个实例（一个应用程序中有多个客户端）

- 支持订阅、发布、认证、遗嘱消息、保持连接心跳机制以及 3 个服务质量 (QoS) 级别（组成全功能客户端）

## 应用示例

- protocols/mqtt/tcp 演示了如何通过 TCP 实现 MQTT 通信（默认端口 1883）。

- protocols/mqtt/ssl 演示了如何使用 SSL 传输来实现基于 TLS 的 MQTT 通信（默认端口 8883）。

- protocols/mqtt/ssl_ds 演示了如何使用数字签名外设进行身份验证，以实现基于 TLS 的 MQTT 通信（默认端口 8883）。

- protocols/mqtt/ssl_mutual_auth 演示了如何使用证书进行身份验证实现 MQTT 通信（默认端口 8883）。

- protocols/mqtt/ssl_psk 演示了如何使用预共享密钥进行身份验证，以实现基于 TLS 的 MQTT 通信（默认端口 8883）。

- protocols/mqtt/ws 演示了如何通过 WebSocket 实现 MQTT 通信（默认端口 80）。

- protocols/mqtt/wss 演示了如何通过 WebSocket Secure 实现 MQTT 通信（默认端口 443）。

- protocols/mqtt5 演示了如何使用 ESP-MQTT 库通过 MQTT v5.0 连接到代理。

- protocols/mqtt/custom_outbox 演示了如何自定义 ESP-MQTT 库中的 outbox。

## MQTT 消息重传

调用 `esp_mqtt_client_publish` 或其非阻塞形式 `esp_mqtt_client_enqueue`，可以创建新的 MQTT 消息。

QoS 0 的消息将只发送一次，QoS 1 和 2 具有不同行为，因为协议需要执行额外步骤来完成该过程。

ESP-MQTT 库将始终重新传输未确认的 QoS 1 和 2 发布消息，以避免连接错误导致信息丢失，虽然 MQTT 规范要求仅在重新连接且 Clean Session 标志设置为 0 时重新传输（针对此行为，将 `disable_clean_session` 设置为 true）。

可能需要重传的 QoS 1 和 2 消息总是处于排队状态，但若使用 `esp_mqtt_client_publish` 则会立即进行第一次传输尝试。未确认消息的重传将在 `message_retransmit_timeout` 之后进行。在 CONFIG_MQTT_OUTBOX_EXPIRED_TIMEOUT_MS 之后，消息会过期并被删除。如已设置 CONFIG_MQTT_REPORT_DELETED_MESSAGES，则会发送事件来通知用户。

## 配置

通过设置 `esp_mqtt_client_config_t` 结构体中的字段来进行配置。配置结构体包含以下子结构体，用于配置客户端的多种操作。

- `esp_mqtt_client_config_t::broker_t` - 允许设置地址和安全验证。

- `esp_mqtt_client_config_t::credentials_t` - 用于身份验证的客户端凭据。

- `esp_mqtt_client_config_t::session_t` - MQTT 会话相关配置。

- `esp_mqtt_client_config_t::network_t` - 网络相关配置。

- `esp_mqtt_client_config_t::task_t` - 允许配置 FreeRTOS 任务。

- `esp_mqtt_client_config_t::buffer_t` - 输入输出的缓冲区大小。

下文将详细介绍不同配置。

### 服务器

#### 地址

通过 `address` 结构体的 `uri` 字段或者 `hostname`、`transport` 以及 `port` 的组合，可以设置服务器地址。也可以选择设置 `path`，该字段对 WebSocket 连接而言非常有用。

使用 `uri` 字段的格式为 `scheme://hostname:port/path`。

- 当前支持 `mqtt`、`mqtts`、`ws` 和 `wss` 协议

- 基于 TCP 的 MQTT 示例：

  - `mqtt://mqtt.eclipseprojects.io`：基于 TCP 的 MQTT，默认端口 1883

  - `mqtt://mqtt.eclipseprojects.io:1884`：基于 TCP 的 MQTT，端口 1884

  - `mqtt://username:password@mqtt.eclipseprojects.io:1884`：基于 TCP 的 MQTT， 端口 1884，带有用户名和密码

- 基于 SSL 的 MQTT 示例：

  - `mqtts://mqtt.eclipseprojects.io`：基于 SSL 的 MQTT，端口 8883

  - `mqtts://mqtt.eclipseprojects.io:8884`：基于 SSL 的 MQTT，端口 8884

- 基于 WebSocket 的 MQTT 示例：

  - `ws://mqtt.eclipseprojects.io:80/mqtt`

- 基于 WebSocket Secure 的 MQTT 示例：

  - `wss://mqtt.eclipseprojects.io:443/mqtt`

- 最简配置：

`
const esp_mqtt_client_config_t mqtt_cfg = {
    .broker.address.uri = "mqtt://mqtt.eclipseprojects.io",
};
esp_mqtt_client_handle_t client = esp_mqtt_client_init(&mqtt_cfg);
esp_mqtt_client_register_event(client, ESP_EVENT_ANY_ID, mqtt_event_handler, client);
esp_mqtt_client_start(client);
`

备注

默认情况下，MQTT 客户端使用事件循环库来发布相关 MQTT 事件（已连接、已订阅、已发布等）。

#### 验证

为验证服务器身份，对于使用 TLS 的安全链接，必须设置 `verification` 结构体。 服务器证书可设置为 PEM 或 DER 格式。如要选择 DER 格式，必须设置等效 `certificate_len` 字段，否则应在 `certificate` 字段传入以空字符结尾的 PEM 格式字符串。

- 从服务器获取证书，例如：`mqtt.eclipseprojects.io`

`
openssl s_client -showcerts -connect mqtt.eclipseprojects.io:8883 < /dev/null \
2> /dev/null | openssl x509 -outform PEM > mqtt_eclipse_org.pem
`

- 检查示例应用程序：protocols/mqtt/ssl

- 配置：

`
const esp_mqtt_client_config_t mqtt_cfg = {
    .broker = {
      .address.uri = "mqtts://mqtt.eclipseprojects.io:8883",
      .verification.certificate = (const char *)mqtt_eclipse_org_pem_start,
    },
};
`

了解其他字段的详细信息，请查看 API 参考 以及 TLS 服务器验证。

### 客户端凭据

`credentials` 字段下包含所有客户端相关凭据。

- `username`：指向用于连接服务器用户名的指针，也可通过 URI 设置

- `client_id`：指向客户端 ID 的指针，默认为 `ESP32_%CHIPID%`，其中 `%CHIPID%` 是十六进制 MAC 地址的最后 3 个字节

#### 认证

可以通过 `authentication` 字段设置认证参数。客户端支持以下认证方式：

- `password`：使用密码

  - `certificate` 和 `key`：进行双向 TLS 身份验证，PEM 或 DER 格式均可

- `use_secure_element`：使用 ESP32 系列中的安全元素 (ATECC608A)

- `ds_data`：使用某些乐鑫设备的数字签名外设

### 会话

使用 `session` 字段进行 MQTT 会话相关配置。

#### 遗嘱消息 (LWT)

通过设置 `last_will` 结构体的以下字段，MQTT 会在一个客户端意外断开连接时通过遗嘱消息通知其他客户端。

- `topic`：指向 LWT 消息主题的指针

- `msg`：指向 LWT 消息的指针

- `msg_len`：LWT 消息的长度，`msg` 不以空字符结尾时需要该字段

- `qos`：LWT 消息的服务质量

- `retain`：指定 LWT 消息的保留标志

### 在项目配置菜单中设置 MQTT

通过 `idf.py menuconfig`，可以在 `Component config` > `ESP-MQTT Configuration` 中找到 MQTT 设置。

相关设置如下：

- CONFIG_MQTT_PROTOCOL_311：启用 MQTT 协议 3.1.1 版本

- CONFIG_MQTT_TRANSPORT_SSL 和 CONFIG_MQTT_TRANSPORT_WEBSOCKET：启用特定 MQTT 传输层，例如 SSL、WEBSOCKET 和 WEBSOCKET_SECURE

- CONFIG_MQTT_CUSTOM_OUTBOX：禁用 mqtt_outbox 默认实现，因此可以提供特定实现

## 事件

MQTT 客户端可能会发布以下事件：

- `MQTT_EVENT_BEFORE_CONNECT`：客户端已初始化并即将开始连接至服务器。

- `MQTT_EVENT_CONNECTED`：客户端已成功连接至服务器。客户端已准备好收发数据。

- `MQTT_EVENT_DISCONNECTED`：由于无法读取或写入数据，例如因为服务器无法使用，客户端已终止连接。

- `MQTT_EVENT_SUBSCRIBED`：服务器已确认客户端的订阅请求。事件数据将包含订阅消息的消息 ID。

- `MQTT_EVENT_UNSUBSCRIBED`：服务器已确认客户端的退订请求。事件数据将包含退订消息的消息 ID。

- `MQTT_EVENT_PUBLISHED`：服务器已确认客户端的发布消息。消息将仅针对 QoS 级别 1 和 2 发布，因为级别 0 不会进行确认。事件数据将包含发布消息的消息 ID。

- `MQTT_EVENT_DATA`：客户端已收到发布消息。事件数据包含：消息 ID、发布消息所属主题名称、收到的数据及其长度。对于超出内部缓冲区的数据，将发布多个 `MQTT_EVENT_DATA`，并更新事件数据的 `current_data_offset` 和 `total_data_len` 以跟踪碎片化消息。

- `MQTT_EVENT_ERROR`：客户端遇到错误。使用事件数据 `error_handle` 字段中的 `error_type`，可以发现错误。错误类型决定 `error_handle` 结构体的哪些部分会被填充。

## API 参考

### Header File

- components/mqtt/esp-mqtt/include/mqtt_client.h

- This header file can be included with:

`
#include "mqtt_client.h"
`

- This header file is a part of the API provided by the `mqtt` component. To declare that your component depends on `mqtt`, add the following to your CMakeLists.txt:

`
REQUIRES mqtt
`

or

`
PRIV_REQUIRES mqtt
`

### Functions

esp_mqtt_client_handle_t esp_mqtt_client_init(const esp_mqtt_client_config_t *config)

Creates MQTT client handle based on the configuration.

参数:

config -- MQTT configuration structure

返回:

mqtt_client_handle if successfully created, NULL on error

esp_err_t esp_mqtt_client_set_uri(esp_mqtt_client_handle_t client, const char *uri)

Sets MQTT connection URI. This API is usually used to overrides the URI configured in esp_mqtt_client_init.

参数:

- client -- MQTT client handle

- uri --

返回:

ESP_FAIL if URI parse error, ESP_OK on success

esp_err_t esp_mqtt_client_start(esp_mqtt_client_handle_t client)

Starts MQTT client with already created client handle.

参数:

client -- MQTT client handle

返回:

ESP_OK on success ESP_ERR_INVALID_ARG on wrong initialization ESP_FAIL on other error

esp_err_t esp_mqtt_client_reconnect(esp_mqtt_client_handle_t client)

This api is typically used to force reconnection upon a specific event.

参数:

client -- MQTT client handle

返回:

ESP_OK on success ESP_ERR_INVALID_ARG on wrong initialization ESP_FAIL if client is in invalid state

esp_err_t esp_mqtt_client_disconnect(esp_mqtt_client_handle_t client)

This api is typically used to force disconnection from the broker.

参数:

client -- MQTT client handle

返回:

ESP_OK on success ESP_ERR_INVALID_ARG on wrong initialization

esp_err_t esp_mqtt_client_stop(esp_mqtt_client_handle_t client)

Stops MQTT client tasks.

- Notes:

- Cannot be called from the MQTT event handler

参数:

client -- MQTT client handle

返回:

ESP_OK on success ESP_ERR_INVALID_ARG on wrong initialization ESP_FAIL if client is in invalid state

int esp_mqtt_client_subscribe_single(esp_mqtt_client_handle_t client, const char *topic, int qos)

Subscribe the client to defined topic with defined qos.

Notes:

- Client must be connected to send subscribe message

- This API is could be executed from a user task or from a MQTT event callback i.e. internal MQTT task (API is protected by internal mutex, so it might block if a longer data receive operation is in progress.

- `esp_mqtt_client_subscribe` could be used to call this function.

参数:

- client -- MQTT client handle

- topic -- topic filter to subscribe

- qos -- Max qos level of the subscription

返回:

message_id of the subscribe message on success -1 on failure -2 in case of full outbox.

int esp_mqtt_client_subscribe_multiple(esp_mqtt_client_handle_t client, const esp_mqtt_topic_t *topic_list, int size)

Subscribe the client to a list of defined topics with defined qos.

Notes:

- Client must be connected to send subscribe message

- This API is could be executed from a user task or from a MQTT event callback i.e. internal MQTT task (API is protected by internal mutex, so it might block if a longer data receive operation is in progress.

- `esp_mqtt_client_subscribe` could be used to call this function.

参数:

- client -- MQTT client handle

- topic_list -- List of topics to subscribe

- size -- size of topic_list

返回:

message_id of the subscribe message on success -1 on failure -2 in case of full outbox.

int esp_mqtt_client_unsubscribe(esp_mqtt_client_handle_t client, const char *topic)

Unsubscribe the client from defined topic.

Notes:

- Client must be connected to send unsubscribe message

- It is thread safe, please refer to `esp_mqtt_client_subscribe_single` for details

参数:

- client -- MQTT client handle

- topic --

返回:

message_id of the subscribe message on success -1 on failure

int esp_mqtt_client_publish(esp_mqtt_client_handle_t client, const char *topic, const char *data, int len, int qos, int retain)

Client to send a publish message to the broker.

Notes:

- This API might block for several seconds, either due to network timeout (10s) or if publishing payloads longer than internal buffer (due to message fragmentation)

- Client doesn't have to be connected for this API to work, enqueueing the messages with qos>1 (returning -1 for all the qos=0 messages if disconnected). If MQTT_SKIP_PUBLISH_IF_DISCONNECTED is enabled, this API will not attempt to publish when the client is not connected and will always return -1.

- It is thread safe, please refer to `esp_mqtt_client_subscribe` for details

参数:

- client -- MQTT client handle

- topic -- topic string

- data -- payload string (set to NULL, sending empty payload message)

- len -- data length, if set to 0, length is calculated from payload string

- qos -- QoS of publish message

- retain -- retain flag

返回:

message_id of the publish message (for QoS 0 message_id will always be zero) on success. -1 on failure, -2 in case of full outbox.

int esp_mqtt_client_enqueue(esp_mqtt_client_handle_t client, const char *topic, const char *data, int len, int qos, int retain, bool store)

Enqueue a message to the outbox, to be sent later. Typically used for messages with qos>0, but could be also used for qos=0 messages if store=true.

This API generates and stores the publish message into the internal outbox and the actual sending to the network is performed in the mqtt-task context (in contrast to the esp_mqtt_client_publish() which sends the publish message immediately in the user task's context). Thus, it could be used as a non blocking version of esp_mqtt_client_publish().

参数:

- client -- MQTT client handle

- topic -- topic string

- data -- payload string (set to NULL, sending empty payload message)

- len -- data length, if set to 0, length is calculated from payload string

- qos -- QoS of publish message

- retain -- retain flag

- store -- if true, all messages are enqueued; otherwise only QoS 1 and QoS 2 are enqueued

返回:

message_id if queued successfully, -1 on failure, -2 in case of full outbox.

esp_err_t esp_mqtt_client_destroy(esp_mqtt_client_handle_t client)

Destroys the client handle.

Notes:

- Cannot be called from the MQTT event handler

参数:

client -- MQTT client handle

返回:

ESP_OK ESP_ERR_INVALID_ARG on wrong initialization

esp_err_t esp_mqtt_set_config(esp_mqtt_client_handle_t client, const esp_mqtt_client_config_t *config)

Set configuration structure, typically used when updating the config (i.e. on "before_connect" event.

Notes:

- When calling this function make sure to have all the intendend configurations set, otherwise default values are set.

参数:

- client -- MQTT client handle

- config -- MQTT configuration structure

返回:

ESP_ERR_NO_MEM if failed to allocate ESP_ERR_INVALID_ARG if conflicts on transport configuration. ESP_OK on success

esp_err_t esp_mqtt_client_register_event(esp_mqtt_client_handle_t client, esp_mqtt_event_id_t event, esp_event_handler_t event_handler, void *event_handler_arg)

Registers MQTT event.

参数:

- client -- MQTT client handle

- event -- event type

- event_handler -- handler callback

- event_handler_arg -- handlers context

返回:

ESP_ERR_NO_MEM if failed to allocate ESP_ERR_INVALID_ARG on wrong initialization ESP_OK on success

esp_err_t esp_mqtt_client_unregister_event(esp_mqtt_client_handle_t client, esp_mqtt_event_id_t event, esp_event_handler_t event_handler)

Unregisters mqtt event.

参数:

- client -- mqtt client handle

- event -- event ID

- event_handler -- handler to unregister

返回:

ESP_ERR_NO_MEM if failed to allocate ESP_ERR_INVALID_ARG on invalid event ID ESP_OK on success

int esp_mqtt_client_get_outbox_size(esp_mqtt_client_handle_t client)

Get outbox size.

参数:

client -- MQTT client handle

返回:

outbox size 0 on wrong initialization

esp_err_t esp_mqtt_dispatch_custom_event(esp_mqtt_client_handle_t client, esp_mqtt_event_t *event)

Dispatch user event to the mqtt internal event loop.

参数:

- client -- MQTT client handle

- event -- MQTT event handle structure

返回:

ESP_OK on success ESP_ERR_TIMEOUT if the event couldn't be queued (ref also CONFIG_MQTT_EVENT_QUEUE_SIZE)

esp_transport_handle_t esp_mqtt_client_get_transport(esp_mqtt_client_handle_t client, char *transport_scheme)

Get a transport from the scheme.

Allows extra settings to be made on the selected transport, for convenience the scheme used by the mqtt client are defined as MQTT_OVER_TCP_SCHEME, MQTT_OVER_SSL_SCHEME, MQTT_OVER_WS_SCHEME and MQTT_OVER_WSS_SCHEME If the transport_scheme is NULL and the client was set with a custom transport the custom transport will be returned.

Notes:

- This function should be called only on MQTT_EVENT_BEFORE_CONNECT.

- The intetion is to provide a way to set different configurations than the ones available from client config.

- If esp_mqtt_client_destroy is called the returned pointer will be invalidated.

- All the required settings should be made in the MQTT_EVENT_BEFORE_CONNECT event handler

参数:

- client -- MQTT client handle

- transport_scheme -- Transport handle to search for.

返回:

the transport handle NULL in case of error

### Structures

struct esp_mqtt_error_codes

MQTT error code structure to be passed as a contextual information into ERROR event

Important: This structure extends `esp_tls_last_error` error structure and is backward compatible with it (so might be down-casted and treated as `esp_tls_last_error` error, but recommended to update applications if used this way previously)

Use this structure directly checking error_type first and then appropriate error code depending on the source of the error:

| error_type | related member variables | note | | MQTT_ERROR_TYPE_TCP_TRANSPORT | esp_tls_last_esp_err, esp_tls_stack_err, esp_tls_cert_verify_flags, sock_errno | Error reported from tcp_transport/esp-tls | | MQTT_ERROR_TYPE_CONNECTION_REFUSED | connect_return_code | Internal error reported from MQTT broker on connection |

Public Members

esp_err_t esp_tls_last_esp_err

last esp_err code reported from esp-tls component

int esp_tls_stack_err

tls specific error code reported from underlying tls stack

int esp_tls_cert_verify_flags

tls flags reported from underlying tls stack during certificate verification

esp_mqtt_error_type_t error_type

error type referring to the source of the error

esp_mqtt_connect_return_code_t connect_return_code

connection refused error code reported from MQTT* broker on connection

int esp_transport_sock_errno

errno from the underlying socket

struct esp_mqtt_event_t

MQTT event configuration structure

Public Members

esp_mqtt_event_id_t event_id

MQTT event type

esp_mqtt_client_handle_t client

MQTT client handle for this event

char *data

Data associated with this event

int data_len

Length of the data for this event

int total_data_len

Total length of the data (longer data are supplied with multiple events)

int current_data_offset

Actual offset for the data associated with this event

char *topic

Topic associated with this event

int topic_len

Length of the topic for this event associated with this event

int msg_id

MQTT messaged id of message

int session_present

MQTT session_present flag for connection event

esp_mqtt_error_codes_t *error_handle

esp-mqtt error handle including esp-tls errors as well as internal MQTT errors

bool retain

Retained flag of the message associated with this event

int qos

QoS of the messages associated with this event

bool dup

dup flag of the message associated with this event

esp_mqtt_protocol_ver_t protocol_ver

MQTT protocol version used for connection, defaults to value from menuconfig

struct esp_mqtt_client_config_t

MQTT client configuration structure

- Default values can be set via menuconfig

- All certificates and key data could be passed in PEM or DER format. PEM format must have a terminating NULL character and the related len field set to 0. DER format requires a related len field set to the correct length.

Public Members

struct esp_mqtt_client_config_t::broker_t broker

Broker address and security verification

struct esp_mqtt_client_config_t::credentials_t credentials

User credentials for broker

struct esp_mqtt_client_config_t::session_t session

MQTT session configuration.

struct esp_mqtt_client_config_t::network_t network

Network configuration

struct esp_mqtt_client_config_t::task_t task

FreeRTOS task configuration.

struct esp_mqtt_client_config_t::buffer_t buffer

Buffer size configuration.

struct esp_mqtt_client_config_t::outbox_config_t outbox

Outbox configuration.

struct broker_t

Broker related configuration

Public Members

struct esp_mqtt_client_config_t::broker_t::address_t address

Broker address configuration

struct esp_mqtt_client_config_t::broker_t::verification_t verification

Security verification of the broker

struct address_t

Broker address

- uri have precedence over other fields

- If uri isn't set at least hostname, transport and port should.

Public Members

const char *uri

Complete MQTT broker URI

const char *hostname

Hostname, to set ipv4 pass it as string)

esp_mqtt_transport_t transport

Selects transport

const char *path

Path in the URI

uint32_t port

MQTT server port

struct verification_t

Broker identity verification

If fields are not set broker's identity isn't verified. it's recommended to set the options in this struct for security reasons.

Public Members

bool use_global_ca_store

Use a global ca_store, look esp-tls documentation for details.

esp_err_t (*crt_bundle_attach)(void *conf)

Pointer to ESP x509 Certificate Bundle attach function for the usage of certificate bundles. Client only attach the bundle, the clean up must be done by the user.

const char *certificate

Certificate data, default is NULL. It's not copied nor freed by the client, user needs to clean up.

size_t certificate_len

Length of the buffer pointed to by certificate.

const struct psk_key_hint *psk_hint_key

Pointer to PSK struct defined in esp_tls.h to enable PSK authentication (as alternative to certificate verification). PSK is enabled only if there are no other ways to verify broker. It's not copied nor freed by the client, user needs to clean up.

bool skip_cert_common_name_check

Skip any validation of server certificate CN field, this reduces the security of TLS and makes the MQTT client susceptible to MITM attacks

const char **alpn_protos

NULL-terminated list of supported application protocols to be used for ALPN.

const char *common_name

Pointer to the string containing server certificate common name. If non-NULL, server certificate CN must match this name, If NULL, server certificate CN must match hostname. This is ignored if skip_cert_common_name_check=true. It's not copied nor freed by the client, user needs to clean up.

struct buffer_t

Client buffer size configuration

Client have two buffers for input and output respectivelly.

Public Members

int size

size of MQTT send/receive buffer

int out_size

size of MQTT output buffer. If not defined, defaults to the size defined by `buffer_size`

struct credentials_t

Client related credentials for authentication.

Public Members

const char *username

MQTT username

const char *client_id

Set MQTT client identifier. Ignored if set_null_client_id == true If NULL set the default client id. Default client id is `ESP32_CHIPID%` where `CHIPID%` are last 3 bytes of MAC address in hex format

bool set_null_client_id

Selects a NULL client id

struct esp_mqtt_client_config_t::credentials_t::authentication_t authentication

Client authentication

struct authentication_t

Client authentication

Fields related to client authentication by broker

For mutual authentication using TLS, user could select certificate and key, secure element or digital signature peripheral if available.

Public Members

const char *password

MQTT password

const char *certificate

Certificate for ssl mutual authentication, not required if mutual authentication is not needed. Must be provided with `key`. It's not copied nor freed by the client, user needs to clean up.

size_t certificate_len

Length of the buffer pointed to by certificate.

const char *key

Private key for SSL mutual authentication, not required if mutual authentication is not needed. If it is not NULL, also `certificate` has to be provided. It's not copied nor freed by the client, user needs to clean up.

size_t key_len

Length of the buffer pointed to by key.

const char *key_password

Client key decryption password, not PEM nor DER, if provided `key_password_len` must be correctly set.

int key_password_len

Length of the password pointed to by `key_password`

bool use_secure_element

Enable secure element, available in ESP32-ROOM-32SE, for SSL connection

void *ds_data

Carrier of handle for digital signature parameters, digital signature peripheral is available in some Espressif devices. It's not copied nor freed by the client, user needs to clean up.

bool use_ecdsa_peripheral

Enable ECDSA peripheral, available in some Espressif devices.

uint8_t ecdsa_key_efuse_blk

ECDSA key block number from efuse, available in some Espressif devices.

struct network_t

Network related configuration

Public Members

int reconnect_timeout_ms

Reconnect to the broker after this value in miliseconds if auto reconnect is not disabled (defaults to 10s)

int timeout_ms

Abort network operation if it is not completed after this value, in milliseconds (defaults to 10s).

int refresh_connection_after_ms

Refresh connection after this value (in milliseconds)

bool disable_auto_reconnect

Client will reconnect to server (when errors/disconnect). Set `disable_auto_reconnect=true` to disable

esp_transport_keep_alive_t tcp_keep_alive_cfg

Transport keep-alive config

esp_transport_handle_t transport

Custom transport handle to use, leave it NULL to allow MQTT client create or recreate its own. Warning: The transport should be valid during the client lifetime and is destroyed when esp_mqtt_client_destroy is called.

struct ifreq *if_name

The name of interface for data to go through. Use the default interface without setting

struct outbox_config_t

Client outbox configuration options.

Public Members

uint64_t limit

Size limit for the outbox in bytes.

struct session_t

MQTT Session related configuration

Public Members

struct esp_mqtt_client_config_t::session_t::last_will_t last_will

Last will configuration

bool disable_clean_session

MQTT clean session, default clean_session is true

int keepalive

MQTT keepalive, default is 120 seconds When configuring this value, keep in mind that the client attempts to communicate with the broker at half the interval that is actually set. This conservative approach allows for more attempts before the broker's timeout occurs

bool disable_keepalive

Set `disable_keepalive=true` to turn off keep-alive mechanism, keepalive is active by default. Note: setting the config value `keepalive` to `0` doesn't disable keepalive feature, but uses a default keepalive period

esp_mqtt_protocol_ver_t protocol_ver

MQTT protocol version used for connection.

int message_retransmit_timeout

timeout for retransmitting of failed packet

struct last_will_t

Last Will and Testament message configuration.

Public Members

const char *topic

LWT (Last Will and Testament) message topic

const char *msg

LWT message, may be NULL terminated

int msg_len

LWT message length, if msg isn't NULL terminated must have the correct length

int qos

LWT message QoS

int retain

LWT retained message flag

struct task_t

Client task configuration

Public Members

int priority

MQTT task priority

int stack_size

MQTT task stack size

struct topic_t

Topic definition struct

Public Members

const char *filter

Topic filter to subscribe

int qos

Max QoS level of the subscription

### Macros

MQTT_OVER_TCP_SCHEME

MQTT_OVER_SSL_SCHEME

MQTT_OVER_WS_SCHEME

MQTT_OVER_WSS_SCHEME

MQTT_ERROR_TYPE_ESP_TLS

MQTT_ERROR_TYPE_TCP_TRANSPORT error type hold all sorts of transport layer errors, including ESP-TLS error, but in the past only the errors from MQTT_ERROR_TYPE_ESP_TLS layer were reported, so the ESP-TLS error type is re-defined here for backward compatibility

esp_mqtt_client_subscribe(client_handle, topic_type, qos_or_size)

Convenience macro to select subscribe function to use.

Notes:

- Usage of `esp_mqtt_client_subscribe_single` is the same as previous esp_mqtt_client_subscribe, refer to it for details.

参数:

- client_handle -- MQTT client handle

- topic_type -- Needs to be char* for single subscription or `esp_mqtt_topic_t` for multiple topics

- qos_or_size -- It's either a qos when subscribing to a single topic or the size of the subscription array when subscribing to multiple topics.

返回:

message_id of the subscribe message on success -1 on failure -2 in case of full outbox.

### Type Definitions

typedef struct esp_mqtt_client *esp_mqtt_client_handle_t

typedef enum esp_mqtt_event_id_t esp_mqtt_event_id_t

MQTT event types.

User event handler receives context data in `esp_mqtt_event_t` structure with

- client - MQTT client handle

- various other data depending on event type

typedef enum esp_mqtt_connect_return_code_t esp_mqtt_connect_return_code_t

MQTT connection error codes propagated via ERROR event

typedef enum esp_mqtt_error_type_t esp_mqtt_error_type_t

MQTT connection error codes propagated via ERROR event

typedef enum esp_mqtt_transport_t esp_mqtt_transport_t

typedef enum esp_mqtt_protocol_ver_t esp_mqtt_protocol_ver_t

MQTT protocol version used for connection

typedef struct esp_mqtt_error_codes esp_mqtt_error_codes_t

MQTT error code structure to be passed as a contextual information into ERROR event

Important: This structure extends `esp_tls_last_error` error structure and is backward compatible with it (so might be down-casted and treated as `esp_tls_last_error` error, but recommended to update applications if used this way previously)

Use this structure directly checking error_type first and then appropriate error code depending on the source of the error:

| error_type | related member variables | note | | MQTT_ERROR_TYPE_TCP_TRANSPORT | esp_tls_last_esp_err, esp_tls_stack_err, esp_tls_cert_verify_flags, sock_errno | Error reported from tcp_transport/esp-tls | | MQTT_ERROR_TYPE_CONNECTION_REFUSED | connect_return_code | Internal error reported from MQTT broker on connection |

typedef struct esp_mqtt_event_t esp_mqtt_event_t

MQTT event configuration structure

typedef esp_mqtt_event_t *esp_mqtt_event_handle_t

typedef struct esp_mqtt_client_config_t esp_mqtt_client_config_t

MQTT client configuration structure

- Default values can be set via menuconfig

- All certificates and key data could be passed in PEM or DER format. PEM format must have a terminating NULL character and the related len field set to 0. DER format requires a related len field set to the correct length.

typedef struct topic_t esp_mqtt_topic_t

Topic definition struct

### Enumerations

enum esp_mqtt_event_id_t

MQTT event types.

User event handler receives context data in `esp_mqtt_event_t` structure with

- client - MQTT client handle

- various other data depending on event type

Values:

enumerator MQTT_EVENT_ANY

enumerator MQTT_EVENT_ERROR

on error event, additional context: connection return code, error handle from esp_tls (if supported)

enumerator MQTT_EVENT_CONNECTED

connected event, additional context: session_present flag

enumerator MQTT_EVENT_DISCONNECTED

disconnected event

enumerator MQTT_EVENT_SUBSCRIBED

subscribed event, additional context:

- msg_id message id

- error_handle `error_type` in case subscribing failed

- data pointer to broker response, check for errors.

- data_len length of the data for this event

enumerator MQTT_EVENT_UNSUBSCRIBED

unsubscribed event, additional context: msg_id

enumerator MQTT_EVENT_PUBLISHED

published event, additional context: msg_id

enumerator MQTT_EVENT_DATA

data event, additional context:

- msg_id message id

- topic pointer to the received topic

- topic_len length of the topic

- data pointer to the received data

- data_len length of the data for this event

- current_data_offset offset of the current data for this event

- total_data_len total length of the data received

- retain retain flag of the message

- qos QoS level of the message

- dup dup flag of the message Note: Multiple MQTT_EVENT_DATA could be fired for one message, if it is longer than internal buffer. In that case only first event contains topic pointer and length, other contain data only with current data length and current data offset updating.

enumerator MQTT_EVENT_BEFORE_CONNECT

The event occurs before connecting

enumerator MQTT_EVENT_DELETED

Notification on delete of one message from the internal outbox, if the message couldn't have been sent or acknowledged before expiring defined in OUTBOX_EXPIRED_TIMEOUT_MS. (events are not posted upon deletion of successfully acknowledged messages)

- This event id is posted only if MQTT_REPORT_DELETED_MESSAGES==1

- Additional context: msg_id (id of the deleted message, always 0 for QoS = 0 messages).

enumerator MQTT_USER_EVENT

Custom event used to queue tasks into mqtt event handler All fields from the esp_mqtt_event_t type could be used to pass an additional context data to the handler.

enum esp_mqtt_connect_return_code_t

MQTT connection error codes propagated via ERROR event

Values:

enumerator MQTT_CONNECTION_ACCEPTED

Connection accepted

enumerator MQTT_CONNECTION_REFUSE_PROTOCOL

MQTT connection refused reason: Wrong protocol

enumerator MQTT_CONNECTION_REFUSE_ID_REJECTED

MQTT connection refused reason: ID rejected

enumerator MQTT_CONNECTION_REFUSE_SERVER_UNAVAILABLE

MQTT connection refused reason: Server unavailable

enumerator MQTT_CONNECTION_REFUSE_BAD_USERNAME

MQTT connection refused reason: Wrong user

enumerator MQTT_CONNECTION_REFUSE_NOT_AUTHORIZED

MQTT connection refused reason: Wrong username or password

enum esp_mqtt_error_type_t

MQTT connection error codes propagated via ERROR event

Values:

enumerator MQTT_ERROR_TYPE_NONE

enumerator MQTT_ERROR_TYPE_TCP_TRANSPORT

enumerator MQTT_ERROR_TYPE_CONNECTION_REFUSED

enumerator MQTT_ERROR_TYPE_SUBSCRIBE_FAILED

enum esp_mqtt_transport_t

Values:

enumerator MQTT_TRANSPORT_UNKNOWN

enumerator MQTT_TRANSPORT_OVER_TCP

MQTT over TCP, using scheme: `MQTT`

enumerator MQTT_TRANSPORT_OVER_SSL

MQTT over SSL, using scheme: `MQTTS`

enumerator MQTT_TRANSPORT_OVER_WS

MQTT over Websocket, using scheme:: `ws`

enumerator MQTT_TRANSPORT_OVER_WSS

MQTT over Websocket Secure, using scheme: `wss`

enum esp_mqtt_protocol_ver_t

MQTT protocol version used for connection

Values:

enumerator MQTT_PROTOCOL_UNDEFINED

enumerator MQTT_PROTOCOL_V_3_1

enumerator MQTT_PROTOCOL_V_3_1_1

enumerator MQTT_PROTOCOL_V_5

### Header File

- components/mqtt/esp-mqtt/include/mqtt5_client.h

- This header file can be included with:

`
#include "mqtt5_client.h"
`

- This header file is a part of the API provided by the `mqtt` component. To declare that your component depends on `mqtt`, add the following to your CMakeLists.txt:

`
REQUIRES mqtt
`

or

`
PRIV_REQUIRES mqtt
`

### Functions

esp_err_t esp_mqtt5_client_set_connect_property(esp_mqtt5_client_handle_t client, const esp_mqtt5_connection_property_config_t *connect_property)

Set MQTT5 client connect property configuration.

参数:

- client -- mqtt client handle

- connect_property -- connect property

返回:

ESP_ERR_NO_MEM if failed to allocate ESP_ERR_INVALID_ARG on wrong initialization ESP_FAIL on fail ESP_OK on success

esp_err_t esp_mqtt5_client_set_publish_property(esp_mqtt5_client_handle_t client, const esp_mqtt5_publish_property_config_t *property)

Set MQTT5 client publish property configuration.

This API will not store the publish property, it is one-time configuration. Before call `esp_mqtt_client_publish` to publish data, call this API to set publish property if have

参数:

- client -- mqtt client handle

- property -- publish property

返回:

ESP_ERR_INVALID_ARG on wrong initialization ESP_FAIL on fail ESP_OK on success

esp_err_t esp_mqtt5_client_set_subscribe_property(esp_mqtt5_client_handle_t client, const esp_mqtt5_subscribe_property_config_t *property)

Set MQTT5 client subscribe property configuration.

This API will not store the subscribe property, it is one-time configuration. Before call `esp_mqtt_client_subscribe` to subscribe topic, call this API to set subscribe property if have

参数:

- client -- mqtt client handle

- property -- subscribe property

返回:

ESP_ERR_INVALID_ARG on wrong initialization ESP_FAIL on fail ESP_OK on success

esp_err_t esp_mqtt5_client_set_unsubscribe_property(esp_mqtt5_client_handle_t client, const esp_mqtt5_unsubscribe_property_config_t *property)

Set MQTT5 client unsubscribe property configuration.

This API will not store the unsubscribe property, it is one-time configuration. Before call `esp_mqtt_client_unsubscribe` to unsubscribe topic, call this API to set unsubscribe property if have

参数:

- client -- mqtt client handle

- property -- unsubscribe property

返回:

ESP_ERR_INVALID_ARG on wrong initialization ESP_FAIL on fail ESP_OK on success

esp_err_t esp_mqtt5_client_set_disconnect_property(esp_mqtt5_client_handle_t client, const esp_mqtt5_disconnect_property_config_t *property)

Set MQTT5 client disconnect property configuration.

This API will not store the disconnect property, it is one-time configuration. Before call `esp_mqtt_client_disconnect` to disconnect connection, call this API to set disconnect property if have

参数:

- client -- mqtt client handle

- property -- disconnect property

返回:

ESP_ERR_NO_MEM if failed to allocate ESP_ERR_INVALID_ARG on wrong initialization ESP_FAIL on fail ESP_OK on success

esp_err_t esp_mqtt5_client_set_user_property(mqtt5_user_property_handle_t *user_property, esp_mqtt5_user_property_item_t item[], uint8_t item_num)

Set MQTT5 client user property configuration.

This API will allocate memory for user_property, please DO NOT forget `call esp_mqtt5_client_delete_user_property` after you use it. Before publish data, subscribe topic, unsubscribe, etc, call this API to set user property if have

参数:

- user_property -- user_property handle

- item -- array of user property data (eg. {{"var","val"},{"other","2"}})

- item_num -- number of items in user property data

返回:

ESP_ERR_NO_MEM if failed to allocate ESP_FAIL on fail ESP_OK on success

esp_err_t esp_mqtt5_client_get_user_property(mqtt5_user_property_handle_t user_property, esp_mqtt5_user_property_item_t *item, uint8_t *item_num)

Get MQTT5 client user property.

This API can use with `esp_mqtt5_client_get_user_property_count` to get list count of user property. And malloc number of count item array memory to store the user property data. Please DO NOT forget the item memory, key and value point in item memory when get user property data successfully.

参数:

- user_property -- user_property handle

- item -- point that store user property data

- item_num -- number of items in user property data

返回:

ESP_ERR_NO_MEM if failed to allocate ESP_FAIL on fail ESP_OK on success

uint8_t esp_mqtt5_client_get_user_property_count(mqtt5_user_property_handle_t user_property)

Get MQTT5 client user property list count.

参数:

user_property -- user_property handle

返回:

user property list count

void esp_mqtt5_client_delete_user_property(mqtt5_user_property_handle_t user_property)

Free the user property list.

This API will free the memory in user property list and free user_property itself

参数:

user_property -- user_property handle

### Structures

struct esp_mqtt5_connection_property_config_t

MQTT5 protocol connect properties and will properties configuration, more details refer to MQTT5 protocol document section 3.1.2.11 and 3.3.2.3

Public Members

uint32_t session_expiry_interval

The interval time of session expiry

uint32_t maximum_packet_size

The maximum packet size that we can receive

uint16_t receive_maximum

The maximum pakcket count that we process concurrently

uint16_t topic_alias_maximum

The maximum topic alias that we support

bool request_resp_info

This value to request Server to return Response information

bool request_problem_info

This value to indicate whether the reason string or user properties are sent in case of failures

mqtt5_user_property_handle_t user_property

The handle for user property, call function esp_mqtt5_client_set_user_property to set it

uint32_t will_delay_interval

The time interval that server delays publishing will message

uint32_t message_expiry_interval

The time interval that message expiry

bool payload_format_indicator

This value is to indicator will message payload format

const char *content_type

This value is to indicator will message content type, use a MIME content type string

const char *response_topic

Topic name for a response message

const char *correlation_data

Binary data for receiver to match the response message

uint16_t correlation_data_len

The length of correlation data

mqtt5_user_property_handle_t will_user_property

The handle for will message user property, call function esp_mqtt5_client_set_user_property to set it

struct esp_mqtt5_publish_property_config_t

MQTT5 protocol publish properties configuration, more details refer to MQTT5 protocol document section 3.3.2.3

Public Members

bool payload_format_indicator

This value is to indicator publish message payload format

uint32_t message_expiry_interval

The time interval that message expiry

uint16_t topic_alias

An interger value to identify the topic instead of using topic name string

const char *response_topic

Topic name for a response message

const char *correlation_data

Binary data for receiver to match the response message

uint16_t correlation_data_len

The length of correlation data

const char *content_type

This value is to indicator publish message content type, use a MIME content type string

mqtt5_user_property_handle_t user_property

The handle for user property, call function esp_mqtt5_client_set_user_property to set it

struct esp_mqtt5_subscribe_property_config_t

MQTT5 protocol subscribe properties configuration, more details refer to MQTT5 protocol document section 3.8.2.1

Public Members

uint16_t subscribe_id

A variable byte represents the identifier of the subscription

bool no_local_flag

Subscription Option to allow that server publish message that client sent

bool retain_as_published_flag

Subscription Option to keep the retain flag as published option

uint8_t retain_handle

Subscription Option to handle retain option

bool is_share_subscribe

Whether subscribe is a shared subscription

const char *share_name

The name of shared subscription which is a part of $share/{share_name}/{topic}

mqtt5_user_property_handle_t user_property

The handle for user property, call function esp_mqtt5_client_set_user_property to set it

struct esp_mqtt5_unsubscribe_property_config_t

MQTT5 protocol unsubscribe properties configuration, more details refer to MQTT5 protocol document section 3.10.2.1

Public Members

bool is_share_subscribe

Whether subscribe is a shared subscription

const char *share_name

The name of shared subscription which is a part of $share/{share_name}/{topic}

mqtt5_user_property_handle_t user_property

The handle for user property, call function esp_mqtt5_client_set_user_property to set it

struct esp_mqtt5_disconnect_property_config_t

MQTT5 protocol disconnect properties configuration, more details refer to MQTT5 protocol document section 3.14.2.2

Public Members

uint32_t session_expiry_interval

The interval time of session expiry

uint8_t disconnect_reason

The reason that connection disconnet, refer to mqtt5_error_reason_code

mqtt5_user_property_handle_t user_property

The handle for user property, call function esp_mqtt5_client_set_user_property to set it

struct esp_mqtt5_event_property_t

MQTT5 protocol for event properties

Public Members

bool payload_format_indicator

Payload format of the message

char *response_topic

Response topic of the message

int response_topic_len

Response topic length of the message

char *correlation_data

Correlation data of the message

uint16_t correlation_data_len

Correlation data length of the message

char *content_type

Content type of the message

int content_type_len

Content type length of the message

uint16_t subscribe_id

Subscription identifier of the message

mqtt5_user_property_handle_t user_property

The handle for user property, call function esp_mqtt5_client_delete_user_property to free the memory

struct esp_mqtt5_user_property_item_t

MQTT5 protocol for user property

Public Members

const char *key

Item key name

const char *value

Item value string

### Type Definitions

typedef struct esp_mqtt_client *esp_mqtt5_client_handle_t

typedef enum mqtt5_error_reason_code_t esp_mqtt5_error_reason_code_t

MQTT5 protocol error reason code, more details refer to MQTT5 protocol document section 2.4

typedef struct mqtt5_user_property_list_t *mqtt5_user_property_handle_t

MQTT5 user property handle

### Enumerations

enum mqtt5_error_reason_code_t

MQTT5 protocol error reason code, more details refer to MQTT5 protocol document section 2.4

Values:

enumerator MQTT5_UNSPECIFIED_ERROR

enumerator MQTT5_MALFORMED_PACKET

enumerator MQTT5_PROTOCOL_ERROR

enumerator MQTT5_IMPLEMENT_SPECIFIC_ERROR

enumerator MQTT5_UNSUPPORTED_PROTOCOL_VER

enumerator MQTT5_INVAILD_CLIENT_ID

enumerator MQTT5_INVALID_CLIENT_ID

enumerator MQTT5_BAD_USERNAME_OR_PWD

enumerator MQTT5_NOT_AUTHORIZED

enumerator MQTT5_SERVER_UNAVAILABLE

enumerator MQTT5_SERVER_BUSY

enumerator MQTT5_BANNED

enumerator MQTT5_SERVER_SHUTTING_DOWN

enumerator MQTT5_BAD_AUTH_METHOD

enumerator MQTT5_KEEP_ALIVE_TIMEOUT

enumerator MQTT5_SESSION_TAKEN_OVER

enumerator MQTT5_TOPIC_FILTER_INVAILD

enumerator MQTT5_TOPIC_FILTER_INVALID

enumerator MQTT5_TOPIC_NAME_INVAILD

enumerator MQTT5_TOPIC_NAME_INVALID

enumerator MQTT5_PACKET_IDENTIFIER_IN_USE

enumerator MQTT5_PACKET_IDENTIFIER_NOT_FOUND

enumerator MQTT5_RECEIVE_MAXIMUM_EXCEEDED

enumerator MQTT5_TOPIC_ALIAS_INVAILD

enumerator MQTT5_TOPIC_ALIAS_INVALID

enumerator MQTT5_PACKET_TOO_LARGE

enumerator MQTT5_MESSAGE_RATE_TOO_HIGH

enumerator MQTT5_QUOTA_EXCEEDED

enumerator MQTT5_ADMINISTRATIVE_ACTION

enumerator MQTT5_PAYLOAD_FORMAT_INVAILD

enumerator MQTT5_PAYLOAD_FORMAT_INVALID

enumerator MQTT5_RETAIN_NOT_SUPPORT

enumerator MQTT5_QOS_NOT_SUPPORT

enumerator MQTT5_USE_ANOTHER_SERVER

enumerator MQTT5_SERVER_MOVED

enumerator MQTT5_SHARED_SUBSCR_NOT_SUPPORTED

enumerator MQTT5_CONNECTION_RATE_EXCEEDED

enumerator MQTT5_MAXIMUM_CONNECT_TIME

enumerator MQTT5_SUBSCRIBE_IDENTIFIER_NOT_SUPPORT

enumerator MQTT5_WILDCARD_SUBSCRIBE_NOT_SUPPORT

此文档对您有帮助吗？

- 反馈已收到，谢谢！

- 如果您有其他意见，欢迎填写乐鑫文档反馈表。

- 我们重视您的反馈。

- 您可以填写乐鑫文档反馈表告诉我们如何改进该文档。
