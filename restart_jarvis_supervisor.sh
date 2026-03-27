#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$SCRIPT_DIR"

SUPERVISOR_PID_FILE="$SCRIPT_DIR/.jarvis_supervisor.pid"
LOCK_PATH="$SCRIPT_DIR/tg_codex_bridge.lock"
HEARTBEAT_PATH="$SCRIPT_DIR/tg_codex_bridge.heartbeat"
BOOT_LOG_PATH="$SCRIPT_DIR/supervisor_boot.log"

log_line() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$1" >> "$BOOT_LOG_PATH"
}

read_pid_file() {
  if [ -f "$1" ]; then
    cat "$1" 2>/dev/null || true
  fi
}

wait_pid_exit() {
  TARGET_PID="$1"
  WAIT_SECONDS="${2:-20}"
  if [ -z "$TARGET_PID" ]; then
    return 0
  fi
  i=0
  while kill -0 "$TARGET_PID" 2>/dev/null; do
    i=$((i + 1))
    if [ "$i" -ge "$WAIT_SECONDS" ]; then
      return 1
    fi
    sleep 1
  done
  return 0
}

clear_stale_lock() {
  if [ ! -f "$LOCK_PATH" ]; then
    return 0
  fi
  LOCK_PID=$(read_pid_file "$LOCK_PATH")
  if [ -n "$LOCK_PID" ] && kill -0 "$LOCK_PID" 2>/dev/null; then
    return 1
  fi
  rm -f "$LOCK_PATH"
  return 0
}

OLD_SUPERVISOR_PID=$(read_pid_file "$SUPERVISOR_PID_FILE")
if [ -n "$OLD_SUPERVISOR_PID" ] && kill -0 "$OLD_SUPERVISOR_PID" 2>/dev/null; then
  log_line "restart helper stopping supervisor pid=$OLD_SUPERVISOR_PID"
  kill -TERM "$OLD_SUPERVISOR_PID" 2>/dev/null || true
  if ! wait_pid_exit "$OLD_SUPERVISOR_PID" 25; then
    log_line "restart helper forcing supervisor pid=$OLD_SUPERVISOR_PID"
    kill -KILL "$OLD_SUPERVISOR_PID" 2>/dev/null || true
    wait_pid_exit "$OLD_SUPERVISOR_PID" 5 || true
  fi
fi

rm -f "$SUPERVISOR_PID_FILE" "$HEARTBEAT_PATH"

i=0
while [ -f "$LOCK_PATH" ]; do
  if clear_stale_lock; then
    break
  fi
  i=$((i + 1))
  if [ "$i" -ge 25 ]; then
    echo "restart helper: live lock still held, aborting" >&2
    exit 1
  fi
  sleep 1
done

log_line "restart helper launching fresh supervisor"
nohup /bin/sh "$SCRIPT_DIR/run_jarvis_supervisor.sh" >/tmp/jarvis_supervisor_restart.log 2>&1 </dev/null &
NEW_SUPERVISOR_PID=$!

sleep 3
if ! kill -0 "$NEW_SUPERVISOR_PID" 2>/dev/null; then
  echo "restart helper: new supervisor failed to stay alive" >&2
  exit 1
fi

log_line "restart helper launched supervisor pid=$NEW_SUPERVISOR_PID"
printf '%s\n' "$NEW_SUPERVISOR_PID"
