"""Tests para las funciones avanzadas del kernel payments:
- Authorize → Capture flow
- Partial refunds
- Cancel intent
- Arqueo de caja con denominaciones
- Múltiples cajeros por sucursal (register_id)
- GET de movimientos y detalle de sesión
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from apps.kernels.payments.models import (
    CashDenomination,
    CashSession,
    PaymentIntent,
)
from apps.kernels.payments.services import (
    authorize_payment_intent_for_scope,
    cancel_payment_intent_for_scope,
    capture_payment_intent_for_scope,
    create_payment_intent_for_scope,
    open_cash_session_for_scope,
    PaymentsInvalidStateError,
    PaymentsValidationError,
    refund_payment_intent_for_scope,
    submit_denomination_count,
)
from apps.modulos.iam.models import OrgUnit
from apps.modulos.rbac.models import Permission, Role, RoleAssignment, RolePermission
from apps.modulos.iam.models import UserMembership
from rest_framework.test import APIClient

User = get_user_model()


def _mk_scope(suffix=""):
    s = suffix or uuid.uuid4().hex[:6]
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name=f"H{s}")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name=f"C{s}", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name=f"B{s}", parent=company)
    return company, branch


def _actor(suffix=""):
    uid = uuid.uuid4().hex[:8]
    name = f"actor_{suffix}_{uid}" if suffix else f"actor_{uid}"
    return User.objects.create_user(username=name, email=f"{name}@test.com", password="x")


def _mk_intent(*, company, branch, actor, amount="100.00", payment_method="CASH"):
    intent, _ = create_payment_intent_for_scope(
        company=company, branch=branch, actor=actor,
        amount=Decimal(amount), currency="NIO",
        payment_method=payment_method,
        idempotency_key=f"k-{uuid.uuid4().hex}",
    )
    return intent


def _client_with_perms(*, company, branch, perms):
    u = User.objects.create_user(username=f"u_{uuid.uuid4().hex[:8]}", password="x")
    UserMembership.objects.create(user=u, org_unit=company, is_active=True)
    UserMembership.objects.create(user=u, org_unit=branch, is_active=True)
    role = Role.objects.create(name=f"r_{uuid.uuid4().hex[:8]}", is_active=True)
    for p in perms:
        perm, _ = Permission.objects.get_or_create(code=p, defaults={"description": p, "is_active": True})
        RolePermission.objects.get_or_create(role=role, permission=perm)
    RoleAssignment.objects.create(user=u, role=role, org_unit=company, is_active=True)
    RoleAssignment.objects.create(user=u, role=role, org_unit=branch, is_active=True)
    c = APIClient()
    login = c.post("/api/auth/login/", {"username": u.username, "password": "x"}, format="json")
    assert login.status_code == 200
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
    c.defaults["HTTP_X_COMPANY_ID"] = str(company.id)
    c.defaults["HTTP_X_BRANCH_ID"] = str(branch.id)
    return c


# ---------------------------------------------------------------------------
# Authorize → Capture flow
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_authorize_then_capture_flow():
    company, branch = _mk_scope()
    actor = _actor()
    intent = _mk_intent(company=company, branch=branch, actor=actor, payment_method="CARD")

    assert intent.status == PaymentIntent.Status.INTENDED
    assert intent.amount_authorized is None

    # Authorize
    authorized = authorize_payment_intent_for_scope(
        company=company, branch=branch, actor=actor,
        payment_id=intent.payment_id,
        amount_authorized=Decimal("100.00"),
        provider_txn_id="AUTH-001",
    )
    assert authorized.status == PaymentIntent.Status.AUTHORIZED
    assert authorized.amount_authorized == Decimal("100.00")
    assert authorized.authorized_at is not None

    # Capture
    captured = capture_payment_intent_for_scope(
        company=company, branch=branch, actor=actor,
        payment_id=intent.payment_id,
    )
    assert captured.status == PaymentIntent.Status.CAPTURED
    assert captured.captured_at is not None


@pytest.mark.django_db
def test_authorize_idempotent():
    company, branch = _mk_scope()
    actor = _actor()
    intent = _mk_intent(company=company, branch=branch, actor=actor, payment_method="TRANSFER")

    a1 = authorize_payment_intent_for_scope(company=company, branch=branch, actor=actor, payment_id=intent.payment_id)
    a2 = authorize_payment_intent_for_scope(company=company, branch=branch, actor=actor, payment_id=intent.payment_id)
    assert a1.id == a2.id
    assert a1.status == PaymentIntent.Status.AUTHORIZED


@pytest.mark.django_db
def test_authorize_from_captured_raises():
    company, branch = _mk_scope()
    actor = _actor()
    intent = _mk_intent(company=company, branch=branch, actor=actor)
    capture_payment_intent_for_scope(company=company, branch=branch, actor=actor, payment_id=intent.payment_id)

    with pytest.raises(PaymentsInvalidStateError):
        authorize_payment_intent_for_scope(company=company, branch=branch, actor=actor, payment_id=intent.payment_id)


# ---------------------------------------------------------------------------
# Cancel
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_cancel_intended_intent():
    company, branch = _mk_scope()
    actor = _actor()
    intent = _mk_intent(company=company, branch=branch, actor=actor)

    cancelled = cancel_payment_intent_for_scope(
        company=company, branch=branch, actor=actor,
        payment_id=intent.payment_id, reason="Cliente no quiso",
    )
    assert cancelled.status == PaymentIntent.Status.CANCELLED
    assert cancelled.cancellation_reason == "Cliente no quiso"


@pytest.mark.django_db
def test_cancel_captured_raises():
    company, branch = _mk_scope()
    actor = _actor()
    intent = _mk_intent(company=company, branch=branch, actor=actor)
    capture_payment_intent_for_scope(company=company, branch=branch, actor=actor, payment_id=intent.payment_id)

    with pytest.raises(PaymentsInvalidStateError, match="capturado"):
        cancel_payment_intent_for_scope(company=company, branch=branch, actor=actor, payment_id=intent.payment_id)


# ---------------------------------------------------------------------------
# Refund — parcial y total
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_partial_refund():
    company, branch = _mk_scope()
    actor = _actor()
    intent = _mk_intent(company=company, branch=branch, actor=actor, amount="500.00")
    captured = capture_payment_intent_for_scope(
        company=company, branch=branch, actor=actor, payment_id=intent.payment_id
    )
    captured.amount_captured = Decimal("500.00")
    captured.save(update_fields=["amount_captured"])

    refund = refund_payment_intent_for_scope(
        company=company, branch=branch, actor=actor,
        payment_id=intent.payment_id,
        amount=Decimal("200.00"),
        idempotency_key="ref-partial-1",
        reason="Devolucion parcial",
    )
    assert refund.amount == Decimal("200.00")
    intent.refresh_from_db()
    assert intent.status == PaymentIntent.Status.PARTIALLY_REFUNDED
    assert intent.amount_refunded == Decimal("200.00")


@pytest.mark.django_db
def test_full_refund():
    company, branch = _mk_scope()
    actor = _actor()
    intent = _mk_intent(company=company, branch=branch, actor=actor, amount="300.00")
    captured = capture_payment_intent_for_scope(
        company=company, branch=branch, actor=actor, payment_id=intent.payment_id
    )
    captured.amount_captured = Decimal("300.00")
    captured.save(update_fields=["amount_captured"])

    refund_payment_intent_for_scope(
        company=company, branch=branch, actor=actor,
        payment_id=intent.payment_id, amount=Decimal("300.00"),
        idempotency_key="ref-full-1",
    )
    intent.refresh_from_db()
    assert intent.status == PaymentIntent.Status.REFUNDED


@pytest.mark.django_db
def test_refund_exceeds_captured_raises():
    company, branch = _mk_scope()
    actor = _actor()
    intent = _mk_intent(company=company, branch=branch, actor=actor, amount="100.00")
    captured = capture_payment_intent_for_scope(
        company=company, branch=branch, actor=actor, payment_id=intent.payment_id
    )
    captured.amount_captured = Decimal("100.00")
    captured.save(update_fields=["amount_captured"])

    with pytest.raises(PaymentsValidationError, match="refundable"):
        refund_payment_intent_for_scope(
            company=company, branch=branch, actor=actor,
            payment_id=intent.payment_id, amount=Decimal("150.00"),
        )


@pytest.mark.django_db
def test_refund_idempotent():
    company, branch = _mk_scope()
    actor = _actor()
    intent = _mk_intent(company=company, branch=branch, actor=actor, amount="200.00")
    captured = capture_payment_intent_for_scope(
        company=company, branch=branch, actor=actor, payment_id=intent.payment_id
    )
    captured.amount_captured = Decimal("200.00")
    captured.save(update_fields=["amount_captured"])

    r1 = refund_payment_intent_for_scope(
        company=company, branch=branch, actor=actor,
        payment_id=intent.payment_id, amount=Decimal("50.00"), idempotency_key="ref-idem",
    )
    r2 = refund_payment_intent_for_scope(
        company=company, branch=branch, actor=actor,
        payment_id=intent.payment_id, amount=Decimal("50.00"), idempotency_key="ref-idem",
    )
    assert r1.id == r2.id


# ---------------------------------------------------------------------------
# Múltiples cajeros — register_id
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_multiple_cashiers_same_branch():
    company, branch = _mk_scope()
    actor1 = _actor("c1")
    actor2 = _actor("c2")

    # Dos sesiones en la misma sucursal, cada una con su register_id
    s1 = open_cash_session_for_scope(
        company=company, branch=branch, actor=actor1,
        opening_amount=Decimal("1000.00"), register_id="CAJA-1"
    )
    s2 = open_cash_session_for_scope(
        company=company, branch=branch, actor=actor2,
        opening_amount=Decimal("500.00"), register_id="CAJA-2"
    )

    assert s1.id != s2.id
    assert s1.status == CashSession.Status.OPEN
    assert s2.status == CashSession.Status.OPEN


# ---------------------------------------------------------------------------
# Arqueo de caja con denominaciones
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_denomination_count_arqueo():
    company, branch = _mk_scope()
    actor = _actor()

    from unittest.mock import MagicMock
    request = MagicMock()
    request.company = company
    request.branch = branch
    request.user = actor

    session = open_cash_session_for_scope(
        company=company, branch=branch, actor=actor, opening_amount=Decimal("500.00")
    )

    denominations = [
        {"denomination_value": "1000", "denomination_type": "BILL", "quantity": 1},
        {"denomination_value": "500", "denomination_type": "BILL", "quantity": 2},
        {"denomination_value": "100", "denomination_type": "BILL", "quantity": 3},
        {"denomination_value": "10", "denomination_type": "COIN", "quantity": 5},
        {"denomination_value": "1", "denomination_type": "COIN", "quantity": 10},
    ]

    session_updated, denoms, total = submit_denomination_count(
        request=request, actor=actor,
        session_id=session.id,
        denominations=denominations,
    )

    # 1×1000 + 2×500 + 3×100 + 5×10 + 10×1 = 1000+1000+300+50+10 = 2360
    assert total == Decimal("2360.00")
    assert session_updated.counted_amount == Decimal("2360.00")
    assert session_updated.status == CashSession.Status.COUNT_PENDING
    assert CashDenomination.objects.filter(session=session).count() == 5


@pytest.mark.django_db
def test_denomination_replaces_previous():
    company, branch = _mk_scope()
    actor = _actor()

    from unittest.mock import MagicMock
    request = MagicMock()
    request.company = company
    request.branch = branch

    session = open_cash_session_for_scope(
        company=company, branch=branch, actor=actor, opening_amount=Decimal("0.00")
    )

    # Primer arqueo
    submit_denomination_count(
        request=request, actor=actor, session_id=session.id,
        denominations=[{"denomination_value": "100", "denomination_type": "BILL", "quantity": 5}],
    )
    assert CashDenomination.objects.filter(session=session).count() == 1

    # Segundo arqueo — reemplaza el anterior
    submit_denomination_count(
        request=request, actor=actor, session_id=session.id,
        denominations=[
            {"denomination_value": "200", "denomination_type": "BILL", "quantity": 3},
            {"denomination_value": "50", "denomination_type": "BILL", "quantity": 2},
        ],
    )
    assert CashDenomination.objects.filter(session=session).count() == 2
    assert not CashDenomination.objects.filter(session=session, denomination_value="100").exists()


# ---------------------------------------------------------------------------
# CashMovement linked to PaymentIntent
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_cash_movement_linked_to_payment_intent_api():
    company, branch = _mk_scope()
    perms = [
        "payments.cash_session.open", "payments.cash_session.read",
        "payments.cash_movement.create", "payments.intent.create",
    ]
    c = _client_with_perms(company=company, branch=branch, perms=perms)

    # Abrir sesión
    r = c.post("/api/payments/cash-sessions/open/", {"opening_amount": "1000.00"}, format="json")
    assert r.status_code == 201
    session_id = r.data["id"]

    # Crear intent
    r = c.post("/api/payments/intents/", {
        "amount": "250.00", "payment_method": "CASH",
        "idempotency_key": f"pi-{uuid.uuid4().hex}",
    }, format="json")
    assert r.status_code == 201
    payment_id = r.data["payment_id"]

    # Movimiento vinculado al intent
    r = c.post(f"/api/payments/cash-sessions/{session_id}/movements/", {
        "movement_type": "INCOME",
        "amount": "250.00",
        "reference": payment_id,
        "idempotency_key": f"mov-{uuid.uuid4().hex}",
    }, format="json")
    assert r.status_code == 201

    # GET movimientos
    r = c.get(f"/api/payments/cash-sessions/{session_id}/movements/")
    assert r.status_code == 200
    assert r.data["count"] == 1
    assert r.data["results"][0]["amount"] == "250.00"


# ---------------------------------------------------------------------------
# Detail endpoints
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_payment_intent_detail_endpoint():
    company, branch = _mk_scope()
    perms = ["payments.intent.read", "payments.intent.create"]
    c = _client_with_perms(company=company, branch=branch, perms=perms)

    r = c.post("/api/payments/intents/", {
        "amount": "750.00", "payment_method": "TRANSFER",
        "idempotency_key": f"pi-det-{uuid.uuid4().hex}",
    }, format="json")
    assert r.status_code == 201
    payment_id = r.data["payment_id"]

    r = c.get(f"/api/payments/intents/{payment_id}/")
    assert r.status_code == 200
    assert r.data["amount"] == "750.00"
    assert r.data["status"] == "INTENDED"
    assert "outstanding_amount" in r.data
    assert "refundable_amount" in r.data


@pytest.mark.django_db
def test_cash_session_detail_endpoint():
    company, branch = _mk_scope()
    perms = ["payments.cash_session.open", "payments.cash_session.read"]
    c = _client_with_perms(company=company, branch=branch, perms=perms)

    r = c.post("/api/payments/cash-sessions/open/", {"opening_amount": "500.00"}, format="json")
    assert r.status_code == 201
    session_id = r.data["id"]

    r = c.get(f"/api/payments/cash-sessions/{session_id}/")
    assert r.status_code == 200
    assert r.data["opening_amount"] == "500.00"
    assert r.data["status"] == "OPEN"
    assert "movements" in r.data
