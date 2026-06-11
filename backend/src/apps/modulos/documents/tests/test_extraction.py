"""Tests de IDP F2: extracción determinista de campos (texto OCR → borrador EXTRACTED).

Fijan: los extractores nicaragüenses (RUC, cédula, fecha, total vs subtotal, número de
documento, placa, galones), la confianza por campo (high con etiqueta, low heurística),
la máquina de estados (PROCESSED → EXTRACTED → REVIEWED solo por humano), que el batch
encadena OCR+extracción, y el invariante F2: la extracción JAMÁS toca `linked_object_*`
ni crea objetos de negocio. Determinista, sin IA, sin binario OCR (se mockea).
"""
from __future__ import annotations

import uuid

import pytest
from django.contrib.auth import get_user_model

from apps.modulos.documents import ocr as ocr_module
from apps.modulos.documents.extraction import EXTRACTOR_VERSION, extract_fields
from apps.modulos.documents.models import DocumentType, ScannedDocument, ScanStatus
from apps.modulos.documents.services import (
    create_scanned_document,
    extract_fields_on_document,
    process_pending_documents,
    process_pending_extractions,
    review_document,
)
from apps.modulos.iam.models import OrgUnit

User = get_user_model()
UT = OrgUnit.UnitType

_FACTURA = """COMERCIAL EL CAFETAL S.A.
RUC: J0310000003457
FACTURA No. 0012345
Fecha: 15/05/2026
Quintal de fertilizante     2,500.00
Sacos de recolección          350.00
SUBTOTAL                    2,850.00
IVA 15%                       427.50
TOTAL C$                    3,277.50
"""

_TICKET_FUEL = """ESTACION DE SERVICIO LA UNION
Diesel
Placa: M 45821
25.5 galones
TOTAL: C$ 980.00
12/05/2026
"""


def _company() -> OrgUnit:
    t = uuid.uuid4().hex[:6]
    holding = OrgUnit.objects.create(unit_type=UT.HOLDING, name=f"H{t}", code=f"H-{t}")
    return OrgUnit.objects.create(unit_type=UT.COMPANY, parent=holding, name=f"C{t}", code=f"C-{t}")


def _user():
    t = uuid.uuid4().hex[:8]
    return User.objects.create_user(username=f"u_{t}", email=f"u_{t}@t.local", password="pass12345")


def _doc(company: OrgUnit, *, ocr_text: str, doc_type: str = DocumentType.GENERAL) -> ScannedDocument:
    doc = create_scanned_document(
        company=company, branch=None, doc_type=doc_type, raw_bytes=b"img", content_type="image/png"
    )
    doc.ocr_text = ocr_text
    doc.status = ScanStatus.PROCESSED
    doc.save(update_fields=["ocr_text", "status", "updated_at"])
    return doc


# --- Extractores (puros, sin DB) --------------------------------------------------

def test_extrae_factura_nicaraguense():
    out = extract_fields(_FACTURA)
    f = out["fields"]
    assert f["ruc"]["value"] == "J0310000003457"
    assert f["ruc"]["confidence"] == "high"  # con etiqueta RUC:
    assert f["fecha"]["value"] == "15/05/2026"
    assert f["numero_documento"]["value"] == "0012345"
    assert out["doc_type_suggested"] == "INVOICE"


def test_total_ignora_subtotal_y_normaliza():
    out = extract_fields(_FACTURA)
    total = out["fields"]["total"]
    assert total["value"] == "3277.50"  # el TOTAL, no el SUBTOTAL ni el IVA
    assert total["confidence"] == "high"
    assert "TOTAL" in total["evidence"]


def test_extrae_ticket_combustible():
    out = extract_fields(_TICKET_FUEL, doc_type=DocumentType.FUEL_TICKET)
    f = out["fields"]
    assert f["placa"]["value"] == "M45821"
    assert f["galones"]["value"] == "25.5"
    assert f["total"]["value"] == "980.00"
    assert out["doc_type_suggested"] == "FUEL_TICKET"


