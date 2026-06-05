"""
Tests del módulo compras (procurement) — ciclo de documento de compra:
DRAFT → POSTED → VOIDED, asignación de número por secuencia, idempotencia.
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model

from apps.modulos.compras.models import (
    PurchaseDocStatus,
    PurchaseDocType,
    PurchaseDocument,
    PurchaseSequence,
)
from apps.modulos.compras.services import (
    ProcurementError,
    ProcurementNotFoundError,
    create_purchase_draft,
    post_purchase_document,
    void_purchase_document,
)
from apps.modulos.iam.models import OrgUnit

User = get_user_model()


def _mk_scope(suffix=""):
    s = suffix or uuid.uuid4().hex[:6]
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name=f"H_{s}")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name=f"C_{s}", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name=f"B_{s}", parent=company)
    return company, branch


def _actor():
    return User.objects.create_user(username=f"u_{uuid.uuid4().hex[:8]}", password="x")


def _request(company, branch, actor):
    # publish_outbox_event lee company/branch/user/request_id/headers del request.
    return SimpleNamespace(
        company=company, branch=branch, user=actor,
        request_id="", headers={},
    )


def _mk_draft(company, branch, actor, *, doc_type="SUPPLIER_INVOICE",
              total="1150.00", subtotal="1000.00", tax="150.00", idem=""):
    req = _request(company, branch, actor)
    result = create_purchase_draft(
        request=req, actor=actor,
        doc_type=doc_type, series="P", currency="NIO",
        supplier_name="Proveedor X", supplier_ref="SR-1", external_ref="",
        subtotal=Decimal(subtotal), tax_total=Decimal(tax), total=Decimal(total),
        idempotency_key=idem,
    )
    return result


# ---------------------------------------------------------------------------
# create_purchase_draft
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_create_draft_basic():
    company, branch = _mk_scope()
    actor = _actor()
    result = _mk_draft(company, branch, actor)

    doc = PurchaseDocument.objects.get(id=result.doc_id)
    assert doc.status == PurchaseDocStatus.DRAFT
    assert doc.number == 0
    assert doc.total == Decimal("1150.00")
    assert doc.company == company


@pytest.mark.django_db
def test_create_draft_invalid_doc_type_raises():
    company, branch = _mk_scope()
    actor = _actor()
    req = _request(company, branch, actor)
    with pytest.raises(ProcurementError, match="doc_type"):
        create_purchase_draft(
            request=req, actor=actor,
            doc_type="NOT_A_TYPE", series="P", currency="NIO",
            supplier_name="X", supplier_ref="", external_ref="",
            subtotal=Decimal("0"), tax_total=Decimal("0"), total=Decimal("0"),
        )


@pytest.mark.django_db
def test_create_draft_idempotent():
    company, branch = _mk_scope()
    actor = _actor()
    r1 = _mk_draft(company, branch, actor, idem="proc-idem-1")
    r2 = _mk_draft(company, branch, actor, idem="proc-idem-1")
    assert r1.doc_id == r2.doc_id
    assert PurchaseDocument.objects.filter(company=company, idempotency_key="proc-idem-1").count() == 1


# ---------------------------------------------------------------------------
# post_purchase_document
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_post_assigns_sequential_number():
    company, branch = _mk_scope()
    actor = _actor()
    r1 = _mk_draft(company, branch, actor)
    r2 = _mk_draft(company, branch, actor)
    req = _request(company, branch, actor)

    out1 = post_purchase_document(request=req, actor=actor, doc_id=r1.doc_id)
    out2 = post_purchase_document(request=req, actor=actor, doc_id=r2.doc_id)

    assert out1["status"] == PurchaseDocStatus.POSTED
    assert out1["number"] == 1
    assert out2["number"] == 2
    # Secuencia avanzó
    seq = PurchaseSequence.objects.get(company=company, branch=branch, doc_type="SUPPLIER_INVOICE", series="P")
    assert seq.next_number == 3


@pytest.mark.django_db
def test_post_idempotent_when_already_posted():
    company, branch = _mk_scope()
    actor = _actor()
    r = _mk_draft(company, branch, actor)
    req = _request(company, branch, actor)

    post_purchase_document(request=req, actor=actor, doc_id=r.doc_id)
    out2 = post_purchase_document(request=req, actor=actor, doc_id=r.doc_id)
    assert out2.get("already_posted") is True


@pytest.mark.django_db
def test_post_nonexistent_raises_not_found():
    company, branch = _mk_scope()
    actor = _actor()
    req = _request(company, branch, actor)
    with pytest.raises(ProcurementNotFoundError):
        post_purchase_document(request=req, actor=actor, doc_id=999999)


# ---------------------------------------------------------------------------
# void_purchase_document
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_void_posted_document():
    company, branch = _mk_scope()
    actor = _actor()
    r = _mk_draft(company, branch, actor)
    req = _request(company, branch, actor)
    post_purchase_document(request=req, actor=actor, doc_id=r.doc_id)

    out = void_purchase_document(request=req, actor=actor, doc_id=r.doc_id, reason="Error proveedor")
    assert out["ok"] is True
    doc = PurchaseDocument.objects.get(id=r.doc_id)
    assert doc.status == PurchaseDocStatus.VOIDED
    assert doc.void_reason == "Error proveedor"


@pytest.mark.django_db
def test_void_draft_raises():
    company, branch = _mk_scope()
    actor = _actor()
    r = _mk_draft(company, branch, actor)
    req = _request(company, branch, actor)
    # No se puede anular un DRAFT (nunca fue posteado)
    with pytest.raises(ProcurementError, match="draft"):
        void_purchase_document(request=req, actor=actor, doc_id=r.doc_id)


@pytest.mark.django_db
def test_void_idempotent_when_already_voided():
    company, branch = _mk_scope()
    actor = _actor()
    r = _mk_draft(company, branch, actor)
    req = _request(company, branch, actor)
    post_purchase_document(request=req, actor=actor, doc_id=r.doc_id)
    void_purchase_document(request=req, actor=actor, doc_id=r.doc_id)

    out2 = void_purchase_document(request=req, actor=actor, doc_id=r.doc_id)
    assert out2.get("already_voided") is True


@pytest.mark.django_db
def test_post_voided_document_raises():
    company, branch = _mk_scope()
    actor = _actor()
    r = _mk_draft(company, branch, actor)
    req = _request(company, branch, actor)
    post_purchase_document(request=req, actor=actor, doc_id=r.doc_id)
    void_purchase_document(request=req, actor=actor, doc_id=r.doc_id)
    # Postear un documento anulado debe fallar
    with pytest.raises(ProcurementError, match="voided"):
        post_purchase_document(request=req, actor=actor, doc_id=r.doc_id)
