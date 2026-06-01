from pathlib import Path

from SwiftPDF.auth import (
    create_user,
    ensure_default_settings,
    get_setting,
    get_total_usage,
    init_db,
    record_tool_usage,
)


def test_weekly_settings_are_initialized(tmp_path: Path) -> None:
    db_path = tmp_path / "test.sqlite3"
    init_db(db_path)
    ensure_default_settings(db_path)

    assert get_setting(db_path, "guest_weekly_limit") == "5"
    assert get_setting(db_path, "free_weekly_limit") == "10"
    assert get_setting(db_path, "premium_weekly_limit") == "0"


def test_record_tool_usage_tracks_weekly_counts(tmp_path: Path) -> None:
    db_path = tmp_path / "test.sqlite3"
    init_db(db_path)
    ensure_default_settings(db_path)

    user_id = create_user(db_path, "Test", "User", "user@example.com", "Passw0rd!234")
    assert get_total_usage(db_path, user_id=user_id) == 0

    record_tool_usage(db_path, "pdf-to-word", user_id=user_id)
    record_tool_usage(db_path, "pdf-to-word", user_id=user_id)

    assert get_total_usage(db_path, user_id=user_id) == 2
