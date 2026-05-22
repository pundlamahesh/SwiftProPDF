from pathlib import Path

from SwiftPDF.cli import default_output_path


def test_default_output_path_adds_unlocked_suffix() -> None:
    assert default_output_path(Path("report.pdf")) == Path("report-unlocked.pdf")
