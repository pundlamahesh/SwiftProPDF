from pathlib import Path

from PIL import Image

from SwiftProPDF.tools.exceptions import ImageConversionError


def compress_image(input_path: Path, output_path: Path, level: str = "medium", overwrite: bool = False) -> None:
    """Compress an image file."""
    input_path = Path(input_path)
    output_path = Path(output_path)

    if not input_path.exists():
        raise ImageConversionError(f"Input image does not exist: {input_path}")

    if output_path.exists() and not overwrite:
        raise ImageConversionError(f"Output file already exists: {output_path}")

    if level not in ("low", "medium", "high"):
        raise ImageConversionError("Compression level must be: low, medium, or high")

    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)

        quality_map = {
            "low": 85,
            "medium": 70,
            "high": 50,
        }
        resize_map = {
            "low": 3000,
            "medium": 2000,
            "high": 1200,
        }
        compress_level_map = {
            "low": 3,
            "medium": 6,
            "high": 9,
        }

        with Image.open(input_path) as img:
            img_format = (img.format or input_path.suffix.lstrip(".")).upper()
            max_dimension = resize_map[level]

            if max(img.size) > max_dimension:
                img.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)

            if img_format in ("JPEG", "JPG"):
                rgb = img.convert("RGB")
                rgb.save(output_path, format="JPEG", quality=quality_map[level], optimize=True, progressive=True)
                return

            if img_format == "PNG":
                img.save(output_path, format="PNG", optimize=True, compress_level=compress_level_map[level])
                return

            if img_format == "WEBP":
                img.save(output_path, format="WEBP", quality=quality_map[level], optimize=True, method=6)
                return

            if img_format == "GIF":
                img.save(output_path, format="GIF", optimize=True)
                return

            img.save(output_path, format=img_format, optimize=True)

    except Exception as exc:
        raise ImageConversionError(f"Could not compress image: {str(exc)}") from exc
