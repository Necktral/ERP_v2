"""PR-2: snapshot de contraparte (proveedor) en el payload de eventos de compras.

Los eventos ProcurementDocumentPosted/Voided llevan `supplier_party_id` + snapshot textual
(`supplier_display_name`, `supplier_tax_id`) para trazar al proveedor aguas abajo (CxP/accounting).

Nota: el enforce de supplier_party NO se aplica en este PR — el modo legacy (proveedor textual
sin Party) está soportado y testeado; exigirlo requiere una decisión de deprecación + migración.
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model

from apps.modulos.compras import services as procurement_services
from apps.modulos.compras.models import PurchaseDocType
from apps.modulos.iam.models import OrgUnit
from apps.modulos.integration.models import OutboxEvent
from apps.modulos.parties.models import Party

User = get_user_model()


def _scope():
    t = uuid.uuid4().hex[:8]
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name=f"H{t}", code=f"H-{t}")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, parent=holding, name=f"C{t}", code=f"C-{t}")
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, parent=company, name=f"B{t}", code=f"B-{t}")
    return company, branch


def _user():
    t = uuid.uuid4().hex[:8]
    return User.objects.create_user(username=f"u_{t}", email=f"u_{t}@test.local", password="Secret123!")


def _request(company, branch, user):
    return SimpleNamespace(
        company=company, branch=branch, user=user, META={}, headers={},
        path="/test/procurement/", method="POST", request_id=f"req-{uuid.uuid4().hex[:8]}",
    )


def _party(company):
    t = uuid.uuid4().hex[:8]
    return Party.objects.create(
        company=company, party_type=Party.PartyType.JURIDICAL,
        display_name=f"Proveedor {t}", tax_id=f"RUC-{t}",
    )


def _create_purchase(*, request, user, supplier_party_id=None):
    return procurement_services.create_purchase_draft(
        request=request, actor=user,
        doc_type=PurchaseDocType.SUPPLIER_INVOICE, series="P", currency="NIO",
        supplier_name="Proveedor Demo", supplier_ref="SUP-001", external_ref="EXT-001",
        subtotal=Decimal("100.00"), tax_total=Decimal("15.00"), total=Decimal("115.00"),
        supplier_party_id=supplier_party_id, notes="t", metadata_json={},
        idempotency_key=f"idem-{uuid.uuid4().hex}",
    )


def _event(event_type, doc_id):
    return (
        OutboxEvent.objects.filter(source_module="PROCUREMENT", event_type=event_type, payload__data__doc_id=doc_id)
        .order_by("-id")
        .first()
    )


@pytest.mark.django_db
def test_posted_payload_includes_supplier_party_and_snapshot():
    company, branch = _scope()
    actor = _user()
    req = _request(company, branch, actor)
    party = _party(company)
    draft = _create_purchase(request=req, user=actor, supplier_party_id=party.id)

    procurement_services.post_purchase_document(request=req, actor=actor, doc_id=draft.doc_id)

    ev = _event("ProcurementDocumentPosted", draft.doc_id)
    assert ev is not None
    data = ev.payload["data"]
    assert data["supplier_party_id"] == party.id
    assert data["supplier_display_name"] == "Proveedor Demo"
    assert data["supplier_tax_id"] == "SUP-001"


@pytest.mark.django_db
def test_voided_payload_includes_supplier_snapshot():
    company, branch = _scope()
    actor = _user()
    req = _request(company, branch, actor)
    party = _party(company)
    draft = _create_purchase(request=req, user=actor, supplier_party_id=party.id)
    procurement_services.post_purchase_document(request=req, actor=actor, doc_id=draft.doc_id)

    procurement_services.void_purchase_document(request=req, actor=actor, doc_id=draft.doc_id, reason="error")

    ev = _event("ProcurementDocumentVoided", draft.doc_id)
    assert ev is not None
    data = ev.payload["data"]
    assert data["supplier_party_id"] == party.id
    assert data["supplier_display_name"] == "Proveedor Demo"


@pytest.mark.django_db
def test_legacy_without_party_still_posts_and_payload_party_is_none():
    # Modo legacy soportado: sin supplier_party el documento se postea igual.
    company, branch = _scope()
    actor = _user()
    req = _request(company, branch, actor)
    draft = _create_purchase(request=req, user=actor, supplier_party_id=None)

    out = procurement_services.post_purchase_document(request=req, actor=actor, doc_id=draft.doc_id)
    assert out["status"] == "POSTED"

    ev = _event("ProcurementDocumentPosted", draft.doc_id)
    assert ev.payload["data"]["supplier_party_id"] is None
    assert ev.payload["data"]["supplier_display_name"] == "Proveedor Demo"
