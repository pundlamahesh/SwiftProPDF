import pytest

from SwiftPDF.core import PdfSplitError, parse_page_ranges


def test_parse_page_ranges_expands_ranges_and_single_pages() -> None:
    assert parse_page_ranges("1-3,5", 6) == [0, 1, 2, 4]


def test_parse_page_ranges_rejects_out_of_bounds_page() -> None:
    with pytest.raises(PdfSplitError):
        parse_page_ranges("1,7", 6)
