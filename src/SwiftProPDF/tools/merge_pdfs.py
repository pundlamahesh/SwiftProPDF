from pathlib import Path

from pypdf import PdfReader, PdfWriter

from SwiftProPDF.tools.exceptions import PdfMergeError


def merge_pdfs(input_paths: list[Path], output_path: Path, overwrite: bool = False) -> None:
    """Merge multiple PDFs into a single PDF."""
    input_paths = [Path(p) for p in input_paths]
    output_path = Path(output_path)

    if output_path.exists() and not overwrite:
        raise PdfMergeError(f"Output file already exists: {output_path}")

    if not input_paths:
        raise PdfMergeError("No PDFs to merge.")

    try:
        writer = PdfWriter()

        for input_path in input_paths:
            if not input_path.exists():
                raise PdfMergeError(f"Input PDF does not exist: {input_path}")

            try:
                reader = PdfReader(str(input_path))

                if reader.is_encrypted:
                    raise PdfMergeError(f"PDF {input_path.name} is encrypted. Unlock it first.")

                for page in reader.pages:
                    writer.add_page(page)
            except PdfMergeError:
                raise
            except Exception as exc:
                raise PdfMergeError(f"Could not read PDF: {input_path}") from exc

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("wb") as output_file:
            writer.write(output_file)

    except PdfMergeError:
        raise
    except Exception as exc:
        raise PdfMergeError("Could not merge PDFs.") from exc
