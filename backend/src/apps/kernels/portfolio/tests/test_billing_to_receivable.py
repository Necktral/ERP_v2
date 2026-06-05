"""PR-3: cableado Billing → portfolio CxC.

Una venta a crédito emitida crea una CxC (Receivable) en portfolio, auditada e idempotente.
El contado / consumidor final (credit_status NONE) NO crea cartera. Respeta ownership:
Billing emite el documento; portfolio posee el saldo.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model

from apps.kernels.facturacion.models import BillingDocument, CreditStatus
from apps.kernels.facturacion.services import create_draft, issue_doc
from apps.kernels.portfolio.models import Receivable
from apps.kernels.portfolio.services import link_billing_document_to_receivable
from apps.modulos.audit.models import AuditEvent
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


def _party(company):
    t = uuid.uuid4().hex[:8]
    return Party.objects.create(
        company=company, party_type=Party.PartyType.JURIDICAL, display_name=f"Cliente {t}", tax_id=f"RUC-{t}",
    )


def _draft(req, actor, *, customer_party_id=None):
    return create_draft(
        request=req, actor=actor, doc_type="INVOICE", series="A", currency="NIO",
        customer_name="Cliente Demo", customer_ref="C-001", is_fiscal=False,
        customer_party_id=customer_party_id,
        lines=[{"description": "Servicio", "quantity": "1", "unit_price": "100", "tax_rate": "0.15"}],
        idempotency_key=f"draft-{uuid.uuid4().hex}",
    )


def _make_credit(doc_id):
    doc = BillingDocument.objects.get(id=doc_id)
    doc.credit_status = CreditStatus.APPROVED
    doc.save(update_fields=["credit_status"])


def _issue(req, actor, doc_id):
    return issue_doc(request=req, actor=actor, doc_id=doc_id, idempotency_key=f"i-{uuid.uuid4().hex}")


def _receivables_for(company, doc_id):
    return Receivable.objects.filter(company=company, reference_type="BILLING_DOC", reference_id=doc_id)


@pytest.mark.django_db
def test_credit_issue_creates_receivable_and_audit():
    company, branch = _scope()
    actor = _user()
    req = _request(company, branch, actor)
    party = _party(company)
    draft = _draft(req, actor, customer_party_id=party.id)
    _make_credit(draft.doc_id)

    _issue(req, actor, draft.doc_id)

    rec = _receivables_for(company, draft.doc_id).first()
    assert rec is not None
    assert rec.party_id == party.id
    assert str(rec.principal_amount) == "115.00"
    assert AuditEvent.objects.filter(
        event_type="PORTFOLIO_RECEIVABLE_CREATED", subject_id=str(rec.obligation_id)
    ).exists()


@pytest.mark.django_db
def test_cash_issue_does_not_create_receivable():
    company, branch = _scope()
    actor = _user()
    req = _request(company, branch, actor)
    draft = _draft(req, actor)  # credit_status NONE (contado), sin party

    _issue(req, actor, draft.doc_id)

    assert not _receivables_for(company, draft.doc_id).exists()


@pytest.mark.django_db
def test_receivable_link_is_idempotent():
    company, branch = _scope()
    actor = _user()
    req = _request(company, branch, actor)
    party = _party(company)
    draft = _draft(req, actor, customer_party_id=party.id)
    _make_credit(draft.doc_id)
    _issue(req, actor, draft.doc_id)

    assert _receivables_for(company, draft.doc_id).count() == 1

    # Reprocesar el mismo evento no duplica la CxC.
    issued = (
        OutboxEvent.objects.filter(
            source_module="BILLING", event_type="DocumentIssued", payload__data__doc_id=draft.doc_id
        )
        .order_by("-id")
        .first()
    )
    result = link_billing_document_to_receivable(outbox_event=issued, actor_user=actor)
    assert result["status"] == "EXISTS"
    assert _receivables_for(company, draft.doc_id).count() == 1
