from pathlib import Path

from SwiftProPDF.auth import log_audit_event
from SwiftProPDF.web_app.celery_app import celery_app
from SwiftProPDF.web_app.job_events import ASYNC_JOB_FAILED_EVENT
from SwiftProPDF.web_app.job_runner import ToolJobError, execute_tool_job


def log_tool_job_failure(payload: dict, error: str) -> None:
    database_path = payload.get("database_path")
    if not database_path:
        return

    actor = payload.get("actor", {})
    user_id = actor.get("user_id")
    tool_name = payload.get("tool_name", "unknown")
    try:
        log_audit_event(
            Path(database_path),
            ASYNC_JOB_FAILED_EVENT,
            user_id=int(user_id) if user_id else None,
            details=f"{tool_name}: {error}",
            ip_address=actor.get("ip_address", ""),
        )
    except Exception:
        return


@celery_app.task(bind=True, name="swiftpropdf.process_tool")
def process_tool_job(self, payload: dict) -> dict:
    self.update_state(state="PROGRESS", meta={"message": "Processing your file."})
    try:
        result = execute_tool_job(
            payload["tool_name"],
            payload.get("form", {}),
            payload.get("files", {}),
            payload["output_dir"],
            payload["database_path"],
            payload.get("actor", {}),
        )
        result["status"] = "success"
        return result
    except ToolJobError as exc:
        log_tool_job_failure(payload, str(exc))
        return {
            "status": "error",
            "error": str(exc),
        }
    except Exception as exc:
        log_tool_job_failure(payload, f"Unexpected {type(exc).__name__}")
        raise
