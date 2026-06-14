from pathlib import Path
import os
import shutil
from uuid import uuid4

from celery.result import AsyncResult
from werkzeug.utils import secure_filename

from SwiftProPDF.web_app.celery_app import celery_app
from SwiftProPDF.web_app.tasks import process_tool_job
from SwiftProPDF.security.file_scanner import save_and_scan_upload


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
