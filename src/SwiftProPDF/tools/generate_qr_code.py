from pathlib import Path

from PIL import Image

from SwiftProPDF.tools.exceptions import QrCodeError


def generate_qr_code(data: str, output_path: Path, size: int = 500, overwrite: bool = False) -> None:
    """Generate a QR code PNG image from a URL or text."""
    output_path = Path(output_path)

    if output_path.exists() and not overwrite:
        raise QrCodeError(f"Output file already exists: {output_path}")

    try:
        import qrcode
        from qrcode.constants import ERROR_CORRECT_M
    except ImportError as exc:
        raise QrCodeError("Install the qrcode package to generate QR codes.") from exc

    try:
        qr = qrcode.QRCode(
            version=None,
            error_correction=ERROR_CORRECT_M,
            box_size=10,
            border=4,
        )
        qr.add_data(data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")

        if hasattr(img, "convert"):
            img = img.convert("RGB")

        resample = getattr(getattr(Image, "Resampling", Image), "LANCZOS", Image.LANCZOS)
        img = img.resize((size, size), resample=resample)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(output_path, format="PNG")
    except Exception as exc:
        raise QrCodeError("Could not generate the QR code.") from exc
