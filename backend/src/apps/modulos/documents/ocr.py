"""Etapa OCR del pipeline IDP (motor: Tesseract, open-source).

Acepta los dos formatos de los canales reales de entrada: **imagen** (JPG/PNG de la app
de remisiones/cámara) y **PDF** (escáner de PC; se renderizan las páginas a imagen con
pypdfium2 y se OCRea cada una). Aislado a propósito: en fases siguientes se suma
extracción estructurada y clasificación sin tocar el resto. `run_ocr` lanza si el motor
o su binario no están disponibles; la capa de servicios captura el fallo y marca el
documento como FAILED.
"""
from __future__ import annotations

import io
from typing import Any

OCR_ENGINE = "tesseract"

_PDF_MAGIC = b"%PDF"
# Tope de páginas por PDF: un escaneo operativo real es de pocas páginas; el tope evita
# que un PDF enorme bloquee el batch (el command corre síncrono, sin runner async).
_PDF_MAX_PAGES = 5
# Escala de render (pdfium usa 72dpi base): 300/72 ≈ texto nítido para Tesseract.
_PDF_RENDER_SCALE = 300 / 72


def ocr_available() -> bool:
    """True si el paquete pytesseract y Pillow están importables (no garantiza el binario)."""
    try:
        import pytesseract  # noqa: F401
        from PIL import Image  # noqa: F401
    except Exception:  # pragma: no cover - depende del entorno
        return False
    return True


def _ocr_pil(image: Any) -> str:
    """OCR de una imagen PIL. Español + inglés; cae a default si falta el idioma 'spa'."""
    import pytesseract

    try:
        return pytesseract.image_to_string(image, lang="spa+eng")
    except pytesseract.TesseractError:  # pragma: no cover - fallback de idioma
        return pytesseract.image_to_string(image)


def _ocr_image(image_bytes: bytes) -> str:
    from PIL import Image

    return _ocr_pil(Image.open(io.BytesIO(image_bytes)))


def _ocr_pdf(pdf_bytes: bytes) -> str:
    """Renderiza las páginas del PDF (hasta `_PDF_MAX_PAGES`) y OCRea cada una."""
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(pdf_bytes)
    texts: list[str] = []
    try:
        for index in range(min(len(pdf), _PDF_MAX_PAGES)):
            page = pdf[index]
            bitmap = page.render(scale=_PDF_RENDER_SCALE)
            texts.append(_ocr_pil(bitmap.to_pil()))
    finally:
        pdf.close()
    return "\n".join(texts)


def run_ocr(image_bytes: bytes) -> str:
    """Extrae texto del documento: PDF (escáner de PC) o imagen (app/cámara)."""
    if image_bytes[: len(_PDF_MAGIC)] == _PDF_MAGIC:
        return _ocr_pdf(image_bytes)
    return _ocr_image(image_bytes)
