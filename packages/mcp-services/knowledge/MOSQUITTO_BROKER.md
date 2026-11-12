来源：https://mosquitto.org/man/mosquitto-8.html

### Name

mosquitto — an MQTT broker

### Synopsis

`mosquitto` [`-c` `config file`] [ `-d` | `--daemon` ] [`-p` `port number`] [`-q`] [`-v`] [`--tls-keylog` `file`]

### Description

mosquitto is a broker for the MQTT protocol version 5.0/3.1.1/3.1.

It is part of the overall mosquitto project. See mosquitto(7) for an overview of all man pages.

### Options

`-c`, `--config-file`

Load configuration from a file. If not given, then the broker will listen on port 1883 bound to the loopback interface, and the default values as described in mosquitto.conf(5) are used.

#### Important

See the `-p` option for a description of changes in behaviour from 1.6.x to 2.0.

`-d`, `--daemon`

Run mosquitto in the background as a daemon. All other behaviour remains the same.

`-p`, `--port`

Listen on the port specified. May be specified up to 10 times to open multiple sockets listening on different ports.

#### Important

In version 1.6.x and earlier, the listener defined by `-p` (or the default port of 1883) would be bound to all interfaces and so be accessible from any network. It could also be used in combination with `-c`.

From version 2.0 onwards, the listeners defined with `-p` are bound to the loopback interface only, and so can only be connected to from the local machine. If both `-p` is used and a listener is defined in a configuration file, then the `-p` options are IGNORED.

`-q`, `--quiet`

Available from version 2.1.

Disable all logging. This is equivalent to setting `log_type` to `none` in the configuration file. This overrides any logging options given in the configuration file and also overrides `--verbose`.

`--test-config`

Available from version 2.1.

Load the config file specified with `-c`, and verify that it is valid but do not start the broker. The broker exit code will be 0 if the config was valid, or non-zero if no config file was specified or the config file was invalid.

`--tls-keylog` `file`

Available from version 2.1.

Log TLS connection information to `file`. This option allows tools such as tcpdump, wireshark and mqttshark to decrypt TLS traffic and inspect the MQTT traffic. In Wireshark this can be done by setting the `(Pre)-Master-Secret log filename` option for the `Transport Layer Security` protocol.

This option should be used for debugging only, it must not be used in production.

`-v`, `--verbose`

Use verbose logging. This is equivalent to setting `log_type` to `all` in the configuration file. This overrides any logging options given in the configuration file.

### Configuration

The broker can be configured using a configuration file as described in mosquitto.conf(5) and this is the main point of information for mosquitto. The files required for SSL/TLS support are described in mosquitto-tls(7).

### Platform limitations

Some versions of Windows have limitations on the number of concurrent connections due to the Windows API being used. In modern versions of Windows, e.g. Windows 10 or Windows Server 2019, this is approximately 8192 connections. In earlier versions of Windows, this limit is 2048 connections.

### MQTT Support

Mosquitto supports MQTT v5.0, v3.1.1, and v3.1.

#### MQTT v5.0

Mosquitto provides full MQTT v5.0 support, but some features are not used directly. The following sections describe the new features and explain where Mosquitto does not make use of a feature.

##### Features

`Enhanced authentication`

Basic MQTT authentication uses username/password checks. Enhanced authentication allows different authentication schemes to be integrated into MQTT, and even those schemes with multiple step processes. Clients request a particular type of authentication and if the broker is configured for that scheme the authentication continues. Mosquitto supports enhanced authentication through plugins.

`Error handling`

Most MQTT packets now have the concept of a `reason code` which indicates success or failure, and what the failure was. Mosquitto provides full support for reason codes, but does not make use of the `reason string` feature which can be used to provide a human readable error string to explain the reason code.

`Flow control`

The number of "in flight" messages for QoS 1 and QoS 2 can be controlled by both the client and the broker.

`Request / response`

MQTT v5.0 adds a request/response pattern that allows a client to publish a message and instruct the subscribers of that message where to publish a response.

`Server redirection`

Server redirection is the concept of telling a client to connect to a different MQTT broker, either on CONNECT or with a broker initiated DISCONNECT. Mosquitto does not currently make use of this feature.

`Shared subscriptions`

When multiple clients subscribe to the same shared subscription, only one client out of the group will receive each message which allows for distributing work loads.

##### Packet properties

MQTT v5.0 allows properties to be added to packets to control certain behaviour. Unless noted, Mosquitto support the properties listed below.

`CONNECT`

- Authentication data

- Authentication method

- Maximum packet size

- Receive maximum

- Request problem information - supported but not used

- Request response information - supported but not used

- Session expiry interval

- Topic alias maximum

- User property

`Last will and testament`

- Content type

- Correlation data

- Message expiry interval

