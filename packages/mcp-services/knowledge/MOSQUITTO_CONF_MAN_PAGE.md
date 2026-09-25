Source: https://mosquitto.org/man/mosquitto-conf-5.html

Name
mosquitto.conf — the configuration file for mosquitto

Synopsis
mosquitto.conf

Description
mosquitto.conf is the configuration file for
mosquitto. This file can reside anywhere as long as mosquitto can read
it. By default, mosquitto does not need a configuration file and will
use the default values listed below. See
mosquitto(8)
for information on how to load a configuration file.

Mosquitto can be instructed to reload the configuration file by
sending a SIGHUP signal as described in the Signals section of
mosquitto(8).
Not all configuration options can be reloaded, as detailed in
the options below.

Sections

The rest of this man page is divided into the following sections:

File Format a description of the configuration
file syntax.Authentication a discussion of the authentication
options available.General Options the general options for configuring
Mosquitto.Listeners general options for configuring listeners,
which are the ways that MQTT clients can connect to Mosquitto,
as well as certificate and pre-shared-key based SSL/TLS options.Configuring Bridges general options for configuring bridges,
which are a way of connecting multiple brokers together,
as well as certificate and pre-shared-key based SSL/TLS options.Other The Files, Bugs, See Also sections.

File Format

All lines with a # as the very first character are treated as a
comment.

Configuration lines start with a variable name. The variable value
is separated from the name by a single space.

Authentication

The authentication options described below allow a wide range of
possibilities in conjunction with the listener options. This
section aims to clarify the possibilities. An overview is also
available at
https://mosquitto.org/documentation/authentication-methods/

The simplest option is to have no authentication at all. This is
the default if no other options are given. Unauthenticated
encrypted support is provided by using the certificate based
SSL/TLS based options certfile and keyfile.

MQTT provides username/password authentication as part of the
protocol. Use the password_file option to define the valid
usernames and passwords. Be sure to use network encryption if you
are using this option otherwise the username and password will be
vulnerable to interception. Use the
per_listener_settings to control whether passwords
are required globally or on a per-listener basis.

Mosquitto provides the Dynamic Security plugin which handles
username/password authentication and access control in a much
more flexible way than a password file. See
https://mosquitto.org/documentation/dynamic-security/

When using certificate based encryption there are three options
that affect authentication. The first is require_certificate, which
may be set to true or false. If false, the SSL/TLS component of the
client will verify the server but there is no requirement for the
client to provide anything for the server: authentication is
limited to the MQTT built in username/password. If
require_certificate is true, the client must provide a valid
certificate in order to connect successfully. In this case, the
second and third options, use_identity_as_username and
use_subject_as_username, become relevant. If set to true,
use_identity_as_username causes the Common Name (CN) from the
client certificate to be used instead of the MQTT username for
access control purposes. The password is not used because it is
assumed that only authenticated clients have valid certificates.
This means that any CA certificates you include in cafile or capath
will be able to issue client certificates that are valid for
connecting to your broker. If use_identity_as_username is false,
the client must authenticate as normal (if required by
password_file) through the MQTT options. The same principle applies
for the use_subject_as_username option, but the entire certificate
subject is used as the username instead of just the CN.

When using pre-shared-key based encryption through the psk_hint
and psk_file options, the client must provide a valid identity and
key in order to connect to the broker before any MQTT communication
takes place. If use_identity_as_username is true, the PSK identity
is used instead of the MQTT username for access control purposes.
If use_identity_as_username is false, the client may still
authenticate using the MQTT username/password if using the
password_file option.

Both certificate and PSK based encryption are configured on a
per-listener basis.

Authentication plugins can be created to augment the
password_file, acl_file and psk_file options with e.g. SQL based
lookups.

It is possible to support multiple authentication schemes at
once. A config could be created that had a listener for all of the
different encryption options described above and hence a large
number of ways of authenticating.

General Options
acl_filefile pathNote: It is suggested that you use the
mosquitto_acl_file plugin instead of this
option. Using plugins for authentication and authorisation
allows greater control of what listeners they are applied to,
without the need for the deprecated
per_listener_settings option.

Set the path to an access control list file. If
defined, the contents of the file are used to control
client access to topics on the broker.

If this parameter is defined then only the topics
listed will have access. Topic access is added with
lines of the format:

topic [read|write|readwrite|deny] <topic>

The access type is controlled using "read", "write",
"readwrite" or "deny". This parameter is optional (unless
<topic> includes a space character) - if not
given then the access is read/write. <topic> can
contain the + or # wildcards as in
subscriptions. The "deny" option can used to explicitly
deny access to a topic that would otherwise be granted
by a broader read/write/readwrite statement. Any "deny"
topics are handled before topics that grant read/write access.

The first set of topics are applied to anonymous
clients, assuming allow_anonymous is
true. User specific topic ACLs are added after a user
line as follows:

user <username>

The username referred to here is the same as in
password_file. It is not the
clientid.

It is also possible to define ACLs based on pattern
substitution within the topic. The form is the same as
for the topic keyword, but using pattern as the
keyword.

pattern [read|write|readwrite|deny] <topic>

The patterns available for substitution are:

%c to match the client id of the client

%u to match the username of the client

The substitution pattern must be the only text for
that level of hierarchy. Pattern ACLs apply to all
users even if the "user" keyword has previously been
given.

Example:
pattern write sensor/%u/data
Allow access for bridge connection messages:
pattern write $SYS/broker/connection/%c/state

If the first character of a line of the ACL file is a
# it is treated as a comment.

If per_listener_settings is
true, this option applies to
the current listener being configured only. If
per_listener_settings is
false, this option applies
to all listeners.

Note: In general it is not possible to grant write
access to topics in the $SYS topic tree. The exception
is $SYS/broker/connection/+/state.

Reloaded on reload signal. The currently loaded ACLs
will be freed and reloaded. Existing subscriptions will
be affected after the reload.

See also
https://mosquitto.org/documentation/dynamic-security/
allow_anonymous [ true | false ]Global boolean value that determines whether clients that
connect without providing a username are allowed to
connect. If set to false
then another means of connection should be created to
control authenticated client access.
Defaults to false,
unless no listeners are defined in the configuration
file, in which case it set to true,
but connections are only allowed from the local machine.

If you want to control this setting for each listener individually,
use the listener_allow_anonymous option.

(Note: Deprecated) If per_listener_settings is
true, this option applies to
the current listener being configured only. If
per_listener_settings is
false, this option applies
to all listeners.
Important
In version 1.6.x and earlier, this option defaulted
to true unless there was another security
option set.

Reloaded on reload signal.
allow_duplicate_messages [ true | false ]This option is deprecated and will be removed in a
future version. The behaviour will default to true.

If a client is subscribed to multiple subscriptions
that overlap, e.g. foo/# and foo/+/baz , then MQTT
expects that when the broker receives a message on a
topic that matches both subscriptions, such as
foo/bar/baz, then the client should only receive the
message once.
Mosquitto keeps track of which clients a message has
been sent to in order to meet this requirement. This
option allows this behaviour to be disabled, which may
be useful if you have a large number of clients
subscribed to the same set of topics and want to
minimise memory usage.
It can be safely set to
true if you know in advance
that your clients will never have overlapping
subscriptions, otherwise your clients must be able to
correctly deal with duplicate messages even when then
have QoS=2.
Defaults to true.
This option applies globally.
Reloaded on reload signal.
allow_zero_length_clientid [ true | false ]MQTT 3.1.1 and MQTT 5 allow clients to connect with a zero
length client id and have the broker generate a client
id for them. Use this option to allow/disallow this
behaviour. Defaults to true.
See also the auto_id_prefix option.
If per_listener_settings is
true, this option applies to
the current listener being configured only. If
per_listener_settings is
false, this option applies
to all listeners.
Reloaded on reload signal.
auth_plugin_deny_special_chars [ true | false ]If true then before an ACL
check is made, the username/client id of the client
needing the check is searched for the presence of
either a '+' or '#' character. If either of these
characters is found in either the username or client
id, then the ACL check is denied before it is sent to
the plugin.
This check prevents the case where a malicious user
could circumvent an ACL check by using one of these
characters as their username or client id. This is the
same issue as was reported with mosquitto itself as
CVE-2017-7650.
If you are entirely sure that the plugin you are
using is not vulnerable to this attack (i.e. if you
never use usernames or client ids in topics) then you
can disable this extra check and hence have all ACL
checks delivered to your plugin by setting this option
to false.
Defaults to true.
Applies to the current authentication plugin being configured.
Not currently reloaded on reload signal.
auto_id_prefixprefix
This option is deprecated, please use listener_auto_id_prefix instead.

