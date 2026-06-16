from pathlib import Path

from SwiftProPDF.auth import init_db, log_audit_event
from SwiftProPDF.web_app.job_events import ASYNC_JOB_FAILED_EVENT
from SwiftProPDF.web_app.job_service import async_job_health


def test_async_job_health_reports_disabled_state_and_recent_errors(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("SWIFTPROPDF_ASYNC_TOOLS", "0")
    database_path = tmp_path / "test.sqlite3"
    init_db(database_path)
    log_audit_event(
        database_path,
        ASYNC_JOB_FAILED_EVENT,
        details="compress: Only PDF files are supported.",
    )

    health = async_job_health(database_path)

    assert health["enabled"] is False
    assert health["queued_jobs"] == 0
    assert health["failed_jobs"] == 1
    assert health["worker_status"] == "Disabled"
    assert health["redis_status"] == "Disabled"
    assert health["recent_errors"][0]["details"] == "compress: Only PDF files are supported."
