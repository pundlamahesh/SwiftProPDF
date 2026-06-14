from pathlib import Path

from PIL import Image

from SwiftProPDF.tools.exceptions import ImageConversionError


def images_to_pdf(input_paths: list[Path], output_path: Path, overwrite: bool = False) -> None:
    """Convert multiple images to a single PDF."""
    input_paths = [Path(p) for p in input_paths]
    output_path = Path(output_path)

    if output_path.exists() and not overwrite:
        raise ImageConversionError(f"Output file already exists: {output_path}")

    if not input_paths:
        raise ImageConversionError("No images provided.")

    try:
        images = []

        for img_path in input_paths:
            if not img_path.exists():
                raise ImageConversionError(f"Image does not exist: {img_path}")

            if img_path.suffix.lower() not in (".jpg", ".jpeg", ".png", ".gif", ".bmp"):
                raise ImageConversionError(f"Unsupported image format: {img_path.suffix}")

            img = Image.open(str(img_path))

            if img.mode in ("RGBA", "LA", "P"):
                rgb_img = Image.new("RGB", img.size, (255, 255, 255))
                rgb_img.paste(img, mask=img.split()[-1] if img.mode in ("RGBA", "LA") else None)
                images.append(rgb_img)
            else:
                images.append(img.convert("RGB"))

        if not images:
            raise ImageConversionError("No valid images to convert.")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        images[0].save(str(output_path), save_all=True, append_images=images[1:], format="PDF")

    except ImageConversionError:
        raise
    except Exception as exc:
        raise ImageConversionError(f"Could not convert images to PDF: {str(exc)}") from exc
