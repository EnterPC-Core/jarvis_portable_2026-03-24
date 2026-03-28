#!/bin/sh
set -eu
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$SCRIPT_DIR"
SUPERVISOR_PID_FILE="$SCRIPT_DIR/.jarvis_supervisor.pid"

if [ -f "$SUPERVISOR_PID_FILE" ]; then
  EXISTING_PID=$(cat "$SUPERVISOR_PID_FILE" 2>/dev/null || echo "")
  if [ -n "$EXISTING_PID" ] && kill -0 "$EXISTING_PID" 2>/dev/null; then
    exit 0
  fi
fi
printf '%s\n' "$$" > "$SUPERVISOR_PID_FILE"

cleanup_supervisor() {
  if [ -n "${BRIDGE_PID:-}" ]; then
    kill -TERM "$BRIDGE_PID" 2>/dev/null || true
    wait "$BRIDGE_PID" 2>/dev/null || true
  fi
  if [ -f "$SUPERVISOR_PID_FILE" ] && [ "$(cat "$SUPERVISOR_PID_FILE" 2>/dev/null || echo '')" = "$$" ]; then
    rm -f "$SUPERVISOR_PID_FILE"
  fi
}

trap cleanup_supervisor EXIT INT TERM

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
BOOT_LOG_PATH="$SCRIPT_DIR/supervisor_boot.log"
LOCK_CONFLICT_EXIT_CODE=75
LOG_ROTATE_SIZE_BYTES=$((1024 * 1024))

rotate_log_if_needed() {
  LOG_FILE="$1"
  if [ ! -f "$LOG_FILE" ]; then
    return 0
  fi
  LOG_SIZE=$(wc -c < "$LOG_FILE" 2>/dev/null || echo 0)
  if [ "${LOG_SIZE:-0}" -lt "$LOG_ROTATE_SIZE_BYTES" ]; then
    return 0
  fi
  ROTATE_STAMP=$(date -u '+%Y%m%dT%H%M%SZ')
  mv "$LOG_FILE" "${LOG_FILE}.${ROTATE_STAMP}.bak"
}

rotate_log_if_needed "$LOG_PATH"
rotate_log_if_needed "$BOOT_LOG_PATH"

read_pid_file() {
  if [ -f "$1" ]; then
    cat "$1" 2>/dev/null || true
  fi
}

is_bridge_healthy() {
  LOCK_PID=$(read_pid_file "$LOCK_PATH")
  if [ -z "$LOCK_PID" ] || ! kill -0 "$LOCK_PID" 2>/dev/null; then
    return 1
  fi
  if [ ! -f "$HEARTBEAT_PATH" ]; then
    return 1
  fi
  NOW_TS=$(date +%s)
  HEARTBEAT_TS=$(stat -c %Y "$HEARTBEAT_PATH" 2>/dev/null || echo 0)
  AGE=$((NOW_TS - HEARTBEAT_TS))
  if [ "$AGE" -gt "$HEARTBEAT_TIMEOUT_SECONDS" ]; then
    return 1
  fi
  return 0
}

printf '[%s] supervisor init script_dir=%s db_path=%s heartbeat=%s timeout=%ss\n' \
  "$(date '+%Y-%m-%d %H:%M:%S')" "$SCRIPT_DIR" "$DB_PATH" "$HEARTBEAT_PATH" "$HEARTBEAT_TIMEOUT_SECONDS" >> "$BOOT_LOG_PATH"
while true; do
  if [ -f "$SCRIPT_DIR/.env" ]; then
    unset OPENAI_API_KEY OPENAI_BASE_URL AUDIO_TRANSCRIBE_MODEL STT_BACKEND
    set -a
    # shellcheck disable=SC1091
    . "$SCRIPT_DIR/.env"
    set +a
  fi
  if is_bridge_healthy; then
    printf '[%s] bridge already healthy, waiting 5s\n' "$(date '+%Y-%m-%d %H:%M:%S')" >> "$BOOT_LOG_PATH"
    sleep 5
    continue
  fi
  rm -f "$HEARTBEAT_PATH"
  printf '[%s] launching bridge db_path=%s lock=%s\n' \
    "$(date '+%Y-%m-%d %H:%M:%S')" "$DB_PATH" "$LOCK_PATH" >> "$BOOT_LOG_PATH"
  RUNNING_UNDER_SUPERVISOR=1 PYTHONUNBUFFERED=1 python3 tg_codex_bridge.py >> "$LOG_PATH" 2>&1 &
  BRIDGE_PID=$!
  printf '[%s] bridge pid=%s started\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$BRIDGE_PID" >> "$BOOT_LOG_PATH"
  while kill -0 "$BRIDGE_PID" 2>/dev/null; do
    if [ -f "$HEARTBEAT_PATH" ]; then
      NOW_TS=$(date +%s)
      HEARTBEAT_TS=$(stat -c %Y "$HEARTBEAT_PATH" 2>/dev/null || echo 0)
      AGE=$((NOW_TS - HEARTBEAT_TS))
      if [ "$AGE" -gt "$HEARTBEAT_TIMEOUT_SECONDS" ]; then
        printf '[%s] heartbeat stale (%ss), killing pid=%s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$AGE" "$BRIDGE_PID" >> "$LOG_PATH"
        printf '[%s] heartbeat stale (%ss), killing pid=%s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$AGE" "$BRIDGE_PID" >> "$BOOT_LOG_PATH"
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
  if [ "$BRIDGE_STATUS" -eq "$LOCK_CONFLICT_EXIT_CODE" ]; then
    if is_bridge_healthy; then
      printf '[%s] bridge pid=%s exited status=%s but another healthy instance owns %s; waiting 5s\n' \
        "$(date '+%Y-%m-%d %H:%M:%S')" "$BRIDGE_PID" "$BRIDGE_STATUS" "$LOCK_PATH" >> "$BOOT_LOG_PATH"
      sleep 5
      continue
    fi
    printf '[%s] bridge lock conflict detected; another instance already owns %s. stopping this supervisor\n' \
      "$(date '+%Y-%m-%d %H:%M:%S')" "$LOCK_PATH" >> "$LOG_PATH"
    printf '[%s] bridge pid=%s exited status=%s due to lock conflict; stopping supervisor to avoid restart loop\n' \
      "$(date '+%Y-%m-%d %H:%M:%S')" "$BRIDGE_PID" "$BRIDGE_STATUS" >> "$BOOT_LOG_PATH"
    exit 0
  fi
  printf '[%s] bridge exited status=%s, restarting in 2s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$BRIDGE_STATUS" >> "$LOG_PATH"
  printf '[%s] bridge pid=%s exited status=%s, restarting in 2s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$BRIDGE_PID" "$BRIDGE_STATUS" >> "$BOOT_LOG_PATH"
  sleep 2
done