- Payload format indicator

- Response topic

- User property

- Will delay interval

`CONNACK`

- Assigned client identifier

- Authentication data

- Authentication method

- Maximum packet size

- Maximum qos

- Reason string - supported but not used

- Receive maximum

- Response information - supported but not used

- Retain available

- Server keep alive

- Server reference - supported but not used

- Session expiry interval

- Shared subscription available

- Subscription identifiers available

- Topic alias maximum

- User property

- Wildcard subscription available

`PUBLISH`

- Content type

- Correlation data

- Message expiry interval

- Payload format indicator

- Response topic

- Subscription identifier

- Topic alias

- User property

`PUBACK / PUBREC / PUBREL / PUBCOMP / SUBACK / SUBSCRIBE / SUBACK`

- Reason string - supported but not used

- User property

`SUBSCRIBE`

- Subscription identifier

- User property

`DISCONNECT`

- Reason string - supported but not used

- Server reference - supported but not used

- Session expiry interval

- User property

`AUTH`

- Authentication method

- Authentication data

- Reason string - supported but not used

- User property

#### MQTT v3.1.1

Mosquitto provides full MQTT v3.1.1 support.

#### MQTT v3.1

Mosquitto provides full MQTT v3.1 support.

#### MQTT v3

MQTT v3 is an obsolete version of the protocol that does not support username/password authentication and used the `clean start` flag in the CONNECT packet which applied only to the start of a session. An MQTT v3 client will be able to successfully connect to a Mosquitto instance that does not require authentication.

### Broker Status

Clients can find information about the broker by subscribing to topics in the $SYS hierarchy as follows. Topics marked as static are only sent once per client on subscription. All other topics are updated every `sys_interval` seconds. If `sys_interval` is 0, then updates are not sent.

Note that if you are using a command line client to interact with the $SYS topics and your shell interprets $ as an environment variable, you need to place the topic in single quotes '$SYS/...' or to escape the dollar symbol: \$SYS/... otherwise the $SYS will be treated as an environment variable.

`$SYS/broker/bytes/received`

The total number of bytes received since the broker started.

`$SYS/broker/bytes/sent`

The total number of bytes sent since the broker started.

`$SYS/broker/clients/connected`, `$SYS/broker/clients/active` (deprecated)

The number of currently connected clients.

`$SYS/broker/clients/expired`

The number of disconnected persistent clients that have been expired and removed through the persistent_client_expiration option.

`$SYS/broker/clients/disconnected`, `$SYS/broker/clients/inactive` (deprecated)

The total number of persistent clients (with clean session disabled) that are registered at the broker but are currently disconnected.

`$SYS/broker/clients/maximum`

The maximum number of clients that have been connected to the broker at the same time.

`$SYS/broker/clients/total`

The total number of connected and disconnected client sessions currently registered on the broker.

`$SYS/broker/connection/#`

When bridges are configured to/from the broker, common practice is to provide a status topic that indicates the state of the connection. This is provided within $SYS/broker/connection/ by default. If the value of the topic is 1 the connection is active, if 0 then it is not active. See the Bridges section below for more information on bridges.

`$SYS/broker/connections/socket/count`

The total number of socket connections that have been made to the broker, whether or not the MQTT connections were ultimately successful.

`$SYS/broker/heap/current`

The current size of the heap memory in use by mosquitto. Note that this topic may be unavailable depending on compile time options.

`$SYS/broker/heap/maximum`

The largest amount of heap memory used by mosquitto. Note that this topic may be unavailable depending on compile time options.

`$SYS/broker/load/connections/+`

The moving average of the number of CONNECT packets received by the broker over different time intervals. The final "+" of the hierarchy can be 1min, 5min or 15min. The value returned represents the number of connections received in 1 minute, averaged over 1, 5 or 15 minutes.

`$SYS/broker/load/bytes/received/+`

The moving average of the number of bytes received by the broker over different time intervals. The final "+" of the hierarchy can be 1min, 5min or 15min. The value returned represents the number of bytes received in 1 minute, averaged over 1, 5 or 15 minutes.

`$SYS/broker/load/bytes/sent/+`

The moving average of the number of bytes sent by the broker over different time intervals. The final "+" of the hierarchy can be 1min, 5min or 15min. The value returned represents the number of bytes sent in 1 minute, averaged over 1, 5 or 15 minutes.

`$SYS/broker/load/messages/received/+`

The moving average of the number of all types of MQTT messages received by the broker over different time intervals. The final "+" of the hierarchy can be 1min, 5min or 15min. The value returned represents the number of messages received in 1 minute, averaged over 1, 5 or 15 minutes.

`$SYS/broker/load/messages/sent/+`

