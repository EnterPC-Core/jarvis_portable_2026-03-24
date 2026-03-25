#!/usr/bin/env python3
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "data" / "runtime_backups"
PRIMARY_DB = PROJECT_ROOT / "jarvis_memory.db"
LEGACY_DB = PROJECT_ROOT.parent / "jarvis_legacy_data" / "jarvis.db"

SAFE_VALUE_TABLES = {
    "bot_meta",
    "chat_modes",
    "warn_settings",
    "welcome_settings",
}
SENSITIVE_TABLE_MARKERS = {
    "chat_history",
    "chat_events",
    "memory_facts",
    "messages",
    "message_log",
    "private_messages",
    "users",
    "appeals",
    "appeal_events",
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def table_names(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    return [row[0] for row in rows]


def table_count(conn: sqlite3.Connection, table_name: str) -> int:
    return int(conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0])


def dump_schema(conn: sqlite3.Connection) -> str:
    rows = conn.execute(
        """
        SELECT sql
        FROM sqlite_master
        WHERE sql IS NOT NULL
          AND type IN ('table', 'index', 'trigger', 'view')
          AND name NOT LIKE 'sqlite_%'
        ORDER BY type, name
        """
    ).fetchall()
    return ";\n\n".join(row[0].strip().rstrip(";") for row in rows if row[0]) + ";\n"


def fetch_safe_rows(conn: sqlite3.Connection, table_name: str, limit: int = 50) -> list[dict]:
    cursor = conn.execute(f"SELECT * FROM {table_name} ORDER BY rowid LIMIT ?", (limit,))
    columns = [item[0] for item in cursor.description]
    rows = []
    for values in cursor.fetchall():
        rows.append({column: values[index] for index, column in enumerate(columns)})
    return rows


def build_summary(db_path: Path) -> dict:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        names = table_names(conn)
        counts = {}
        safe_tables = {}
        sensitive = {}
        for name in names:
            count = table_count(conn, name)
            counts[name] = count
            if name in SAFE_VALUE_TABLES:
                safe_tables[name] = fetch_safe_rows(conn, name)
            if name in SENSITIVE_TABLE_MARKERS:
                sensitive[name] = {
                    "rows": count,
                    "content_exported": False,
                }
        return {
            "database": str(db_path),
            "generated_at_utc": utc_now_iso(),
            "tables": names,
            "row_counts": counts,
            "safe_table_rows": safe_tables,
            "sensitive_tables": sensitive,
        }
    finally:
        conn.close()


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def export_db(db_path: Path, slug: str) -> None:
    conn = sqlite3.connect(db_path)
    try:
        schema_sql = dump_schema(conn)
    finally:
        conn.close()
    write_text(OUTPUT_DIR / f"{slug}.schema.sql", schema_sql)
    write_json(OUTPUT_DIR / f"{slug}.summary.json", build_summary(db_path))


def main() -> int:
    export_db(PRIMARY_DB, "jarvis_memory")
    if LEGACY_DB.exists():
        export_db(LEGACY_DB, "legacy_jarvis")
    manifest = {
        "generated_at_utc": utc_now_iso(),
        "project_root": str(PROJECT_ROOT),
        "artifacts": sorted(path.name for path in OUTPUT_DIR.glob("*") if path.is_file()),
        "notes": [
            "Это GitHub-safe snapshots: схемы, счётчики и ограниченные безопасные таблицы.",
            "Сырые переписки, события и приватные данные в репозиторий не экспортируются.",
        ],
    }
    write_json(OUTPUT_DIR / "manifest.json", manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
