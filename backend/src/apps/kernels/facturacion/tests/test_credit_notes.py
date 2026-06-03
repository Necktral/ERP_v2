"""Tests de emisión de Notas de Crédito (facturacion)."""
from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model

from apps.kernels.facturacion.credit_notes import issue_credit_note
from apps.kernels.facturacion.models import BillingDocument, DocStatus, DocType
from apps.kernels.facturacion.services import BillingError, create_draft, issue_doc
from apps.modulos.iam.models import OrgUnit
from apps.modulos.integration.models import OutboxEvent

User = get_user_model()


def _scope():
    t = uuid.uuid4().hex[:8]
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name=f"H{t}", code=f"H-{t}")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, parent=holding, name=f"C{t}", code=f"C-{t}")
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, parent=company, name=f"B{t}", code=f"B-{t}")
    user = User.objects.create_user(username=f"u_{t}", email=f"u_{t}@test.local", password="Secret123!")
    request = SimpleNamespace(
        company=company, branch=branch, user=user, META={}, headers={},
        path="/t/billing/", method="POST", request_id=f"req-{t}",
    )
    return company, branch, user, request


def _issued_invoice(request, actor, *, unit_price="100", qty="1", tax="0.15") -> BillingDocument:
    draft = create_draft(
        request=request,
        actor=actor,
        doc_type=DocType.INVOICE,
        series="A",
        currency="NIO",
        customer_name="Cliente Demo",
        customer_ref="C-001",
        is_fiscal=False,
        lines=[{"description": "Servicio", "quantity": qty, "unit_price": unit_price, "tax_rate": tax}],
        idempotency_key=f"inv-{uuid.uuid4().hex}",
    )
    issue_doc(request=request, actor=actor, doc_id=draft.doc_id, apply_inventory=False, idempotency_key=f"iss-{uuid.uuid4().hex}")
    return BillingDocument.objects.get(id=draft.doc_id)


@pytest.mark.django_db
def test_full_credit_note_links_and_updates_creditable():
    _, _, user, request = _scope()
    inv = _issued_invoice(request, user)  # total 115.00
    assert inv.total == Decimal("115.00")

    cn = issue_credit_note(request=request, actor=user, original_doc_id=inv.id, reason="devolución total")
    assert cn.doc_type == DocType.CREDIT_NOTE
    assert cn.status == DocStatus.ISSUED
    assert cn.related_doc_id == inv.id
    assert cn.total == Decimal("115.00")
    assert cn.number > 0
    assert cn.fiscal_status == "ISSUED"

    inv.refresh_from_db()
    assert inv.credited_total == Decimal("115.00")

    ev = OutboxEvent.objects.filter(source_module="BILLING", event_type="CreditNoteIssued").order_by("-id").first()
    assert ev is not None
    assert ev.payload["data"]["original_doc_id"] == inv.id


@pytest.mark.django_db
def test_partial_credit_note():
    _, _, user, request = _scope()
    inv = _issued_invoice(request, user)  # 115.00
    cn = issue_credit_note(
        request=request,
        actor=user,
        original_doc_id=inv.id,
        reason="devolución parcial",
        lines=[{"description": "Parcial", "quantity": "1", "unit_price": "40", "tax_rate": "0.15"}],
    )
    assert cn.total == Decimal("46.00")  # 40 + 15%
    inv.refresh_from_db()
    assert inv.credited_total == Decimal("46.00")


@pytest.mark.django_db
def test_over_credit_is_rejected():
    _, _, user, request = _scope()
    inv = _issued_invoice(request, user)  # 115.00
    issue_credit_note(request=request, actor=user, original_doc_id=inv.id, reason="total")  # acredita 115
    with pytest.raises(BillingError):
        issue_credit_note(request=request, actor=user, original_doc_id=inv.id, reason="otra vez")


@pytest.mark.django_db
def test_cannot_credit_a_draft_or_non_invoice():
    _, _, user, request = _scope()
    draft = create_draft(
        request=request, actor=user, doc_type=DocType.INVOICE, series="A", currency="NIO",
        customer_name="X", customer_ref="", is_fiscal=False,
        lines=[{"description": "x", "quantity": "1", "unit_price": "10", "tax_rate": "0"}],
        idempotency_key=f"d-{uuid.uuid4().hex}",
    )
    with pytest.raises(BillingError):
        issue_credit_note(request=request, actor=user, original_doc_id=draft.doc_id, reason="x")


@pytest.mark.django_db
def test_credit_note_is_idempotent():
    _, _, user, request = _scope()
    inv = _issued_invoice(request, user)
    key = f"cn-{uuid.uuid4().hex}"
    cn1 = issue_credit_note(request=request, actor=user, original_doc_id=inv.id, reason="x", idempotency_key=key)
    cn2 = issue_credit_note(request=request, actor=user, original_doc_id=inv.id, reason="x", idempotency_key=key)
    assert cn1.id == cn2.id
    inv.refresh_from_db()
    assert inv.credited_total == Decimal("115.00")  # no se duplica
