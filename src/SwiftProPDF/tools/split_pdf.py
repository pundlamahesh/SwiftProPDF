from pathlib import Path

from pypdf import PdfReader, PdfWriter

from SwiftProPDF.tools.exceptions import PdfSplitError
from SwiftProPDF.tools.page_ranges import parse_page_ranges


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
