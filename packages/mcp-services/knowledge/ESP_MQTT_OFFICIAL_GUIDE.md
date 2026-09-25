Source: https://docs.espressif.com/projects/esp-mqtt/en/latest/esp32/index.html

ESP-MQTT
[中文]
Overview
ESP-MQTT is an implementation of MQTT protocol client, which is a lightweight publish/subscribe messaging protocol. Now ESP-MQTT supports MQTT v5.0.

Features
Support MQTT over TCP, SSL with Mbed TLS, MQTT over WebSocket, and MQTT over WebSocket Secure

Easy to setup with URI

Multiple instances (multiple clients in one application)

Support subscribing, publishing, authentication, last will messages, keep alive pings, and all 3 Quality of Service (QoS) levels (it should be a fully functional client)

Application Examples
tcp demonstrates how to implement MQTT communication over TCP (default port 1883).

ssl demonstrates how to use SSL transport to implement MQTT communication over TLS (default port 8883).

ssl_ds demonstrates how to use digital signature peripheral for authentication to implement MQTT communication over TLS (default port 8883).

ssl_mutual_auth demonstrates how to use certificates for authentication to implement MQTT communication (default port 8883).

ssl_psk demonstrates how to use pre-shared keys for authentication to implement MQTT communication over TLS (default port 8883).

ws demonstrates how to implement MQTT communication over WebSocket (default port 80).

wss demonstrates how to implement MQTT communication over WebSocket Secure (default port 443).

mqtt5 demonstrates how to use ESP-MQTT library to connect to broker with MQTT v5.0.

custom_outbox demonstrates how to customize the outbox in the ESP-MQTT library.

MQTT Message Retransmission
A new MQTT message can be created by calling esp_mqtt_client_publish or its non-blocking counterpart esp_mqtt_client_enqueue.
Messages with QoS 0 are sent only once. QoS 1 and 2 behave differently since the protocol requires additional steps to complete the process.
The ESP-MQTT library opts to always retransmit unacknowledged QoS 1 and 2 publish messages to prevent data loss in faulty connections, even though the MQTT specification requires the re-transmission only on reconnect with Clean Session flag been set to 0 (set disable_clean_session to true for this behavior).
QoS 1 and 2 messages that may need retransmission are always enqueued, but first transmission try occurs immediately if esp_mqtt_client_publish is used. A transmission retry for unacknowledged messages will occur after message_retransmit_timeout. After CONFIG_MQTT_OUTBOX_EXPIRED_TIMEOUT_MS messages will expire and be deleted. If CONFIG_MQTT_REPORT_DELETED_MESSAGES is set, an event will be sent to notify the user.

Configuration
The configuration is made by setting fields in esp_mqtt_client_config_t struct. The configuration struct has the following sub structs to configure different aspects of the client operation.
esp_mqtt_client_config_t::broker_t - Allow to set address and security verification.

esp_mqtt_client_config_t::credentials_t - Client credentials for authentication.

esp_mqtt_client_config_t::session_t - Configuration for MQTT session aspects.

esp_mqtt_client_config_t::network_t - Networking related configuration.

esp_mqtt_client_config_t::task_t - Allow to configure FreeRTOS task.

esp_mqtt_client_config_t::buffer_t - Buffer size for input and output.

In the following sections, the most common aspects are detailed.
Broker
Address
Broker address can be set by usage of address struct. The configuration can be made by usage of uri field or the combination of hostname, transport and port. Optionally, path could be set, this field is useful in WebSocket connections.
The uri field is used in the format scheme://hostname:port/path.
Currently support mqtt, mqtts, ws, wss schemes

MQTT over TCP samples:
mqtt://mqtt.eclipseprojects.io: MQTT over TCP, default port 1883

mqtt://mqtt.eclipseprojects.io:1884: MQTT over TCP, port 1884

mqtt://username:password@mqtt.eclipseprojects.io:1884: MQTT over TCP,
port 1884, with username and password

MQTT over SSL samples:
mqtts://mqtt.eclipseprojects.io: MQTT over SSL, port 8883

mqtts://mqtt.eclipseprojects.io:8884: MQTT over SSL, port 8884

MQTT over WebSocket samples:
ws://mqtt.eclipseprojects.io:80/mqtt

MQTT over WebSocket Secure samples:
wss://mqtt.eclipseprojects.io:443/mqtt

Minimal configurations:

constesp_mqtt_client_config_tmqtt_cfg={.broker.address.uri="mqtt://mqtt.eclipseprojects.io",};esp_mqtt_client_handle_tclient=esp_mqtt_client_init(&mqtt_cfg);esp_mqtt_client_register_event(client,ESP_EVENT_ANY_ID,mqtt_event_handler,client);esp_mqtt_client_start(client);

Note
By default MQTT client uses event loop library to post related MQTT events (connected, subscribed, published, etc.).

Verification
For secure connections with TLS used, and to guarantee Broker’s identity, the verification struct must be set.
The broker certificate may be set in PEM or DER format. To select DER, the equivalent certificate_len field must be set. Otherwise, a null-terminated string in PEM format should be provided to certificate field.
Get certificate from server, example: mqtt.eclipseprojects.io
openssls_client-showcerts-connectmqtt.eclipseprojects.io:8883</dev/null \
2>/dev/null|opensslx509-outformPEM>mqtt_eclipse_org.pem

Check the sample application: ssl

Configuration:

constesp_mqtt_client_config_tmqtt_cfg={.broker={.address.uri="mqtts://mqtt.eclipseprojects.io:8883",.verification.certificate=(constchar*)mqtt_eclipse_org_pem_start,},};

For details about other fields, please check the API Reference and esp_tls_server_verification.

Client Credentials
All client related credentials are under the credentials field.
username: pointer to the username used for connecting to the broker, can also be set by URI

