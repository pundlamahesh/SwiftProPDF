from pathlib import Path
import shutil
import subprocess
import tempfile

from SwiftProPDF.tools.exceptions import OfficeConversionError


def office_to_pdf(input_path: Path, output_path: Path, overwrite: bool = False) -> None:
    """Convert Office documents to PDF using LibreOffice."""
    input_path = Path(input_path)
    output_path = Path(output_path)

    if not input_path.exists():
        raise OfficeConversionError(f"Input file does not exist: {input_path}")

    if output_path.exists() and not overwrite:
        raise OfficeConversionError(f"Output file already exists: {output_path}")

    supported_formats = (".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt")
    if input_path.suffix.lower() not in supported_formats:
        raise OfficeConversionError(f"Unsupported format: {input_path.suffix}")

    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temp_dir = Path(tempfile.mkdtemp(prefix="office2pdf-"))

        try:
            libreoffice_cmd = shutil.which("soffice") or shutil.which("libreoffice")

            if not libreoffice_cmd:
                raise OfficeConversionError("LibreOffice is not installed or not available in PATH.")

            result = subprocess.run(
                [
                    libreoffice_cmd,
                    "--headless",
                    "--convert-to",
                    "pdf",
                    "--outdir",
                    str(temp_dir),
                    str(input_path),
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode != 0:
                raise OfficeConversionError(
                    f"LibreOffice conversion failed:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
                )

            temp_pdf = temp_dir / f"{input_path.stem}.pdf"
            if not temp_pdf.exists():
                raise OfficeConversionError(f"Conversion completed but PDF not found: {temp_pdf}")

            shutil.move(str(temp_pdf), str(output_path))

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    except OfficeConversionError:
        raise
    except subprocess.TimeoutExpired as exc:
        raise OfficeConversionError("Conversion timeout. File may be too large.") from exc
    except Exception as exc:
        raise OfficeConversionError(f"Could not convert Office document to PDF: {str(exc)}") from exc
