import sqlite3
from pathlib import Path

from SwiftProPDF.auth import init_db


def table_names(database_path: Path) -> set[str]:
    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    return {row[0] for row in rows}


def column_names(database_path: Path, table_name: str) -> set[str]:
    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {row[1] for row in rows}


def test_init_db_applies_alembic_schema(tmp_path: Path) -> None:
    db_path = tmp_path / "test.sqlite3"

    init_db(db_path)

    assert {
        "alembic_version",
        "users",
        "audit_events",
        "usage_tracking",
        "browser_hits",
        "user_security_questions",
        "user_sessions",
        "settings",
    }.issubset(table_names(db_path))
    assert {
        "premium_valid_from",
        "premium_valid_until",
        "weekly_usage_count",
        "lifetime_usage_count",
    }.issubset(column_names(db_path, "users"))
    assert {
        "user_id",
        "anonymous_id",
        "ip_address",
        "path",
        "hit_count",
    }.issubset(column_names(db_path, "browser_hits"))


def test_init_db_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "test.sqlite3"

    init_db(db_path)
    init_db(db_path)

    with sqlite3.connect(db_path) as connection:
        revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]

    assert revision == "20260619_0002"
