from pathlib import Path

from pypdf import PdfReader, PdfWriter

from SwiftProPDF.tools.exceptions import PdfLockError


def lock_pdf(input_path: Path, output_path: Path, password: str, overwrite: bool = False) -> None:
    """Encrypt a PDF with the given password."""
    input_path = Path(input_path)
    output_path = Path(output_path)

    if not input_path.exists():
        raise PdfLockError(f"Input PDF does not exist: {input_path}")

    if output_path.exists() and not overwrite:
        raise PdfLockError(f"Output file already exists: {output_path}")

    if not password:
        raise PdfLockError("Enter a password to lock the PDF.")

    try:
        reader = PdfReader(str(input_path))
    except Exception as exc:
        raise PdfLockError(f"Could not read PDF: {input_path}") from exc

    if reader.is_encrypted:
        raise PdfLockError("This PDF is already encrypted. Unlock it before locking again.")

    try:
        writer = PdfWriter()
        for page in reader.pages:
            writer.add_page(page)

        writer.encrypt(password)
    except Exception as exc:
        raise PdfLockError("Could not lock this PDF.") from exc

    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with output_path.open("wb") as output_file:
            writer.write(output_file)
    except Exception as exc:
        raise PdfLockError(f"Could not write locked PDF: {output_path}") from exc
