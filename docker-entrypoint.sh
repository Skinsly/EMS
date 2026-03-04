#!/bin/sh
set -eu

mkdir -p /app/data /app/uploads

if [ "$(id -u)" = "0" ]; then
  chown -R appuser:appgroup /app/data /app/uploads || true
  exec su -s /bin/sh appuser -c 'exec "$@"' -- "$@"
fi

exec "$@"
