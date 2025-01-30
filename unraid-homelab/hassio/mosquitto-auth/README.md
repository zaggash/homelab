### What

Build Mosquitto along with Mosquitto Go Auth
* https://github.com/eclipse-mosquitto/mosquitto
* https://github.com/iegomez/mosquitto-go-auth

### Why
Use SQLite db to manage authentication.
This allow to use colon, ":", character in username.
This help to integrate Meross devices managed locally which require MAC address as username.
* https://github.com/krahabb/meross_lan
  * https://github.com/krahabb/meross_lan/discussions/63
* https://github.com/bytespider/Meross

### How

mosquitto.conf
```
# Listen on port 1883 on all IPv4 interfaces
listener 1883
socket_domain ipv4
protocol mqtt

# SSL/TLS Configuration
listener 8883 0.0.0.0
socket_domain ipv4
protocol mqtt

require_certificate false
certfile /mosquitto/config/mqtt.crt
keyfile /mosquitto/config/mqtt.key

# Save the in-memory database to disk
persistence true
persistence_location /mosquitto/data

# Log to stderr and logfile
log_dest stderr

# Limits
max_queued_messages 8192

# Require authentication
allow_anonymous false

# Authentication plugin
auth_plugin /usr/share/mosquitto/go-auth.so
auth_opt_backends sqlite
auth_opt_hasher pbkdf2
auth_opt_cache true
auth_opt_auth_cache_seconds 300
auth_opt_auth_jitter_seconds 30
auth_opt_acl_cache_seconds 300
auth_opt_acl_jitter_seconds 30
auth_opt_log_level info

# Auth Sqlite plugin config
auth_opt_sqlite_source /mosquitto/config/authentication.db
auth_opt_sqlite_userquery SELECT Password FROM Users WHERE Name = ? LIMIT 1
```

Initiate the sqlite authentication.db database
```
sqlite3 authentication.db

CREATE TABLE Users (Name STRING, Password STRING);
.exit
```

Use the `pw` binary from the container to get the required password encrypted version.
```
$ pw -p password
PBKDF2$sha512$100000$wQ5MDv53lQSfxYJfXo7C6A==$Vj1ev0AlGwWdEeQgS0Ya2NC/j4qf970wQZkxJ0TME6OFGydOqRkshWfPAFWxJtPFLFX7pLEeOlnDL8xOK77Nng==
```

Populate authentication.db with auth credentials
```
sqlite3 authentication.db

INSERT INTO Users VALUES ('the-user', 'the-hashed-password');
.exit
```

Update a user password
```
sqlite3 authentication.db

UPDATE Users SET Password = '' WHERE Name = 'my-user';
.exit
```
