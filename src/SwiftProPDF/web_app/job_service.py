import os
import shutil
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

from celery.result import AsyncResult
from werkzeug.utils import secure_filename

from SwiftProPDF.auth import parse_timestamp, utc_now
from SwiftProPDF.database import DBRow, connect
from SwiftProPDF.web_app.celery_app import celery_app
from SwiftProPDF.web_app.celery_app import redis_url as celery_redis_url
from SwiftProPDF.web_app.job_events import ASYNC_JOB_FAILED_EVENT
from SwiftProPDF.web_app.tasks import process_tool_job
from SwiftProPDF.security.file_scanner import save_and_scan_upload

ASYNC_QUEUE_NAME = os.getenv("SWIFTPROPDF_ASYNC_QUEUE_NAME", "celery")
ASYNC_HEALTH_TIMEOUT_SECONDS = 0.5


def async_tools_enabled() -> bool:
    return os.getenv("SWIFTPROPDF_ASYNC_TOOLS", "0") == "1"


def jobs_root(default_instance_path: Path) -> Path:
    configured = os.getenv("SWIFTPROPDF_JOBS_DIR")
    if configured:
        return Path(configured)
    return default_instance_path / "jobs"


def save_request_files(files, input_dir: Path) -> dict[str, list[dict]]:
    saved: dict[str, list[dict]] = {}
    for field_name in files:
        saved[field_name] = []
        for uploaded_file in files.getlist(field_name):
            if not uploaded_file or uploaded_file.filename == "":
                continue
            filename = secure_filename(uploaded_file.filename)
            input_path = input_dir / f"{len(saved[field_name]):02d}-{uuid4()}-{filename}"
            save_and_scan_upload(uploaded_file, input_path)
            saved[field_name].append(
                {
                    "filename": filename,
                    "path": str(input_path),
                }
            )
    return saved


def enqueue_tool_job(
    tool_name: str,
    form,
    files,
    instance_path: Path,
    database_path: Path,
    actor: dict,
) -> tuple[str, dict]:
    job_id = uuid4().hex
    root = jobs_root(instance_path)
    job_dir = root / job_id
    input_dir = job_dir / "input"
    output_dir = job_dir / "output"
    input_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        payload = {
            "tool_name": tool_name,
            "form": {key: form.get(key, "") for key in form.keys()},
            "files": save_request_files(files, input_dir),
            "output_dir": str(output_dir),
            "database_path": str(database_path),
            "actor": actor,
        }
        task = process_tool_job.apply_async(args=[payload], task_id=job_id)
    except Exception:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise

    return task.id, payload


def job_result(job_id: str) -> AsyncResult:
    return AsyncResult(job_id, app=celery_app)


def list_async_job_errors(database_path: Path, limit: int = 5) -> list[dict]:
    with connect(database_path) as connection:
        connection.row_factory = DBRow
        rows = connection.execute(
            """
            SELECT audit_events.id, audit_events.user_id, audit_events.event_type,
                   audit_events.details, audit_events.ip_address, audit_events.created_at,
                   users.email
            FROM audit_events
            LEFT JOIN users ON users.id = audit_events.user_id
            WHERE audit_events.event_type = ?
            ORDER BY audit_events.created_at DESC, audit_events.id DESC
            LIMIT ?
            """,
            (ASYNC_JOB_FAILED_EVENT, limit),
        ).fetchall()
    return [dict(row) for row in rows]


def count_recent_async_job_errors(database_path: Path, hours: int = 24) -> int:
    cutoff = utc_now() - timedelta(hours=hours)
    recent_errors = list_async_job_errors(database_path, limit=500)
    return sum(
        1
        for event in recent_errors
        if (parse_timestamp(event.get("created_at")) or cutoff) >= cutoff
    )


def async_job_health(database_path: Path) -> dict:
    recent_errors = list_async_job_errors(database_path)
    failed_jobs = count_recent_async_job_errors(database_path)
    health = {
        "enabled": async_tools_enabled(),
        "queued_jobs": 0,
        "active_jobs": 0,
        "failed_jobs": failed_jobs,
        "worker_status": "Disabled",
        "worker_status_variant": "status-pill--muted",
        "worker_meta": "Async tools are off.",
        "redis_status": "Disabled",
        "redis_status_variant": "status-pill--muted",
        "redis_meta": "Redis is not required while async tools are off.",
        "recent_errors": recent_errors,
    }

    if not health["enabled"]:
        return health

    redis_ok, queued_jobs, redis_error = redis_queue_status()
    health["queued_jobs"] = queued_jobs
    if redis_ok:
        health.update(
            {
                "redis_status": "Connected",
                "redis_status_variant": "status-pill--success",
                "redis_meta": f"Broker queue: {ASYNC_QUEUE_NAME}",
            }
        )
    else:
        health.update(
            {
                "redis_status": "Unavailable",
                "redis_status_variant": "status-pill--danger",
                "redis_meta": redis_error or "Could not connect to Redis.",
                "worker_status": "Unknown",
                "worker_status_variant": "status-pill--warning",
                "worker_meta": "Worker state cannot be checked without Redis.",
            }
        )
        return health

    worker_state = celery_worker_state()
    health["active_jobs"] = worker_state["active_jobs"]
    health["queued_jobs"] += worker_state["reserved_jobs"] + worker_state["scheduled_jobs"]
    if worker_state["worker_count"]:
        health.update(
            {
                "worker_status": "Online",
                "worker_status_variant": "status-pill--success",
                "worker_meta": (
                    f"{worker_state['worker_count']} worker(s), "
                    f"{worker_state['active_jobs']} active job(s)."
                ),
            }
        )
    else:
        health.update(
            {
                "worker_status": "Offline",
                "worker_status_variant": "status-pill--danger",
                "worker_meta": "No Celery workers responded.",
            }
        )
    return health


def redis_queue_status() -> tuple[bool, int, str]:
    try:
        import redis

        client = redis.Redis.from_url(
            celery_redis_url(),
            socket_connect_timeout=ASYNC_HEALTH_TIMEOUT_SECONDS,
            socket_timeout=ASYNC_HEALTH_TIMEOUT_SECONDS,
        )
        client.ping()
        queued_jobs = int(client.llen(ASYNC_QUEUE_NAME) or 0)
        return True, queued_jobs, ""
    except Exception as exc:
        return False, 0, str(exc)


def celery_worker_state() -> dict[str, int]:
    try:
        inspector = celery_app.control.inspect(timeout=ASYNC_HEALTH_TIMEOUT_SECONDS)
        stats = inspector.stats() or {}
        if not stats:
            return {
                "worker_count": 0,
                "active_jobs": 0,
                "reserved_jobs": 0,
                "scheduled_jobs": 0,
            }
        active = inspector.active() or {}
        reserved = inspector.reserved() or {}
        scheduled = inspector.scheduled() or {}
    except Exception:
        return {
            "worker_count": 0,
            "active_jobs": 0,
            "reserved_jobs": 0,
            "scheduled_jobs": 0,
        }

    return {
        "worker_count": len(stats),
        "active_jobs": sum(len(tasks) for tasks in active.values()),
        "reserved_jobs": sum(len(tasks) for tasks in reserved.values()),
        "scheduled_jobs": sum(len(tasks) for tasks in scheduled.values()),
    }
