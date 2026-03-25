#!/usr/bin/env python3
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    os.environ.setdefault("BOT_TOKEN", "smoke-check-token")

    import tg_codex_bridge as bridge

    state = bridge.BridgeState(
        bridge.DEFAULT_HISTORY_LIMIT,
        bridge.DEFAULT_MODE_NAME,
        str(ROOT / bridge.DEFAULT_DB_PATH),
    )
    try:
        snapshot = state.get_status_snapshot(bridge.OWNER_USER_ID)
        required_keys = {
            "events_count",
            "facts_count",
            "history_count",
            "user_memory_profiles",
            "summary_snapshots",
            "relation_memory_rows",
        }
        missing = required_keys.difference(snapshot.keys())
        if missing:
            raise RuntimeError(f"status snapshot keys missing: {sorted(missing)}")
        self_model = state.get_self_model_state()
        if not self_model["identity"]:
            raise RuntimeError("self_model_state identity is empty")
        if len(state.get_drive_scores()) != len(bridge.DRIVE_NAMES):
            raise RuntimeError("drive_scores not initialized")
        print("smoke-check: ok")
        return 0
    finally:
        state.db.close()


if __name__ == "__main__":
    raise SystemExit(main())
