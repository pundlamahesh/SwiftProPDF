from pathlib import Path

from pypdf import PdfReader, PdfWriter

from SwiftProPDF.tools.exceptions import PdfEditError, PdfSplitError
from SwiftProPDF.tools.page_ranges import parse_page_ranges


def delete_pdf_pages(input_path: Path, output_path: Path, page_ranges: str, overwrite: bool = False) -> None:
    """Delete specified pages from a PDF."""
    input_path = Path(input_path)
    output_path = Path(output_path)

    if not input_path.exists():
        raise PdfEditError(f"Input PDF does not exist: {input_path}")

    if output_path.exists() and not overwrite:
        raise PdfEditError(f"Output file already exists: {output_path}")

    try:
        reader = PdfReader(str(input_path))
        writer = PdfWriter()

        if reader.is_encrypted:
            raise PdfEditError("Cannot edit encrypted PDFs.")

        pages_to_delete = set(parse_page_ranges(page_ranges, len(reader.pages)))

        for page_idx, page in enumerate(reader.pages):
            if page_idx not in pages_to_delete:
                writer.add_page(page)

        if len(writer.pages) == 0:
            raise PdfEditError("Cannot delete all pages from PDF.")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("wb") as f:
            writer.write(f)

    except (PdfEditError, PdfSplitError) as exc:
        if isinstance(exc, PdfSplitError):
            raise PdfEditError(str(exc)) from exc
        raise
    except Exception as exc:
        raise PdfEditError(f"Could not delete PDF pages: {str(exc)}") from exc
