"""Tests de auditoría de PaymentIntent (Unidad #3, incremento #1).

Cada operación con efecto del intent (authorize/capture/reverse/cancel/refund) debe
emitir su `AuditEvent` `PAYMENTS_INTENT_*` con subject `PAYMENT_INTENT`, actor y
snapshots before/after (invariante #4).
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from apps.kernels.payments.models import PaymentIntent
from apps.kernels.payments.services import (
    authorize_payment_intent_for_scope,
    cancel_payment_intent_for_scope,
    capture_payment_intent_for_scope,
    create_payment_intent_for_scope,
    refund_payment_intent_for_scope,
    reverse_captured_payment_intent_for_scope,
)
from apps.modulos.audit.models import AuditEvent
from apps.modulos.iam.models import OrgUnit

User = get_user_model()
PaymentStatus = PaymentIntent.Status


def _mk_scope():
    s = uuid.uuid4().hex[:6]
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name=f"H{s}")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name=f"C{s}", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name=f"B{s}", parent=company)
    return company, branch


def _actor():
    name = f"actor_{uuid.uuid4().hex[:8]}"
    return User.objects.create_user(username=name, email=f"{name}@test.com", password="x")


def _mk_intent(*, company, branch, actor, amount="100.00", payment_method="CARD"):
    intent, _ = create_payment_intent_for_scope(
        company=company, branch=branch, actor=actor,
        amount=Decimal(amount), currency="NIO",
        payment_method=payment_method,
        idempotency_key=f"k-{uuid.uuid4().hex}",
    )
    return intent


def _audit(event_type, subject_id):
    return AuditEvent.objects.filter(event_type=event_type, subject_id=str(subject_id))


@pytest.mark.django_db
def test_authorize_emits_audit():
    company, branch = _mk_scope()
    actor = _actor()
    intent = _mk_intent(company=company, branch=branch, actor=actor)
    authorize_payment_intent_for_scope(
        company=company, branch=branch, actor=actor, payment_id=intent.payment_id
    )
    ev = _audit("PAYMENTS_INTENT_AUTHORIZED", intent.payment_id).first()
    assert ev is not None
    assert ev.subject_type == "PAYMENT_INTENT"
    assert ev.before_snapshot.get("status") == PaymentStatus.INTENDED
    assert ev.after_snapshot.get("status") == PaymentStatus.AUTHORIZED


@pytest.mark.django_db
def test_capture_emits_audit():
    company, branch = _mk_scope()
    actor = _actor()
    intent = _mk_intent(company=company, branch=branch, actor=actor)
    capture_payment_intent_for_scope(
        company=company, branch=branch, actor=actor, payment_id=intent.payment_id
    )
    ev = _audit("PAYMENTS_INTENT_CAPTURED", intent.payment_id).first()
    assert ev is not None
    assert ev.after_snapshot.get("status") == PaymentStatus.CAPTURED


@pytest.mark.django_db
def test_cancel_emits_audit():
    company, branch = _mk_scope()
    actor = _actor()
    intent = _mk_intent(company=company, branch=branch, actor=actor)
    cancel_payment_intent_for_scope(
        company=company, branch=branch, actor=actor, payment_id=intent.payment_id, reason="duplicado"
    )
    ev = _audit("PAYMENTS_INTENT_CANCELLED", intent.payment_id).first()
    assert ev is not None
    assert ev.after_snapshot.get("status") == PaymentStatus.CANCELLED


@pytest.mark.django_db
def test_refund_emits_audit():
    company, branch = _mk_scope()
    actor = _actor()
    intent = _mk_intent(company=company, branch=branch, actor=actor, amount="200.00")
    captured = capture_payment_intent_for_scope(
        company=company, branch=branch, actor=actor, payment_id=intent.payment_id
    )
    captured.amount_captured = Decimal("200.00")
    captured.save(update_fields=["amount_captured"])

    refund = refund_payment_intent_for_scope(
        company=company, branch=branch, actor=actor, payment_id=intent.payment_id,
        amount=Decimal("50.00"), idempotency_key=f"r-{uuid.uuid4().hex}", reason="ajuste",
    )
    ev = _audit("PAYMENTS_INTENT_REFUNDED", intent.payment_id).first()
    assert ev is not None
    assert ev.after_snapshot.get("status") == PaymentStatus.PARTIALLY_REFUNDED
    assert ev.metadata.get("refund_id") == str(refund.refund_id)


@pytest.mark.django_db
def test_reverse_emits_audit():
    company, branch = _mk_scope()
    actor = _actor()
    intent = _mk_intent(company=company, branch=branch, actor=actor, payment_method="CARD")
    capture_payment_intent_for_scope(
        company=company, branch=branch, actor=actor, payment_id=intent.payment_id
    )
    reverse_captured_payment_intent_for_scope(
        company=company, branch=branch, actor=actor, payment_id=intent.payment_id,
        idempotency_key=f"rev-{uuid.uuid4().hex}", reason="contracargo",
    )
    ev = _audit("PAYMENTS_INTENT_REVERSED", intent.payment_id).first()
    assert ev is not None
    assert ev.after_snapshot.get("status") == PaymentStatus.REFUNDED
