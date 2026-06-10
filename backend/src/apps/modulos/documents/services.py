"""Lógica del pipeline IDP (F1: captura → OCR → revisión).

Sin dependencia de HTTP para que el `management command` y el sync reusen lo mismo.
Audit y straight-through (F4) se suman como hardening posterior.
"""
from __future__ import annotations

from typing import Any

from django.utils import timezone

from apps.modulos.iam.models import OrgUnit

from . import ocr as ocr_engine
from .models import ScannedDocument, ScanStatus
from .storage import load_image_bytes, store_image


def create_scanned_document(
    *,
    company: OrgUnit,
    branch: OrgUnit | None,
    doc_type: str,
    raw_bytes: bytes,
    content_type: str = "",
    uploaded_by: Any = None,
) -> ScannedDocument:
    """Crea el documento en estado PENDING_OCR con la imagen ya almacenada."""
    doc = ScannedDocument(
        company=company,
        branch=branch,
        doc_type=doc_type,
        status=ScanStatus.PENDING_OCR,
        uploaded_by=uploaded_by,
    )
    store_image(doc, raw_bytes, content_type=content_type)
    doc.save()
    return doc


def run_ocr_on_document(doc: ScannedDocument) -> ScannedDocument:
    """Corre la etapa OCR sobre un documento; degrada a FAILED ante cualquier fallo del motor."""
    try:
        raw = load_image_bytes(doc)
        text = ocr_engine.run_ocr(raw)
    except Exception as exc:  # noqa: BLE001 - cualquier fallo del motor → FAILED trazable
        doc.status = ScanStatus.FAILED
        doc.ocr_error = str(exc)[:255]
        doc.processed_at = timezone.now()
        doc.save(update_fields=["status", "ocr_error", "processed_at", "updated_at"])
        return doc

    doc.ocr_text = text
    doc.ocr_engine = ocr_engine.OCR_ENGINE
    doc.ocr_error = ""
    doc.status = ScanStatus.PROCESSED
    doc.processed_at = timezone.now()
    doc.save(
        update_fields=["ocr_text", "ocr_engine", "ocr_error", "status", "processed_at", "updated_at"]
    )
    return doc


def process_pending_documents(*, limit: int = 50) -> int:
    """Procesa con OCR los documentos PENDING_OCR (etapa híbrida: en el servidor)."""
    pending = list(
        ScannedDocument.objects.filter(status=ScanStatus.PENDING_OCR).order_by("created_at")[:limit]
    )
    for doc in pending:
        run_ocr_on_document(doc)
    return len(pending)


def review_document(
    *,
    doc: ScannedDocument,
    reviewed_by: Any = None,
    extracted_fields: dict[str, Any] | None = None,
    doc_type: str | None = None,
) -> ScannedDocument:
    """Revisión humana (human-in-the-loop): confirma/corrige y marca REVIEWED."""
    if extracted_fields is not None:
        doc.extracted_fields = extracted_fields
    if doc_type:
        doc.doc_type = doc_type
    doc.reviewed_by = reviewed_by
    doc.reviewed_at = timezone.now()
    doc.status = ScanStatus.REVIEWED
    doc.save(
        update_fields=["extracted_fields", "doc_type", "reviewed_by", "reviewed_at", "status", "updated_at"]
    )
    return doc
