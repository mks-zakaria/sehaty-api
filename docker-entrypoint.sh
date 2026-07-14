#!/usr/bin/env bash
# Idempotent entrypoint. Schema is owned by sehaty-db (run `sehaty-migrate`
# out-of-band); this service never migrates on boot.
set -euo pipefail

role="${1:-web}"

case "$role" in
  web)
    exec uvicorn main:app --app-dir src --host 0.0.0.0 --port "${PORT:-8000}"
    ;;
  shell)
    exec /bin/bash
    ;;
  *)
    echo "unknown role: $role" >&2
    exit 1
    ;;
esac