def test_cedula_sin_etiqueta_es_confianza_media_y_va_a_revision():
    out = extract_fields("Recibí de 001-123456-0001A la suma de 500.00")
    assert out["fields"]["ruc"]["value"] == "0011234560001A"
    assert out["fields"]["ruc"]["confidence"] == "medium"
    assert "ruc" in out["needs_review"]


def test_monto_europeo_se_normaliza():
    out = extract_fields("TOTAL 1.234,56")
    assert out["fields"]["total"]["value"] == "1234.56"


def test_texto_sin_campos_no_inventa():
    out = extract_fields("nota manuscrita ilegible sin datos")
    assert out["fields"] == {}
    assert out["extractor"] == EXTRACTOR_VERSION


def test_determinista_mismo_texto_mismo_resultado():
    assert extract_fields(_FACTURA) == extract_fields(_FACTURA)


# --- Máquina de estados + invariante F2 (DB) ---------------------------------------

@pytest.mark.django_db
def test_extraccion_pasa_a_extracted_con_borrador():
    doc = _doc(_company(), ocr_text=_FACTURA)
    doc = extract_fields_on_document(doc)
    assert doc.status == ScanStatus.EXTRACTED
    assert doc.extracted_fields["fields"]["ruc"]["value"] == "J0310000003457"


@pytest.mark.django_db
def test_extraccion_requiere_processed():
    doc = create_scanned_document(
        company=_company(), branch=None, doc_type=DocumentType.GENERAL, raw_bytes=b"img"
    )
    with pytest.raises(ValueError):
        extract_fields_on_document(doc)  # sigue PENDING_OCR


@pytest.mark.django_db
def test_extraccion_jamas_toca_linked_object():
    # Invariante F2: extraer NUNCA integra; eso es F4, después de la revisión humana.
    doc = _doc(_company(), ocr_text=_FACTURA)
    doc = extract_fields_on_document(doc)
    assert doc.linked_object_type == ""
    assert doc.linked_object_id == ""


@pytest.mark.django_db
def test_extracted_no_es_reviewed_hasta_que_un_humano_revisa():
    doc = _doc(_company(), ocr_text=_FACTURA)
    doc = extract_fields_on_document(doc)
    assert doc.status == ScanStatus.EXTRACTED
    assert doc.reviewed_by is None
    revisor = _user()
    corregidos = dict(doc.extracted_fields)
    corregidos["fields"]["total"]["value"] = "3300.00"  # el humano corrige
    doc = review_document(doc=doc, reviewed_by=revisor, extracted_fields=corregidos)
    assert doc.status == ScanStatus.REVIEWED
    assert doc.reviewed_by == revisor
    assert doc.extracted_fields["fields"]["total"]["value"] == "3300.00"


@pytest.mark.django_db
def test_batch_encadena_ocr_y_extraccion(monkeypatch):
    monkeypatch.setattr(ocr_module, "run_ocr", lambda _b: _FACTURA)
    company = _company()
    doc = create_scanned_document(
        company=company, branch=None, doc_type=DocumentType.INVOICE, raw_bytes=b"img"
    )
    assert process_pending_documents() == 1
    doc.refresh_from_db()
    assert doc.status == ScanStatus.EXTRACTED  # OCR + F2 en una pasada
    assert doc.extracted_fields["fields"]["total"]["value"] == "3277.50"


@pytest.mark.django_db
def test_batch_de_rezagados_processed(monkeypatch):
    doc = _doc(_company(), ocr_text=_TICKET_FUEL, doc_type=DocumentType.FUEL_TICKET)
    assert process_pending_extractions() == 1
    doc.refresh_from_db()
    assert doc.status == ScanStatus.EXTRACTED
    assert doc.extracted_fields["fields"]["galones"]["value"] == "25.5"


@pytest.mark.django_db
def test_ocr_fallido_no_se_extrae(monkeypatch):
    def _boom(_b):
        raise RuntimeError("engine down")

    monkeypatch.setattr(ocr_module, "run_ocr", _boom)
    company = _company()
    doc = create_scanned_document(
        company=company, branch=None, doc_type=DocumentType.GENERAL, raw_bytes=b"img"
    )
    process_pending_documents()
    doc.refresh_from_db()
    assert doc.status == ScanStatus.FAILED
    assert doc.extracted_fields == {}
