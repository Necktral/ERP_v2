"""Tests de auditoría del ciclo de caja y detección de diferencia (Unidad #3)."""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from apps.kernels.payments.services import (
    close_cash_session_for_scope,
    open_cash_session_for_scope,
)
from apps.modulos.audit.models import AuditEvent
from apps.modulos.iam.models import OrgUnit
from apps.modulos.integration.models import OutboxEvent

User = get_user_model()


def _mk_scope():
    s = uuid.uuid4().hex[:6]
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name=f"H{s}")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name=f"C{s}", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name=f"B{s}", parent=company)
    return company, branch


def _actor():
    name = f"actor_{uuid.uuid4().hex[:8]}"
    return User.objects.create_user(username=name, email=f"{name}@test.com", password="x")


def _audit(event_type, subject_id):
    return AuditEvent.objects.filter(event_type=event_type, subject_id=str(subject_id))


@pytest.mark.django_db
def test_open_and_close_balanced_emits_audit_no_difference():
    company, branch = _mk_scope()
    actor = _actor()
    s = open_cash_session_for_scope(
        company=company, branch=branch, actor=actor, opening_amount=Decimal("100.00"), register_id="R1"
    )
    assert _audit("PAYMENTS_CASH_SESSION_OPENED", s.id).exists()

    closed = close_cash_session_for_scope(
        company=company, branch=branch, actor=actor, session_id=s.id, counted_amount=Decimal("100.00")
    )
    assert closed.difference_amount == Decimal("0.00")
    assert _audit("PAYMENTS_CASH_SESSION_CLOSED", s.id).exists()
    # Caja cuadrada: sin evento de diferencia.
    assert not _audit("PAYMENTS_CASH_DIFFERENCE_DETECTED", s.id).exists()
    assert not OutboxEvent.objects.filter(source_module="PAYMENTS", event_type="CashDifferenceDetected").exists()


@pytest.mark.django_db
def test_close_with_shortage_detects_difference_and_audits():
    company, branch = _mk_scope()
    actor = _actor()
    s = open_cash_session_for_scope(
        company=company, branch=branch, actor=actor, opening_amount=Decimal("100.00"), register_id="R2"
    )
    # Contado 90 vs esperado 100 -> faltante de 10.
    closed = close_cash_session_for_scope(
        company=company, branch=branch, actor=actor, session_id=s.id, counted_amount=Decimal("90.00")
    )
    assert closed.difference_amount == Decimal("-10.00")
    assert _audit("PAYMENTS_CASH_DIFFERENCE_DETECTED", s.id).exists()

    ev = (
        OutboxEvent.objects.filter(source_module="PAYMENTS", event_type="CashDifferenceDetected")
        .order_by("-id")
        .first()
    )
    assert ev is not None
    data = ev.payload.get("data", {})
    assert data.get("kind") == "SHORT"
    assert data.get("difference_amount") == "-10.00"


@pytest.mark.django_db
def test_close_with_overage_is_over():
    company, branch = _mk_scope()
    actor = _actor()
    s = open_cash_session_for_scope(
        company=company, branch=branch, actor=actor, opening_amount=Decimal("100.00"), register_id="R3"
    )
    closed = close_cash_session_for_scope(
        company=company, branch=branch, actor=actor, session_id=s.id, counted_amount=Decimal("115.00")
    )
    assert closed.difference_amount == Decimal("15.00")
    ev = (
        OutboxEvent.objects.filter(source_module="PAYMENTS", event_type="CashDifferenceDetected")
        .order_by("-id")
        .first()
    )
    assert ev is not None and ev.payload["data"]["kind"] == "OVER"