client_id: pointer to the client ID, defaults to ESP32_%CHIPID% where %CHIPID% are the last 3 bytes of MAC address in hex format

Authentication
It is possible to set authentication parameters through the authentication field. The client supports the following authentication methods:
password: use a password by setting

certificate and key: mutual authentication with TLS, and both can be provided in PEM or DER format

use_secure_element: use secure element (ATECC608A) interfaced to ESP32 series

ds_data: use Digital Signature Peripheral available in some Espressif devices

Session
For MQTT session-related configurations, session fields should be used.
Last Will and Testament
MQTT allows for a last will and testament (LWT) message to notify other clients when a client ungracefully disconnects. This is configured by the following fields in the last_will struct.
topic: pointer to the LWT message topic

msg: pointer to the LWT message

msg_len: length of the LWT message, required if msg is not null-terminated

qos: quality of service for the LWT message

retain: specifies the retain flag of the LWT message

Change Settings in Project Configuration Menu
The settings for MQTT can be found using idf.pymenuconfig, under Componentconfig > ESP-MQTTConfiguration.
The following settings are available:
CONFIG_MQTT_PROTOCOL_311: enable 3.1.1 version of MQTT protocol

CONFIG_MQTT_TRANSPORT_SSL and CONFIG_MQTT_TRANSPORT_WEBSOCKET: enable specific MQTT transport layer, such as SSL, WEBSOCKET, and WEBSOCKET_SECURE

CONFIG_MQTT_CUSTOM_OUTBOX: disable default implementation of mqtt_outbox, so a specific implementation can be supplied

Events
The following events may be posted by the MQTT client:
MQTT_EVENT_BEFORE_CONNECT: The client is initialized and about to start connecting to the broker.

MQTT_EVENT_CONNECTED: The client has successfully established a connection to the broker. The client is now ready to send and receive data.

MQTT_EVENT_DISCONNECTED: The client has aborted the connection due to being unable to read or write data, e.g., because the server is unavailable.

MQTT_EVENT_SUBSCRIBED: The broker has acknowledged the client’s subscribe request. The event data contains the message ID of the subscribe message.

MQTT_EVENT_UNSUBSCRIBED: The broker has acknowledged the client’s unsubscribe request. The event data contains the message ID of the unsubscribe message.

MQTT_EVENT_PUBLISHED: The broker has acknowledged the client’s publish message. This is only posted for QoS level 1 and 2, as level 0 does not use acknowledgements. The event data contains the message ID of the publish message.

MQTT_EVENT_DATA: The client has received a publish message. The event data contains: message ID, name of the topic it was published to, received data and its length. For data that exceeds the internal buffer, multiple MQTT_EVENT_DATA events are posted and current_data_offset and total_data_len from event data updated to keep track of the fragmented message.

MQTT_EVENT_ERROR: The client has encountered an error. The field error_handle in the event data contains error_type that can be used to identify the error. The type of error determines which parts of the error_handle struct is filled.

API Reference
Header File
include/mqtt_client.h

Functions
esp_mqtt_client_handle_tesp_mqtt_client_init(constesp_mqtt_client_config_t*config)
Creates MQTT client handle based on the configuration.
Parameters:config – MQTT configuration structure
Returns:mqtt_client_handle if successfully created, NULL on error
esp_err_tesp_mqtt_client_set_uri(esp_mqtt_client_handle_tclient, constchar*uri)
Sets MQTT connection URI. This API is usually used to overrides the URI configured in esp_mqtt_client_init.
Parameters:client – MQTT client handle

uri –

Returns:ESP_FAIL if URI parse error, ESP_OK on success
esp_err_tesp_mqtt_client_start(esp_mqtt_client_handle_tclient)
Starts MQTT client with already created client handle.
Parameters:client – MQTT client handle
Returns:ESP_OK on success ESP_ERR_INVALID_ARG on wrong initialization ESP_FAIL on other error
esp_err_tesp_mqtt_client_reconnect(esp_mqtt_client_handle_tclient)
This api is typically used to force reconnection upon a specific event.
Parameters:client – MQTT client handle
Returns:ESP_OK on success ESP_ERR_INVALID_ARG on wrong initialization ESP_FAIL if client is in invalid state
esp_err_tesp_mqtt_client_disconnect(esp_mqtt_client_handle_tclient)
This api is typically used to force disconnection from the broker.
Parameters:client – MQTT client handle
Returns:ESP_OK on success ESP_ERR_INVALID_ARG on wrong initialization
esp_err_tesp_mqtt_client_stop(esp_mqtt_client_handle_tclient)
Stops MQTT client tasks.
Notes:

Cannot be called from the MQTT event handler

Parameters:client – MQTT client handle
Returns:ESP_OK on success ESP_ERR_INVALID_ARG on wrong initialization ESP_FAIL if client is in invalid state
intesp_mqtt_client_subscribe_single(esp_mqtt_client_handle_tclient, constchar*topic, intqos)
Subscribe the client to defined topic with defined qos.
Notes:Client must be connected to send subscribe message

