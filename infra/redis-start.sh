#!/bin/sh
set -eu
# A dedicated, generated local secret. Do not reuse the database password.
case "${CL_JOBS_BROKER_PASSWORD:-}" in *[!a-f0-9]*|"") echo 'Invalid broker secret configuration.' >&2; exit 1;; esac
[ "${#CL_JOBS_BROKER_PASSWORD}" -eq 64 ] || { echo 'Invalid broker secret length.' >&2; exit 1; }
umask 077
# Password is not put in process arguments. Host/Docker admins can still inspect
# container environment and this temporary file; this is not an encrypted vault.
printf 'bind 0.0.0.0
port 6379
protected-mode yes
requirepass %s
save ""
appendonly no
maxmemory 128mb
maxmemory-policy noeviction
' "$CL_JOBS_BROKER_PASSWORD" > /tmp/ledger-redis.conf
exec redis-server /tmp/ledger-redis.conf
