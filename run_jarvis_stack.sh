#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$SCRIPT_DIR"

SUP_PID=''
API_PID=''

shutdown() {
  if [ -n "$SUP_PID" ]; then
    kill "$SUP_PID" 2>/dev/null || true
  fi
  if [ -n "$API_PID" ]; then
    kill "$API_PID" 2>/dev/null || true
  fi
  wait 2>/dev/null || true
}

trap shutdown INT TERM EXIT

sh "$SCRIPT_DIR/run_jarvis_supervisor.sh" &
SUP_PID=$!

sh "$SCRIPT_DIR/run_jarvis_mobile_api.sh" &
API_PID=$!

printf 'Jarvis stack started: supervisor pid=%s, mobile_api pid=%s\n' "$SUP_PID" "$API_PID"

while :; do
  if ! kill -0 "$SUP_PID" 2>/dev/null; then
    printf 'Jarvis supervisor exited, stopping stack\n'
    exit 1
  fi
  if ! kill -0 "$API_PID" 2>/dev/null; then
    printf 'Jarvis mobile API exited, stopping stack\n'
    exit 1
  fi
  sleep 2
done