If allow_zero_length_clientid is
true, this option allows you
to set a string that will be prefixed to the
automatically generated client ids to aid visibility in
logs. Defaults to auto-.
If per_listener_settings is
true, this option applies to
the current listener being configured only. If
per_listener_settings is
false, this option applies
to all listeners.
Reloaded on reload signal.
autosave_intervalseconds
The number of seconds that mosquitto will wait
between each time it saves the in-memory database to
disk. If set to 0, the in-memory database will only be
saved when mosquitto exits or when receiving the
SIGUSR1 signal. Note that this setting only has an
effect if the built-in persistence is enabled. Defaults
to 1800 seconds (30 minutes).

This option applies globally.
Reloaded on reload signal.
autosave_on_changes [ true | false ]If true, mosquitto will
count the number of subscription changes, retained
messages received and queued messages and if the total
exceeds autosave_interval then the
in-memory database will be saved to disk. If
false, mosquitto will save
the in-memory database to disk by treating
autosave_interval as a time in
seconds.
Applies to built-in persistence only.
This option applies globally.
Reloaded on reload signal.
check_retain_source [ true | false ]This option affects the scenario when a client
subscribes to a topic that has retained messages. It is
possible that the client that published the retained
message to the topic had access at the time they
published, but that access has been subsequently
removed. If check_retain_source is set
to true, the default, the source of a retained message
will be checked for access rights before it is
republished. When set to false, no check will be made
and the retained message will always be
published.
This option applies globally, regardless of the
per_listener_settings option.
clientid_prefixesprefixThis option is deprecated and will be removed in a
future version.
If defined, only clients that have a clientid with a
prefix that matches clientid_prefixes will be allowed
to connect to the broker. For example, setting
"secure-" here would mean a client "secure-client"
could connect but another with clientid "mqtt"
couldn't. By default, all client ids are valid.
This option applies globally.
Reloaded on reload signal. Note that currently
connected clients will be unaffected by any
changes.
connection_messages [ true | false ]If set to true, the log
will include entries when clients connect and
disconnect. If set to false,
these entries will not appear.
This option applies globally.
Reloaded on reload signal.
enable_control_api [ true | false ]If set to true, the
$CONTROL/broker/v1 will be enabled. This currently
allows interrogating which plugins are enabled, but in the future
will allow access to configuring general broker options. If you enable
this you should ensure you have authentication and appropriate access
control configured, i.e. only allowing access to
$CONTROL/broker/# for a limited set of users.

This option applies globally.
Reloaded on reload signal.
global_max_clientscount
The maximum number of client sessions to allow across
the whole broker. In this context a client session means
either a client currently connected via the network, or
a client that has clean_session = False (MQTT v3.x) and
is disconnected, or has disconnected and still hasn't
exceeded its session expiry interval (MQTT v5).

See also the max_connections setting, which applies to
listeners. If you set global_max_clients
to 1000 and max_connections on a
listener to 10, then that means only 10 simultaneous
connections will be allowed at once, with an overall
maximum of 1000 client sessions.

This option applies globally.
Defaults to -1 (unlimited)
Reloaded on reload signal.
global_max_connectionscount
The maximum number of currently connected clients to
allow across the whole broker.

See also the global_max_clients and
max_connections settings.

This option applies globally.
Defaults to -1 (unlimited)
Reloaded on reload signal.
global_pluginfile path
Load an external module to extend broker features. This loads plugins
for use across all listeners, regardless of the value of the
per_listener_settings option. This option functions
the same as the plugin option in all other ways.

If you set per_listener_settings true, then define both a
global_plugin and a plugin (which will be
attached to a specific listener), then the global plugin will always be
processed first.

If you set per_listener_settings false, then
global_plugin behaves identically to
plugin.

include_dirdirExternal configuration files may be included by using
the include_dir option. This defines a directory that
will be searched for config files. All files that end
in '.conf' will be loaded as a configuration file. It
is best to have this as the last option in the main
file. This option will only be processed from the main
configuration file. The directory specified must not
contain the main configuration file.
The configuration files in
include_dir are loaded in case
sensitive alphabetical order, with the upper case of
each letter ordered before the lower case of the same
letter.
Example Load Order for include_dir. 
Given the files
b.conf,
A.conf,
01.conf,
a.conf,
B.conf, and
00.conf inside
include_dir, the config files
would be loaded in this order:

00.conf
01.conf
A.conf
a.conf
B.conf
b.conf

If this option is used multiple times, then each
include_dir option is processed
completely in the order that they are written in the
main configuration file.
Example Load Order for Multiple include_dir. 
Assuming a directory
one.d containing
files B.conf and
C.conf, and a second
directory two.d
containing files
A.conf and
D.conf, and a
config:

include_dir one.d
include_dir two.d

Then the config files would be loaded in this order:

# files from one.d
B.conf
C.conf
# files from two.d
A.conf
D.conf

log_destdestinationsSend log messages to a particular destination.
Possible destinations are: stdoutstderrsyslogtopicfiledltandroid.
stdout and
stderr log to the console on the
named output.
syslog uses the userspace syslog
facility which usually ends up in /var/log/messages or
similar.
topic logs to the broker topic
'$SYS/broker/log/<severity>', where severity is
one of E, W, N, I, M which are error,
warning, notice, information and message. Message type
severity is used by the subscribe and unsubscribe
log_type options and publishes log messages at
$SYS/broker/log/M/subscribe and
$SYS/broker/log/M/unsubscribe. Debug messages are never
logged on topics.
The file destination requires an
additional parameter which is the file to be logged to,
e.g. "log_dest file /var/log/mosquitto.log". The file
will be closed and reopened when the broker receives a
HUP signal. Only a single file destination may be
configured.
The dlt destination is for the
automotive `Diagnostic Log and Trace` tool. This
requires that Mosquitto has been compiled with DLT
support.
The android destination is for
Android only, and will output to the logd daemon.
Use "log_dest none" if you wish to disable logging.
Defaults to stderr. This option may be specified
multiple times.
Note that if the broker is running as a Windows
service it will default to "log_dest none" and neither
stdout nor stderr logging is available.
Reloaded on reload signal.
log_facilitylocal facilityIf using syslog logging (not on Windows), messages
will be logged to the "daemon" facility by default. Use
the log_facility option to choose
which of local0 to local7 to log to instead. The option
value should be an integer value, e.g. "log_facility 5"
to use local5.
log_timestamp [ true | false ]Boolean value, if set to
true a timestamp value will
be added to each log entry. The default is
true.
Reloaded on reload signal.
log_timestamp_formatformatSet the format of the log timestamp. If left unset,
this is the number of seconds since the Unix epoch.
This option is a free text string which will be passed
to the strftime function as the format specifier. To
get an ISO 8601 datetime, for example:

