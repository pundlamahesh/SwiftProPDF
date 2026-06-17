import os
from os import path
from pathlib import Path
from xmlrpc import client

from alembic.util import status
from celery import result, signature


class FileScanError(Exception):
    """Raised when an uploaded file fails antivirus validation."""


def antivirus_enabled() -> bool:
    return os.getenv("CLAMAV_ENABLED", "0") == "1"


def scan_file(path: Path | str) -> None:
    """Scan a saved upload with ClamAV when antivirus scanning is enabled."""
    if not antivirus_enabled():
        return

    path = Path(path)
    if not path.exists():
        raise FileScanError("Uploaded file could not be scanned.")

    try:
        import clamd
    except ImportError as exc:
        raise FileScanError(
            "Antivirus scanning is enabled but clamd is not installed."
        ) from exc

    client = clamd.ClamdNetworkSocket(
        host=os.getenv("CLAMAV_HOST", "localhost"),
        port=int(os.getenv("CLAMAV_PORT", "3310")),
        timeout=float(os.getenv("CLAMAV_TIMEOUT", "30")),
    )

    try:
        client.ping()

        with open(path, "rb") as file_handle:
            result = client.instream(file_handle)

    except Exception as exc:
        raise FileScanError(f"Could not scan uploaded file: {exc}") from exc

    if not result:
        return

    status, signature = next(iter(result.values()))

    if status != "OK":
        raise FileScanError(
            f"Uploaded file failed antivirus scan: {signature}"
        )


def save_and_scan_upload(uploaded_file, input_path: Path | str) -> None:
    """Persist a Werkzeug upload and scan it before any parser processes it."""
    input_path = Path(input_path)
    input_path.parent.mkdir(parents=True, exist_ok=True)
    uploaded_file.save(input_path)
    scan_file(input_path)
