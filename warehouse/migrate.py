"""Lightweight SQLite column migrations."""

from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


def _has_column(engine: Engine, table: str, column: str) -> bool:
    return column in {c["name"] for c in inspect(engine).get_columns(table)}


def migrate_sqlite(engine: Engine) -> None:
    if not str(engine.url).startswith("sqlite"):
        return
    alters = [
        ("chat_instances", "goal_text", "ALTER TABLE chat_instances ADD COLUMN goal_text TEXT"),
        ("chat_instances", "live_enabled", "ALTER TABLE chat_instances ADD COLUMN live_enabled BOOLEAN DEFAULT 1"),
        (
            "chat_instances",
            "live_state_json",
            "ALTER TABLE chat_instances ADD COLUMN live_state_json TEXT DEFAULT '{}'",
        ),
        (
            "chat_instances",
            "report_snapshot_json",
            "ALTER TABLE chat_instances ADD COLUMN report_snapshot_json TEXT",
        ),
        ("chat_instances", "dataset_json", "ALTER TABLE chat_instances ADD COLUMN dataset_json TEXT"),
        (
            "chat_instances",
            "dataset_row_count",
            "ALTER TABLE chat_instances ADD COLUMN dataset_row_count INTEGER DEFAULT 0",
        ),
        (
            "chat_messages",
            "is_live_carrier",
            "ALTER TABLE chat_messages ADD COLUMN is_live_carrier BOOLEAN DEFAULT 0",
        ),
    ]
    with engine.begin() as conn:
        for table, column, stmt in alters:
            if not _has_column(engine, table, column):
                conn.execute(text(stmt))