The moving average of the number of all types of MQTT messages sent by the broker over different time intervals. The final "+" of the hierarchy can be 1min, 5min or 15min. The value returned represents the number of messages send in 1 minute, averaged over 1, 5 or 15 minutes.

`$SYS/broker/load/publish/dropped/+`

The moving average of the number of publish messages dropped by the broker over different time intervals. This shows the rate at which durable clients that are disconnected are losing messages. The final "+" of the hierarchy can be 1min, 5min or 15min. The value returned represents the number of messages dropped in 1 minute, averaged over 1, 5 or 15 minutes.

`$SYS/broker/load/publish/received/+`

The moving average of the number of publish messages received by the broker over different time intervals. The final "+" of the hierarchy can be 1min, 5min or 15min. The value returned represents the number of publish messages received in 1 minute, averaged over 1, 5 or 15 minutes.

`$SYS/broker/load/publish/sent/+`

The moving average of the number of publish messages sent by the broker over different time intervals. The final "+" of the hierarchy can be 1min, 5min or 15min. The value returned represents the number of publish messages sent in 1 minute, averaged over 1, 5 or 15 minutes.

`$SYS/broker/load/sockets/+`

The moving average of the number of socket connections opened to the broker over different time intervals. The final "+" of the hierarchy can be 1min, 5min or 15min. The value returned represents the number of socket connections in 1 minute, averaged over 1, 5 or 15 minutes.

`$SYS/broker/messages/received`

The total number of messages of any type received since the broker started.

`$SYS/broker/messages/sent`

The total number of messages of any type sent since the broker started.

`$SYS/broker/mqtt/connect/received`

The total number of MQTT CONNECT messages received since the broker started.

`$SYS/broker/mqtt/connack/sent`

The total number of MQTT CONNACK messages sent since the broker started.

`$SYS/broker/mqtt/publish/dropped`, `$SYS/broker/publish/messages/dropped`

The total number of MQTT PUBLISH messages that have been dropped due to inflight/queuing limits. See the max_inflight_messages and max_queued_messages options in mosquitto.conf(5) for more information.

`$SYS/broker/mqtt/publish/received`, `$SYS/broker/publish/messages/received`

The total number of MQTT PUBLISH messages received since the broker started.

`$SYS/broker/mqtt/publish/sent`, `$SYS/broker/publish/messages/sent`

The total number of MQTT PUBLISH messages sent since the broker started.

`$SYS/broker/mqtt/puback/received`

The total number of MQTT PUBACK messages received since the broker started.

`$SYS/broker/mqtt/puback/sent`

The total number of MQTT PUBACK messages sent since the broker started.

`$SYS/broker/mqtt/pubrec/received`

The total number of MQTT PUBREC messages received since the broker started.

`$SYS/broker/mqtt/pubrec/sent`

The total number of MQTT PUBREC messages sent since the broker started.

`$SYS/broker/mqtt/pubrel/received`

The total number of MQTT PUBREL messages received since the broker started.

`$SYS/broker/mqtt/pubrel/sent`

The total number of MQTT PUBREL messages sent since the broker started.

`$SYS/broker/mqtt/pubcomp/received`

The total number of MQTT PUBCOMP messages received since the broker started.

`$SYS/broker/mqtt/pubcomp/sent`

The total number of MQTT PUBCOMP messages sent since the broker started.

`$SYS/broker/mqtt/subscribe/received`

The total number of MQTT SUBSCRIBE messages received since the broker started.

`$SYS/broker/mqtt/suback/sent`

The total number of MQTT SUBACK messages sent since the broker started.

`$SYS/broker/mqtt/unsubscribe/received`

The total number of MQTT UNSUBSCRIBE messages received since the broker started.

`$SYS/broker/mqtt/unsuback/sent`

The total number of MQTT UNSUBACK messages sent since the broker started.

`$SYS/broker/mqtt/pingreq/received`

The total number of MQTT PINGREQ messages received since the broker started.

`$SYS/broker/mqtt/pingresp/sent`

The total number of MQTT PINGRESP messages sent since the broker started.

`$SYS/broker/mqtt/disconnect/received`

The total number of MQTT DISCONNECT messages received since the broker started.

`$SYS/broker/mqtt/disconnect/sent`

The total number of MQTT DISCONNECT messages sent since the broker started.

`$SYS/broker/mqtt/auth/received`

The total number of MQTT AUTH messages received since the broker started.

`$SYS/broker/mqtt/auth/sent`

The total number of MQTT AUTH messages sent since the broker started.

`$SYS/broker/packet/out/count`

The current number of packets queued for delivery across all clients. A large and increasing value here may indicate messages are being sent faster than the network can handle.

`$SYS/broker/packet/out/bytes`

The current number of bytes in packets queued for delivery across all clients. A large and increasing value here may indicate messages are being sent faster than the network can handle.

