#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
OUT="$SCRIPT_DIR/enterprise_server.out"
BOOT_LOG="$SCRIPT_DIR/enterprise_server_boot.log"
NVM_NODE_BIN="/home/userland/.nvm/versions/node/v18.20.8/bin"

if ps -ef | awk '/python3 .*enterprise_server.py/ && !/awk/ {found=1} END {exit(found ? 0 : 1)}'; then
  exit 0
fi

cd "$SCRIPT_DIR"
if [ -x "$NVM_NODE_BIN/node" ]; then
  PATH="$NVM_NODE_BIN:$PATH"
  export PATH
fi
printf '[%s] start_enterprise_on_userland.sh launching enterprise_server.py\n' "$(date '+%Y-%m-%d %H:%M:%S')" >> "$BOOT_LOG"
nohup python3 "$SCRIPT_DIR/enterprise_server.py" >> "$OUT" 2>&1 &
