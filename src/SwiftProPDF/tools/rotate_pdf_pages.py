from pathlib import Path

from pypdf import PdfReader, PdfWriter

from SwiftProPDF.tools.exceptions import PdfEditError, PdfSplitError
from SwiftProPDF.tools.page_ranges import parse_page_ranges


def rotate_pdf_pages(input_path: Path, output_path: Path, page_ranges: str, angle: int, overwrite: bool = False) -> None:
    """Rotate PDF pages by the specified angle."""
    input_path = Path(input_path)
    output_path = Path(output_path)

    if not input_path.exists():
        raise PdfEditError(f"Input PDF does not exist: {input_path}")

    if output_path.exists() and not overwrite:
        raise PdfEditError(f"Output file already exists: {output_path}")

    if angle not in (90, 180, 270, -90):
        raise PdfEditError("Rotation angle must be 90, 180, 270, or -90 degrees")

    try:
        reader = PdfReader(str(input_path))
        writer = PdfWriter()

        if reader.is_encrypted:
            raise PdfEditError("Cannot edit encrypted PDFs.")

        selected_pages = (
            list(range(len(reader.pages)))
            if not page_ranges.strip()
            else parse_page_ranges(page_ranges, len(reader.pages))
        )
        selected_set = set(selected_pages)

        for page_idx, page in enumerate(reader.pages):
            if page_idx in selected_set:
                page.rotate(angle)
            writer.add_page(page)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("wb") as f:
            writer.write(f)

    except (PdfEditError, PdfSplitError) as exc:
        if isinstance(exc, PdfSplitError):
            raise PdfEditError(str(exc)) from exc
        raise
    except Exception as exc:
        raise PdfEditError(f"Could not rotate PDF pages: {str(exc)}") from exc
