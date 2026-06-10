"""Tests del pipeline IDP F1 (servicios + command). OCR se mockea para no depender del binario."""
from __future__ import annotations

import uuid

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command

from apps.modulos.documents import ocr as ocr_module
from apps.modulos.documents.models import DocumentType, ScannedDocument, ScanStatus
from apps.modulos.documents.services import (
    create_scanned_document,
    process_pending_documents,
    review_document,
)
from apps.modulos.documents.storage import load_image_bytes
from apps.modulos.iam.models import OrgUnit

User = get_user_model()
UT = OrgUnit.UnitType


def _company() -> OrgUnit:
    t = uuid.uuid4().hex[:6]
    holding = OrgUnit.objects.create(unit_type=UT.HOLDING, name=f"H{t}", code=f"H-{t}")
    return OrgUnit.objects.create(unit_type=UT.COMPANY, parent=holding, name=f"C{t}", code=f"C-{t}")


def _user():
    t = uuid.uuid4().hex[:8]
    return User.objects.create_user(username=f"u_{t}", email=f"u_{t}@t.local", password="pass12345")


@pytest.mark.django_db
def test_create_document_is_pending_and_stores_image():
    company = _company()
    user = _user()
    doc = create_scanned_document(
        company=company,
        branch=None,
        doc_type=DocumentType.FUEL_TICKET,
        raw_bytes=b"imagen-binaria",
        content_type="image/png",
        uploaded_by=user,
    )
    assert doc.status == ScanStatus.PENDING_OCR
    assert doc.byte_size == len(b"imagen-binaria")
    assert doc.content_type == "image/png"
    # roundtrip de almacenamiento (base64 en DB)
    assert load_image_bytes(doc) == b"imagen-binaria"


@pytest.mark.django_db
def test_process_pending_runs_ocr_and_marks_processed(monkeypatch):
    company = _company()
    create_scanned_document(
        company=company, branch=None, doc_type=DocumentType.GENERAL, raw_bytes=b"img"
    )
    monkeypatch.setattr(ocr_module, "run_ocr", lambda _b: "TEXTO OCR")

    n = process_pending_documents(limit=10)

    assert n == 1
    doc = ScannedDocument.objects.get(company=company)
    assert doc.status == ScanStatus.PROCESSED
    assert doc.ocr_text == "TEXTO OCR"
    assert doc.ocr_engine == ocr_module.OCR_ENGINE
    assert doc.processed_at is not None


@pytest.mark.django_db
def test_process_pending_degrades_to_failed_on_engine_error(monkeypatch):
    company = _company()
    create_scanned_document(
        company=company, branch=None, doc_type=DocumentType.GENERAL, raw_bytes=b"img"
    )

    def _boom(_b):
        raise RuntimeError("tesseract no disponible")

    monkeypatch.setattr(ocr_module, "run_ocr", _boom)

    process_pending_documents(limit=10)

    doc = ScannedDocument.objects.get(company=company)
    assert doc.status == ScanStatus.FAILED
    assert "tesseract no disponible" in doc.ocr_error


@pytest.mark.django_db
def test_review_marks_reviewed_and_keeps_extracted_fields():
    company = _company()
    reviewer = _user()
    doc = create_scanned_document(
        company=company, branch=None, doc_type=DocumentType.GENERAL, raw_bytes=b"img"
    )
    doc = review_document(
        doc=doc,
        reviewed_by=reviewer,
        extracted_fields={"total": "1234.56", "ruc": "J0310000000000"},
        doc_type=DocumentType.INVOICE,
    )
    assert doc.status == ScanStatus.REVIEWED
    assert doc.doc_type == DocumentType.INVOICE
    assert doc.extracted_fields["total"] == "1234.56"
    assert doc.reviewed_by_id == reviewer.id
    assert doc.reviewed_at is not None


@pytest.mark.django_db
def test_command_process_pending_ocr(monkeypatch):
    company = _company()
    create_scanned_document(
        company=company, branch=None, doc_type=DocumentType.GENERAL, raw_bytes=b"img"
    )
    monkeypatch.setattr(ocr_module, "run_ocr", lambda _b: "ok")

    call_command("process_pending_ocr", "--limit", "5")

    assert ScannedDocument.objects.get(company=company).status == ScanStatus.PROCESSED