This API is could be executed from a user task or from a MQTT event callback i.e. internal MQTT task (API is protected by internal mutex, so it might block if a longer data receive operation is in progress.

esp_mqtt_client_subscribe could be used to call this function.

Parameters:client – MQTT client handle

topic – topic filter to subscribe

qos – Max qos level of the subscription

Returns:message_id of the subscribe message on success -1 on failure -2 in case of full outbox.
intesp_mqtt_client_subscribe_multiple(esp_mqtt_client_handle_tclient, constesp_mqtt_topic_t*topic_list, intsize)
Subscribe the client to a list of defined topics with defined qos.
Notes:Client must be connected to send subscribe message

This API is could be executed from a user task or from a MQTT event callback i.e. internal MQTT task (API is protected by internal mutex, so it might block if a longer data receive operation is in progress.

esp_mqtt_client_subscribe could be used to call this function.

Parameters:client – MQTT client handle

topic_list – List of topics to subscribe

size – size of topic_list

Returns:message_id of the subscribe message on success -1 on failure -2 in case of full outbox.
intesp_mqtt_client_unsubscribe(esp_mqtt_client_handle_tclient, constchar*topic)
Unsubscribe the client from defined topic.
Notes:Client must be connected to send unsubscribe message

It is thread safe, please refer to esp_mqtt_client_subscribe_single for details

Parameters:client – MQTT client handle

topic –

Returns:message_id of the subscribe message on success -1 on failure
intesp_mqtt_client_publish(esp_mqtt_client_handle_tclient, constchar*topic, constchar*data, intlen, intqos, intretain)
Client to send a publish message to the broker.
Notes:This API might block for several seconds, either due to network timeout (10s) or if publishing payloads longer than internal buffer (due to message fragmentation)

Client doesn’t have to be connected for this API to work, enqueueing the messages with qos>1 (returning -1 for all the qos=0 messages if disconnected). If MQTT_SKIP_PUBLISH_IF_DISCONNECTED is enabled, this API will not attempt to publish when the client is not connected and will always return -1.

It is thread safe, please refer to esp_mqtt_client_subscribe for details

Parameters:client – MQTT client handle

topic – topic string

data – payload string (set to NULL, sending empty payload message)

len – data length, if set to 0, length is calculated from payload string

qos – QoS of publish message

retain – retain flag

Returns:message_id of the publish message (for QoS 0 message_id will always be zero) on success. -1 on failure, -2 in case of full outbox.
intesp_mqtt_client_enqueue(esp_mqtt_client_handle_tclient, constchar*topic, constchar*data, intlen, intqos, intretain, boolstore)
Enqueue a message to the outbox, to be sent later. Typically used for messages with qos>0, but could be also used for qos=0 messages if store=true.
This API generates and stores the publish message into the internal outbox and the actual sending to the network is performed in the mqtt-task context (in contrast to the esp_mqtt_client_publish() which sends the publish message immediately in the user task’s context). Thus, it could be used as a non blocking version of esp_mqtt_client_publish().
Parameters:client – MQTT client handle

topic – topic string

data – payload string (set to NULL, sending empty payload message)

len – data length, if set to 0, length is calculated from payload string

qos – QoS of publish message

retain – retain flag

store – if true, all messages are enqueued; otherwise only QoS 1 and QoS 2 are enqueued

Returns:message_id if queued successfully, -1 on failure, -2 in case of full outbox.
esp_err_tesp_mqtt_client_destroy(esp_mqtt_client_handle_tclient)
Destroys the client handle.
Notes:Cannot be called from the MQTT event handler

Parameters:client – MQTT client handle
Returns:ESP_OK ESP_ERR_INVALID_ARG on wrong initialization
esp_err_tesp_mqtt_set_config(esp_mqtt_client_handle_tclient, constesp_mqtt_client_config_t*config)
Set configuration structure, typically used when updating the config (i.e. on “before_connect” event.
Notes:When calling this function make sure to have all the intendend configurations set, otherwise default values are set.

Parameters:client – MQTT client handle

config – MQTT configuration structure

Returns:ESP_ERR_NO_MEM if failed to allocate ESP_ERR_INVALID_ARG if conflicts on transport configuration. ESP_OK on success
esp_err_tesp_mqtt_client_register_event(esp_mqtt_client_handle_tclient, esp_mqtt_event_id_tevent, esp_event_handler_tevent_handler, void*event_handler_arg)
Registers MQTT event.
Parameters:client – MQTT client handle

event – event type

event_handler – handler callback

event_handler_arg – handlers context

Returns:ESP_ERR_NO_MEM if failed to allocate ESP_ERR_INVALID_ARG on wrong initialization ESP_OK on success
esp_err_tesp_mqtt_client_unregister_event(esp_mqtt_client_handle_tclient, esp_mqtt_event_id_tevent, esp_event_handler_tevent_handler)
Unregisters mqtt event.
Parameters:client – mqtt client handle

event – event ID

event_handler – handler to unregister

Returns:ESP_ERR_NO_MEM if failed to allocate ESP_ERR_INVALID_ARG on invalid event ID ESP_OK on success
intesp_mqtt_client_get_outbox_size(esp_mqtt_client_handle_tclient)
Get outbox size.
Parameters:client – MQTT client handle
Returns:outbox size 0 on wrong initialization
esp_err_tesp_mqtt_dispatch_custom_event(esp_mqtt_client_handle_tclient, esp_mqtt_event_t*event)
Dispatch user event to the mqtt internal event loop.
Parameters:client – MQTT client handle

event – MQTT event handle structure

Returns:ESP_OK on success ESP_ERR_TIMEOUT if the event couldn’t be queued (ref also CONFIG_MQTT_EVENT_QUEUE_SIZE)
esp_transport_handle_tesp_mqtt_client_get_transport(esp_mqtt_client_handle_tclient, char*transport_scheme)
Get a transport from the scheme.
Allows extra settings to be made on the selected transport, for convenience the scheme used by the mqtt client are defined as MQTT_OVER_TCP_SCHEME, MQTT_OVER_SSL_SCHEME, MQTT_OVER_WS_SCHEME and MQTT_OVER_WSS_SCHEME If the transport_scheme is NULL and the client was set with a custom transport the custom transport will be returned.
Notes:This function should be called only on MQTT_EVENT_BEFORE_CONNECT.

The intetion is to provide a way to set different configurations than the ones available from client config.

If esp_mqtt_client_destroy is called the returned pointer will be invalidated.

All the required settings should be made in the MQTT_EVENT_BEFORE_CONNECT event handler

Parameters:client – MQTT client handle

transport_scheme – Transport handle to search for.

Returns:the transport handle NULL in case of error

Structures
structesp_mqtt_error_codes
MQTT error code structure to be passed as a contextual information into ERROR event
Important: This structure extends esp_tls_last_error error structure and is backward compatible with it (so might be down-casted and treated as esp_tls_last_error error, but recommended to update applications if used this way previously)
Use this structure directly checking error_type first and then appropriate error code depending on the source of the error:
| error_type | related member variables | note | | MQTT_ERROR_TYPE_TCP_TRANSPORT | esp_tls_last_esp_err, esp_tls_stack_err, esp_tls_cert_verify_flags, sock_errno | Error reported from tcp_transport/esp-tls | | MQTT_ERROR_TYPE_CONNECTION_REFUSED | connect_return_code | Internal error reported from MQTT broker on connection |
Public Members
esp_err_tesp_tls_last_esp_err
last esp_err code reported from esp-tls component
intesp_tls_stack_err
tls specific error code reported from underlying tls stack
intesp_tls_cert_verify_flags
tls flags reported from underlying tls stack during certificate verification
esp_mqtt_error_type_terror_type
error type referring to the source of the error
esp_mqtt_connect_return_code_tconnect_return_code
connection refused error code reported from MQTT* broker on connection
intesp_transport_sock_errno
errno from the underlying socket

structesp_mqtt_event_t
MQTT event configuration structure
Public Members
esp_mqtt_event_id_tevent_id
MQTT event type
esp_mqtt_client_handle_tclient
MQTT client handle for this event
char*data
Data associated with this event
intdata_len
Length of the data for this event
inttotal_data_len
Total length of the data (longer data are supplied with multiple events)
intcurrent_data_offset
Actual offset for the data associated with this event
char*topic
Topic associated with this event
inttopic_len
Length of the topic for this event associated with this event
intmsg_id
MQTT messaged id of message
intsession_present
MQTT session_present flag for connection event
esp_mqtt_error_codes_t*error_handle
esp-mqtt error handle including esp-tls errors as well as internal MQTT errors
boolretain
Retained flag of the message associated with this event
intqos
QoS of the messages associated with this event
booldup
dup flag of the message associated with this event
esp_mqtt_protocol_ver_tprotocol_ver
MQTT protocol version used for connection, defaults to value from menuconfig

structesp_mqtt_client_config_t
MQTT client configuration structure
Default values can be set via menuconfig

All certificates and key data could be passed in PEM or DER format. PEM format must have a terminating NULL character and the related len field set to 0. DER format requires a related len field set to the correct length.

Public Members
structesp_mqtt_client_config_t::broker_tbroker
Broker address and security verification
structesp_mqtt_client_config_t::credentials_tcredentials
User credentials for broker
structesp_mqtt_client_config_t::session_tsession
MQTT session configuration.
structesp_mqtt_client_config_t::network_tnetwork
Network configuration
structesp_mqtt_client_config_t::task_ttask
FreeRTOS task configuration.
structesp_mqtt_client_config_t::buffer_tbuffer
Buffer size configuration.
structesp_mqtt_client_config_t::outbox_config_toutbox
Outbox configuration.

structbroker_t
Broker related configuration
Public Members
structesp_mqtt_client_config_t::broker_t::address_taddress
Broker address configuration
structesp_mqtt_client_config_t::broker_t::verification_tverification
Security verification of the broker

structaddress_t
Broker address
uri have precedence over other fields

If uri isn’t set at least hostname, transport and port should.

Public Members
constchar*uri
Complete MQTT broker URI
constchar*hostname
Hostname, to set ipv4 pass it as string)
esp_mqtt_transport_ttransport
Selects transport
constchar*path
Path in the URI
uint32_tport
MQTT server port

structverification_t
Broker identity verification
If fields are not set broker’s identity isn’t verified. it’s recommended to set the options in this struct for security reasons.
Public Members
booluse_global_ca_store
Use a global ca_store, look esp-tls documentation for details.
esp_err_t(*crt_bundle_attach)(void*conf)
Pointer to ESP x509 Certificate Bundle attach function for the usage of certificate bundles. Client only attach the bundle, the clean up must be done by the user.
constchar*certificate
Certificate data, default is NULL. It’s not copied nor freed by the client, user needs to clean up.
size_tcertificate_len
Length of the buffer pointed to by certificate.
conststructpsk_key_hint*psk_hint_key
Pointer to PSK struct defined in esp_tls.h to enable PSK authentication (as alternative to certificate verification). PSK is enabled only if there are no other ways to verify broker. It’s not copied nor freed by the client, user needs to clean up.
boolskip_cert_common_name_check
Skip any validation of server certificate CN field, this reduces the security of TLS and makes the MQTT client susceptible to MITM attacks
constchar**alpn_protos
NULL-terminated list of supported application protocols to be used for ALPN.
constchar*common_name
Pointer to the string containing server certificate common name. If non-NULL, server certificate CN must match this name, If NULL, server certificate CN must match hostname. This is ignored if skip_cert_common_name_check=true. It’s not copied nor freed by the client, user needs to clean up.
constint*ciphersuites_list
Pointer to a zero-terminated array of IANA identifiers of TLS cipher suites. Please ensure the validity of the list, and note that it is not copied or freed by the client.

structbuffer_t
Client buffer size configuration
Client have two buffers for input and output respectivelly.
Public Members
intsize
size of MQTT send/receive buffer
intout_size
size of MQTT output buffer. If not defined, defaults to the size defined by buffer_size

structcredentials_t
Client related credentials for authentication.
Public Members
constchar*username
MQTT username
constchar*client_id
Set MQTT client identifier. Ignored if set_null_client_id == true If NULL set the default client id. Default client id is ESP32_CHIPID% where CHIPID% are last 3 bytes of MAC address in hex format
boolset_null_client_id
Selects a NULL client id
structesp_mqtt_client_config_t::credentials_t::authentication_tauthentication
Client authentication

structauthentication_t
Client authentication
Fields related to client authentication by broker
For mutual authentication using TLS, user could select certificate and key, secure element or digital signature peripheral if available.
Public Members
constchar*password
MQTT password
constchar*certificate
Certificate for ssl mutual authentication, not required if mutual authentication is not needed. Must be provided with key. It’s not copied nor freed by the client, user needs to clean up.
size_tcertificate_len
Length of the buffer pointed to by certificate.
constchar*key
Private key for SSL mutual authentication, not required if mutual authentication is not needed. If it is not NULL, also certificate has to be provided. It’s not copied nor freed by the client, user needs to clean up.
size_tkey_len
Length of the buffer pointed to by key.
constchar*key_password
Client key decryption password, not PEM nor DER, if provided key_password_len must be correctly set.
intkey_password_len
Length of the password pointed to by key_password
booluse_secure_element
Enable secure element, available in ESP32-ROOM-32SE, for SSL connection
void*ds_data
Carrier of handle for digital signature parameters, digital signature peripheral is available in some Espressif devices. It’s not copied nor freed by the client, user needs to clean up.
booluse_ecdsa_peripheral
Enable ECDSA peripheral, available in some Espressif devices.
uint8_tecdsa_key_efuse_blk
ECDSA key block number from efuse, available in some Espressif devices.

structnetwork_t
Network related configuration
Public Members
intreconnect_timeout_ms
Reconnect to the broker after this value in miliseconds if auto reconnect is not disabled (defaults to 10s)
inttimeout_ms
Abort network operation if it is not completed after this value, in milliseconds (defaults to 10s).
intrefresh_connection_after_ms
Refresh connection after this value (in milliseconds)
booldisable_auto_reconnect
Client will reconnect to server (when errors/disconnect). Set disable_auto_reconnect=true to disable
esp_transport_keep_alive_ttcp_keep_alive_cfg
Transport keep-alive config
esp_transport_handle_ttransport
Custom transport handle to use, leave it NULL to allow MQTT client create or recreate its own. Warning: The transport should be valid during the client lifetime and is destroyed when esp_mqtt_client_destroy is called.
structifreq*if_name
The name of interface for data to go through. Use the default interface without setting

structoutbox_config_t
Client outbox configuration options.
Public Members
uint64_tlimit
Size limit for the outbox in bytes.

structsession_t
MQTT Session related configuration
Public Members
structesp_mqtt_client_config_t::session_t::last_will_tlast_will
Last will configuration
booldisable_clean_session
MQTT clean session, default clean_session is true
intkeepalive
MQTT keepalive, default is 120 seconds When configuring this value, keep in mind that the client attempts to communicate with the broker at half the interval that is actually set. This conservative approach allows for more attempts before the broker’s timeout occurs
booldisable_keepalive
Set disable_keepalive=true to turn off keep-alive mechanism, keepalive is active by default. Note: setting the config value keepalive to 0 doesn’t disable keepalive feature, but uses a default keepalive period
esp_mqtt_protocol_ver_tprotocol_ver
MQTT protocol version used for connection.
intmessage_retransmit_timeout
timeout for retransmitting of failed packet

structlast_will_t
Last Will and Testament message configuration.
Public Members
constchar*topic
LWT (Last Will and Testament) message topic
constchar*msg
LWT message, may be NULL terminated
intmsg_len
LWT message length, if msg isn’t NULL terminated must have the correct length
intqos
LWT message QoS
intretain
LWT retained message flag

structtask_t
Client task configuration
Public Members
intpriority
MQTT task priority
intstack_size
MQTT task stack size

structtopic_t
Topic definition struct
Public Members
constchar*filter
Topic filter to subscribe
intqos
Max QoS level of the subscription

Macros
MQTT_OVER_TCP_SCHEME
MQTT_OVER_SSL_SCHEME
MQTT_OVER_WS_SCHEME
MQTT_OVER_WSS_SCHEME
MQTT_ERROR_TYPE_ESP_TLS
MQTT_ERROR_TYPE_TCP_TRANSPORT error type hold all sorts of transport layer errors, including ESP-TLS error, but in the past only the errors from MQTT_ERROR_TYPE_ESP_TLS layer were reported, so the ESP-TLS error type is re-defined here for backward compatibility
esp_mqtt_client_subscribe(client_handle, topic_type, qos_or_size)
Convenience macro to select subscribe function to use.
Notes:Usage of esp_mqtt_client_subscribe_single is the same as previous esp_mqtt_client_subscribe, refer to it for details.

Parameters:client_handle – MQTT client handle

topic_type – Needs to be char* for single subscription or esp_mqtt_topic_t for multiple topics

qos_or_size – It’s either a qos when subscribing to a single topic or the size of the subscription array when subscribing to multiple topics.

Returns:message_id of the subscribe message on success -1 on failure -2 in case of full outbox.

Type Definitions
typedefvoid*esp_event_loop_handle_t
typedefvoid*esp_event_handler_t
typedefstructesp_mqtt_client*esp_mqtt_client_handle_t
typedefenumesp_mqtt_event_id_tesp_mqtt_event_id_t
MQTT event types.
User event handler receives context data in esp_mqtt_event_t structure withclient - MQTT client handle

various other data depending on event type

typedefenumesp_mqtt_connect_return_code_tesp_mqtt_connect_return_code_t
MQTT connection error codes propagated via ERROR event
typedefenumesp_mqtt_error_type_tesp_mqtt_error_type_t
MQTT connection error codes propagated via ERROR event
typedefenumesp_mqtt_transport_tesp_mqtt_transport_t
typedefenumesp_mqtt_protocol_ver_tesp_mqtt_protocol_ver_t
MQTT protocol version used for connection
typedefstructesp_mqtt_error_codesesp_mqtt_error_codes_t
MQTT error code structure to be passed as a contextual information into ERROR event
Important: This structure extends esp_tls_last_error error structure and is backward compatible with it (so might be down-casted and treated as esp_tls_last_error error, but recommended to update applications if used this way previously)
Use this structure directly checking error_type first and then appropriate error code depending on the source of the error:
| error_type | related member variables | note | | MQTT_ERROR_TYPE_TCP_TRANSPORT | esp_tls_last_esp_err, esp_tls_stack_err, esp_tls_cert_verify_flags, sock_errno | Error reported from tcp_transport/esp-tls | | MQTT_ERROR_TYPE_CONNECTION_REFUSED | connect_return_code | Internal error reported from MQTT broker on connection |
typedefstructesp_mqtt_event_tesp_mqtt_event_t
MQTT event configuration structure
typedefesp_mqtt_event_t*esp_mqtt_event_handle_t
typedefstructesp_mqtt_client_config_tesp_mqtt_client_config_t
MQTT client configuration structure
Default values can be set via menuconfig

All certificates and key data could be passed in PEM or DER format. PEM format must have a terminating NULL character and the related len field set to 0. DER format requires a related len field set to the correct length.

typedefstructtopic_tesp_mqtt_topic_t
Topic definition struct

Enumerations
enumesp_mqtt_event_id_t
MQTT event types.
User event handler receives context data in esp_mqtt_event_t structure withclient - MQTT client handle

various other data depending on event type

Values:
enumeratorMQTT_EVENT_ANY
enumeratorMQTT_EVENT_ERROR
on error event, additional context: connection return code, error handle from esp_tls (if supported)
enumeratorMQTT_EVENT_CONNECTED
connected event, additional context: session_present flag
enumeratorMQTT_EVENT_DISCONNECTED
disconnected event
enumeratorMQTT_EVENT_SUBSCRIBED
subscribed event, additional context:msg_id message id

error_handle error_type in case subscribing failed

data pointer to broker response, check for errors.

data_len length of the data for this event

enumeratorMQTT_EVENT_UNSUBSCRIBED
unsubscribed event, additional context: msg_id
enumeratorMQTT_EVENT_PUBLISHED
published event, additional context: msg_id
enumeratorMQTT_EVENT_DATA
data event, additional context:msg_id message id

topic pointer to the received topic

topic_len length of the topic

data pointer to the received data

data_len length of the data for this event

current_data_offset offset of the current data for this event

total_data_len total length of the data received

retain retain flag of the message

qos QoS level of the message

dup dup flag of the message Note: Multiple MQTT_EVENT_DATA could be fired for one message, if it is longer than internal buffer. In that case only first event contains topic pointer and length, other contain data only with current data length and current data offset updating.

enumeratorMQTT_EVENT_BEFORE_CONNECT
The event occurs before connecting
enumeratorMQTT_EVENT_DELETED
Notification on delete of one message from the internal outbox, if the message couldn’t have been sent or acknowledged before expiring defined in OUTBOX_EXPIRED_TIMEOUT_MS. (events are not posted upon deletion of successfully acknowledged messages)This event id is posted only if MQTT_REPORT_DELETED_MESSAGES==1

Additional context: msg_id (id of the deleted message, always 0 for QoS = 0 messages).

enumeratorMQTT_USER_EVENT
Custom event used to queue tasks into mqtt event handler All fields from the esp_mqtt_event_t type could be used to pass an additional context data to the handler.
enumesp_mqtt_connect_return_code_t
MQTT connection error codes propagated via ERROR event
Values:
enumeratorMQTT_CONNECTION_ACCEPTED
Connection accepted
enumeratorMQTT_CONNECTION_REFUSE_PROTOCOL
MQTT connection refused reason: Wrong protocol
enumeratorMQTT_CONNECTION_REFUSE_ID_REJECTED
MQTT connection refused reason: ID rejected
enumeratorMQTT_CONNECTION_REFUSE_SERVER_UNAVAILABLE
MQTT connection refused reason: Server unavailable
enumeratorMQTT_CONNECTION_REFUSE_BAD_USERNAME
MQTT connection refused reason: Wrong user
enumeratorMQTT_CONNECTION_REFUSE_NOT_AUTHORIZED
MQTT connection refused reason: Wrong username or password
enumesp_mqtt_error_type_t
MQTT connection error codes propagated via ERROR event
Values:
enumeratorMQTT_ERROR_TYPE_NONE
enumeratorMQTT_ERROR_TYPE_TCP_TRANSPORT
enumeratorMQTT_ERROR_TYPE_CONNECTION_REFUSED
enumeratorMQTT_ERROR_TYPE_SUBSCRIBE_FAILED
enumesp_mqtt_transport_t
Values:
enumeratorMQTT_TRANSPORT_UNKNOWN
enumeratorMQTT_TRANSPORT_OVER_TCP
MQTT over TCP, using scheme: MQTT
enumeratorMQTT_TRANSPORT_OVER_SSL
MQTT over SSL, using scheme: MQTTS
enumeratorMQTT_TRANSPORT_OVER_WS
MQTT over Websocket, using scheme:: ws
enumeratorMQTT_TRANSPORT_OVER_WSS
MQTT over Websocket Secure, using scheme: wss
enumesp_mqtt_protocol_ver_t
MQTT protocol version used for connection
Values:
enumeratorMQTT_PROTOCOL_UNDEFINED
enumeratorMQTT_PROTOCOL_V_3_1
enumeratorMQTT_PROTOCOL_V_3_1_1
enumeratorMQTT_PROTOCOL_V_5

Header File
include/mqtt5_client.h

Functions
esp_err_tesp_mqtt5_client_set_connect_property(esp_mqtt5_client_handle_tclient, constesp_mqtt5_connection_property_config_t*connect_property)
Set MQTT5 client connect property configuration.
Parameters:client – mqtt client handle

connect_property – connect property

Returns:ESP_ERR_NO_MEM if failed to allocate ESP_ERR_INVALID_ARG on wrong initialization ESP_FAIL on fail ESP_OK on success
esp_err_tesp_mqtt5_client_set_publish_property(esp_mqtt5_client_handle_tclient, constesp_mqtt5_publish_property_config_t*property)
Set MQTT5 client publish property configuration.
This API will not store the publish property, it is one-time configuration. Before call esp_mqtt_client_publish to publish data, call this API to set publish property if have
Parameters:client – mqtt client handle

property – publish property

Returns:ESP_ERR_INVALID_ARG on wrong initialization ESP_FAIL on fail ESP_OK on success
esp_err_tesp_mqtt5_client_set_subscribe_property(esp_mqtt5_client_handle_tclient, constesp_mqtt5_subscribe_property_config_t*property)
Set MQTT5 client subscribe property configuration.
This API will not store the subscribe property, it is one-time configuration. Before call esp_mqtt_client_subscribe to subscribe topic, call this API to set subscribe property if have
Parameters:client – mqtt client handle

property – subscribe property

Returns:ESP_ERR_INVALID_ARG on wrong initialization ESP_FAIL on fail ESP_OK on success
esp_err_tesp_mqtt5_client_set_unsubscribe_property(esp_mqtt5_client_handle_tclient, constesp_mqtt5_unsubscribe_property_config_t*property)
Set MQTT5 client unsubscribe property configuration.
This API will not store the unsubscribe property, it is one-time configuration. Before call esp_mqtt_client_unsubscribe to unsubscribe topic, call this API to set unsubscribe property if have
Parameters:client – mqtt client handle

property – unsubscribe property

Returns:ESP_ERR_INVALID_ARG on wrong initialization ESP_FAIL on fail ESP_OK on success
esp_err_tesp_mqtt5_client_set_disconnect_property(esp_mqtt5_client_handle_tclient, constesp_mqtt5_disconnect_property_config_t*property)
Set MQTT5 client disconnect property configuration.
This API will not store the disconnect property, it is one-time configuration. Before call esp_mqtt_client_disconnect to disconnect connection, call this API to set disconnect property if have
Parameters:client – mqtt client handle

property – disconnect property

Returns:ESP_ERR_NO_MEM if failed to allocate ESP_ERR_INVALID_ARG on wrong initialization ESP_FAIL on fail ESP_OK on success
esp_err_tesp_mqtt5_client_set_user_property(mqtt5_user_property_handle_t*user_property, esp_mqtt5_user_property_item_titem[], uint8_titem_num)
Set MQTT5 client user property configuration.
This API will allocate memory for user_property, please DO NOT forget callesp_mqtt5_client_delete_user_property after you use it. Before publish data, subscribe topic, unsubscribe, etc, call this API to set user property if have
Parameters:user_property – user_property handle

item – array of user property data (eg. {{“var”,”val”},{“other”,”2”}})

item_num – number of items in user property data

Returns:ESP_ERR_NO_MEM if failed to allocate ESP_FAIL on fail ESP_OK on success
esp_err_tesp_mqtt5_client_get_user_property(mqtt5_user_property_handle_tuser_property, esp_mqtt5_user_property_item_t*item, uint8_t*item_num)
Get MQTT5 client user property.

This API can use with esp_mqtt5_client_get_user_property_count to get list count of user property. And malloc number of count item array memory to store the user property data. Please DO NOT forget the item memory, key and value point in item memory when get user property data successfully.
Parameters:user_property – user_property handle

item – point that store user property data

item_num – number of items in user property data

Returns:ESP_ERR_NO_MEM if failed to allocate ESP_FAIL on fail ESP_OK on success
uint8_tesp_mqtt5_client_get_user_property_count(mqtt5_user_property_handle_tuser_property)
Get MQTT5 client user property list count.
Parameters:user_property – user_property handle
Returns:user property list count
voidesp_mqtt5_client_delete_user_property(mqtt5_user_property_handle_tuser_property)
Free the user property list.

This API will free the memory in user property list and free user_property itself
Parameters:user_property – user_property handle

Structures
structesp_mqtt5_connection_property_config_t
MQTT5 protocol connect properties and will properties configuration, more details refer to MQTT5 protocol document section 3.1.2.11 and 3.3.2.3
Public Members
uint32_tsession_expiry_interval
The interval time of session expiry
uint32_tmaximum_packet_size
The maximum packet size that we can receive
uint16_treceive_maximum
The maximum pakcket count that we process concurrently
uint16_ttopic_alias_maximum
The maximum topic alias that we support
boolrequest_resp_info
This value to request Server to return Response information
boolrequest_problem_info
This value to indicate whether the reason string or user properties are sent in case of failures
mqtt5_user_property_handle_tuser_property
The handle for user property, call function esp_mqtt5_client_set_user_property to set it
uint32_twill_delay_interval
The time interval that server delays publishing will message
uint32_tmessage_expiry_interval
The time interval that message expiry
boolpayload_format_indicator
This value is to indicator will message payload format
constchar*content_type
This value is to indicator will message content type, use a MIME content type string
constchar*response_topic
Topic name for a response message
constchar*correlation_data
Binary data for receiver to match the response message
uint16_tcorrelation_data_len
The length of correlation data
mqtt5_user_property_handle_twill_user_property
The handle for will message user property, call function esp_mqtt5_client_set_user_property to set it

structesp_mqtt5_publish_property_config_t
MQTT5 protocol publish properties configuration, more details refer to MQTT5 protocol document section 3.3.2.3
Public Members
boolpayload_format_indicator
This value is to indicator publish message payload format
uint32_tmessage_expiry_interval
The time interval that message expiry
uint16_ttopic_alias
An interger value to identify the topic instead of using topic name string
constchar*response_topic
Topic name for a response message
constchar*correlation_data
Binary data for receiver to match the response message
uint16_tcorrelation_data_len
The length of correlation data
constchar*content_type
This value is to indicator publish message content type, use a MIME content type string
mqtt5_user_property_handle_tuser_property
The handle for user property, call function esp_mqtt5_client_set_user_property to set it

structesp_mqtt5_subscribe_property_config_t
MQTT5 protocol subscribe properties configuration, more details refer to MQTT5 protocol document section 3.8.2.1
Public Members
uint16_tsubscribe_id
A variable byte represents the identifier of the subscription
boolno_local_flag
Subscription Option to allow that server publish message that client sent
boolretain_as_published_flag
Subscription Option to keep the retain flag as published option
uint8_tretain_handle
Subscription Option to handle retain option
boolis_share_subscribe
Whether subscribe is a shared subscription
constchar*share_name
The name of shared subscription which is a part of $share/{share_name}/{topic}
mqtt5_user_property_handle_tuser_property
The handle for user property, call function esp_mqtt5_client_set_user_property to set it

structesp_mqtt5_unsubscribe_property_config_t
MQTT5 protocol unsubscribe properties configuration, more details refer to MQTT5 protocol document section 3.10.2.1
Public Members
boolis_share_subscribe
Whether subscribe is a shared subscription
constchar*share_name
The name of shared subscription which is a part of $share/{share_name}/{topic}
mqtt5_user_property_handle_tuser_property
The handle for user property, call function esp_mqtt5_client_set_user_property to set it

structesp_mqtt5_disconnect_property_config_t
MQTT5 protocol disconnect properties configuration, more details refer to MQTT5 protocol document section 3.14.2.2
Public Members
uint32_tsession_expiry_interval
The interval time of session expiry
uint8_tdisconnect_reason
The reason that connection disconnet, refer to mqtt5_error_reason_code
mqtt5_user_property_handle_tuser_property
The handle for user property, call function esp_mqtt5_client_set_user_property to set it

structesp_mqtt5_event_property_t
MQTT5 protocol for event properties
Public Members
boolpayload_format_indicator
Payload format of the message
char*response_topic
Response topic of the message
intresponse_topic_len
Response topic length of the message
char*correlation_data
Correlation data of the message
uint16_tcorrelation_data_len
Correlation data length of the message
char*content_type
Content type of the message
intcontent_type_len
Content type length of the message
uint16_tsubscribe_id
Subscription identifier of the message
mqtt5_user_property_handle_tuser_property
The handle for user property, call function esp_mqtt5_client_delete_user_property to free the memory

structesp_mqtt5_user_property_item_t
MQTT5 protocol for user property
Public Members
constchar*key
Item key name
constchar*value
Item value string

Type Definitions
typedefstructesp_mqtt_client*esp_mqtt5_client_handle_t
typedefenummqtt5_error_reason_code_tesp_mqtt5_error_reason_code_t
MQTT5 protocol error reason code, more details refer to MQTT5 protocol document section 2.4
typedefstructmqtt5_user_property_list_t*mqtt5_user_property_handle_t
MQTT5 user property handle

Enumerations
enummqtt5_error_reason_code_t
MQTT5 protocol error reason code, more details refer to MQTT5 protocol document section 2.4
Values:
enumeratorMQTT5_UNSPECIFIED_ERROR
enumeratorMQTT5_MALFORMED_PACKET
enumeratorMQTT5_PROTOCOL_ERROR
enumeratorMQTT5_IMPLEMENT_SPECIFIC_ERROR
enumeratorMQTT5_UNSUPPORTED_PROTOCOL_VER
enumerator__attribute__
enumeratorMQTT5_INVALID_CLIENT_ID
enumeratorMQTT5_BAD_USERNAME_OR_PWD
enumeratorMQTT5_NOT_AUTHORIZED
enumeratorMQTT5_SERVER_UNAVAILABLE
enumeratorMQTT5_SERVER_BUSY
enumeratorMQTT5_BANNED
enumeratorMQTT5_SERVER_SHUTTING_DOWN
enumeratorMQTT5_BAD_AUTH_METHOD
enumeratorMQTT5_KEEP_ALIVE_TIMEOUT
enumeratorMQTT5_SESSION_TAKEN_OVER
enumerator__attribute__
enumeratorMQTT5_TOPIC_FILTER_INVALID
enumerator__attribute__
enumeratorMQTT5_TOPIC_NAME_INVALID
enumeratorMQTT5_PACKET_IDENTIFIER_IN_USE
enumeratorMQTT5_PACKET_IDENTIFIER_NOT_FOUND
enumeratorMQTT5_RECEIVE_MAXIMUM_EXCEEDED
enumerator__attribute__
enumeratorMQTT5_TOPIC_ALIAS_INVALID
enumeratorMQTT5_PACKET_TOO_LARGE
enumeratorMQTT5_MESSAGE_RATE_TOO_HIGH
enumeratorMQTT5_QUOTA_EXCEEDED
enumeratorMQTT5_ADMINISTRATIVE_ACTION
enumerator__attribute__
enumeratorMQTT5_PAYLOAD_FORMAT_INVALID
enumeratorMQTT5_RETAIN_NOT_SUPPORT
enumeratorMQTT5_QOS_NOT_SUPPORT
enumeratorMQTT5_USE_ANOTHER_SERVER
enumeratorMQTT5_SERVER_MOVED
enumeratorMQTT5_SHARED_SUBSCR_NOT_SUPPORTED
enumeratorMQTT5_CONNECTION_RATE_EXCEEDED
enumeratorMQTT5_MAXIMUM_CONNECT_TIME
enumeratorMQTT5_SUBSCRIBE_IDENTIFIER_NOT_SUPPORT
enumeratorMQTT5_WILDCARD_SUBSCRIBE_NOT_SUPPORT