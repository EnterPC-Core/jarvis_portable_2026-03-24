#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
OUT="$SCRIPT_DIR/enterprise_server.out"
BOOT_LOG="$SCRIPT_DIR/enterprise_server_boot.log"
NVM_NODE_BIN="/home/userland/.nvm/versions/node/v18.20.8/bin"
SUPERVISOR="$SCRIPT_DIR/run_enterprise_supervisor.sh"
HEALTH_URL="${ENTERPRISE_SERVER_HEALTH_URL:-http://127.0.0.1:8766/health}"

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

if is_server_healthy; then
  exit 0
fi

if ps -ef | awk '/run_enterprise_supervisor\.sh/ && !/awk/ {found=1} END {exit(found ? 0 : 1)}'; then
  exit 0
fi

cd "$SCRIPT_DIR"
if [ -x "$NVM_NODE_BIN/node" ]; then
  PATH="$NVM_NODE_BIN:$PATH"
  export PATH
fi
printf '[%s] start_enterprise_on_userland.sh launching supervisor=%s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$SUPERVISOR" >> "$BOOT_LOG"
nohup /bin/sh "$SUPERVISOR" >> "$OUT" 2>&1 &
