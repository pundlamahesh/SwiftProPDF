from pathlib import Path

from pypdf.errors import DependencyError
from pypdf import PdfReader, PdfWriter


class PdfUnlockError(Exception):
    """Raised when a PDF cannot be unlocked."""


class PdfSplitError(Exception):
    """Raised when a PDF cannot be split."""


def parse_page_ranges(page_ranges: str, page_count: int) -> list[int]:
    """Parse 1-based page ranges into unique 0-based page indexes."""
    if page_count < 1:
        raise PdfSplitError("PDF does not contain any pages.")

    if not page_ranges.strip():
        raise PdfSplitError("Enter page ranges such as 1-3,5.")

    selected_pages: list[int] = []
    seen_pages: set[int] = set()

    for part in page_ranges.split(","):
        part = part.strip()
        if not part:
            continue

        if "-" in part:
            start_text, end_text = [value.strip() for value in part.split("-", 1)]
            if not start_text.isdigit() or not end_text.isdigit():
                raise PdfSplitError("Page ranges must use numbers, for example 1-3,5.")

            start_page = int(start_text)
            end_page = int(end_text)
            if start_page > end_page:
                raise PdfSplitError("Page range start cannot be greater than the end.")

            pages = range(start_page, end_page + 1)
        else:
            if not part.isdigit():
                raise PdfSplitError("Page ranges must use numbers, for example 1-3,5.")
            pages = range(int(part), int(part) + 1)

        for page_number in pages:
            if page_number < 1 or page_number > page_count:
                raise PdfSplitError(f"Page {page_number} is outside this PDF's 1-{page_count} page range.")

            page_index = page_number - 1
            if page_index not in seen_pages:
                selected_pages.append(page_index)
                seen_pages.add(page_index)

    if not selected_pages:
        raise PdfSplitError("Enter at least one page number.")

    return selected_pages


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
            # Accept an unnecessary password so scripts can handle mixed encrypted/plain PDFs.
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


def split_pdf(input_path: Path, output_path: Path, page_ranges: str, overwrite: bool = False) -> None:
    """Write a new PDF containing only the requested pages."""
    input_path = Path(input_path)
    output_path = Path(output_path)

    if not input_path.exists():
        raise PdfSplitError(f"Input PDF does not exist: {input_path}")

    if output_path.exists() and not overwrite:
        raise PdfSplitError(f"Output file already exists: {output_path}")

    try:
        reader = PdfReader(str(input_path))
    except Exception as exc:
        raise PdfSplitError(f"Could not read PDF: {input_path}") from exc

    if reader.is_encrypted:
        raise PdfSplitError("Encrypted PDFs must be unlocked before splitting.")

    try:
        selected_pages = parse_page_ranges(page_ranges, len(reader.pages))
        writer = PdfWriter()
        for page_index in selected_pages:
            writer.add_page(reader.pages[page_index])
    except PdfSplitError:
        raise
    except Exception as exc:
        raise PdfSplitError("Could not split this PDF.") from exc

    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with output_path.open("wb") as output_file:
            writer.write(output_file)
    except Exception as exc:
        raise PdfSplitError(f"Could not write split PDF: {output_path}") from exc
