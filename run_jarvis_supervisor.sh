#!/bin/sh
set -eu
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$SCRIPT_DIR"

if [ -f "$SCRIPT_DIR/.env" ]; then
  unset OPENAI_API_KEY OPENAI_BASE_URL AUDIO_TRANSCRIBE_MODEL STT_BACKEND
  set -a
  # shellcheck disable=SC1091
  . "$SCRIPT_DIR/.env"
  set +a
fi

NVM_NODE_BIN="/home/userland/.nvm/versions/node/v18.20.8/bin"
if [ -x "$NVM_NODE_BIN/node" ]; then
  PATH="$NVM_NODE_BIN:$PATH"
  export PATH
fi

: "${BOT_TOKEN:?BOT_TOKEN is required. Put it in .env or export it before launch.}"
: "${DB_PATH:=$SCRIPT_DIR/jarvis_memory.db}"
LOCK_PATH="${LOCK_PATH:-$SCRIPT_DIR/tg_codex_bridge.lock}"
: "${HEARTBEAT_PATH:=$SCRIPT_DIR/tg_codex_bridge.heartbeat}"
: "${HEARTBEAT_TIMEOUT_SECONDS:=90}"
: "${LEGACY_JARVIS_DB_PATH:=$SCRIPT_DIR/../jarvis_legacy_data/jarvis.db}"
LOG_PATH="$SCRIPT_DIR/tg_codex_bridge.log"
while true; do
  rm -f "$HEARTBEAT_PATH"
  RUNNING_UNDER_SUPERVISOR=1 PYTHONUNBUFFERED=1 python3 tg_codex_bridge.py >> "$LOG_PATH" 2>&1 &
  BRIDGE_PID=$!
  while kill -0 "$BRIDGE_PID" 2>/dev/null; do
    if [ -f "$HEARTBEAT_PATH" ]; then
      NOW_TS=$(date +%s)
      HEARTBEAT_TS=$(stat -c %Y "$HEARTBEAT_PATH" 2>/dev/null || echo 0)
      AGE=$((NOW_TS - HEARTBEAT_TS))
      if [ "$AGE" -gt "$HEARTBEAT_TIMEOUT_SECONDS" ]; then
        printf '[%s] heartbeat stale (%ss), killing pid=%s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$AGE" "$BRIDGE_PID" >> "$LOG_PATH"
        kill -TERM "$BRIDGE_PID" 2>/dev/null || true
        sleep 3
        kill -KILL "$BRIDGE_PID" 2>/dev/null || true
        wait "$BRIDGE_PID" 2>/dev/null || true
        break
      fi
    fi
    sleep 5
  done
  BRIDGE_STATUS=0
  wait "$BRIDGE_PID" 2>/dev/null || BRIDGE_STATUS=$?
  printf '[%s] bridge exited status=%s, restarting in 2s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$BRIDGE_STATUS" >> "$LOG_PATH"
  sleep 2
done
