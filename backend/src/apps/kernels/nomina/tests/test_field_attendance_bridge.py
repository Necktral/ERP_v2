"""Tests del puente asistencia de campo → planilla (apply → PayrollEntry).

La asistencia APROBADA alimenta `PayrollEntry.days_worked/days_subsidy/sunday_worked_days`
(cierra el hueco de los días tipeados a mano) y bloquea las consolidaciones aplicadas.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model

from apps.kernels.nomina.models import (
    FieldAttendanceConsolidation,
    FieldAttendanceConsolidationStatus,
    FieldWorkerEventType,
    PayrollEntry,
    PayrollPeriod,
    PayrollSheet,
    PeriodType,
)
from apps.kernels.nomina.services import (
    FieldAttendanceError,
    aggregate_attendance_for_employee,
    apply_field_attendance_to_entry,
    apply_field_attendance_to_sheet,
    approve_field_attendance,
    consolidate_field_attendance,
    create_default_nicaragua_config,
    open_field_work_day,
    record_worker_event,
    submit_rollcall,
)
from apps.modulos.audit.models import AuditEvent
from apps.modulos.hr.models import Employee
from apps.modulos.iam.models import OrgUnit

User = get_user_model()


def _mk_scope(suffix: str = ""):
    tag = suffix or uuid.uuid4().hex[:6]
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name=f"H_{tag}")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name=f"C_{tag}", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name=f"B_{tag}", parent=company)
    return company, branch


def _actor(prefix: str = "planillero"):
    username = f"{prefix}_{uuid.uuid4().hex[:8]}"
    return User.objects.create_user(username=username, email=f"{username}@test.local", password="x")


def _request(actor, *, company=None, branch=None):
    return SimpleNamespace(
        user=actor, META={}, company=company, branch=branch, _request=None,
        ctx=None, request_id=f"req_{uuid.uuid4().hex[:8]}", path="", method="POST",
    )


def _period(company):
    return PayrollPeriod.objects.create(
        company=company, year=2026, month=6, period_type=PeriodType.CATORCENA,
        start_date=date(2026, 6, 1), end_date=date(2026, 6, 14), working_days=14,
    )


def _employee(company, first_name="Trabajador"):
    return Employee.objects.create(
        company=company, employee_code=f"E-{uuid.uuid4().hex[:6]}",
        first_name=first_name, last_name="Campo", is_active=True,
    )


def _entry(sheet, employee, *, base_salary_nio="14000.00"):
    return PayrollEntry.objects.create(
        sheet=sheet, employee=employee, full_name=f"{employee.first_name} Campo",
        has_inss=True, base_salary_nio=Decimal(base_salary_nio),
        days_in_period=14, days_worked=Decimal("0.00"),
    )


def _approve_present_day(company, branch, actor, period, worker, *, work_date, sick=False, constancia=False):
    """Abre día, marca PRESENTE (opcional enfermo), consolida y aprueba → consolidación APPROVED."""
    work_day = open_field_work_day(
        request=_request(actor, company=company, branch=branch), actor=actor,
        company=company, branch=branch, payroll_period=period, work_date=work_date,
    )
    submit_rollcall(
        request=_request(actor, company=company, branch=branch), actor=actor,
        work_day=work_day, lines=[{"employee": worker, "status": "PRESENT"}],
    )
    if sick:
        metadata = {"constancia_medica": True, "day_value": "1.0"} if constancia else {}
        record_worker_event(
            request=_request(actor, company=company, branch=branch), actor=actor,
            work_day=work_day, employee=worker, event_type=FieldWorkerEventType.SICK,
            details="Gripe en el campo",
            metadata=metadata,
        )
    consolidate_field_attendance(
        request=_request(actor, company=company, branch=branch), actor=actor, work_day=work_day
    )
    approve_field_attendance(
        request=_request(actor, company=company, branch=branch), actor=actor, work_day=work_day
    )
    return work_day


@pytest.mark.django_db
def test_apply_attendance_sets_days_worked_and_locks_consolidations():
    company, branch = _mk_scope()
    actor = _actor()
    create_default_nicaragua_config(
        request=_request(actor, company=company), actor=actor, company=company, fiscal_year=2026
    )
    period = _period(company)
    worker = _employee(company, "Luis")
    # Dos días trabajados completos (martes y miércoles).
    _approve_present_day(company, branch, actor, period, worker, work_date=date(2026, 6, 2))
    _approve_present_day(company, branch, actor, period, worker, work_date=date(2026, 6, 3))

    sheet = PayrollSheet.objects.create(period=period, branch=branch, sheet_name="Finca CON INSS", has_inss=True)
    entry = _entry(sheet, worker)

    applied = apply_field_attendance_to_entry(request=_request(actor, company=company, branch=branch), actor=actor, entry=entry)

    applied.refresh_from_db()
    assert applied.days_worked == Decimal("2.00")
    assert applied.days_subsidy == Decimal("0.00")
    assert applied.quincenal_salary > Decimal("0.00")  # recálculo corrió

    # Consolidaciones bloqueadas para planilla (no recalculables).
    locked = FieldAttendanceConsolidation.objects.filter(
        payroll_period=period, employee=worker, status=FieldAttendanceConsolidationStatus.LOCKED_FOR_PAYROLL
    ).count()
    assert locked == 2
    assert AuditEvent.objects.filter(
        event_type="FIELD_ATTENDANCE_APPLIED_TO_PAYROLL", subject_id=str(entry.id)
    ).exists()


@pytest.mark.django_db
def test_enfermo_paga_segun_constancia_medica():
    """REGLA del dueño: enfermo con constancia médica certificada → el día se pone;
    sin constancia → no se paga (y el subsidio INSS queda como casilla manual)."""
    company, branch = _mk_scope()
    actor = _actor()
    create_default_nicaragua_config(
        request=_request(actor, company=company), actor=actor, company=company, fiscal_year=2026
    )
    period = _period(company)
    worker = _employee(company, "Ana")
    _approve_present_day(company, branch, actor, period, worker, work_date=date(2026, 6, 2))  # trabajado
    _approve_present_day(company, branch, actor, period, worker, work_date=date(2026, 6, 3), sick=True)  # sin constancia
    _approve_present_day(company, branch, actor, period, worker, work_date=date(2026, 6, 4), sick=True, constancia=True)

    agg = aggregate_attendance_for_employee(period=period, employee=worker)
    # 1 trabajado + 1 enfermo con constancia; el enfermo sin constancia no suma.
    assert agg["days_worked"] == Decimal("2.00")
    assert agg["days_subsidy"] == Decimal("0.00")


@pytest.mark.django_db
def test_apply_attendance_sunday_counts_as_sunday_worked():
    company, branch = _mk_scope()
    actor = _actor()
    period = _period(company)
    worker = _employee(company, "Carlos")
    _approve_present_day(company, branch, actor, period, worker, work_date=date(2026, 6, 7))  # domingo

    agg = aggregate_attendance_for_employee(period=period, employee=worker)
    assert agg["days_worked"] == Decimal("1.00")
    assert agg["sunday_worked_days"] == 1


@pytest.mark.django_db
def test_apply_without_approved_attendance_raises():
    company, branch = _mk_scope()
    actor = _actor()
    period = _period(company)
    worker = _employee(company, "Marta")
    sheet = PayrollSheet.objects.create(period=period, branch=branch, sheet_name="S", has_inss=True)
    entry = _entry(sheet, worker)

    with pytest.raises(FieldAttendanceError):
        apply_field_attendance_to_entry(request=_request(actor, company=company, branch=branch), actor=actor, entry=entry)


@pytest.mark.django_db
def test_apply_to_sheet_applies_only_entries_with_attendance():
    company, branch = _mk_scope()
    actor = _actor()
    create_default_nicaragua_config(
        request=_request(actor, company=company), actor=actor, company=company, fiscal_year=2026
    )
    period = _period(company)
    with_att = _employee(company, "ConAsistencia")
    without_att = _employee(company, "SinAsistencia")
    _approve_present_day(company, branch, actor, period, with_att, work_date=date(2026, 6, 2))

    sheet = PayrollSheet.objects.create(period=period, branch=branch, sheet_name="Finca", has_inss=True)
    e1 = _entry(sheet, with_att)
    e2 = _entry(sheet, without_att)

    result = apply_field_attendance_to_sheet(request=_request(actor, company=company, branch=branch), actor=actor, sheet=sheet)

    assert e1.id in result["applied"]
    assert e2.id in result["skipped"]
    e1.refresh_from_db()
    assert e1.days_worked == Decimal("1.00")
