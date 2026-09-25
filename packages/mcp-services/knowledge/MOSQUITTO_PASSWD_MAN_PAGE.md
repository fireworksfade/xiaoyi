Source: https://mosquitto.org/man/mosquitto_passwd-1.html

Name

mosquitto_passwd — manage password files for mosquitto

Synopsis

mosquitto_passwd [ -H hash ] [ -c | -D ] passwordfile username

mosquitto_passwd [ -H hash ] -b passwordfile username password

mosquitto_passwd -U passwordfile

Description

mosquitto_passwd is a tool for managing
password files for the mosquitto MQTT broker.

Usernames must not contain ":". Passwords are stored in a similar
format to crypt (3) .

Options

-b

Run in batch mode. This allows the password to be
provided at the command line which can be convenient
but should be used with care because the password will
be visible on the command line and in command
history.

-c

Create a new password file. If the file already
exists, it will be overwritten. If the filename
is specified as a dash - then the output will be to stdout. This only really
makes sense with -b .

-D

Delete the specified user from the password file.

-H

Choose the hash to use. Can be one of argon2id , sha512-pbkdf2 , or sha512 . Defaults to argon2id . The sha512 option is provided for
creating password files for use with Mosquitto 1.6
and earlier.

-U

This option can be used to upgrade/convert a password
file with plain text passwords into one using hashed
passwords. It will modify the specified file. It does
not detect whether passwords are already hashed, so
using it on a password file that already contains
hashed passwords will generate new hashes based on the
old hashes and render the password file
unusable.

passwordfile

The password file to modify.

username

The username to add/update/delete.

password

The password to use when in batch mode.

Exit Status

mosquitto_passwd returns zero on success or non-zero on error.

Examples

Add a user to a new password file:

mosquitto_passwd -c /etc/mosquitto/passwd ral

Add a user to an existing password file:

mosquitto_passwd /etc/mosquitto/passwd ral

Add a user to an existing password file, passing the password on the command line:

mosquitto_passwd -b /etc/mosquitto/passwd ral z2Dr0BsvtZ

Update the password for a user in an existing password file:

mosquitto_passwd /etc/mosquitto/passwd ral

Add a user to an existing password file using the sha512 hash for Mosquitto 1.6 compatibility:

mosquitto_passwd -H sha512 /etc/mosquitto/passwd ral

Delete a user from a password file

mosquitto_passwd -D /etc/mosquitto/passwd ral

Environment Variables

MOSQUITTO_UNSAFE_ALLOW_SYMLINKS

By default, sensitive file with a path including a
symbolic link will be refused to be loaded. Set this
environment variable to any value to allow load files
through symbolic links. Note that making use of this
variable could expose you to symlink attacks and so it
should only be used in cases where you are absolutely
sure this is not a risk.

Bugs

mosquitto bug information can be found at https://github.com/eclipse-mosquitto/mosquitto/issues

See Also
mosquitto (7) , mosquitto (8) , mosquitto.conf (5) , mqtt (7)

Author

Roger Light < roger@atchoo.org >
