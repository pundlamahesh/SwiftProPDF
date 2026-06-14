from pathlib import Path

import fitz

from SwiftProPDF.tools.exceptions import ImageConversionError


def pdf_to_images(input_path: Path, output_dir: Path, dpi: int = 150, overwrite: bool = False) -> list[Path]:
    """Convert all PDF pages to JPG images."""
    input_path = Path(input_path)
    output_dir = Path(output_dir)

    if not input_path.exists():
        raise ImageConversionError(f"Input PDF does not exist: {input_path}")

    if dpi < 72 or dpi > 300:
        raise ImageConversionError("DPI must be between 72 and 300")

    try:
        output_paths = []
        doc = fitz.open(str(input_path))

        output_dir.mkdir(parents=True, exist_ok=True)

        for page_num in range(len(doc)):
            page = doc[page_num]
            mat = fitz.Matrix(dpi / 72, dpi / 72)
            pix = page.get_pixmap(matrix=mat, alpha=False)

            output_path = output_dir / f"page_{page_num + 1:04d}.jpg"
            pix.save(str(output_path))
            output_paths.append(output_path)

        doc.close()
        return output_paths

    except Exception as exc:
        raise ImageConversionError(f"Could not convert PDF to images: {str(exc)}") from exc
