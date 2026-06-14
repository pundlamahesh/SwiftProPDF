from pathlib import Path
import zipfile

from SwiftProPDF.auth import log_audit_event, record_tool_usage
from SwiftProPDF.core import (
    ImageConversionError,
    OfficeConversionError,
    PdfCompressError,
    PdfConversionError,
    PdfEditError,
    PdfLockError,
    PdfMergeError,
    PdfSplitError,
    PdfUnlockError,
    QrCodeError,
    compress_image,
    compress_pdf,
    delete_pdf_pages,
    generate_qr_code,
    images_to_pdf,
    lock_pdf,
    merge_pdfs,
    office_to_pdf,
    pdf_to_excel,
    pdf_to_images,
    pdf_to_powerpoint,
    pdf_to_word,
    rotate_pdf_pages,
    split_pdf,
    unlock_pdf,
)
from SwiftProPDF.security.file_scanner import FileScanError, scan_file


class ToolJobError(Exception):
    """Raised when a background tool job fails validation or processing."""


def record_success(database_path: Path, tool_name: str, audit_event: str, audit_details: str, actor: dict) -> None:
    user_id = actor.get("user_id")
    anonymous_id = actor.get("anonymous_id")
    ip_address = actor.get("ip_address", "")
    log_audit_event(
        database_path,
        audit_event,
        user_id=int(user_id) if user_id else None,
        details=audit_details,
        ip_address=ip_address,
    )
    if user_id:
        record_tool_usage(database_path, tool_name, user_id=int(user_id), ip_address=ip_address)
    else:
        record_tool_usage(database_path, tool_name, anonymous_id=anonymous_id, ip_address=ip_address)


def require_file(files: dict, field_name: str) -> dict:
    uploads = files.get(field_name) or []
    if not uploads:
        raise ToolJobError("Choose a file first.")
    return uploads[0]


def require_files(files: dict, field_name: str, message: str) -> list[dict]:
    uploads = files.get(field_name) or []
    if not uploads:
        raise ToolJobError(message)
    return uploads


def output_result(output_path: Path, download_name: str) -> dict:
    return {
        "output_path": str(output_path),
        "download_name": download_name,
    }


def scan_job_files(files: dict) -> None:
    for uploads in files.values():
        for upload in uploads:
            scan_file(upload["path"])


