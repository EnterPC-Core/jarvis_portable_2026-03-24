#!/bin/sh
set -eu
SCRIPT_DIR="/data/data/com.termux/files/home/jarvis-ai-worker"
SUPERVISOR="$SCRIPT_DIR/run_jarvis_supervisor.sh"
OUT="$SCRIPT_DIR/tg_supervisor.out"
BOOT_LOG="$SCRIPT_DIR/supervisor_boot.log"
PATTERN="run_jarvis_supervisor.sh"
if pgrep -f "$PATTERN" >/dev/null 2>&1; then
  exit 0
fi
cd "$SCRIPT_DIR"
printf '[%s] start_jarvis_on_termux.sh launching supervisor=%s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$SUPERVISOR" >> "$BOOT_LOG"
nohup sh "$SUPERVISOR" >> "$OUT" 2>&1 &