log_timestamp_format %Y-%m-%dT%H:%M:%S

Reloaded on reload signal.
log_typetypesChoose types of messages to log. Possible types are:
debug,
error,
warning,
notice,
information,
subscribe,
unsubscribe,
websockets,
none,
all.
Defaults to error,
warning, notice
and
information. This option
may be specified multiple times. Note that the
debug type (used for
decoding incoming/outgoing network packets) is never
logged in topics.
Reloaded on reload signal.
max_inflight_bytescountOutgoing QoS 1 and 2 messages will be allowed in flight until this byte
limit is reached. This allows control of outgoing message rate based on
message size rather than message count. If the limit is set to 100,
messages of over 100 bytes are still allowed, but only a single message
can be in flight at once. Defaults to 0. (No limit).
See also the max_inflight_messages option.
This option applies globally.
Reloaded on reload signal.
max_inflight_messagescountThe maximum number of outgoing QoS 1 or 2 messages that can be
in the process of being transmitted simultaneously.
This includes messages currently going through
handshakes and messages that are being retried.
Defaults to 20. Set to 0 for no maximum. If set to 1,
this will guarantee in-order delivery of
messages.
This option applies globally.
Reloaded on reload signal.
max_keepalivevalueFor MQTT v5 clients, it is possible to have the
server send a "server keepalive" value that will
override the keepalive value set by the client. This
is intended to be used as a mechanism to say that the
server will disconnect the client earlier than it
anticipated, and that the client should use the new
keepalive value. The max_keepalive option allows you to
specify that clients may only connect with keepalive
less than or equal to this value, otherwise they will
be sent a server keepalive telling them to use
max_keepalive. This only applies to MQTT v5 clients.
The maximum value is 65535. Set to 0 to allow infinite
keepalive. Defaults to 0.

Set to 0 to allow clients to set keepalive = 0, which
means no keepalive checks are made and the client will
never be disconnected by the broker if no messages are
received. You should be very sure this is the behaviour
that you want.

For MQTT v3.1.1 and v3.1 clients, there is no mechanism
to tell the client what keepalive value they should use.
If an MQTT v3.1.1 or v3.1 client specifies a keepalive
time greater than max_keepalive they will be sent a
CONNACK message with the "identifier rejected" reason
code, and disconnected.

This option applies globally.
Reloaded on reload signal.
max_packet_sizevalueFor MQTT v5 clients, it is possible to have the
server send a "maximum packet size" value that will
instruct the client it will not accept MQTT packets
with size greater than value bytes.
This applies to the full MQTT packet, not just the
payload. Setting this option to a positive value will
set the maximum packet size to that number of bytes. If
a client sends a packet which is larger than this
value, it will be disconnected. This applies to all
clients regardless of the protocol version they are
using, but v3.1.1 and earlier clients will of course
not have received the maximum packet size information.

Defaults to 2000000 bytes since 2.1. Earlier versions
defaulted to no limit.

This option applies to all clients, not just those
using MQTT v5, but it is not possible to notify clients
using MQTT v3.1.1 or MQTT v3.1 of the limit.
Setting below 20 bytes is forbidden because it is
likely to interfere with normal client operation even
with small payloads.
This option applies globally.
Reloaded on reload signal.
max_queued_bytescountThe number of outgoing QoS 1 and 2 messages above those currently in-flight will be
queued (per client) by the broker. Once this limit has been reached, subsequent
messages will be silently dropped. This is an important option if you are sending
messages at a high rate and/or have clients who are slow to respond or may be offline
for extended periods of time. Defaults to 0. (No maximum).
See also the
max_queued_messages option.
If both max_queued_messages and max_queued_bytes are specified,
packets will be queued until the first limit is reached.

This option applies globally.
Reloaded on reload signal.
max_queued_messagescountThe maximum number of QoS 1 or 2 messages to hold in the
queue (per client) above those messages that are currently
in flight. Defaults to 1000. Set to 0 for no maximum (not
recommended). See also the
queue_qos0_messages and
max_queued_bytes options.
This option applies globally.
Reloaded on reload signal.
memory_limitlimit
This option sets the maximum number of heap memory bytes that the broker
will allocate, and hence sets a hard limit on memory use by the broker.
Memory requests that exceed this value will be denied. The effect will
vary depending on what has been denied. If an incoming message is being
processed, then the message will be dropped and the publishing client
will be disconnected. If an outgoing message is being sent, then the
individual message will be dropped and the receiving client will be
disconnected. Defaults to no limit.
This option is only available if memory tracking support is compiled
in.
Reloaded on reload signal. Setting to a lower value and reloading will
not result in memory being freed.
message_size_limitlimitThis option sets the maximum publish payload size
that the broker will allow. Received messages that
exceed this size will not be accepted by the broker. This means that the
message will not be forwarded on to subscribing clients, but the QoS flow
will be completed for QoS 1 or QoS 2 messages. MQTT v5 clients using QoS 1
or QoS 2 will receive a PUBACK or PUBREC with the "implementation specific
error" reason code.
The default value is 0, which means that all valid MQTT
messages are accepted. MQTT imposes a maximum payload
size of 268435455 bytes.
This option applies globally.
Reloaded on reload signal.
password_filefile pathNote: It is suggested that you use the
mosquitto_password_file plugin instead of this
option. Using plugins for authentication and authorisation
allows greater control of what listeners they are applied to,
without the need for the deprecated
per_listener_settings option.

Set the path to a password file. If defined, the
contents of the file are used to control client access
to the broker. The file can be created using the
mosquitto_passwd(1)
utility. If mosquitto is compiled without TLS support
(it is recommended that TLS support is included), then
the password file should be a text file with each line
in the format "username:password", where the colon and
password are optional but recommended. If
allow_anonymous is set to
false, only users defined in
this file will be able to connect. Setting
allow_anonymous to
true when
password_fileis defined is
valid and could be used with acl_file to have e.g. read
only guest/anonymous accounts and defined users that
can publish.
If per_listener_settings is
true, this option applies to
the current listener being configured only. If
per_listener_settings is
false, this option applies
to all listeners.
Reloaded on reload signal. The currently loaded
username and password data will be freed and reloaded.
Clients that are already connected will not be
affected.
See also
mosquitto_passwd(1) and
https://mosquitto.org/documentation/dynamic-security/
per_listener_settings [ true | false ]If true, then
authentication and access control settings will be
controlled on a per-listener basis. The following
options are affected:
password_file,
acl_file, psk_file,
allow_anonymous,
allow_zero_length_clientid,
auto_id_prefix.
plugin,
plugin_opt_*,
Note that if set to true, then a durable client (i.e.
with clean session set to false) that has disconnected
will use the ACL settings defined for the listener that
it was most recently connected to.
The default behaviour is for this to be set to
false, which maintains the
settings behaviour from previous versions of
mosquitto.
Reloaded on reload signal.
persistence [ true | false ]
If true, then built-in persistence
is enabled. It is recommended that a plugin based persistence
is used instead.

If enabled, connection, subscription and message data
will be written to disk in mosquitto.db at the location
dictated by persistence_location. When mosquitto is
restarted, it will reload the information stored in
mosquitto.db. The data will be written to disk when
mosquitto closes and also at periodic intervals as
defined by autosave_interval. Writing of the persistence
database may also be forced by sending mosquitto the
SIGUSR1 signal. If false,
the data will be stored in memory only. Defaults to
false.

The persistence file may change its format in a new
version. The broker can currently read all old formats,
but will only save in the latest format. It should always
be safe to upgrade, but cautious users may wish to take a
copy of the persistence file before installing a new
version so that they can roll back to an earlier version
if necessary.
This option applies globally.
Reloaded on reload signal.
persistence_filefile name
The filename to use for the built-in persistent database.
Defaults to mosquitto.db.

