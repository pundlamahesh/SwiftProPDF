from pathlib import Path

from SwiftPDF.auth import (
    AuthError,
    create_user,
    create_user_session,
    delete_user_session,
    ensure_default_settings,
    get_setting,
    get_total_usage,
    init_db,
    is_user_session_active,
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


def test_user_session_limit_allows_only_two_active_sessions(tmp_path: Path) -> None:
    db_path = tmp_path / "test.sqlite3"
    init_db(db_path)

    user_id = create_user(db_path, "Test", "User", "user@example.com", "Passw0rd!234")
    create_user_session(db_path, user_id, "session-one", "Browser A", "127.0.0.1")
    create_user_session(db_path, user_id, "session-two", "Browser B", "127.0.0.2")

    try:
        create_user_session(db_path, user_id, "session-three", "Browser C", "127.0.0.3")
    except AuthError as exc:
        assert "already logged in on 2 devices" in str(exc)
    else:
        raise AssertionError("Expected third concurrent session to be rejected")

    assert is_user_session_active(db_path, user_id, "session-one")
    assert is_user_session_active(db_path, user_id, "session-two")


def test_deleting_user_session_frees_login_slot(tmp_path: Path) -> None:
    db_path = tmp_path / "test.sqlite3"
    init_db(db_path)

    user_id = create_user(db_path, "Test", "User", "user@example.com", "Passw0rd!234")
    create_user_session(db_path, user_id, "session-one")
    create_user_session(db_path, user_id, "session-two")

    delete_user_session(db_path, user_id, "session-one")
    create_user_session(db_path, user_id, "session-three")

    assert not is_user_session_active(db_path, user_id, "session-one")
    assert is_user_session_active(db_path, user_id, "session-three")
