#!/bin/sh
set -eu
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$SCRIPT_DIR"

if [ -f "$SCRIPT_DIR/.env" ]; then
  # shellcheck disable=SC1091
  . "$SCRIPT_DIR/.env"
fi

: "${BOT_TOKEN:?BOT_TOKEN is required. Put it in .env or export it before launch.}"
: "${DB_PATH:=$SCRIPT_DIR/jarvis_memory.db}"
LOCK_PATH="${LOCK_PATH:-$SCRIPT_DIR/tg_codex_bridge.lock}"
: "${LEGACY_JARVIS_DB_PATH:=$SCRIPT_DIR/../jarvis_legacy_data/jarvis.db}"
LOG_PATH="$SCRIPT_DIR/tg_codex_bridge.log"
while true; do
  BOT_TOKEN="$BOT_TOKEN" \
  DB_PATH="$DB_PATH" \
  LOCK_PATH="$LOCK_PATH" \
  LEGACY_JARVIS_DB_PATH="$LEGACY_JARVIS_DB_PATH" \
  python3 tg_codex_bridge.py >> "$LOG_PATH" 2>&1 || true
  printf '[%s] bridge exited, restarting in 2s\n' "$(date '+%Y-%m-%d %H:%M:%S')" >> "$LOG_PATH"
  sleep 2
done