This option applies globally.
Reloaded on reload signal.
persistence_locationpath
The path where plugins should store any persistence
data, and the path where the built-in persistence will
store its data. If not given, then the current directory
is used.

This option applies globally.
Reloaded on reload signal.
persistent_client_expirationduration
This option allows the session of persistent clients (those with clean
session set to false) that are not currently connected to be removed if they
do not reconnect within a certain time frame. This is a non-standard option
in MQTT v3.1. MQTT v3.1.1 and v5.0 allow brokers to remove client sessions.

Badly designed clients may set clean session to false whilst using a randomly
generated client id. This leads to persistent clients that connect once and
never reconnect. This option allows these clients to be removed. This option
allows persistent clients (those with clean session set to false) to be
removed if they do not reconnect within a certain time frame.

The expiration period should be an integer followed
by one of s h d w m y for second, hour, day, week, month and year
respectively. For example:

persistent_client_expiration 2m

persistent_client_expiration 14d

persistent_client_expiration 1y

Although it is possible to specify the expiration time in seconds, this is not a
suggestion that you should use a short expiration interval. If you have a system
where you think the clients should be automatically expired in a short time you
should see about fixing the clients instead where possible.

As this is a non-standard option, the default if not
set is to never expire persistent clients.

This option applies globally.
Reloaded on reload signal.
pid_filefile pathWrite a pid file to the file specified. If not given
(the default), no pid file will be written. If the pid
file cannot be written, mosquitto will exit.
If mosquitto is being automatically started by an
init script it will usually be required to write a pid
file. This should then be configured as e.g.
/var/run/mosquitto/mosquitto.pid
Not reloaded on reload signal.
plugin_opt_*value
Options to be passed to the most recent
plugin defined in the
configuration file. See the specific
plugin instructions for details of what
options are available.

Applies to the current plugin/global_plugin being configured.

This is also available as the auth_opt_*
option, but this use is deprecated and will be removed
in a future version.

pluginfile pathSpecify an external module to use for authentication,
access control, and other features. This allows custom
username/password and access control functions to be
created and other behaviour to be modified.
Can be specified multiple times to load multiple
plugins. The plugins will be processed in the order
that they are specified.
If password_file, or
acl_file are used in the config file
alongsize plugin, the plugin
checks will run before the built in checks.
Not currently reloaded on reload signal.

If per_listener_settings is set to
true, this plugin will be
loaded for the current listener only.

See also
https://mosquitto.org/documentation/dynamic-security/
and the global_plugin option.

This is also available as the auth_plugin
option, but this use is deprecated and will be removed
in a future version.

psk_filefile pathSet the path to a pre-shared-key file. This option
requires a listener to be have PSK support enabled. If
defined, the contents of the file are used to control
client access to the broker. Each line should be in the
format "identity:key", where the key is a hexadecimal
string with no leading "0x". A client connecting to a
listener that has PSK support enabled must provide a
matching identity and PSK to allow the encrypted
connection to proceed.
If per_listener_settings is
true, this option applies to
the current listener being configured only. If
per_listener_settings is
false, this option applies
to all listeners.
Reloaded on reload signal. The currently loaded
identity and key data will be freed and reloaded.
Clients that are already connected will not be
affected.
queue_qos0_messages [ true | false ]Set to true to queue
messages with QoS 0 when a persistent client is
disconnected. When bridges topics are configured with QoS level 1 or 2 incoming
QoS 0 messages for these topics are also queued.
These messages are included in the limit
imposed by max_queued_messages. Defaults to
false.
Note that the MQTT v3.1.1 spec states that only QoS 1
and 2 messages should be saved in this situation so
this is a non-standard option.
This option applies globally.
Reloaded on reload signal.
retain_available [ true | false ]If set to false, then retained messages are not
supported. Clients that send a message with the retain
bit will be disconnected if this option is set to
false. Defaults to true.
This option applies globally.
Reloaded on reload signal.
retain_expiry_intervalminutes
The default behaviour of mosquitto is to remove retained
messages that have reached their message-expiry-interval
property the next time that that message is accessed -
either by being replaced by a new message, or on the
next subscription that matches the message. If you have
a pattern of publishing many retained messages with a
message-expiry-interval, but that are not subscribed to,
then the expired retained messages will remain in
memory. This option configures the broker to
periodically check the retained tree for expired
messages.

Defaults to off. Setting to a value greater than zero
means the broker will make a check at an interval of
that number of minutes.

This option applies globally.
Reloaded on reload signal.
set_tcp_nodelay [ true | false ]If set to true, the TCP_NODELAY option will be set on
client sockets to disable Nagle's algorithm. This
has the effect of reducing latency of some messages
at potentially increasing the number of TCP packets
being sent. Defaults to false.
This option applies globally.
Reloaded on reload signal.
sys_intervalsecondsThe integer number of seconds between updates of the
$SYS subscription hierarchy, which provides status
information about the broker. If unset, defaults to 10
seconds.
Set to 0 to disable publishing the $SYS hierarchy
completely.
This option applies globally.
Reloaded on reload signal.
upgrade_outgoing_qos [ true | false ]The MQTT specification requires that the QoS of a
message delivered to a subscriber is never upgraded to
match the QoS of the subscription. Enabling this option
changes this behaviour. If
upgrade_outgoing_qos is set
true, messages sent to a
subscriber will always match the QoS of its
subscription. This is a non-standard option not
provided for by the spec. Defaults to
false.
This option applies globally.
Reloaded on reload signal.
userusernameWhen run as root, change to this user and its primary
group on startup. If set to "mosquitto" or left unset,
and if the "mosquitto" user does not exist, then
mosquitto will change to the "nobody" user instead.
If this is set to another value and mosquitto is unable
to change to this user and group, it will exit with an
error. The user specified must have read/write access
to the persistence database if it is to be written. If
run as a non-root user, this setting has no effect.
Defaults to mosquitto.
This setting has no effect on Windows and so you
should run mosquitto as the user you wish it to run
as.
Not reloaded on reload signal.

Listeners
The network ports that mosquitto listens on can be controlled
using listeners. The default listener options can be overridden and
further listeners can be created.
General Options
accept_protocol_versionsversions
Accepted protocol versions. This sets what versions
of the MQTT protocol will be accepted on this
listener. Can be any combination of 3, 4, 5 in a
comma separated list, e.g.

# Allow v5.0 only:
listener 1883
accept_protocol_versions 5

# Allow v3.1 and v3.1.1:
listener 1884
accept_protocol_versions 3, 4

Defaults to allowing all versions.

Reloaded on reload signal.
bind_addressaddressThis option is deprecated and will be removed in a
future version. Use the listener instead.

Listen for incoming network connections on the
specified IP address/hostname only. This is useful
to restrict access to certain network interfaces.
To restrict access to mosquitto to the local host
only, use "bind_address localhost". This only
applies to the default listener. Use the
listener option to control other
listeners.
It is recommended to use an explicit
listener rather than rely on the
implicit default listener options like this.
Not reloaded on reload signal.
bind_interfacedeviceListen for incoming network connections only on
the specified interface. This is similar to the
bind_address option but is useful
when an interface has multiple addresses or the
address may change.
If used at the same time as the
bind_address for the default
listener, or the bind
address/host part of the
listener, then bind_interface
will take priority.
This option is not available on Windows and AIX.
Not reloaded on reload signal.
enable_proxy_protocol [ 2 | 1 ]
Enable PROXY protocol support for this listener.
Versions 1 and 2 are supported, if you have the
choice then version 2 is recommended because it
gives you access to TLS information, and support
Unix sockets.

