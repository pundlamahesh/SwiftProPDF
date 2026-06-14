from pathlib import Path

from pypdf import PdfReader, PdfWriter
from pypdf.errors import DependencyError

from SwiftProPDF.tools.exceptions import PdfUnlockError


def unlock_pdf(input_path: Path, output_path: Path, password: str, overwrite: bool = False) -> None:
    """Unlock a PDF with the given password and write an unencrypted copy."""
    input_path = Path(input_path)
    output_path = Path(output_path)

    if not input_path.exists():
        raise PdfUnlockError(f"Input PDF does not exist: {input_path}")

    if output_path.exists() and not overwrite:
        raise PdfUnlockError(f"Output file already exists: {output_path}")

    try:
        reader = PdfReader(str(input_path))
    except Exception as exc:
        raise PdfUnlockError(f"Could not read PDF: {input_path}") from exc

    try:
        if reader.is_encrypted:
            decrypt_result = reader.decrypt(password)
            if decrypt_result == 0:
                raise PdfUnlockError("Could not unlock PDF. Check the password.")
        elif password:
            pass

        writer = PdfWriter()
        for page in reader.pages:
            writer.add_page(page)
    except DependencyError as exc:
        raise PdfUnlockError(
            "This PDF uses AES encryption. Install crypto support with: "
            'python -m pip install --upgrade -e . or python -m pip install "pypdf[crypto]" cryptography'
        ) from exc

    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with output_path.open("wb") as output_file:
            writer.write(output_file)
    except Exception as exc:
        raise PdfUnlockError(f"Could not write unlocked PDF: {output_path}") from exc
