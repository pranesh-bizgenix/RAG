"""OCR extraction for common image formats."""

from pathlib import Path


def parse_image(path: Path) -> list[dict[str, str]]:
    try:
        import pytesseract
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("Image parsing requires 'Pillow' and 'pytesseract'.") from exc

    try:
        with Image.open(path) as image:
            text = pytesseract.image_to_string(image).strip()
    except pytesseract.TesseractNotFoundError as exc:
        raise RuntimeError("Tesseract OCR must be installed and available on PATH.") from exc
    return [{"source": f"{path.name}:ocr", "text": text}] if text else []
