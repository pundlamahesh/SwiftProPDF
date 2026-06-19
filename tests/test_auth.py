from datetime import datetime, timedelta, timezone
from pathlib import Path

import SwiftProPDF.auth as auth_module
from SwiftProPDF.auth import (
    AuthError,
    USER_SESSION_IDLE_MINUTES,
    admin_stats,
    create_user,
    create_user_with_role,
    create_user_session,
    delete_user_session,
    ensure_default_settings,
    get_setting,
    get_total_usage,
    init_db,
    is_user_session_active,
    record_browser_hit,
    record_tool_usage,
)


def test_weekly_settings_are_initialized(tmp_path: Path) -> None:
    db_path = tmp_path / "test.sqlite3"
    init_db(db_path)
    ensure_default_settings(db_path)

    assert get_setting(db_path, "guest_weekly_limit") == "20"
    assert get_setting(db_path, "free_weekly_limit") == "30"
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


def test_browser_hits_count_unregistered_visitors(tmp_path: Path) -> None:
    db_path = tmp_path / "test.sqlite3"
    init_db(db_path)

    user_id = create_user_with_role(db_path, "Test", "User", "user@example.com", "Passw0rd!234", "FREE")

    record_browser_hit(db_path, "/", anonymous_id="guest-one", ip_address="127.0.0.1")
    record_browser_hit(db_path, "/", anonymous_id="guest-one", ip_address="127.0.0.1")
    record_browser_hit(db_path, "/account", user_id=user_id, ip_address="127.0.0.2")

    stats = admin_stats(db_path)
    assert stats["browser_hits"] == 3
    assert stats["unregistered_browser_hits"] == 2


def test_user_session_limit_allows_only_two_active_sessions(tmp_path: Path) -> None:
    db_path = tmp_path / "test.sqlite3"
    init_db(db_path)

    user_id = create_user_with_role(db_path, "Test", "User", "user@example.com", "Passw0rd!234", "FREE")
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


def test_admin_user_session_limit_is_unlimited(tmp_path: Path) -> None:
    db_path = tmp_path / "test.sqlite3"
    init_db(db_path)

    user_id = create_user_with_role(db_path, "Admin", "User", "admin@example.com", "Passw0rd!234", "ADMIN")

    create_user_session(db_path, user_id, "session-one")
    create_user_session(db_path, user_id, "session-two")
    create_user_session(db_path, user_id, "session-three")

    assert is_user_session_active(db_path, user_id, "session-one")
    assert is_user_session_active(db_path, user_id, "session-two")
    assert is_user_session_active(db_path, user_id, "session-three")


def test_deleting_user_session_frees_login_slot(tmp_path: Path) -> None:
    db_path = tmp_path / "test.sqlite3"
    init_db(db_path)

    user_id = create_user_with_role(db_path, "Test", "User", "user@example.com", "Passw0rd!234", "FREE")
    create_user_session(db_path, user_id, "session-one")
    create_user_session(db_path, user_id, "session-two")

    delete_user_session(db_path, user_id, "session-one")
    create_user_session(db_path, user_id, "session-three")

    assert not is_user_session_active(db_path, user_id, "session-one")
    assert is_user_session_active(db_path, user_id, "session-three")


def test_user_session_expires_after_idle_limit(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "test.sqlite3"
    init_db(db_path)
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    monkeypatch.setattr(auth_module, "utc_now", lambda: start)

    user_id = create_user_with_role(db_path, "Test", "User", "user@example.com", "Passw0rd!234", "FREE")
    create_user_session(db_path, user_id, "session-one")

    expired_at = start + timedelta(minutes=USER_SESSION_IDLE_MINUTES, seconds=1)
    monkeypatch.setattr(auth_module, "utc_now", lambda: expired_at)

    assert not is_user_session_active(db_path, user_id, "session-one")


def test_active_user_session_refreshes_idle_limit(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "test.sqlite3"
    init_db(db_path)
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    monkeypatch.setattr(auth_module, "utc_now", lambda: start)

    user_id = create_user_with_role(db_path, "Test", "User", "user@example.com", "Passw0rd!234", "FREE")
    create_user_session(db_path, user_id, "session-one")

    first_request = start + timedelta(minutes=USER_SESSION_IDLE_MINUTES - 1)
    monkeypatch.setattr(auth_module, "utc_now", lambda: first_request)
    assert is_user_session_active(db_path, user_id, "session-one")

    refreshed_request = first_request + timedelta(minutes=USER_SESSION_IDLE_MINUTES - 1)
    monkeypatch.setattr(auth_module, "utc_now", lambda: refreshed_request)
    assert is_user_session_active(db_path, user_id, "session-one")
