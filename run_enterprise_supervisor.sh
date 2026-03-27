#!/bin/sh
set -eu
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$SCRIPT_DIR"
SUPERVISOR_PID_FILE="$SCRIPT_DIR/.enterprise_supervisor.pid"
LOG_PATH="$SCRIPT_DIR/enterprise_server.log"
BOOT_LOG_PATH="$SCRIPT_DIR/enterprise_supervisor_boot.log"
NVM_NODE_BIN="/home/userland/.nvm/versions/node/v18.20.8/bin"

if [ -f "$SUPERVISOR_PID_FILE" ]; then
  EXISTING_PID=$(cat "$SUPERVISOR_PID_FILE" 2>/dev/null || echo "")
  if [ -n "$EXISTING_PID" ] && kill -0 "$EXISTING_PID" 2>/dev/null; then
    exit 0
  fi
fi
printf '%s\n' "$$" > "$SUPERVISOR_PID_FILE"

cleanup_supervisor() {
  if [ -n "${SERVER_PID:-}" ]; then
    kill -TERM "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
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

printf '[%s] enterprise supervisor init\n' "$(date '+%Y-%m-%d %H:%M:%S')" >> "$BOOT_LOG_PATH"
while true; do
  printf '[%s] launching enterprise_server.py\n' "$(date '+%Y-%m-%d %H:%M:%S')" >> "$BOOT_LOG_PATH"
  PYTHONUNBUFFERED=1 python3 enterprise_server.py >> "$LOG_PATH" 2>&1 &
  SERVER_PID=$!
  wait "$SERVER_PID" 2>/dev/null || true
  printf '[%s] enterprise server exited, restarting in 2s\n' "$(date '+%Y-%m-%d %H:%M:%S')" >> "$BOOT_LOG_PATH"
  sleep 2
done
