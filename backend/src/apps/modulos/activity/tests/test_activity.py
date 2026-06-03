"""Tests de la capa de Actividad/Tiempo (app activity)."""
from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.modulos.activity.models import ActivityEvent, DeviceRegistry, UserSession, WorkSession
from apps.modulos.activity.services import (
    WorkSessionAlreadyOpenError,
    clock_in,
    clock_out,
    end_user_session,
    record_activity,
    register_or_touch_device,
    revoke_device,
    start_user_session,
    touch_user_session,
)
from apps.modulos.iam.models import OrgUnit

User = get_user_model()


def _mk_user(prefix="act"):
    username = f"{prefix}_{uuid.uuid4().hex[:8]}"
    return User.objects.create_user(username=username, email=f"{username}@test.local", password="pass12345")


def _mk_company():
    s = uuid.uuid4().hex[:6]
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name=f"H_{s}")
    return OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name=f"C_{s}", parent=holding)


# --- DeviceRegistry ---------------------------------------------------------

@pytest.mark.django_db
def test_register_device_creates_then_touches():
    user = _mk_user()
    t0 = timezone.now()
    d1 = register_or_touch_device(user=user, fingerprint="fp-1", label="Laptop", platform="WEB", now=t0)
    assert d1.is_active is True
    assert d1.first_seen_at == t0

    t1 = t0 + timedelta(minutes=5)
    d2 = register_or_touch_device(user=user, fingerprint="fp-1", platform="WEB", now=t1)
    assert d2.id == d1.id  # mismo dispositivo
    assert d2.last_seen_at == t1
    assert DeviceRegistry.objects.filter(user=user).count() == 1


@pytest.mark.django_db
def test_revoke_device_and_touch_does_not_unrevoke():
    user = _mk_user()
    d = register_or_touch_device(user=user, fingerprint="fp-1")
    revoke_device(device=d)
    assert d.is_active is False
    again = register_or_touch_device(user=user, fingerprint="fp-1")
    assert again.revoked_at is not None  # tocar no des-revoca


@pytest.mark.django_db
def test_device_unique_per_user_fingerprint():
    user = _mk_user()
    DeviceRegistry.objects.create(user=user, fingerprint="fp-x")
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            DeviceRegistry.objects.create(user=user, fingerprint="fp-x")


# --- UserSession ------------------------------------------------------------

@pytest.mark.django_db
def test_user_session_lifecycle_and_duration():
    user = _mk_user()
    t0 = timezone.now()
    s = start_user_session(user=user, ip="10.0.0.1", user_agent="UA", now=t0)
    assert s.is_active is True
    assert s.duration_seconds >= 0

    touch_user_session(session=s, now=t0 + timedelta(seconds=30))
    assert s.last_seen_at == t0 + timedelta(seconds=30)

    end = t0 + timedelta(minutes=10)
    end_user_session(session=s, reason=UserSession.EndReason.LOGOUT, now=end)
    assert s.is_active is False
    assert s.duration_seconds == 600
    # idempotente
    end_user_session(session=s, reason=UserSession.EndReason.EXPIRED, now=end + timedelta(minutes=1))
    assert s.end_reason == UserSession.EndReason.LOGOUT


# --- ActivityEvent ----------------------------------------------------------

@pytest.mark.django_db
def test_record_activity_persists_and_truncates():
    user = _mk_user()
    ev = record_activity(
        user=user, route="x" * 400, method="GET", status_code=200, duration_ms=42, request_id="r" * 100
    )
    assert ev.pk is not None
    assert len(ev.route) == 255
    assert len(ev.request_id) == 64
    assert ev.duration_ms == 42
    assert ActivityEvent.objects.filter(user=user).count() == 1


# --- WorkSession ------------------------------------------------------------

@pytest.mark.django_db
def test_clock_in_out_computes_hours():
    user = _mk_user()
    company = _mk_company()
    t0 = timezone.now()
    ws = clock_in(user=user, company=company, source=WorkSession.Source.WEB, now=t0)
    assert ws.is_open is True
    assert ws.hours_worked == Decimal("0.00")

    clock_out(work_session=ws, now=t0 + timedelta(hours=8, minutes=30))
    assert ws.is_open is False
    assert ws.hours_worked == Decimal("8.50")
    # clock_out idempotente
    clock_out(work_session=ws, now=t0 + timedelta(hours=10))
    assert ws.hours_worked == Decimal("8.50")


@pytest.mark.django_db
def test_clock_in_twice_raises():
    user = _mk_user()
    company = _mk_company()
    clock_in(user=user, company=company)
    with pytest.raises(WorkSessionAlreadyOpenError):
        clock_in(user=user, company=company)


@pytest.mark.django_db
def test_clock_in_again_after_clock_out_is_allowed():
    user = _mk_user()
    company = _mk_company()
    ws = clock_in(user=user, company=company)
    clock_out(work_session=ws)
    ws2 = clock_in(user=user, company=company)
    assert ws2.is_open is True
    assert WorkSession.objects.filter(user=user, company=company).count() == 2
