"""Tests de las máquinas de estado explícitas (Unidad #3, incremento #2).

Cubre la tabla `_ALLOWED_TRANSITIONS`/`can_transition_to` de PaymentIntent y
CashSession (nivel modelo) y su enforcement en los servicios (§9).
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model

from apps.kernels.payments.models import CashSession, PaymentIntent
from apps.kernels.payments.services import (
    PaymentsInvalidStateError,
    authorize_payment_intent_for_scope,
    cancel_payment_intent_for_scope,
    capture_payment_intent_for_scope,
    close_cash_session_for_scope,
    create_payment_intent_for_scope,
    open_cash_session_for_scope,
    reopen_cash_session_for_investigation,
)
from apps.modulos.iam.models import OrgUnit

User = get_user_model()
PS = PaymentIntent.Status
CS = CashSession.Status


def _mk_scope():
    s = uuid.uuid4().hex[:6]
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name=f"H{s}")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name=f"C{s}", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name=f"B{s}", parent=company)
    return company, branch


def _actor():
    name = f"actor_{uuid.uuid4().hex[:8]}"
    return User.objects.create_user(username=name, email=f"{name}@test.com", password="x")


def _request(company, branch, user):
    return SimpleNamespace(
        company=company, branch=branch, user=user, META={}, headers={},
        path="/test/payments/", method="POST", request_id=f"req-{uuid.uuid4().hex[:8]}",
    )


def _mk_intent(*, company, branch, actor, amount="100.00", payment_method="CARD"):
    intent, _ = create_payment_intent_for_scope(
        company=company, branch=branch, actor=actor,
        amount=Decimal(amount), currency="NIO", payment_method=payment_method,
        idempotency_key=f"k-{uuid.uuid4().hex}",
    )
    return intent


# --------------------------------------------------------------------------- #
# Nivel modelo: tabla de transiciones
# --------------------------------------------------------------------------- #

def test_intent_transition_table():
    i = PaymentIntent(status=PS.INTENDED)
    assert i.can_transition_to(PS.AUTHORIZED)
    assert i.can_transition_to(PS.CAPTURED)
    assert i.can_transition_to(PS.CANCELLED)
    assert i.can_transition_to(PS.INTENDED)  # mismo estado = idempotente
    assert not i.can_transition_to(PS.REFUNDED)

    i.status = PS.CAPTURED
    assert i.can_transition_to(PS.REFUNDED)
    assert i.can_transition_to(PS.PARTIALLY_REFUNDED)
    assert not i.can_transition_to(PS.AUTHORIZED)
    assert not i.can_transition_to(PS.CANCELLED)

    i.status = PS.REFUNDED  # terminal
    assert not i.can_transition_to(PS.CAPTURED)
    assert not i.can_transition_to(PS.PARTIALLY_REFUNDED)


def test_cash_session_transition_table():
    s = CashSession(status=CS.OPEN)
    assert s.can_transition_to(CS.CLOSED)
    assert s.can_transition_to(CS.COUNT_PENDING)
    assert not s.can_transition_to(CS.REOPENED_FOR_INVESTIGATION)

    s.status = CS.CLOSED
    assert s.can_transition_to(CS.REOPENED_FOR_INVESTIGATION)
    assert not s.can_transition_to(CS.OPEN)

    s.status = CS.REOPENED_FOR_INVESTIGATION
    assert s.can_transition_to(CS.CLOSED)  # re-cierre tras investigación


# --------------------------------------------------------------------------- #
# Enforcement en servicios — transiciones inválidas rechazadas
# --------------------------------------------------------------------------- #

@pytest.mark.django_db
def test_authorize_from_captured_rejected():
    company, branch = _mk_scope()
    actor = _actor()
    intent = _mk_intent(company=company, branch=branch, actor=actor)
    capture_payment_intent_for_scope(company=company, branch=branch, actor=actor, payment_id=intent.payment_id)
    with pytest.raises(PaymentsInvalidStateError):
        authorize_payment_intent_for_scope(
            company=company, branch=branch, actor=actor, payment_id=intent.payment_id
        )


@pytest.mark.django_db
def test_capture_from_cancelled_rejected():
    company, branch = _mk_scope()
    actor = _actor()
    intent = _mk_intent(company=company, branch=branch, actor=actor)
    cancel_payment_intent_for_scope(company=company, branch=branch, actor=actor, payment_id=intent.payment_id)
    with pytest.raises(PaymentsInvalidStateError):
        capture_payment_intent_for_scope(
            company=company, branch=branch, actor=actor, payment_id=intent.payment_id
        )


@pytest.mark.django_db
def test_cancel_from_captured_rejected():
    company, branch = _mk_scope()
    actor = _actor()
    intent = _mk_intent(company=company, branch=branch, actor=actor)
    capture_payment_intent_for_scope(company=company, branch=branch, actor=actor, payment_id=intent.payment_id)
    with pytest.raises(PaymentsInvalidStateError):
        cancel_payment_intent_for_scope(
            company=company, branch=branch, actor=actor, payment_id=intent.payment_id
        )


@pytest.mark.django_db
def test_reopen_open_session_rejected():
    company, branch = _mk_scope()
    actor = _actor()
    s = open_cash_session_for_scope(
        company=company, branch=branch, actor=actor, opening_amount=Decimal("100.00"), register_id="RX"
    )
    req = _request(company, branch, actor)
    with pytest.raises(PaymentsInvalidStateError):
        reopen_cash_session_for_investigation(request=req, actor=actor, session_id=s.id, reason="x")


@pytest.mark.django_db
def test_close_reopen_close_cycle_allowed():
    company, branch = _mk_scope()
    actor = _actor()
    s = open_cash_session_for_scope(
        company=company, branch=branch, actor=actor, opening_amount=Decimal("100.00"), register_id="RY"
    )
    close_cash_session_for_scope(
        company=company, branch=branch, actor=actor, session_id=s.id, counted_amount=Decimal("100.00")
    )
    req = _request(company, branch, actor)
    reopened = reopen_cash_session_for_investigation(
        request=req, actor=actor, session_id=s.id, reason="auditoría"
    )
    assert reopened.status == CS.REOPENED_FOR_INVESTIGATION
    # REOPENED_FOR_INVESTIGATION -> CLOSED debe ser permitido.
    closed2 = close_cash_session_for_scope(
        company=company, branch=branch, actor=actor, session_id=s.id, counted_amount=Decimal("100.00")
    )
    assert closed2.status == CS.CLOSED
