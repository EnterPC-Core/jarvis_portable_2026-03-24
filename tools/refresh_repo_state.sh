#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)

cd "$PROJECT_DIR"

python3 -m py_compile tg_codex_bridge.py
python3 tools/export_runtime_backups.py

printf 'Repo state refreshed:\n'
printf ' - syntax check passed\n'
printf ' - runtime backups updated\n'
