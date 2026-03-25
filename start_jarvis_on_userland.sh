#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SUPERVISOR="$SCRIPT_DIR/run_jarvis_supervisor.sh"
OUT="$SCRIPT_DIR/tg_supervisor.out"
PATTERN="$SCRIPT_DIR/run_jarvis_supervisor.sh"

if pgrep -f "$PATTERN" >/dev/null 2>&1; then
  exit 0
fi

cd "$SCRIPT_DIR"
nohup sh "$SUPERVISOR" >> "$OUT" 2>&1 &
