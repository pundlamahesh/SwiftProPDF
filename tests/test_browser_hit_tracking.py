from pathlib import Path

from SwiftProPDF.auth import ensure_default_settings, init_db
from SwiftProPDF.database import connect
from SwiftProPDF.web_app.app import create_app, is_browser_hit_ignored_ip


def browser_hit_count(database_path: Path) -> int:
    with connect(database_path) as connection:
        return int(connection.execute("SELECT COUNT(*) FROM browser_hits").fetchone()[0])


def test_loopback_monitoring_ip_is_ignored_for_browser_hits(tmp_path: Path) -> None:
    db_path = tmp_path / "test.sqlite3"
    init_db(db_path)
    ensure_default_settings(db_path)
    app = create_app()
    app.config["DATABASE"] = db_path

    response = app.test_client().get("/", environ_base={"REMOTE_ADDR": "127.0.0.1"})

    assert response.status_code == 200
    assert browser_hit_count(db_path) == 0


def test_real_ip_is_tracked_for_browser_hits(tmp_path: Path) -> None:
    db_path = tmp_path / "test.sqlite3"
    init_db(db_path)
    ensure_default_settings(db_path)
    app = create_app()
    app.config["DATABASE"] = db_path

    response = app.test_client().get("/", environ_base={"REMOTE_ADDR": "203.0.113.10"})

    assert response.status_code == 200
    assert browser_hit_count(db_path) == 1


def test_browser_hit_ignored_ips_support_cidr_ranges() -> None:
    assert is_browser_hit_ignored_ip("10.0.3.4", ("10.0.0.0/8",))
    assert not is_browser_hit_ignored_ip("203.0.113.10", ("10.0.0.0/8",))
