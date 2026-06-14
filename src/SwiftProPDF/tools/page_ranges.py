from SwiftProPDF.tools.exceptions import PdfSplitError


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