This option requires the use of a load
balancer/proxy such as HAProxy in front of
Mosquitto, with the proxy configured to use the
PROXY protocol.

The PROXY protocol is used to send information about
client socket connections from the proxy to the
broker. Without this, the connection information and
logs in the broker will contain the IP address and
port of the proxy itself, rather than the client.

Enabling this option should only be done when a
trusted proxy is placed in front of Mosquitto, and
when no other external access to Mosquitto is
possible. Giving external access to a listener with
this option enabled is a security risk, particularly
if you are using client certificates on the proxy.

When using PROXY version 2, this option can be used
with TLS termination on the proxy. In this case, TLS
information will be passed to the broker as well.
Use proxy_protocol_v2_require_tls
to reject clients that do not use TLS - this is strongly
recommended. Enabling require_certificate
on the listener will result in the broker checking the TLS
information provided to ensure that the client has provided
a valid certificate. Enabling use_identity_as_username
as well will result in the commonName
value from the certificate being used as the client username instead
of any provided in the CONNECT packet. In both cases, the listener
must not have TLS configured.

It is not possible to use the use_subject_as_username,
certfile, or keyfile options
in conjunction with enable_proxy_protocol.

Not reloaded on reload signal.
http_dirdirectoryWhen a listener is using the http_api protocol,
it is possible to serve http data as well. Set
http_dir to a directory which
contains the files you wish to serve. If this
option is not specified, then no normal http
connections will be possible.

This option is also available for websockets
listeners if Mosquitto is
compiled with websockets support provided by
libwebsockets. This is not the default, and will be
removed in version 3.0.

Not reloaded on reload signal.
listenerport[bind address/host/unix socket path]Listen for incoming network connection on the
specified port. A second optional argument allows
the listener to be bound to a specific ip
address/hostname. If this variable is used and
neither the global bind_address
nor port options are used then the
default listener will not be started.
The bind address/host option
allows this listener to be bound to a specific IP
address by passing an IP address or hostname. For
websockets listeners, it is only possible to pass
an IP address here.
On systems that support Unix Domain Sockets, this
option can also be used to create a Unix socket rather
than opening a TCP socket. In this case, the port must
be set to 0, and the unix socket path must be given.
This option may be specified multiple times. See
also the mount_point
option.
Not reloaded on reload signal.
listener_allow_anonymous [ true | false ]
Boolean value that determines whether clients that
connect without providing a username are allowed to
connect to this specific listener. If set, this overrides
the value set by allow_anonymous

If set to false
then another means of connection should be created to
control authenticated client access.

If not explicitly set, the value from allow_anonymous will be used.

Not reloaded on reload signal.
auto_id_prefixprefix
This option allows you to set a string that will be prefixed
to the automatically generated client ids (i.e. for when a
client connects without providing a client id) to aid
visibility in logs. Defaults to auto-.

Not reloaded on reload signal.
max_connectionscountLimit the total number of clients connected for
the current listener. Set to -1
to have "unlimited" connections. Note that other
limits may be imposed that are outside the control
of mosquitto. See e.g.
limits.conf.
Not reloaded on reload signal.
max_qosvalueLimit the QoS value allowed for clients connecting to this
listener. Defaults to 2, which means any QoS can be
used. Set to 0 or 1 to limit to those QoS values.
This makes use of an MQTT v5 feature to notify
clients of the limitation. MQTT v3.1.1 clients will
not be aware of the limitation. Clients publishing
to this listener with a too-high QoS will be
disconnected.
Not reloaded on reload signal.
max_topic_alias_brokernumberWhen publishing to MQTT v5 clients, Mosquitto can
create topic aliases on a first come first serve basis,
i.e. the topics that are published to a client first have
aliases created. This option controls the number of aliases
per client. It applies per listener.
Note that this behaviour is not guaranteed to remain
the same. It is possible that future versions introduce
mechanisms for controlling which topics receive aliases.

This option sets the maximum number topic aliases
that Mosquitto will create for an MQTT v5 client,
even if the client allows more.
For example, if the client sets
topic-alias-maximum to 100 and this option is set to
10, the broker will create at most 10 topic aliases.
Likewise, if the client sets topic-alias-maximum to
20 and this option is set to 100, then the broker
will create at most 20 topic aliases.
Defaults to 10. Maximum of 65535. Set to 0 to
disable broker to client topic aliases completely.

Not reloaded on reload signal.
max_topic_aliasnumberThis option sets the maximum number topic aliases
that an MQTT v5 client is allowed to create. This option
applies per listener. Defaults to 10. Set to 0 to
disallow topic aliases from clients. The maximum value possible is 65535.
Not reloaded on reload signal.
mount_pointtopic prefixThis option is used with the listener option to
isolate groups of clients. When a client connects
to a listener which uses this option, the string
argument is attached to the start of all topics for
this client. This prefix is removed when any
messages are sent to the client. This means a
client connected to a listener with mount point
example can only see
messages that are published in the topic hierarchy
example and below.
Not reloaded on reload signal.
portport numberThis option is deprecated and will be removed in a
future version. Use the listener instead.

Set the network port for the default listener to
listen on. Defaults to 1883.
Not reloaded on reload signal.
It is recommended to use an explicit
listener rather than rely on the
implicit default listener options like this.
protocolvalue
Set the protocol to accept for the current listener. Can
be mqtt, the default,
websockets, or http_api.

mqtt: the standard MQTT listener.

websockets: MQTT tunnelled over WebSockets.
If the legacy websockets support using libwebsockets is used,
then only a reduced TLS feature set is available, namely
cafile, certfile,
keyfile, ciphers, and
ciphers_tls1.3.

http_api: This starts the listener as a very
simple webserver (see the http_dir option)
that can also serve some HTTP API requests. TLS is supported
for this listener, however only the certfile and
keyfile options are allowed. Authentication is
not currently possible - to use this listener it is strongly
recommended to bind the listener to the loopback interface and
then configure a reverse proxy with the appropriate encryption
and authentication.

Not reloaded on reload signal.
proxy_protocol_v2_require_tls [ true | false ]
When a listener is using the PROXY protocol, this
option can be used to require that the client
connection is using TLS. If set to true, then the
PROXY protocol header must contain a TLS
indicator. If it does not, the connection will be
closed. Defaults to false.

Not reloaded on reload signal.
socket_domain [ ipv4 | ipv6 ]By default, a listener will attempt to listen on
all supported IP protocol versions. If you do not
have an IPv4 or IPv6 interface you may wish to
disable support for either of those protocol
versions. In particular, note that due to the
limitations of the websockets library, it will only
ever attempt to open IPv6 sockets if IPv6 support
is compiled in, and so will fail if IPv6 is not
available.
Set to ipv4 to force the
listener to only use IPv4, or set to
ipv6 to force the listener to only
use IPv6. If you want support for both IPv4 and
IPv6, then do not use the
socket_domain option.
Not reloaded on reload signal.
use_username_as_clientid [ true | false ]Set use_username_as_clientid to
true to replace the clientid that a client
connected with its username. This allows
authentication to be tied to the clientid, which
means that it is possible to prevent one client
disconnecting another by using the same
clientid. Defaults to false.
If a client connects with no username it will be
disconnected as not authorised when this option is
set to true. Do not use in conjunction with
clientid_prefixes.
This does not apply globally, but on a per-listener basis.
See also
use_identity_as_username.
Not reloaded on reload signal.
packet_buffer_sizesize, websockets_headers_sizesize
Change the size of the buffer used when reading from
the network before the size of the MQTT packet is
known. Defaults to 4096. Packets received that are
smaller than this value in principle only need a
single read() call, making reading packets more
efficient.

