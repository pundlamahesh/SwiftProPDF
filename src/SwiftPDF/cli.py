import argparse
import getpass
from pathlib import Path

from SwiftPDF.core import PdfUnlockError, unlock_pdf


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="swiftpdf",
        description="Create an unlocked copy of a password-protected PDF.",
    )
    parser.add_argument("input_pdf", type=Path, help="Path to the locked PDF file.")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Path for the unlocked PDF. Defaults to '<input>-unlocked.pdf'.",
    )
    parser.add_argument(
        "-p",
        "--password",
        help="PDF password. Omit this option to be prompted securely.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace the output file if it already exists.",
    )
    return parser


def default_output_path(input_pdf: Path) -> Path:
    return input_pdf.with_name(f"{input_pdf.stem}-unlocked{input_pdf.suffix}")


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    password = args.password
    if password is None:
        password = getpass.getpass("PDF password: ")

    output_pdf = args.output or default_output_path(args.input_pdf)

    try:
        unlock_pdf(args.input_pdf, output_pdf, password, overwrite=args.overwrite)
    except PdfUnlockError as exc:
        parser.exit(1, f"Error: {exc}\n")

    print(f"Unlocked PDF written to: {output_pdf}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
