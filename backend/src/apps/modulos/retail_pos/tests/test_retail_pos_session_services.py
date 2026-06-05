"""
Tests a nivel de servicio del módulo retail_pos — backbone de sesión y ticket.

Complementa los tests de API existentes (test_retail_pos_api.py) con cobertura
directa del ciclo de vida: open/close de PosSession y apertura de PosTicket.
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model

from apps.modulos.estacion_servicios.models import FuelShift
from apps.modulos.iam.models import OrgUnit
from apps.modulos.retail_pos.models import (
    PosSession,
    PosSessionStatus,
    PosTicket,
    PosTicketStatus,
)
from apps.modulos.retail_pos.services import (
    close_pos_session,
    get_current_pos_session,
    open_pos_session,
    open_ticket,
)

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
    # Cubre lo que leen retail_pos + payments(open_cash_session) + audit(write_event).
    return SimpleNamespace(
        company=company, branch=branch, user=actor,
        request_id="", headers={}, META={}, path="", method="POST",
        _request=None, ctx=None,
    )


def _shift(company, branch, actor):
    return FuelShift.objects.create(company=company, branch=branch, opened_by=actor)


# ---------------------------------------------------------------------------
# open_pos_session
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_open_pos_session_creates_session_and_cash_session():
    company, branch = _mk_scope()
    actor = _actor()
    req = _request(company, branch, actor)

    result = open_pos_session(request=req, actor_user=actor, opening_amount=Decimal("1000.00"))

    assert result.duplicate is False
    assert result.session.status == PosSessionStatus.OPEN
    assert result.session.cash_session_id is not None
    assert result.session.opening_amount == Decimal("1000.00")
    assert get_current_pos_session(company=company, branch=branch).id == result.session.id


@pytest.mark.django_db
def test_open_pos_session_duplicate_returns_existing():
    company, branch = _mk_scope()
    actor = _actor()
    req = _request(company, branch, actor)

    r1 = open_pos_session(request=req, actor_user=actor)
    r2 = open_pos_session(request=req, actor_user=actor)

    assert r2.duplicate is True
    assert r1.session.id == r2.session.id
    assert PosSession.objects.filter(company=company, branch=branch, status=PosSessionStatus.OPEN).count() == 1


# ---------------------------------------------------------------------------
# close_pos_session
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_close_pos_session_sets_difference():
    company, branch = _mk_scope()
    actor = _actor()
    req = _request(company, branch, actor)
    session = open_pos_session(request=req, actor_user=actor, opening_amount=Decimal("1000.00")).session

    closed = close_pos_session(
        request=req, actor_user=actor, session=session, counted_amount=Decimal("1250.00"),
    )

    assert closed.status == PosSessionStatus.CLOSED
    assert closed.counted_amount == Decimal("1250.00")
    assert closed.difference_amount == Decimal("250.00")
    assert closed.closed_at is not None


@pytest.mark.django_db
def test_close_pos_session_idempotent_when_closed():
    company, branch = _mk_scope()
    actor = _actor()
    req = _request(company, branch, actor)
    session = open_pos_session(request=req, actor_user=actor).session
    close_pos_session(request=req, actor_user=actor, session=session, counted_amount=Decimal("0.00"))

    # Volver a cerrar la misma sesión retorna sin error
    again = close_pos_session(request=req, actor_user=actor, session=session, counted_amount=Decimal("0.00"))
    assert again.status == PosSessionStatus.CLOSED


@pytest.mark.django_db
def test_open_pos_session_after_close_is_new_session():
    company, branch = _mk_scope()
    actor = _actor()
    req = _request(company, branch, actor)
    s1 = open_pos_session(request=req, actor_user=actor).session
    close_pos_session(request=req, actor_user=actor, session=s1, counted_amount=Decimal("0.00"))

    s2 = open_pos_session(request=req, actor_user=actor)
    assert s2.duplicate is False
    assert s2.session.id != s1.id


# ---------------------------------------------------------------------------
# open_ticket
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_open_ticket_happy_path():
    company, branch = _mk_scope()
    actor = _actor()
    req = _request(company, branch, actor)
    session = open_pos_session(request=req, actor_user=actor).session
    shift = _shift(company, branch, actor)

    result = open_ticket(
        request=req, actor_user=actor, session=session, shift_id=shift.id,
        sale_type="PUBLIC", payment_method="CASH",
    )

    assert result.duplicate is False
    assert result.ticket.status == PosTicketStatus.CART_OPEN
    assert result.ticket.correlation_id  # se asignó correlation
    assert result.ticket.session_id == session.id


@pytest.mark.django_db
def test_open_ticket_idempotent():
    company, branch = _mk_scope()
    actor = _actor()
    req = _request(company, branch, actor)
    session = open_pos_session(request=req, actor_user=actor).session
    shift = _shift(company, branch, actor)

    r1 = open_ticket(
        request=req, actor_user=actor, session=session, shift_id=shift.id,
        sale_type="PUBLIC", payment_method="CASH", idempotency_key="pos-tk-1",
    )
    r2 = open_ticket(
        request=req, actor_user=actor, session=session, shift_id=shift.id,
        sale_type="PUBLIC", payment_method="CASH", idempotency_key="pos-tk-1",
    )
    assert r2.duplicate is True
    assert r1.ticket.id == r2.ticket.id
    assert PosTicket.objects.filter(company=company, idempotency_key="pos-tk-1").count() == 1


@pytest.mark.django_db
def test_open_ticket_on_closed_session_raises():
    company, branch = _mk_scope()
    actor = _actor()
    req = _request(company, branch, actor)
    session = open_pos_session(request=req, actor_user=actor).session
    shift = _shift(company, branch, actor)
    close_pos_session(request=req, actor_user=actor, session=session, counted_amount=Decimal("0.00"))

    with pytest.raises(ValueError, match="cerrada"):
        open_ticket(
            request=req, actor_user=actor, session=session, shift_id=shift.id,
            sale_type="PUBLIC", payment_method="CASH",
        )


@pytest.mark.django_db
def test_open_ticket_invalid_shift_raises():
    company, branch = _mk_scope()
    actor = _actor()
    req = _request(company, branch, actor)
    session = open_pos_session(request=req, actor_user=actor).session

    with pytest.raises(ValueError, match="Shift"):
        open_ticket(
            request=req, actor_user=actor, session=session, shift_id=999999,
            sale_type="PUBLIC", payment_method="CASH",
        )