This also operates as the option that sets the size
of the buffer used by websockets when reading the
initial header. If you are passing large header data
such as cookies then you may need to increase this
value.

websockets_log_levellevelChange the websockets logging level. This is a
global option, it is not possible to set per
listener. This is an integer that is interpreted by
libwebsockets as a bit mask for its lws_log_levels
enum. See the libwebsockets documentation for more
details.
To use this option, log_type
websockets must also be enabled.
Defaults to 0.
websockets_originlevel
If set, this will be compared to the http origin
header when a connection attempts to upgrade to
WebSockets. Only matching origins will be allowed.
Use the exact string provided by the browser in the
origin header, e.g.
http://example.com:8080.
Can be specified multiple times per listener.

If not set, connections from any origin will be allowed.

Requires libwebsockets 3.1.0 or later.

Certificate based SSL/TLS Support
The following options are available for all listeners to
configure certificate based SSL support. See also
"Pre-shared-key based SSL/TLS support".
cafilefile pathcafile is used to define the
path to a file containing the PEM encoded CA
certificates that are trusted when checking incoming
client certificates.

capathdirectory pathcapath is used to define a
directory that contains PEM encoded CA certificates
that are trusted when checking incoming client
certificates. For capath to
work correctly, the certificates files must have
".pem" as the file ending and you must run
"openssl rehash <path to capath>" each time
you add/remove a certificate.

capath is not supported for websockets.
certfilefile path
Path to the PEM encoded server certificate. This
option and keyfile must be present
to enable certificate based TLS encryption.

The certificate pointed to by this option will be
reloaded when Mosquitto receives a SIGHUP signal.
This can be used to load new certificates prior to
the existing ones expiring.

cipherscipher:list
The list of allowed ciphers for this listener, for
TLS v1.2 and earlier only, each separated with
a colon. Available ciphers can be obtained using
the "openssl ciphers" command.

ciphers_tls1.3cipher:list
The list of allowed ciphersuites for this listener,
for TLS v1.3, each separated with a colon.

crlfilefile pathIf you have require_certificate
set to true, you can
create a certificate revocation list file to revoke
access to particular client certificates. If you
have done this, use crlfile to point to the PEM
encoded revocation file.
dhparamfilefile pathTo allow the use of ephemeral DH key exchange,
which provides forward security, the listener must
load DH parameters. This can be specified with the
dhparamfile option. The dhparamfile can be
generated with the command e.g.

openssl dhparam -out dhparam.pem 2048
disable_client_cert_date_checks [ true | false ]
If set true, disable_client_cert_date_checks will change the certificate
verification behaviour to allow client certificates that are expired or are not yet
valid, when using require_certificate true.

Defaults to false
keyfilefile path
If tls_keyform equals "pem" this is the
path to the PEM encoded server key. This option
and certfile must be present
to enable certificate based TLS encryption. If
tls_keyform is "engine" this represents
the engine handle of the private key.

The private key pointed to by this option will be
reloaded when Mosquitto receives a SIGHUP signal.
This can be used to load new keys prior to
the existing ones expiring.

require_certificate [ true | false ]By default an SSL/TLS enabled listener will
operate in a similar fashion to a https enabled web
server, in that the server has a certificate signed
by a CA and the client will verify that it is a
trusted certificate. The overall aim is encryption
of the network traffic. By setting
require_certificate to
true, a client connecting
to this listener must provide a valid certificate in
order for the network connection to proceed. This
allows access to the broker to be controlled outside
of the mechanisms provided by MQTT.
tls_engineengineA valid openssl engine id. These can be listed with
openssl engine command.
tls_engine_kpass_sha1engine_kpass_sha1SHA1 of the private key password when using an
TLS engine. Some TLS engines such as the TPM
engine may require the use of a password in order
to be accessed. This option allows a hex encoded
SHA1 hash of the password to the engine directly,
instead of the user being prompted for the
password.
tls_keyform [ pem | engine ]Specifies the type of private key in use when
making TLS connections.. This can be "pem" or
"engine". This parameter is useful when a TPM
module is being used and the private key has been
created with it. Defaults to "pem", which means
normal private key files are used.
tls_versionversion
Configure the minimum version of the TLS protocol to be
used for this listener. Possible values are
tlsv1.3 and
tlsv1.2.
If left unset, the default is to allow TLS v1.3 and v1.2.

In Mosquitto version 1.6.x and earlier, this
option set the only TLS protocol version that
was allowed, rather than the minimum.

use_identity_as_username [ true | false ]If require_certificate is
true, you may set
use_identity_as_username to
true to use the CN value
from the client certificate as a username. If this
is true, the
password_file option will not be
used for this listener.
This takes priority over
use_subject_as_username if both
are set to true.
See also
use_subject_as_username
use_subject_as_username [ true | false ]If require_certificate is
true, you may set
use_subject_as_username to
true to use the complete subject value
from the client certificate as a username. If this
is true, the
password_file option will not be
used for this listener.
The subject will be generated in a form similar
to CN=test client,OU=Production,O=Server,L=Nottingham,ST=Nottinghamshire,C=GB.
See also
use_identity_as_username

Pre-shared-key based SSL/TLS Support
The following options are available for all listeners to
configure pre-shared-key based SSL support. See also
"Certificate based SSL/TLS support".
cipherscipher:listWhen using PSK, the encryption ciphers used will
be chosen from the list of available PSK ciphers.
If you want to control which ciphers are available,
use this option. The list of available ciphers can
be obtained using the "openssl ciphers" command and
should be provided in the same format as the output
of that command.
psk_hinthintThe psk_hint option enables
pre-shared-key support for this listener and also
acts as an identifier for this listener. The hint
is sent to clients and may be used locally to aid
authentication. The hint is a free form string that
doesn't have much meaning in itself, so feel free
to be creative.
If this option is provided, see
psk_file to define the pre-shared
keys to be used or create a security plugin to
handle them.
tls_versionversion
Configure the minimum version of the TLS protocol to be
used for this listener. Possible values are
tlsv1.3 and
tlsv1.2.
If left unset, the default is to allow TLS v1.3 and v1.2.

In Mosquitto version 1.6.x and earlier, this
option set the only TLS protocol version that
was allowed, rather than the minimum.
use_identity_as_username [ true | false ]Set use_identity_as_username to
have the psk identity sent by the client used as
its username. The username will be checked as
normal, so password_file or
another means of authentication checking must be
used. No password will be used.

Configuring Bridges
Multiple bridges (connections to other brokers) can be configured
using the following variables.
Reloaded on reload signal.
addressaddress[:port][address[:port]], addressesaddress[:port][address[:port]]Specify the address and optionally the port of the
bridge to connect to. This must be given for each
bridge connection. If the port is not specified, the
default of 1883 is used.
If you use an IPv6 address, then the port is not
optional.
Multiple host addresses can be specified on the
address config. See the round_robin
option for more details on the behaviour of bridges
with multiple addresses.
bridge_attempt_unsubscribe [ true | false ]If a bridge has topics that have "out" direction, the
default behaviour is to send an unsubscribe request to
the remote broker on that topic. This means that
changing a topic direction from "in" to "out" will not
keep receiving incoming messages. Sending these
unsubscribe requests is not always desirable, setting
bridge_attempt_unsubscribe to
false will disable sending
the unsubscribe request. Defaults to
true.
bridge_bind_addressip address
If you need to have the bridge connect over a particular
network interface, use bridge_bind_address to tell the
bridge which local IP address the socket should bind to,
e.g. bridge_bind_address 192.168.1.10.

bridge_max_packet_sizevalue
If you wish to restrict the size of messages sent to a
remote bridge, use this option. This sets the maximum
number of bytes for the total message, including headers
and payload. Note that MQTT v5 brokers may provide their
own maximum-packet-size property. In this case, the
smaller of the two limits will be used. Set to 0 for
"unlimited".

