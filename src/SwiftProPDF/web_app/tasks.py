from SwiftProPDF.web_app.celery_app import celery_app
from SwiftProPDF.web_app.job_runner import ToolJobError, execute_tool_job


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
        return {
            "status": "error",
            "error": str(exc),
        }
