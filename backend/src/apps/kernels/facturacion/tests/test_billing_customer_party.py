"""PR-1: Party fuerte en Billing (enforce crédito + payload de contraparte).

Una venta a crédito/con-saldo (genera cartera/CxC) exige `customer_party`; el contado
a consumidor final (credit_status == NONE) puede emitirse sin party. Los eventos
DocumentIssued/Voided llevan `customer_party_id` + snapshot textual para trazar la
contraparte aguas abajo (CxC/accounting).
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model

from apps.kernels.facturacion.models import BillingDocument, CreditStatus, DocStatus
from apps.kernels.facturacion.services import BillingError, create_draft, issue_doc
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
        path="/test/billing/", method="POST", request_id=f"req-{uuid.uuid4().hex[:8]}",
    )


def _party(company, *, suffix=""):
    t = suffix or uuid.uuid4().hex[:8]
    return Party.objects.create(
        company=company,
        party_type=Party.PartyType.JURIDICAL,
        display_name=f"Cliente {t}",
        tax_id=f"RUC-{t}",
    )


def _draft(request, actor, *, customer_party_id=None, customer_name="Cliente Demo", customer_ref="C-001"):
    return create_draft(
        request=request, actor=actor,
        doc_type="INVOICE", series="A", currency="NIO",
        customer_name=customer_name, customer_ref=customer_ref,
        is_fiscal=False, customer_party_id=customer_party_id,
        lines=[{"description": "Servicio", "quantity": "1", "unit_price": "100", "tax_rate": "0.15"}],
        idempotency_key=f"draft-{uuid.uuid4().hex}",
    )


def _make_credit(doc_id):
    doc = BillingDocument.objects.get(id=doc_id)
    doc.credit_status = CreditStatus.APPROVED
    doc.save(update_fields=["credit_status"])
    return doc


def _issued_outbox(doc_id):
    return (
        OutboxEvent.objects.filter(source_module="BILLING", event_type="DocumentIssued", payload__data__doc_id=doc_id)
        .order_by("-id")
        .first()
    )


@pytest.mark.django_db
def test_credit_sale_without_party_is_blocked():
    company, branch = _scope()
    actor = _user()
    req = _request(company, branch, actor)
    draft = _draft(req, actor)  # sin party
    _make_credit(draft.doc_id)

    with pytest.raises(BillingError):
        issue_doc(request=req, actor=actor, doc_id=draft.doc_id, idempotency_key=f"i-{uuid.uuid4().hex}")

    assert BillingDocument.objects.get(id=draft.doc_id).status == DocStatus.DRAFT


@pytest.mark.django_db
def test_credit_sale_with_party_issues_and_payload_has_party():
    company, branch = _scope()
    actor = _user()
    req = _request(company, branch, actor)
    party = _party(company)
    draft = _draft(req, actor, customer_party_id=party.id, customer_name="ACME S.A.")
    _make_credit(draft.doc_id)

    issue_doc(request=req, actor=actor, doc_id=draft.doc_id, idempotency_key=f"i-{uuid.uuid4().hex}")

    assert BillingDocument.objects.get(id=draft.doc_id).status == DocStatus.ISSUED
    ev = _issued_outbox(draft.doc_id)
    assert ev is not None
    data = ev.payload["data"]
    assert data["customer_party_id"] == party.id
    assert data["customer_display_name"] == "ACME S.A."


@pytest.mark.django_db
def test_cash_consumer_final_without_party_issues():
    company, branch = _scope()
    actor = _user()
    req = _request(company, branch, actor)
    draft = _draft(req, actor)  # credit_status NONE (default), sin party

    issue_doc(request=req, actor=actor, doc_id=draft.doc_id, idempotency_key=f"i-{uuid.uuid4().hex}")

    assert BillingDocument.objects.get(id=draft.doc_id).status == DocStatus.ISSUED


@pytest.mark.django_db
def test_cross_company_party_rejected_at_draft():
    company, branch = _scope()
    other_company, _ = _scope()
    actor = _user()
    req = _request(company, branch, actor)
    foreign_party = _party(other_company)  # party de OTRA company

    with pytest.raises(BillingError):
        _draft(req, actor, customer_party_id=foreign_party.id)