bridge_max_topic_aliasvalueIf the bridge is using MQTT v5, this option sets the
maximum number of topic aliases that the bridge will
allow the remote broker to configure. Defaults to 10,
maximum of 65535. Set to 0 to disable incoming topic
aliases completely.
bridge_outgoing_retain [ true | false ]Some MQTT brokers do not allow retained messages. MQTT v5 gives
a mechanism for brokers to tell clients that they do not support
retained messages, but this is not possible for MQTT v3.1.1 or v3.1.
If you need to bridge to a v3.1.1 or v3.1 broker that does not support
retained messages, set the bridge_outgoing_retain
option to false. This will remove the
retain bit on all outgoing messages to that bridge, regardless of any
other setting. Defaults to true.
bridge_protocol_versionversionSet the version of the MQTT protocol to use with for
this bridge. Can be one of
mqttv50,
mqttv311 or
mqttv31. Defaults to
mqttv311.
bridge_receive_maximumcount
If the bridge is using MQTT v5.0 then use
bridge_receive_maximum
to limit the number QoS 1 or 2 messages that can be
in-flight at once. Must be 1-65535. Defaults to
max_inflight_messages, which defaults
to 20.

bridge_session_expiry_intervalinterval
If the bridge is using MQTT v5.0 then use
bridge_session_expiry_interval
to set the session expiry interval. Set to
0 to have the session expire
immediately when the connection drops. Set to
0xFFFFFFFF to have an infinite
expiry interval. Otherwise the expiry interval is set to
the number of seconds that you specify. Defaults to 0.

bridge_tcp_keepaliveidleintervalcounter
Set TCP keepalive parameters for this bridge connection.
Use this option to allow you to set a long MQTT
keepalive value, whilst still being able to detect the
connection dropping in a reasonable time.

This may be useful when bridging to services that bill
for PINGREQ messages.

Disabled by default.
bridge_tcp_user_timeouttimeout
It specifies the maximum amount of time (in milliseconds) that
transmitted data may remain unacknowledged at TCP level.
Popular Linux distributions seem to set this time to "up to 20
minutes with system defaults" (from Linux tcp man page).
The default time is related to tcp_retries2.
Reducing this value helps detecting dropped connections faster.

Be aware that when used in combination with TCP Keepalive, it might
change the latter's behavior.

You can find more details about this setting at:
https://blog.cloudflare.com/when-tcp-sockets-refuse-to-die/

Only available on Linux.

cleansession [ true | false ]Set the clean session option for this bridge. Setting
to false (the default),
means that all subscriptions on the remote broker are
kept in case of the network connection dropping. If set
to true, all subscriptions
and messages on the remote broker will be cleaned up if
the connection drops. Note that setting to
true may cause a large
amount of retained messages to be sent each time the
bridge reconnects.
If you are using bridges with
cleansession set to
false (the default), then
you may get unexpected behaviour from incoming topics
if you change what topics you are subscribing to. This
is because the remote broker keeps the subscription for
the old topic. If you have this problem, connect your
bridge with cleansession set to
true, then reconnect with
cleansession set to false as
normal.
local_cleansession [ true | false]The regular cleansession covers both the local subscriptions
and the remote subscriptions. local_cleansession allows splitting this.
Setting false will mean that the local connection
will preserve subscription, independent of the remote connection.

Defaults to the value of bridge.cleansession unless explicitly specified.
connectionnameThis variable marks the start of a new bridge
connection. It is also used to give the bridge a name
which is used as the client id on the remote
broker.
keepalive_intervalsecondsSet the number of seconds after which the bridge
should send a ping if no other traffic has occurred.
Defaults to 60. A minimum value of 5 seconds
is allowed.
idle_timeoutsecondsSet the amount of time a bridge using the lazy start
type must be idle before it will be stopped. Defaults
to 60 seconds.
local_clientididSet the clientid to use on the local broker. If not
defined, this defaults to
local.<remote_clientid>. If you are
bridging a broker to itself, it is important that
local_clientid and remote_clientid do not match.
local_passwordpasswordConfigure the password to be used when connecting
this bridge to the local broker. This may be important
when authentication and ACLs are being used.
local_usernameusernameConfigure the username to be used when connecting
this bridge to the local broker. This may be important
when authentication and ACLs are being used.
notifications [ true | false ]If set to true, publish
notification messages to the local and remote brokers
giving information about the state of the bridge
connection. Retained messages are published to the
topic $SYS/broker/connection/<remote_clientid>/state
unless otherwise set with
notification_topics. If the message
is 1 then the connection is active, or 0 if the
connection has failed. Defaults to
true.
This uses the Last Will and Testament (LWT) feature.
notifications_local_only [ true | false ]If set to true, only publish
notification messages to the local broker giving
information about the state of the bridge connection.
Defaults to false.
notification_topictopicChoose the topic on which notifications will be
published for this bridge. If not set the messages will
be sent on the topic
$SYS/broker/connection/<remote_clientid>/state.
remote_clientididSet the client id for this bridge connection. If not
defined, this defaults to 'name.hostname', where name
is the connection name and hostname is the hostname of
this computer.
This replaces the old "clientid" option to avoid
confusion with local/remote sides of the bridge.
"clientid" remains valid for the time being.
remote_passwordvalueConfigure a password for the bridge. This is used for
authentication purposes when connecting to a broker
that supports MQTT v3.1 and up and requires a username
and/or password to connect. This option is only valid
if a remote_username is also supplied.
This replaces the old "password" option to avoid
confusion with local/remote sides of the bridge.
"password" remains valid for the time being.
remote_usernamenameConfigure a username for the bridge. This is used for
authentication purposes when connecting to a broker
that supports MQTT v3.1 and up and requires a username
and/or password to connect. See also the
remote_password option.
This replaces the old "username" option to avoid
confusion with local/remote sides of the bridge.
"username" remains valid for the time being.
restart_timeoutbase cap [stable], restart_timeoutconstantSet the amount of time a bridge using the automatic
start type will wait until attempting to reconnect.
This option can be configured to use a constant delay
time in seconds, or to use a backoff mechanism based on
"Decorrelated Jitter", which adds a degree of
randomness to when the restart occurs, starting at the
base and increasing up to the cap. The backoff time will be reset to
base after a successful connection.
When stable is specified, the backoff time
will be reset only if the connection remains open for at least
stable seconds. Base has a minimum of 1 second
and a maximum of 3600 seconds. Cap has a minimum of base, and a maximum of
7200 seconds.
Set a constant timeout of 20 seconds:

restart_timeout 20
Set backoff with a base (start value) of 10 seconds and a cap (upper
limit) of 60 seconds:

restart_timeout 10 60
Same as previous example, but wait for the connection to be stable for
at least 30 seconds before resetting the backoff:

