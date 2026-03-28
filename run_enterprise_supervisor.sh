#!/bin/sh
set -eu
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$SCRIPT_DIR"
SUPERVISOR_PID_FILE="$SCRIPT_DIR/.enterprise_supervisor.pid"
LOG_PATH="$SCRIPT_DIR/enterprise_server.log"
BOOT_LOG_PATH="$SCRIPT_DIR/enterprise_supervisor_boot.log"
NVM_NODE_BIN="/home/userland/.nvm/versions/node/v18.20.8/bin"
HEALTH_URL="${ENTERPRISE_SERVER_HEALTH_URL:-http://127.0.0.1:8766/health}"

if [ -f "$SUPERVISOR_PID_FILE" ]; then
  EXISTING_PID=$(cat "$SUPERVISOR_PID_FILE" 2>/dev/null || echo "")
  if [ -n "$EXISTING_PID" ] && kill -0 "$EXISTING_PID" 2>/dev/null; then
    exit 0
  fi
fi
printf '%s\n' "$$" > "$SUPERVISOR_PID_FILE"

cleanup_supervisor() {
  if [ -f "$SUPERVISOR_PID_FILE" ] && [ "$(cat "$SUPERVISOR_PID_FILE" 2>/dev/null || echo '')" = "$$" ]; then
    rm -f "$SUPERVISOR_PID_FILE"
  fi
}

trap cleanup_supervisor EXIT INT TERM

if [ -f "$SCRIPT_DIR/.env" ]; then
  set -a
  . "$SCRIPT_DIR/.env"
  set +a
fi

if [ -x "$NVM_NODE_BIN/node" ]; then
  PATH="$NVM_NODE_BIN:$PATH"
  export PATH
fi

is_server_healthy() {
  python3 - "$HEALTH_URL" <<'PY'
import json
import sys
import urllib.request

url = sys.argv[1]
try:
    with urllib.request.urlopen(url, timeout=2) as response:
        payload = json.loads(response.read().decode("utf-8", "replace"))
    raise SystemExit(0 if payload.get("ok") else 1)
except Exception:
    raise SystemExit(1)
PY
}

printf '[%s] enterprise supervisor init\n' "$(date '+%Y-%m-%d %H:%M:%S')" >> "$BOOT_LOG_PATH"
while true; do
  if is_server_healthy; then
    printf '[%s] enterprise server already healthy, waiting 5s\n' "$(date '+%Y-%m-%d %H:%M:%S')" >> "$BOOT_LOG_PATH"
    sleep 5
    continue
  fi
  printf '[%s] launching enterprise_server.py\n' "$(date '+%Y-%m-%d %H:%M:%S')" >> "$BOOT_LOG_PATH"
  nohup env PYTHONUNBUFFERED=1 python3 "$SCRIPT_DIR/enterprise_server.py" >> "$LOG_PATH" 2>&1 &
  sleep 2
  if is_server_healthy; then
    printf '[%s] enterprise server healthy after launch, waiting 5s\n' "$(date '+%Y-%m-%d %H:%M:%S')" >> "$BOOT_LOG_PATH"
    sleep 5
    continue
  fi
  printf '[%s] enterprise server still unavailable, retrying in 2s\n' "$(date '+%Y-%m-%d %H:%M:%S')" >> "$BOOT_LOG_PATH"
  sleep 2
done
