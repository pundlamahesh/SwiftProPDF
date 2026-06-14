from pathlib import Path

from pdf2docx import Converter as PDFToWordConverter

from SwiftProPDF.tools.exceptions import PdfConversionError


def pdf_to_word(input_path: Path, output_path: Path, overwrite: bool = False) -> None:
    """Convert PDF to Word document."""
    input_path = Path(input_path)
    output_path = Path(output_path)

    if not input_path.exists():
        raise PdfConversionError(f"Input PDF does not exist: {input_path}")

    if output_path.exists() and not overwrite:
        raise PdfConversionError(f"Output file already exists: {output_path}")

    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)

        converter = PDFToWordConverter(str(input_path))
        converter.convert(str(output_path), start=0, end=None)
        converter.close()

    except Exception as exc:
        raise PdfConversionError(f"Could not convert PDF to Word: {str(exc)}") from exc
