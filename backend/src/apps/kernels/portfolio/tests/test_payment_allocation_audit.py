"""PR-5: aplicación (allocation) de pagos capturados contra obligaciones de portfolio.

Cierra `audit=0` en la ruta de aplicación de dinero: `allocate_payment_to_obligation`
(reusada también por `auto_allocate_payment`) ahora emite PORTFOLIO_PAYMENT_ALLOCATED.
Verifica el flujo end-to-end: pago CAPTURED → aplicado a una CxC → saldo/estado
actualizado (PARTIAL/PAID) + AuditEvent.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from apps.kernels.payments.services import (
    capture_payment_intent_for_scope,
    create_payment_intent_for_scope,
)
from apps.kernels.portfolio.models import ObligationStatus, PaymentAllocation
from apps.kernels.portfolio.services import allocate_payment_to_obligation, create_receivable
from apps.modulos.audit.models import AuditEvent
from apps.modulos.iam.models import OrgUnit
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
    return User.objects.create_user(username=f"u_{t}", email=f"u_{t}@test.local", password="x")


def _party(company):
    t = uuid.uuid4().hex[:8]
    return Party.objects.create(
        company=company, party_type=Party.PartyType.JURIDICAL, display_name=f"Cliente {t}", tax_id=f"RUC-{t}",
    )


def _captured_intent(*, company, branch, actor, amount="115.00"):
    intent, _ = create_payment_intent_for_scope(
        company=company, branch=branch, actor=actor,
        amount=Decimal(amount), currency="NIO", payment_method="CARD",
        idempotency_key=f"k-{uuid.uuid4().hex}",
    )
    return capture_payment_intent_for_scope(
        company=company, branch=branch, actor=actor, payment_id=intent.payment_id
    )


def _receivable(*, company, branch, party, amount="115.00"):
    return create_receivable(
        company=company, branch=branch, party=party,
        reference_type="BILLING_DOC", reference_id=int(uuid.uuid4().int % 1_000_000),
        principal_amount=Decimal(amount), currency="NIO",
        issue_date=date.today(), due_date=date.today(),
    )


@pytest.mark.django_db
def test_partial_allocation_updates_balance_and_audits():
    company, branch = _scope()
    actor = _user()
    party = _party(company)
    intent = _captured_intent(company=company, branch=branch, actor=actor)
    rec = _receivable(company=company, branch=branch, party=party)

    allocation = allocate_payment_to_obligation(
        payment_intent=intent, obligation=rec,
        allocated_amount=Decimal("50.00"), allocation_date=date.today(), created_by=actor,
    )

    assert allocation.allocated_amount == Decimal("50.00")
    rec.refresh_from_db()
    assert rec.status == ObligationStatus.PARTIAL
    assert AuditEvent.objects.filter(
        event_type="PORTFOLIO_PAYMENT_ALLOCATED", subject_id=str(allocation.allocation_id)
    ).exists()


@pytest.mark.django_db
def test_full_allocation_marks_paid():
    company, branch = _scope()
    actor = _user()
    party = _party(company)
    intent = _captured_intent(company=company, branch=branch, actor=actor)
    rec = _receivable(company=company, branch=branch, party=party)

    allocate_payment_to_obligation(
        payment_intent=intent, obligation=rec,
        allocated_amount=Decimal("115.00"), allocation_date=date.today(), created_by=actor,
    )

    rec.refresh_from_db()
    assert rec.status == ObligationStatus.PAID
    assert PaymentAllocation.objects.filter(payment_intent=intent).count() == 1
