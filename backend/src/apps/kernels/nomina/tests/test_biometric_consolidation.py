"""Tests del cruce a 3 fuentes: biométrico × lista del mandador × reporte del capataz.

Reglas (B2):
  - Sin chequeos matched ese día → la consolidación se comporta EXACTAMENTE igual
    que antes (el aparato está en prueba; su ausencia no castiga a nadie).
  - Máquina dice ENTRÓ + lista dice AUSENTE → CONFLICTO duro (señal de fraude).
  - Presente en campo sin chequeo (aparato operando) → ADVERTENCIA, no conflicto.
  - Chequeó pero no está en ninguna lista/reporte → ADVERTENCIA con día 0.00
    (no se paga solo; lo resuelve nómina).
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.kernels.nomina.models import (
    BiometricCheck,
    BiometricCheckDirection,
    BiometricDevice,
    FieldAttendanceConsolidationStatus,
    FieldWorkerEventType,
    PayrollPeriod,
    PeriodType,
)
from apps.kernels.nomina.services import (
    consolidate_field_attendance,
    create_field_crew,
    open_field_work_day,
    submit_crew_report,
    submit_rollcall,
)
from apps.modulos.hr.models import Employee
from apps.modulos.iam.models import OrgUnit

User = get_user_model()

WORK_DATE = date(2026, 6, 5)


def _mk_scope():
    tag = uuid.uuid4().hex[:6]
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name=f"H_{tag}")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name=f"C_{tag}", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name=f"B_{tag}", parent=company)
    return company, branch


def _actor():
    username = f"bio_{uuid.uuid4().hex[:8]}"
    return User.objects.create_user(username=username, email=f"{username}@test.local", password="x")


def _request(actor, *, company=None, branch=None):
    return SimpleNamespace(
        user=actor, META={}, company=company, branch=branch, _request=None,
        ctx=None, request_id=f"req_{uuid.uuid4().hex[:8]}", path="", method="POST",
    )


def _employee(company, first_name="Trabajador"):
    return Employee.objects.create(
        company=company, employee_code=f"E-{uuid.uuid4().hex[:6]}",
        first_name=first_name, last_name="Campo", is_active=True,
    )


def _open_day(company, branch, actor):
    period = PayrollPeriod.objects.create(
        company=company, year=2026, month=6, period_type=PeriodType.CATORCENA,
        start_date=date(2026, 6, 1), end_date=date(2026, 6, 14), working_days=14,
    )
    return open_field_work_day(
        request=_request(actor, company=company, branch=branch),
        actor=actor, company=company, branch=branch,
        payroll_period=period, work_date=WORK_DATE,
    )


def _bio_check(company, employee, *, hour=6, minute=0, direction=BiometricCheckDirection.IN):
    device, _ = BiometricDevice.objects.get_or_create(company=company, name="Portón hacienda")
    when = timezone.make_aware(datetime(WORK_DATE.year, WORK_DATE.month, WORK_DATE.day, hour, minute))
    return BiometricCheck.objects.create(
        device=device, company=company, employee=employee,
        external_code=employee.employee_code, direction=direction,
        checked_at=when, work_date=WORK_DATE, dedupe_key=uuid.uuid4().hex,
    )


def _setup_present_worker(company, branch, actor, work_day, worker):
    """Lista PRESENT + reporte de cuadrilla PRESENT (las fuentes ② y ③ de acuerdo)."""
    submit_rollcall(
        request=_request(actor, company=company, branch=branch), actor=actor,
        work_day=work_day, lines=[{"employee": worker, "status": "PRESENT"}],
    )
    crew = create_field_crew(
        request=_request(actor, company=company, branch=branch), actor=actor,
        work_day=work_day, name="Cuadrilla 1", supervisor_employee=_employee(company, "Capataz"),
    )
    submit_crew_report(
        request=_request(actor, company=company, branch=branch), actor=actor,
        crew=crew, lines=[{"employee": worker, "event_type": FieldWorkerEventType.PRESENT}],
    )


@pytest.mark.django_db
def test_without_biometric_data_consolidation_is_unchanged():
    company, branch = _mk_scope()
    actor = _actor()
    worker = _employee(company, "Juan")
    work_day = _open_day(company, branch, actor)
    _setup_present_worker(company, branch, actor, work_day, worker)

    [cons] = consolidate_field_attendance(
        request=_request(actor, company=company, branch=branch), actor=actor, work_day=work_day
    )
    assert cons.status == FieldAttendanceConsolidationStatus.OK
    assert cons.day_value == Decimal("1.00")
    assert not any(code.startswith("BIOMETRIC") or code == "MISSING_BIOMETRIC_CHECK" for code in cons.conflict_codes)
    assert cons.source_summary["biometric_in_play"] is False


@pytest.mark.django_db
def test_three_sources_agree_is_ok_with_evidence():
    company, branch = _mk_scope()
    actor = _actor()
    worker = _employee(company, "Juan")
    work_day = _open_day(company, branch, actor)
    _setup_present_worker(company, branch, actor, work_day, worker)
    _bio_check(company, worker, hour=6)
    _bio_check(company, worker, hour=16, direction=BiometricCheckDirection.OUT)

    [cons] = consolidate_field_attendance(
        request=_request(actor, company=company, branch=branch), actor=actor, work_day=work_day
    )
    assert cons.status == FieldAttendanceConsolidationStatus.OK
    assert cons.day_value == Decimal("1.00")
    assert cons.conflict_codes == []
    assert cons.source_summary["biometric_in_play"] is True
    assert len(cons.source_summary["biometric_check_ids"]) == 2
    assert cons.source_summary["biometric_first_check"] is not None


@pytest.mark.django_db
def test_biometric_present_but_rollcall_absent_is_conflict():
    company, branch = _mk_scope()
    actor = _actor()
    worker = _employee(company, "Juan")
    work_day = _open_day(company, branch, actor)
    submit_rollcall(
        request=_request(actor, company=company, branch=branch), actor=actor,
        work_day=work_day, lines=[{"employee": worker, "status": "ABSENT"}],
    )
    _bio_check(company, worker, hour=6)

    [cons] = consolidate_field_attendance(
        request=_request(actor, company=company, branch=branch), actor=actor, work_day=work_day
    )
    assert cons.status == FieldAttendanceConsolidationStatus.CONFLICT
    assert "BIOMETRIC_PRESENT_ROLLCALL_ABSENT" in cons.conflict_codes


@pytest.mark.django_db
def test_present_in_field_without_check_is_warning_when_device_operated():
    company, branch = _mk_scope()
    actor = _actor()
    worker = _employee(company, "Juan")  # presente en campo, SIN chequeo
    other = _employee(company, "Ana")  # ella sí chequeó → el aparato operó ese día
    work_day = _open_day(company, branch, actor)
    _setup_present_worker(company, branch, actor, work_day, worker)
    _bio_check(company, other, hour=6)

    consolidations = consolidate_field_attendance(
        request=_request(actor, company=company, branch=branch), actor=actor, work_day=work_day
    )
    by_emp = {c.employee_id: c for c in consolidations}

    cons = by_emp[worker.id]
    assert cons.status == FieldAttendanceConsolidationStatus.WARNING
    assert "MISSING_BIOMETRIC_CHECK" in cons.conflict_codes
    assert cons.day_value == Decimal("1.00")  # la lista del mandador sigue validando el día


@pytest.mark.django_db
def test_biometric_only_not_listed_is_warning_with_zero_day():
    company, branch = _mk_scope()
    actor = _actor()
    listed = _employee(company, "Juan")
    ghost = _employee(company, "Pedro")  # chequeó en el portón pero no está en listas
    work_day = _open_day(company, branch, actor)
    _setup_present_worker(company, branch, actor, work_day, listed)
    _bio_check(company, listed, hour=6)
    _bio_check(company, ghost, hour=6, minute=10)

    consolidations = consolidate_field_attendance(
        request=_request(actor, company=company, branch=branch), actor=actor, work_day=work_day
    )
    by_emp = {c.employee_id: c for c in consolidations}

    assert by_emp[listed.id].status == FieldAttendanceConsolidationStatus.OK

    ghost_cons = by_emp[ghost.id]
    assert ghost_cons.status == FieldAttendanceConsolidationStatus.WARNING
    assert "BIOMETRIC_ONLY_NOT_LISTED" in ghost_cons.conflict_codes
    assert ghost_cons.day_value == Decimal("0.00")  # no se paga solo: lo resuelve nómina