restart_timeout 10 60 30
Defaults to jitter with a base of 5 seconds and cap
of 30 seconds.
round_robin [ true | false ]If the bridge has more than one address given in the
address/addresses configuration, the round_robin option
defines the behaviour of the bridge on a failure of the
bridge connection. If round_robin is
false, the default value,
then the first address is treated as the main bridge
connection. If the connection fails, the other
secondary addresses will be attempted in turn. Whilst
connected to a secondary bridge, the bridge will
periodically attempt to reconnect to the main bridge
until successful.
If round_robin is true,
then all addresses are treated as equals. If a
connection fails, the next address will be tried and if
successful will remain connected until it fails.
start_type [ automatic | lazy | once ]Set the start type of the bridge. This controls how
the bridge starts and can be one of three types:
automatic, lazy
and once. Note
that RSMB provides a fourth start type "manual" which
isn't currently supported by mosquitto.
automatic is the default
start type and means that the bridge connection will be
started automatically when the broker starts and also
restarted after a short delay (30 seconds) if the
connection fails.
Bridges using the lazy
start type will be started automatically when the
number of queued messages exceeds the number set with
the threshold option. It will be
stopped automatically after the time set by the
idle_timeout parameter. Use this start
type if you wish the connection to only be active when
it is needed.
A bridge using the once
start type will be started automatically when the
broker starts but will not be restarted if the
connection fails.
thresholdcountSet the number of messages that need to be queued for
a bridge with lazy start type to be restarted.
Defaults to 10 messages.
topicpattern [[[ out | in | both ] qos-level] local-prefix remote-prefix]
Define a topic pattern to be shared between the two
brokers. Any topics matching the pattern (which may
include wildcards) are shared. The pattern may be
enclosed in double quotes in case it contains a space.
The second parameter
defines the direction that the messages will be shared
in, so it is possible to import messages from a remote
broker using in, export
messages to a remote broker using
out or share messages in
both directions. If this parameter is not defined, the
default of out is used. The
QoS level defines the publish/subscribe QoS level used
for this topic and defaults to 0.

The local-prefix and
remote-prefix options allow
topics to be remapped when publishing to and receiving
from remote brokers. This allows a topic tree from the
local broker to be inserted into the topic tree of the
remote broker at an appropriate place.
For incoming topics, the bridge will prepend the
pattern with the remote prefix and subscribe to the
resulting topic on the remote broker. When a matching
incoming message is received, the remote prefix will be
removed from the topic and then the local prefix
added.
For outgoing topics, the bridge will prepend the
pattern with the local prefix and subscribe to the
resulting topic on the local broker. When an outgoing
message is processed, the local prefix will be removed
from the topic then the remote prefix added.
When using topic mapping, an empty prefix can be
defined using the place marker
"". Using the empty marker
for the topic itself is also valid. The table below
defines what combination of empty or value is
valid. The Full Local Topic and
Full Remote Topic show the resulting
topics that would be used on the local and remote ends
of the bridge. For example, for the first table row if
you publish to L/topic on the local
broker, then the remote broker will receive a message
on the topic R/topic.
PatternLocal PrefixRemote PrefixValidityFull Local TopicFull Remote Topic
patternL/R/validL/patternR/pattern
patternL/""validL/patternpattern
pattern""R/validpatternR/pattern
pattern""""valid (no remapping)patternpattern
""localremotevalid (remap single local topic to remote)localremote
""local""invalid
""""remoteinvalid
""""""invalid

To remap an entire topic tree, use e.g.:

topic # both 2 local/topic/ remote/topic/
This option can be specified multiple times per
bridge.
Care must be taken to ensure that loops are not
created with this option. If you are experiencing high
CPU load from a broker, it is possible that you have a
loop where each broker is forever forwarding each other
the same messages.
See also the cleansession option if
you have messages arriving on unexpected topics when
using incoming topics.
Example Bridge Topic Remapping. 
The configuration below connects a bridge to the
broker at test.mosquitto.org. It
subscribes to the remote topic
$SYS/broker/clients/total and
republishes the messages received to the local topic
test/mosquitto/org/clients/total

connection test-mosquitto-org
address test.mosquitto.org
cleansession true
topic clients/total in 0 test/mosquitto/org/ $SYS/broker/

try_private [ true | false ]If try_private is set to
true, the bridge will
attempt to indicate to the remote broker that it is a
bridge not an ordinary client. If successful, this
means that loop detection will be more effective and
that retained messages will be propagated correctly.
Not all brokers support this feature so it may be
necessary to set try_private to
false if your bridge does
not connect properly.
Defaults to true.
bridge_reload_type [ lazy | immediate ]If you change bridge options in the configuration file,
those configuration changes are applied during a bridge
reconnection. The bridge_reload_type option
determines when that reconnection happens, and can be set to either
lazy or immediate.
lazy is the default, and means
that any connected bridge will remain in its current state until
a natural reconnection happens, at which point the new configuration
will be used.
immediate forces a reconnection and so
uses the new configuration straight away.

SSL/TLS Support
The following options are available for all bridges to
configure SSL/TLS support.
bridge_alpnalpnConfigure the application layer protocol negotiation
option for the TLS session. Useful for brokers that support
both websockets and MQTT on the same port.
bridge_cafilefile pathAt least one of bridge_cafile, bridge_capath, or
bridge_tls_use_os_certs must be provided to
allow SSL/TLS support.
bridge_cafile is used to define the path to a file
containing the PEM encoded CA certificates that
have signed the certificate for the remote broker.

bridge_capathfile pathAt least one of bridge_cafile, bridge_capath, or
bridge_tls_use_os_certs must be provided to
allow SSL/TLS support.
bridge_capath is used to define the path to a
directory containing the PEM encoded CA
certificates that have signed the certificate for
the remote broker. For bridge_capath to work
correctly, the certificate files must have ".crt"
as the file ending and you must run "openssl rehash
<path to bridge_capath>" each time you
add/remove a certificate.
bridge_certfilefile pathPath to the PEM encoded client certificate for
this bridge, if required by the remote
broker.
bridge_identityidentityPre-shared-key encryption provides an alternative
to certificate based encryption. A bridge can be
configured to use PSK with the
bridge_identity and
bridge_psk options. This is the
client identity used with PSK encryption. Only one
of certificate and PSK based encryption can be used
on one bridge at once.
bridge_insecure [ true | false ]When using certificate based TLS, the bridge will
attempt to verify the hostname provided in the
remote certificate matches the host/address being
connected to. This may cause problems in testing
scenarios, so bridge_insecure may
be set to true to
disable the hostname verification.
Setting this option to
true means that a
malicious third party could potentially impersonate
your server, so it should always be set to
false in production
environments.
bridge_keyfilefile pathPath to the PEM encoded private key for this
bridge, if required by the remote broker.
bridge_pskkeyPre-shared-key encryption provides an alternative
to certificate based encryption. A bridge can be
configured to use PSK with the
bridge_identity and
bridge_psk options. This is the
pre-shared-key in hexadecimal format with no "0x".
Only one of certificate and PSK based encryption
can be used on one bridge at once.
bridge_require_ocsp [ true | false ]When set to true, the bridge requires OCSP on the TLS
connection it opens as client.
bridge_tls_use_os_certs [ true | false ]At least one of bridge_cafile, bridge_capath, or
bridge_tls_use_os_certs must be provided to
allow SSL/TLS support.
Set bridge_tls_use_os_certs
to true to enable TLS for this bridge, and to
configure it to trust the default certificates
provided by openssl. This is typically a large
number of certificates. Defaults to false.
bridge_tls_versionversion
Configure the version of the TLS protocol to be
used for this bridge. Possible values are
tlsv1.3 and
tlsv1.2. Defaults to
tlsv1.2. The remote
broker must support the same version of TLS for the
connection to succeed.

bridge_cipherscipher:list
The list of allowed ciphers for this bridge, for
TLS v1.2 and earlier only, each separated with
a colon. Available ciphers can be obtained using
the "openssl ciphers" command.

bridge_ciphers_tls1.3cipher:list
The list of allowed ciphersuites for this bridge,
for TLS v1.3, each separated with a colon.

Files
mosquitto.conf

Bugs
mosquitto bug information can be found at
https://github.com/eclipse-mosquitto/mosquitto/issues

See Also
mosquitto(7)
,
mosquitto(8)
,
mosquitto_passwd(1)
,
mosquitto-tls(7)
,
mqtt(7)
,
limits.conf(5)
Author
Roger Light <roger@atchoo.org>