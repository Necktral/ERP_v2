"""Etapa OCR del pipeline IDP (motor: Tesseract, open-source).

Aislado a propósito: en fases siguientes se suma extracción estructurada (PaddleOCR /
LayoutLM) y clasificación, sin tocar el resto. `run_ocr` lanza si el motor o su binario no
están disponibles; la capa de servicios captura el fallo y marca el documento como FAILED.
"""
from __future__ import annotations

import io

OCR_ENGINE = "tesseract"


def ocr_available() -> bool:
    """True si el paquete pytesseract y Pillow están importables (no garantiza el binario)."""
    try:
        import pytesseract  # noqa: F401
        from PIL import Image  # noqa: F401
    except Exception:  # pragma: no cover - depende del entorno
        return False
    return True


def run_ocr(image_bytes: bytes) -> str:
    """Extrae texto de la imagen. Español + inglés; cae a default si falta el idioma 'spa'."""
    import pytesseract
    from PIL import Image

    image = Image.open(io.BytesIO(image_bytes))
    try:
        return pytesseract.image_to_string(image, lang="spa+eng")
    except pytesseract.TesseractError:  # pragma: no cover - fallback de idioma
        return pytesseract.image_to_string(image)
