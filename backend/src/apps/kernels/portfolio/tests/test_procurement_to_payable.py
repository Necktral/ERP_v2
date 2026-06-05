"""PR-4: cableado Compras → portfolio CxP.

Un documento de compra posteado CON proveedor fuerte (Party) crea su CxP (Payable) en
portfolio, auditada e idempotente. El modo legacy (proveedor textual sin Party) NO crea
cartera. Ownership: Compras genera el documento; portfolio posee el saldo.
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model

from apps.kernels.portfolio.models import Payable
from apps.kernels.portfolio.services import link_procurement_document_to_payable
from apps.modulos.audit.models import AuditEvent
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
        company=company, party_type=Party.PartyType.JURIDICAL, display_name=f"Proveedor {t}", tax_id=f"RUC-{t}",
    )


def _create_purchase(*, req, user, supplier_party_id=None):
    return procurement_services.create_purchase_draft(
        request=req, actor=user, doc_type=PurchaseDocType.SUPPLIER_INVOICE, series="P", currency="NIO",
        supplier_name="Proveedor Demo", supplier_ref="SUP-001", external_ref="EXT-001",
        subtotal=Decimal("100.00"), tax_total=Decimal("15.00"), total=Decimal("115.00"),
        supplier_party_id=supplier_party_id, notes="t", metadata_json={},
        idempotency_key=f"idem-{uuid.uuid4().hex}",
    )


def _payables_for(company, doc_id):
    return Payable.objects.filter(company=company, reference_type="PROCUREMENT_DOC", reference_id=doc_id)


@pytest.mark.django_db
def test_posting_with_party_creates_payable_and_audit():
    company, branch = _scope()
    actor = _user()
    req = _request(company, branch, actor)
    party = _party(company)
    draft = _create_purchase(req=req, user=actor, supplier_party_id=party.id)

    procurement_services.post_purchase_document(request=req, actor=actor, doc_id=draft.doc_id)

    pay = _payables_for(company, draft.doc_id).first()
    assert pay is not None
    assert pay.party_id == party.id
    assert str(pay.principal_amount) == "115.00"
    assert AuditEvent.objects.filter(
        event_type="PORTFOLIO_PAYABLE_CREATED", subject_id=str(pay.obligation_id)
    ).exists()


@pytest.mark.django_db
def test_legacy_posting_without_party_creates_no_payable():
    company, branch = _scope()
    actor = _user()
    req = _request(company, branch, actor)
    draft = _create_purchase(req=req, user=actor, supplier_party_id=None)

    procurement_services.post_purchase_document(request=req, actor=actor, doc_id=draft.doc_id)

    assert not _payables_for(company, draft.doc_id).exists()


@pytest.mark.django_db
def test_payable_link_is_idempotent():
    company, branch = _scope()
    actor = _user()
    req = _request(company, branch, actor)
    party = _party(company)
    draft = _create_purchase(req=req, user=actor, supplier_party_id=party.id)
    procurement_services.post_purchase_document(request=req, actor=actor, doc_id=draft.doc_id)

    assert _payables_for(company, draft.doc_id).count() == 1

    posted = (
        OutboxEvent.objects.filter(
            source_module="PROCUREMENT", event_type="ProcurementDocumentPosted", payload__data__doc_id=draft.doc_id
        )
        .order_by("-id")
        .first()
    )
    result = link_procurement_document_to_payable(outbox_event=posted, actor_user=actor)
    assert result["status"] == "EXISTS"
    assert _payables_for(company, draft.doc_id).count() == 1
