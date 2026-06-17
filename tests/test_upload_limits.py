import io

from SwiftProPDF.web_app.app import create_app


def oversized_pdf_payload() -> dict:
    return {
        "pdf": (io.BytesIO(b"x" * (1024 * 1024 + 64)), "too-large.pdf"),
        "level": "medium",
    }


def test_oversized_upload_returns_custom_json_message(monkeypatch) -> None:
    monkeypatch.setenv("MAX_UPLOAD_MB", "1")
    monkeypatch.setenv("SWIFTPROPDF_ASYNC_TOOLS", "0")
    app = create_app()

    response = app.test_client().post(
        "/compress",
        data=oversized_pdf_payload(),
        content_type="multipart/form-data",
        headers={"X-Requested-With": "fetch"},
    )

    assert response.status_code == 413
    assert response.get_json() == {
        "error": "File is too large. Please upload files up to 1 MB.",
    }


def test_async_oversized_upload_keeps_custom_json_message(monkeypatch) -> None:
    monkeypatch.setenv("MAX_UPLOAD_MB", "1")
    monkeypatch.setenv("SWIFTPROPDF_ASYNC_TOOLS", "1")
    app = create_app()

    response = app.test_client().post(
        "/compress",
        data=oversized_pdf_payload(),
        content_type="multipart/form-data",
        headers={"X-Requested-With": "fetch"},
    )

    assert response.status_code == 413
    assert response.get_json() == {
        "error": "File is too large. Please upload files up to 1 MB.",
    }