`$SYS/broker/publish/bytes/received`

The total number of PUBLISH payload bytes received since the broker started.

`$SYS/broker/publish/bytes/sent`

The total number of PUBLISH payload bytes sent since the broker started.

`$SYS/broker/retained messages/count`

The total number of retained messages active on the broker.

`$SYS/broker/store/messages/count`, `$SYS/broker/messages/stored` (deprecated)

The number of messages currently held in the message store. This includes retained messages and messages queued for durable clients.

`$SYS/broker/store/messages/bytes`

The number of bytes currently held by message payloads in the message store. This includes retained messages and messages queued for durable clients.

`$SYS/broker/shared_subscriptions/count`

The total number of shared subscriptions active on the broker.

`$SYS/broker/subscriptions/count`

The total number of subscriptions active on the broker.

`$SYS/broker/version`

The version of the broker. Static.

### Wildcard Topic Subscriptions

In addition to allowing clients to subscribe to specific topics, mosquitto also allows the use of two wildcards in subscriptions. `+` is the wildcard used to match a single level of hierarchy. For example, for a topic of "a/b/c/d", the following example subscriptions will match:

- a/b/c/d

- +/b/c/d

- a/+/c/d

- a/+/+/d

- +/+/+/+

The following subscriptions will not match:

- a/b/c

- b/+/c/d

- +/+/+

The second wildcard is `#` and is used to match all subsequent levels of hierarchy. With a topic of "a/b/c/d", the following example subscriptions will match:

- a/b/c/d

- #

- a/#

- a/b/#

- a/b/c/#

- +/b/c/#

The $SYS hierarchy does not match a subscription of "#". If you want to observe the entire $SYS hierarchy, subscribe to $SYS/#.

Note that the wildcards must be only ever used on their own, so a subscription of "a/b+/c" is not valid use of a wildcard. The `#` wildcard must only ever be used as the final character of a subscription.

### Bridges

Multiple brokers can be connected together with the bridging functionality. This is useful where it is desirable to share information between locations, but where not all of the information needs to be shared. An example could be where a number of users are running a broker to help record power usage and for a number of other reasons. The power usage could be shared through bridging all of the user brokers to a common broker, allowing the power usage of all users to be collected and compared. The other information would remain local to each broker.

For information on configuring bridges, see mosquitto.conf(5).

### Signals

On POSIX systems Mosquitto can receive signals and act on them as described below. To send signals, use e.g. kill -HUP <process id of mosquitto>

SIGHUP

Upon receiving the SIGHUP signal, mosquitto will attempt to reload configuration file data, assuming that the `-c` argument was provided when mosquitto was started. Not all configuration parameters can be reloaded without restarting. See mosquitto.conf(5) for details.

If TLS certificates are in use, then mosquitto will also reload certificate on receiving a SIGHUP.

The logs will also be closed and reopened.

SIGRTMIN

Upon receiving the SIGRTMIN signal, mosquitto will close and reopen the logs to support log rotation.

SIGUSR1

Upon receiving the SIGUSR1 signal, mosquitto will write the persistence database to disk. This signal is only acted upon if persistence is enabled.

SIGUSR2

The SIGUSR2 signal causes mosquitto to print out the current subscription tree, along with information about where retained messages exist. This is intended as a testing feature only and may be removed at any time.

### Environment Variables

`MOSQUITTO_UNSAFE_ALLOW_SYMLINKS`

By default, sensitive file with a path including a symbolic link will be refused to be loaded. Set this environment variable to any value to allow load files through symbolic links. Note that making use of this variable could expose you to symlink attacks and so it should only be used in cases where you are absolutely sure this is not a risk.

### Files

`/etc/mosquitto/mosquitto.conf`

Configuration file. See mosquitto.conf(5).

`/var/lib/mosquitto/mosquitto.db`

Persistent message data storage location if persist enabled.

`/etc/hosts.allow`, `/etc/hosts.deny`

Host access control via tcp-wrappers as described in hosts_access(5).

### Bugs

mosquitto bug information can be found at https://github.com/eclipse-mosquitto/mosquitto/issues

### See Also

mosquitto(7) , mqtt(7) , mosquitto-tls(7) , mosquitto.conf(5) , mosquitto_ctrl(1) , mosquitto_passwd(1) , mosquitto_pub(1) , mosquitto_rr(1) , mosquitto_sub(1) , libmosquitto(3)

### Thanks

Thanks to Andy Stanford-Clark for being one of the people who came up with MQTT in the first place. Thanks to Andy and Nicholas O'Leary for providing clarifications of the protocol.

Thanks also to everybody at the Ubuntu UK Podcast and Linux Outlaws for organising OggCamp, where Andy gave a talk that inspired mosquitto.

### Author

Roger Light `<roger@atchoo.org>`
