"""Tests del canal "PC con documentos escaneados": PDF → render de páginas → OCR.

Fijan: el ruteo por magic bytes (`%PDF` → pypdfium2; imagen → PIL), el tope de páginas
(un PDF enorme no bloquea el batch síncrono), y que un PDF corrupto degrada el documento
a FAILED sin romper nada. El OCR de la imagen renderizada se mockea (no depende del
binario tesseract); el render de pypdfium2 es REAL.
"""
from __future__ import annotations

import io

import pytest

from apps.modulos.documents import ocr as ocr_module
from apps.modulos.documents.models import DocumentType, ScannedDocument, ScanStatus
from apps.modulos.documents.services import create_scanned_document, process_pending_documents
from apps.modulos.iam.models import OrgUnit

UT = OrgUnit.UnitType


def _pdf_minimo(paginas: int = 1) -> bytes:
    """PDF mínimo válido hecho a mano (pdfium reconstruye el xref ausente)."""
    kids = " ".join(f"{3 + i} 0 R" for i in range(paginas))
    objetos = "".join(
        f"{3 + i} 0 obj <</Type /Page /Parent 2 0 R /MediaBox [0 0 100 100]>> endobj\n"
        for i in range(paginas)
    )
    doc = (
        "%PDF-1.4\n"
        "1 0 obj <</Type /Catalog /Pages 2 0 R>> endobj\n"
        f"2 0 obj <</Type /Pages /Kids [{kids}] /Count {paginas}>> endobj\n"
        f"{objetos}"
        "trailer <</Root 1 0 R>>\n"
        "%%EOF\n"
    )
    return doc.encode("latin-1")


def _png_minimo() -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (4, 4), color="white").save(buf, format="PNG")
    return buf.getvalue()


def test_pdf_se_rutea_y_renderiza(monkeypatch):
    monkeypatch.setattr(ocr_module, "_ocr_pil", lambda img: "TEXTO DESDE PDF")
    assert ocr_module.run_ocr(_pdf_minimo()) == "TEXTO DESDE PDF"


def test_imagen_sigue_ruteando_a_pil(monkeypatch):
    monkeypatch.setattr(ocr_module, "_ocr_pil", lambda img: "TEXTO DESDE IMAGEN")
    assert ocr_module.run_ocr(_png_minimo()) == "TEXTO DESDE IMAGEN"


def test_tope_de_paginas_no_bloquea_el_batch(monkeypatch):
    llamadas: list[int] = []
    monkeypatch.setattr(ocr_module, "_ocr_pil", lambda img: llamadas.append(1) or "p")
    monkeypatch.setattr(ocr_module, "_PDF_MAX_PAGES", 2)
    out = ocr_module.run_ocr(_pdf_minimo(paginas=4))
    assert len(llamadas) == 2  # solo las primeras 2 páginas
    assert out == "p\np"


@pytest.mark.django_db
def test_pdf_corrupto_degrada_a_failed():
    t = "pdfx"
    holding = OrgUnit.objects.create(unit_type=UT.HOLDING, name=f"H{t}", code=f"H-{t}")
    company = OrgUnit.objects.create(unit_type=UT.COMPANY, parent=holding, name=f"C{t}", code=f"C-{t}")
    create_scanned_document(
        company=company,
        branch=None,
        doc_type=DocumentType.GENERAL,
        raw_bytes=b"%PDF-1.4 basura corrupta sin estructura",
        content_type="application/pdf",
    )
    process_pending_documents()
    doc = ScannedDocument.objects.get(company=company)
    assert doc.status == ScanStatus.FAILED  # nunca rompe la request/batch
    assert doc.ocr_error != ""