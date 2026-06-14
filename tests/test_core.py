from pathlib import Path

import pytest
from PIL import Image
from pypdf import PdfReader, PdfWriter

from SwiftProPDF.core import (
    PdfEditError,
    PdfLockError,
    PdfSplitError,
    QrCodeError,
    compress_image,
    delete_pdf_pages,
    generate_qr_code,
    images_to_pdf,
    lock_pdf,
    merge_pdfs,
    parse_page_ranges,
    pdf_to_images,
    rotate_pdf_pages,
    split_pdf,
    unlock_pdf,
)


def write_pdf(path: Path, page_count: int = 1, encrypted_password: str | None = None) -> None:
    writer = PdfWriter()
    for _ in range(page_count):
        writer.add_blank_page(width=72, height=72)
    if encrypted_password:
        writer.encrypt(encrypted_password)
    with path.open("wb") as output_file:
        writer.write(output_file)


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

    write_pdf(source_path)

    lock_pdf(source_path, output_path, password="secret", overwrite=True)

    reader = PdfReader(str(output_path))
    assert reader.is_encrypted
    assert reader.decrypt("secret") != 0
    assert len(reader.pages) == 1


def test_lock_pdf_requires_password(tmp_path: Path) -> None:
    source_path = tmp_path / "source.pdf"
    output_path = tmp_path / "source-locked.pdf"

    write_pdf(source_path)

    with pytest.raises(PdfLockError):
        lock_pdf(source_path, output_path, password="", overwrite=True)


def test_parse_page_ranges_rejects_out_of_bounds_page() -> None:
    with pytest.raises(PdfSplitError):
        parse_page_ranges("1,7", 6)


def test_split_pdf_writes_selected_pages(tmp_path: Path) -> None:
    source_path = tmp_path / "source.pdf"
    output_path = tmp_path / "split.pdf"
    write_pdf(source_path, page_count=4)

    split_pdf(source_path, output_path, "2-3", overwrite=True)

    assert len(PdfReader(str(output_path)).pages) == 2


def test_merge_pdfs_combines_all_pages(tmp_path: Path) -> None:
    first_path = tmp_path / "first.pdf"
    second_path = tmp_path / "second.pdf"
    output_path = tmp_path / "merged.pdf"
    write_pdf(first_path, page_count=1)
    write_pdf(second_path, page_count=2)

    merge_pdfs([first_path, second_path], output_path, overwrite=True)

    assert len(PdfReader(str(output_path)).pages) == 3


def test_unlock_pdf_removes_encryption(tmp_path: Path) -> None:
    locked_path = tmp_path / "locked.pdf"
    output_path = tmp_path / "unlocked.pdf"
    write_pdf(locked_path, encrypted_password="secret")

    unlock_pdf(locked_path, output_path, password="secret", overwrite=True)

    reader = PdfReader(str(output_path))
    assert not reader.is_encrypted
    assert len(reader.pages) == 1


def test_delete_pdf_pages_removes_requested_pages(tmp_path: Path) -> None:
    source_path = tmp_path / "source.pdf"
    output_path = tmp_path / "deleted.pdf"
    write_pdf(source_path, page_count=3)

    delete_pdf_pages(source_path, output_path, "2", overwrite=True)

    assert len(PdfReader(str(output_path)).pages) == 2


def test_delete_pdf_pages_rejects_deleting_all_pages(tmp_path: Path) -> None:
    source_path = tmp_path / "source.pdf"
    output_path = tmp_path / "deleted.pdf"
    write_pdf(source_path, page_count=1)

    with pytest.raises(PdfEditError):
        delete_pdf_pages(source_path, output_path, "1", overwrite=True)


def test_rotate_pdf_pages_rotates_selected_page(tmp_path: Path) -> None:
    source_path = tmp_path / "source.pdf"
    output_path = tmp_path / "rotated.pdf"
    write_pdf(source_path, page_count=2)

    rotate_pdf_pages(source_path, output_path, "1", 90, overwrite=True)

    reader = PdfReader(str(output_path))
    assert reader.pages[0].get("/Rotate") == 90
    assert reader.pages[1].get("/Rotate") in (None, 0)


def test_images_to_pdf_creates_one_page_per_image(tmp_path: Path) -> None:
    image_paths = []
    for index, color in enumerate(("red", "blue"), start=1):
        path = tmp_path / f"image-{index}.png"
        Image.new("RGB", (40, 40), color=color).save(path)
        image_paths.append(path)
    output_path = tmp_path / "images.pdf"

    images_to_pdf(image_paths, output_path, overwrite=True)

    assert len(PdfReader(str(output_path)).pages) == 2


def test_pdf_to_images_exports_each_page(tmp_path: Path) -> None:
    pytest.importorskip("fitz")
    source_path = tmp_path / "source.pdf"
    output_dir = tmp_path / "pages"
    write_pdf(source_path, page_count=2)

    output_paths = pdf_to_images(source_path, output_dir, dpi=72, overwrite=True)

    assert len(output_paths) == 2
    assert all(path.exists() for path in output_paths)


def test_generate_qr_code_creates_png(tmp_path: Path) -> None:
    pytest.importorskip("qrcode")
    output_path = tmp_path / "qr.png"

    generate_qr_code("https://example.com", output_path, size=128, overwrite=True)

    image = Image.open(output_path)
    assert image.size == (128, 128)


def test_generate_qr_code_respects_overwrite_flag(tmp_path: Path) -> None:
    pytest.importorskip("qrcode")
    output_path = tmp_path / "qr.png"
    output_path.write_bytes(b"existing")

    with pytest.raises(QrCodeError):
        generate_qr_code("https://example.com", output_path)
