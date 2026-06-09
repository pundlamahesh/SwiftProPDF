from pathlib import Path

import pytest
from PIL import Image
from pypdf import PdfReader, PdfWriter

from SwiftPDF.core import PdfLockError, PdfSplitError, compress_image, lock_pdf, parse_page_ranges


def test_parse_page_ranges_expands_ranges_and_single_pages() -> None:
    assert parse_page_ranges("1-3,5", 6) == [0, 1, 2, 4]


def test_compress_image_reduces_output_size(tmp_path: Path) -> None:
    source_path = tmp_path / "source.png"
    output_path = tmp_path / "source-compressed.png"

    image = Image.new("RGB", (800, 800), color=(255, 0, 0))
    image.save(source_path, format="PNG", optimize=False)

    compress_image(source_path, output_path, level="high", overwrite=True)

    assert output_path.exists()
    assert output_path.stat().st_size <= source_path.stat().st_size


def test_lock_pdf_encrypts_output_with_password(tmp_path: Path) -> None:
    source_path = tmp_path / "source.pdf"
    output_path = tmp_path / "source-locked.pdf"

    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    with source_path.open("wb") as source_file:
        writer.write(source_file)

    lock_pdf(source_path, output_path, password="secret", overwrite=True)

    reader = PdfReader(str(output_path))
    assert reader.is_encrypted
    assert reader.decrypt("secret") != 0
    assert len(reader.pages) == 1


def test_lock_pdf_requires_password(tmp_path: Path) -> None:
    source_path = tmp_path / "source.pdf"
    output_path = tmp_path / "source-locked.pdf"

    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    with source_path.open("wb") as source_file:
        writer.write(source_file)

    with pytest.raises(PdfLockError):
        lock_pdf(source_path, output_path, password="", overwrite=True)


def test_parse_page_ranges_rejects_out_of_bounds_page() -> None:
    with pytest.raises(PdfSplitError):
        parse_page_ranges("1,7", 6)
