"""Tests de reapertura de periodo fiscal (Unidad #4, endurecimiento).

Cierra el contrato `ACCOUNTING_PERIOD_REOPENED` (antes declarado pero sin
implementar). Cubre: transición CLOSED->OPEN con auditoría #4, idempotencia,
guarda cronológica (no reabrir si hay un periodo posterior cerrado) y SoD
maker-checker (quien cerró no reabre su propio cierre).
"""
from __future__ import annotations

import uuid

import pytest
from django.contrib.auth import get_user_model

from apps.kernels.accounting.models import FiscalPeriod
from apps.kernels.accounting.services import (
    AccountingConflictError,
    close_fiscal_period,
    reopen_fiscal_period,
)
from apps.modulos.audit.models import AuditEvent
from apps.modulos.iam.models import OrgUnit

User = get_user_model()


def _mk_company():
    s = uuid.uuid4().hex[:6]
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name=f"H_{s}")
    return OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name=f"C_{s}", parent=holding)


def _actor():
    name = f"u_{uuid.uuid4().hex[:8]}"
    return User.objects.create_user(username=name, email=f"{name}@test.com", password="x")


def _audit(event_type, subject_id):
    return AuditEvent.objects.filter(event_type=event_type, subject_id=str(subject_id))


@pytest.mark.django_db
def test_reopen_closed_period_opens_and_emits_audit():
    company = _mk_company()
    closer, reopener = _actor(), _actor()
    period = FiscalPeriod.objects.create(company=company, year=2026, month=1, status=FiscalPeriod.Status.OPEN)
    close_fiscal_period(company_id=company.id, year=2026, month=1, actor_user=closer)

    result = reopen_fiscal_period(
        company_id=company.id, year=2026, month=1, reason="reproceso de nómina", actor_user=reopener
    )

    assert result.was_already_open is False
    assert result.status == FiscalPeriod.Status.OPEN
    period.refresh_from_db()
    assert period.status == FiscalPeriod.Status.OPEN
    assert period.reopened_by_id == reopener.id
    assert period.reopen_reason == "reproceso de nómina"
    assert period.reopened_at is not None

    ev = _audit("ACCOUNTING_PERIOD_REOPENED", period.id).first()
    assert ev is not None
    assert ev.subject_type == "FISCAL_PERIOD"
    assert ev.before_snapshot.get("status") == FiscalPeriod.Status.CLOSED
    assert ev.after_snapshot.get("status") == FiscalPeriod.Status.OPEN
    manifest_hash = ev.metadata.get("reopen_manifest_hash")
    assert isinstance(manifest_hash, str) and len(manifest_hash) == 64  # sha256 hex


@pytest.mark.django_db
def test_reopen_open_period_is_idempotent_no_audit():
    company = _mk_company()
    actor = _actor()
    period = FiscalPeriod.objects.create(company=company, year=2026, month=4, status=FiscalPeriod.Status.OPEN)

    result = reopen_fiscal_period(
        company_id=company.id, year=2026, month=4, reason="ya abierto", actor_user=actor
    )

    assert result.was_already_open is True
    assert result.status == FiscalPeriod.Status.OPEN
    assert not _audit("ACCOUNTING_PERIOD_REOPENED", period.id).exists()


@pytest.mark.django_db
def test_reopen_blocked_when_later_period_closed():
    company = _mk_company()
    closer, reopener = _actor(), _actor()
    FiscalPeriod.objects.create(company=company, year=2026, month=1, status=FiscalPeriod.Status.OPEN)
    FiscalPeriod.objects.create(company=company, year=2026, month=2, status=FiscalPeriod.Status.OPEN)
    close_fiscal_period(company_id=company.id, year=2026, month=1, actor_user=closer)
    close_fiscal_period(company_id=company.id, year=2026, month=2, actor_user=closer)

    # Reabrir enero con febrero todavía cerrado -> bloqueado por integridad cronológica.
    with pytest.raises(AccountingConflictError) as exc:
        reopen_fiscal_period(company_id=company.id, year=2026, month=1, reason="x", actor_user=reopener)
    assert "2026-02" in str(exc.value)

    # force salta la guarda cronológica (reopener != closer, así que SoD no aplica).
    result = reopen_fiscal_period(
        company_id=company.id, year=2026, month=1, reason="x", force=True, actor_user=reopener
    )
    assert result.was_already_open is False
    assert result.force_applied is True