def execute_tool_job(
    tool_name: str,
    form: dict,
    files: dict,
    output_dir: str,
    database_path: str,
    actor: dict,
) -> dict:
    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    database = Path(database_path)

    try:
        scan_job_files(files)

        if tool_name == "unlock":
            upload = require_file(files, "pdf")
            filename = upload["filename"]
            if not filename.lower().endswith(".pdf"):
                raise ToolJobError("Only PDF files are supported.")
            output_name = f"{Path(filename).stem}-unlocked.pdf"
            output_path = output_root / output_name
            unlock_pdf(Path(upload["path"]), output_path, form.get("password", ""), overwrite=True)
            record_success(database, "unlock", "tool_unlock", f"Unlocked {filename}.", actor)
            return output_result(output_path, output_name)

        if tool_name == "lock":
            upload = require_file(files, "pdf")
            filename = upload["filename"]
            password = form.get("password", "")
            if not password:
                raise ToolJobError("Enter a password to lock the PDF.")
            if not filename.lower().endswith(".pdf"):
                raise ToolJobError("Only PDF files are supported.")
            output_name = f"{Path(filename).stem}-locked.pdf"
            output_path = output_root / output_name
            lock_pdf(Path(upload["path"]), output_path, password=password, overwrite=True)
            record_success(database, "lock", "tool_lock", f"Locked {filename}.", actor)
            return output_result(output_path, output_name)

        if tool_name == "split":
            upload = require_file(files, "pdf")
            filename = upload["filename"]
            if not filename.lower().endswith(".pdf"):
                raise ToolJobError("Only PDF files are supported.")
            output_name = f"{Path(filename).stem}-split.pdf"
            output_path = output_root / output_name
            page_ranges = form.get("page_ranges", "")
            split_pdf(Path(upload["path"]), output_path, page_ranges, overwrite=True)
            record_success(database, "split", "tool_split", f"Split {filename} with pages {page_ranges}.", actor)
            return output_result(output_path, output_name)

        if tool_name == "merge":
            uploads = require_files(files, "pdfs", "Choose at least one PDF file.")
            input_paths = []
            for upload in uploads:
                filename = upload["filename"]
                if not filename.lower().endswith(".pdf"):
                    raise ToolJobError("Only PDF files are supported.")
                input_paths.append(Path(upload["path"]))
            output_name = "merged.pdf"
            output_path = output_root / output_name
            merge_pdfs(input_paths, output_path, overwrite=True)
            record_success(database, "merge", "tool_merge", f"Merged {len(input_paths)} PDF file(s).", actor)
            return output_result(output_path, output_name)

        if tool_name == "compress":
            upload = require_file(files, "pdf")
            filename = upload["filename"]
            level = form.get("level", "medium")
            if not filename.lower().endswith(".pdf"):
                raise ToolJobError("Only PDF files are supported.")
            if level not in ("low", "medium", "high"):
                raise ToolJobError("Invalid compression level.")
            output_name = f"{Path(filename).stem}-compressed.pdf"
            output_path = output_root / output_name
            compress_pdf(Path(upload["path"]), output_path, level=level, overwrite=True)
            record_success(database, "compress", "tool_compress", f"Compressed {filename} at {level} level.", actor)
            return output_result(output_path, output_name)

        if tool_name == "compress-image":
            upload = require_file(files, "image")
            filename = upload["filename"]
            suffix = Path(filename).suffix.lower()
            level = form.get("level", "medium")
            if suffix not in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"):
                raise ToolJobError("Only JPG, PNG, WEBP, GIF, and BMP image files are supported.")
            if level not in ("low", "medium", "high"):
                raise ToolJobError("Invalid compression level.")
            output_name = f"{Path(filename).stem}-compressed{suffix}"
            output_path = output_root / output_name
            compress_image(Path(upload["path"]), output_path, level=level, overwrite=True)
            record_success(database, "compress-image", "tool_compress_image", f"Compressed {filename} at {level} level.", actor)
            return output_result(output_path, output_name)

        if tool_name == "pdf-to-images":
            upload = require_file(files, "pdf")
            filename = upload["filename"]
            if not filename.lower().endswith(".pdf"):
                raise ToolJobError("Only PDF files are supported.")
            try:
                dpi = int(form.get("dpi", "150"))
            except ValueError as exc:
                raise ToolJobError("DPI must be a number between 72 and 300.") from exc
            images_dir = output_root / "images"
            pdf_to_images(Path(upload["path"]), images_dir, dpi=dpi)
            zip_path = output_root / "images.zip"
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for img_path in sorted(images_dir.glob("*.jpg")):
                    zf.write(img_path, arcname=img_path.name)
            output_name = f"{Path(filename).stem}-images.zip"
            record_success(database, "pdf-to-images", "tool_pdf_to_images", f"Converted {filename} to images at {dpi} DPI.", actor)
            return output_result(zip_path, output_name)

        if tool_name == "images-to-pdf":
            uploads = require_files(files, "images", "Choose at least one image file.")
            input_paths = []
            for upload in uploads:
                filename = upload["filename"]
                if filename.lower().split(".")[-1] not in ("jpg", "jpeg", "png", "gif", "bmp"):
                    raise ToolJobError("Only image files are supported (JPG, PNG, GIF, BMP).")
                input_paths.append(Path(upload["path"]))
            output_name = "images.pdf"
            output_path = output_root / output_name
            images_to_pdf(input_paths, output_path, overwrite=True)
            record_success(database, "images-to-pdf", "tool_images_to_pdf", f"Created PDF from {len(input_paths)} image file(s).", actor)
            return output_result(output_path, output_name)

        if tool_name == "pdf-to-word":
            upload = require_file(files, "pdf")
            filename = upload["filename"]
            if not filename.lower().endswith(".pdf"):
                raise ToolJobError("Only PDF files are supported.")
            output_name = f"{Path(filename).stem}.docx"
            output_path = output_root / output_name
            pdf_to_word(Path(upload["path"]), output_path, overwrite=True)
            record_success(database, "pdf-to-word", "tool_pdf_to_word", f"Converted {filename} to Word.", actor)
            return output_result(output_path, output_name)

        if tool_name == "pdf-to-powerpoint":
            upload = require_file(files, "pdf")
            filename = upload["filename"]
            if not filename.lower().endswith(".pdf"):
                raise ToolJobError("Only PDF files are supported.")
            output_name = f"{Path(filename).stem}.pptx"
            output_path = output_root / output_name
            pdf_to_powerpoint(Path(upload["path"]), output_path, overwrite=True)
            record_success(database, "pdf-to-powerpoint", "tool_pdf_to_powerpoint", f"Converted {filename} to PowerPoint.", actor)
            return output_result(output_path, output_name)

        if tool_name == "pdf-to-excel":
            upload = require_file(files, "pdf")
            filename = upload["filename"]
            if not filename.lower().endswith(".pdf"):
                raise ToolJobError("Only PDF files are supported.")
            output_name = f"{Path(filename).stem}.xlsx"
            output_path = output_root / output_name
            pdf_to_excel(Path(upload["path"]), output_path, overwrite=True)
            record_success(database, "pdf-to-excel", "tool_pdf_to_excel", f"Converted {filename} to Excel.", actor)
            return output_result(output_path, output_name)

        if tool_name == "office-to-pdf":
            upload = require_file(files, "document")
            filename = upload["filename"]
            extension = filename.lower().split(".")[-1]
            if extension not in ("docx", "doc", "xlsx", "xls", "pptx", "ppt"):
                raise ToolJobError("Supported formats: DOCX, DOC, XLSX, XLS, PPTX, PPT")
            output_name = f"{Path(filename).stem}.pdf"
            output_path = output_root / output_name
            office_to_pdf(Path(upload["path"]), output_path, overwrite=True)
            record_success(database, "office-to-pdf", "tool_office_to_pdf", f"Converted {filename} to PDF.", actor)
            return output_result(output_path, output_name)

        if tool_name == "qr-code":
            url_value = form.get("url", "").strip()
            if not url_value:
                raise ToolJobError("Enter a website URL to generate a QR code.")
            from urllib.parse import urlparse

            normalized_url = url_value
            parsed_url = urlparse(normalized_url)
            if not parsed_url.scheme:
                normalized_url = f"https://{normalized_url}"
                parsed_url = urlparse(normalized_url)
            if not parsed_url.netloc:
                raise ToolJobError("Enter a valid website URL.")
            output_name = "qr-code.png"
            output_path = output_root / output_name
            generate_qr_code(normalized_url, output_path, overwrite=True)
            record_success(database, "qr-code", "tool_qr_code", f"Generated QR code for {normalized_url}.", actor)
            return output_result(output_path, output_name)

        if tool_name == "rotate":
            upload = require_file(files, "pdf")
            filename = upload["filename"]
            if not filename.lower().endswith(".pdf"):
                raise ToolJobError("Only PDF files are supported.")
            try:
                angle = int(form.get("angle", "90"))
            except ValueError as exc:
                raise ToolJobError("Rotation angle must be 90, 180, 270, or -90.") from exc
            page_ranges = form.get("page_ranges", "")
            output_name = f"{Path(filename).stem}-rotated.pdf"
            output_path = output_root / output_name
            rotate_pdf_pages(Path(upload["path"]), output_path, page_ranges, angle, overwrite=True)
            record_success(database, "rotate-pdf", "tool_rotate_pdf", f"Rotated {filename} by {angle} degrees.", actor)
            return output_result(output_path, output_name)

        if tool_name == "delete-pages":
            upload = require_file(files, "pdf")
            filename = upload["filename"]
            if not filename.lower().endswith(".pdf"):
                raise ToolJobError("Only PDF files are supported.")
            page_ranges = form.get("page_ranges", "")
            output_name = f"{Path(filename).stem}-pages-deleted.pdf"
            output_path = output_root / output_name
            delete_pdf_pages(Path(upload["path"]), output_path, page_ranges, overwrite=True)
            record_success(database, "delete-pdf-pages", "tool_delete_pages", f"Deleted pages {page_ranges} from {filename}.", actor)
            return output_result(output_path, output_name)

        raise ToolJobError("Unknown PDF tool.")
    except (
        FileScanError,
        ImageConversionError,
        OfficeConversionError,
        PdfCompressError,
        PdfConversionError,
        PdfEditError,
        PdfLockError,
        PdfMergeError,
        PdfSplitError,
        PdfUnlockError,
        QrCodeError,
    ) as exc:
        raise ToolJobError(str(exc)) from exc
