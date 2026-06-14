from pathlib import Path
import shutil
import subprocess

import fitz

from SwiftProPDF.tools.exceptions import PdfCompressError


def compress_pdf(input_path: Path, output_path: Path, level: str = "medium", overwrite: bool = False) -> None:
    """Compress PDF."""
    input_path = Path(input_path)
    output_path = Path(output_path)

    if not input_path.exists():
        raise PdfCompressError(f"Input PDF does not exist: {input_path}")

    if output_path.exists() and not overwrite:
        raise PdfCompressError(f"Output file already exists: {output_path}")

    if level not in ("low", "medium", "high"):
        raise PdfCompressError("Compression level must be: low, medium, or high")

    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if level == "low":
            with fitz.open(str(input_path)) as doc:
                if doc.needs_pass:
                    raise PdfCompressError("Encrypted PDFs must be unlocked before compressing.")

                doc.save(
                    str(output_path),
                    garbage=4,
                    clean=True,
                    deflate=True,
                    deflate_images=True,
                    deflate_fonts=True,
                )
            return

        gs_binary = shutil.which("gs") or shutil.which("gswin64c") or shutil.which("gswin32c")
        if not gs_binary:
            raise PdfCompressError("Ghostscript is not installed on the server.")

        pdf_setting = {
            "medium": "/ebook",
            "high": "/screen",
        }[level]

        subprocess.run(
            [
                gs_binary,
                "-sDEVICE=pdfwrite",
                "-dCompatibilityLevel=1.4",
                f"-dPDFSETTINGS={pdf_setting}",
                "-dNOPAUSE",
                "-dQUIET",
                "-dBATCH",
                f"-sOutputFile={output_path}",
                str(input_path),
            ],
            check=True,
            capture_output=True,
        )

        if not output_path.exists():
            raise PdfCompressError("Compression completed but output file was not created.")

    except PdfCompressError:
        raise
    except subprocess.CalledProcessError as exc:
        error_msg = exc.stderr.decode(errors="ignore")
        raise PdfCompressError(f"Ghostscript compression failed: {error_msg}") from exc
    except Exception as exc:
        raise PdfCompressError(f"Could not compress PDF: {str(exc)}") from exc
