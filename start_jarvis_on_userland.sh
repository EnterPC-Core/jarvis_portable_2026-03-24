#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SUPERVISOR="$SCRIPT_DIR/run_jarvis_supervisor.sh"
OUT="$SCRIPT_DIR/tg_supervisor.out"
BOOT_LOG="$SCRIPT_DIR/supervisor_boot.log"
PATTERN="run_jarvis_supervisor.sh"
LOCK_PATH="${LOCK_PATH:-$SCRIPT_DIR/tg_codex_bridge.lock}"
HEARTBEAT_PATH="${HEARTBEAT_PATH:-$SCRIPT_DIR/tg_codex_bridge.heartbeat}"
HEARTBEAT_TIMEOUT_SECONDS="${HEARTBEAT_TIMEOUT_SECONDS:-90}"

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
  [ "$AGE" -le "$HEARTBEAT_TIMEOUT_SECONDS" ]
}

if is_bridge_healthy; then
  exit 0
fi

if pgrep -f "$PATTERN" >/dev/null 2>&1; then
  exit 0
fi

cd "$SCRIPT_DIR"
printf '[%s] start_jarvis_on_userland.sh launching supervisor=%s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$SUPERVISOR" >> "$BOOT_LOG"
nohup sh "$SUPERVISOR" >> "$OUT" 2>&1 &