@pytest.mark.django_db
def test_reopen_sod_same_closer_blocked_unless_override():
    company = _mk_company()
    actor = _actor()
    FiscalPeriod.objects.create(company=company, year=2026, month=6, status=FiscalPeriod.Status.OPEN)
    close_fiscal_period(company_id=company.id, year=2026, month=6, actor_user=actor)

    # Sin periodo posterior cerrado: la guarda cronológica pasa, pero SoD bloquea al mismo actor.
    with pytest.raises(AccountingConflictError) as exc:
        reopen_fiscal_period(company_id=company.id, year=2026, month=6, reason="x", actor_user=actor)
    assert "SoD" in str(exc.value)

    # allow_same_closer habilita el override.
    result = reopen_fiscal_period(
        company_id=company.id, year=2026, month=6, reason="x", allow_same_closer=True, actor_user=actor
    )
    assert result.was_already_open is False


@pytest.mark.django_db
def test_reopen_requires_reason():
    company = _mk_company()
    FiscalPeriod.objects.create(company=company, year=2026, month=7, status=FiscalPeriod.Status.CLOSED)
    with pytest.raises(ValueError):
        reopen_fiscal_period(company_id=company.id, year=2026, month=7, reason="   ")


@pytest.mark.django_db
def test_reopen_nonexistent_period_raises():
    company = _mk_company()
    with pytest.raises(ValueError):
        reopen_fiscal_period(company_id=company.id, year=2026, month=9, reason="x")


@pytest.mark.django_db
def test_close_reopen_close_cycle():
    company = _mk_company()
    a, b = _actor(), _actor()
    FiscalPeriod.objects.create(company=company, year=2026, month=8, status=FiscalPeriod.Status.OPEN)
    close_fiscal_period(company_id=company.id, year=2026, month=8, actor_user=a)
    reopen_fiscal_period(company_id=company.id, year=2026, month=8, reason="ciclo", actor_user=b)
    # Tras reabrir, se puede volver a cerrar.
    res = close_fiscal_period(company_id=company.id, year=2026, month=8, actor_user=a)
    assert res.status == FiscalPeriod.Status.CLOSED
    assert res.was_already_closed is False


# --------------------------------------------------------------------------- #
# Management command `reopen_fiscal_period`
# --------------------------------------------------------------------------- #

@pytest.mark.django_db
def test_reopen_fiscal_period_management_command():
    import json
    from io import StringIO

    from django.core.management import call_command

    company = _mk_company()
    closer = _actor()
    FiscalPeriod.objects.create(company=company, year=2026, month=3, status=FiscalPeriod.Status.OPEN)
    close_fiscal_period(company_id=company.id, year=2026, month=3, actor_user=closer)

    out = StringIO()
    call_command(
        "reopen_fiscal_period",
        "--company-id", str(company.id), "--year", "2026", "--month", "3",
        "--reason", "reproceso CLI", stdout=out,
    )
    payload = json.loads(out.getvalue().strip())
    assert payload["status"] == FiscalPeriod.Status.OPEN
    assert payload["was_already_open"] is False
    assert payload["reason"] == "reproceso CLI"
    assert payload["company_id"] == company.id
    period = FiscalPeriod.objects.get(company=company, year=2026, month=3)
    assert period.status == FiscalPeriod.Status.OPEN


@pytest.mark.django_db
def test_reopen_fiscal_period_command_wraps_errors():
    from django.core.management import call_command
    from django.core.management.base import CommandError

    company = _mk_company()
    # Periodo inexistente → el servicio lanza ValueError, el comando lo envuelve en CommandError.
    with pytest.raises(CommandError):
        call_command(
            "reopen_fiscal_period",
            "--company-id", str(company.id), "--year", "2099", "--month", "1", "--reason", "x",
        )
