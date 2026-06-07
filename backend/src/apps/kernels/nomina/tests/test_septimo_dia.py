"""Tests del séptimo día y feriados laborados (casilla legal INSS).

Regla: el séptimo (domingo pagado) se gana con la semana completa; solo la falta
INJUSTIFICADA (ABSENT) lo pierde — subsidio/enfermedad no rompen la semana.
Jornaleros (DAILY) lo cobran aparte; mensuales lo llevan embebido.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model

from apps.kernels.nomina.models import (
    FieldWorkerEventType,
    PayrollEntry,
    PayrollPeriod,
    PayrollSheet,
    PeriodType,
    SalaryType,
)
from apps.kernels.nomina.services import (
    aggregate_attendance_for_employee,
    approve_field_attendance,
    apply_field_attendance_to_entry,
    compute_entry,
    consolidate_field_attendance,
    create_default_nicaragua_config,
    open_field_work_day,
    record_worker_event,
    submit_rollcall,
)
from apps.modulos.hr.models import Employee
from apps.modulos.iam.models import OrgUnit

User = get_user_model()


def _mk_scope():
    tag = uuid.uuid4().hex[:6]
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name=f"H_{tag}")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name=f"C_{tag}", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name=f"B_{tag}", parent=company)
    return company, branch


def _actor():
    u = f"u_{uuid.uuid4().hex[:8]}"
    return User.objects.create_user(username=u, email=f"{u}@t.local", password="x")


def _req(actor, *, company=None, branch=None):
    return SimpleNamespace(
        user=actor, META={}, company=company, branch=branch, _request=None,
        ctx=None, request_id=f"r_{uuid.uuid4().hex[:6]}", path="", method="POST",
    )


def _period(company):
    return PayrollPeriod.objects.create(
        company=company, year=2026, month=6, period_type=PeriodType.CATORCENA,
        start_date=date(2026, 6, 1), end_date=date(2026, 6, 14), working_days=14,
    )


def _employee(company, name="Jornalero"):
    return Employee.objects.create(
        company=company, employee_code=f"E-{uuid.uuid4().hex[:6]}",
        first_name=name, last_name="Campo", is_active=True,
    )


def _config(company, actor):
    return create_default_nicaragua_config(
        request=_req(actor, company=company), actor=actor, company=company, fiscal_year=2026
    )


def _approve_day(company, branch, actor, period, worker, *, work_date, status="PRESENT", sick=False):
    """Abre día, marca asistencia, consolida y aprueba (1 consolidación APPROVED)."""
    wd = open_field_work_day(
        request=_req(actor, company=company, branch=branch), actor=actor,
        company=company, branch=branch, payroll_period=period, work_date=work_date,
    )
    submit_rollcall(
        request=_req(actor, company=company, branch=branch), actor=actor,
        work_day=wd, lines=[{"employee": worker, "status": status}],
    )
    if sick:
        record_worker_event(
            request=_req(actor, company=company, branch=branch), actor=actor,
            work_day=wd, employee=worker, event_type=FieldWorkerEventType.SICK, details="Gripe",
        )
    consolidate_field_attendance(request=_req(actor, company=company, branch=branch), actor=actor, work_day=wd)
    approve_field_attendance(request=_req(actor, company=company, branch=branch), actor=actor, work_day=wd)
    return wd


# --------------------------------------------------------------------------- #
# Cálculo (compute_all): DAILY vs MONTHLY
# --------------------------------------------------------------------------- #

@pytest.mark.django_db
def test_daily_worker_gets_seventh_day_paid_and_in_inss_base():
    company, branch = _mk_scope()
    actor = _actor()
    config = _config(company, actor)
    period = _period(company)
    sheet = PayrollSheet.objects.create(period=period, branch=branch, sheet_name="EVENTUAL", has_inss=True)
    emp = _employee(company)
    entry = PayrollEntry.objects.create(
        sheet=sheet, employee=emp, full_name="Jornalero X", has_inss=True,
        salary_type=SalaryType.DAILY, base_salary_nio=Decimal("6000.00"),  # diario = 200
        days_in_period=14, days_worked=Decimal("12.00"), seventh_day_days=Decimal("2.00"),
    )
    compute_entry(entry=entry)
    entry.refresh_from_db()

    assert entry.daily_rate_nio == Decimal("200.000000")
    assert entry.quincenal_salary == Decimal("2400.00")          # 200 × 12
    assert entry.seventh_day_amount == Decimal("400.00")         # 200 × 2 × 1.0
    # INSS sobre básico devengado (2400 + 400 = 2800), no solo el salario trabajado.
    expected_inss = (Decimal("2800.00") * config.inss_laboral_rate).quantize(Decimal("0.01"))
    assert entry.inss_laboral == expected_inss
    assert entry.total_income >= Decimal("2800.00")


@pytest.mark.django_db
def test_monthly_worker_has_no_separate_seventh_day():
    company, branch = _mk_scope()
    actor = _actor()
    config = _config(company, actor)
    period = _period(company)
    sheet = PayrollSheet.objects.create(period=period, branch=branch, sheet_name="ADMON", has_inss=True)
    emp = _employee(company)
    entry = PayrollEntry.objects.create(
        sheet=sheet, employee=emp, full_name="Admin X", has_inss=True,
        salary_type=SalaryType.MONTHLY, base_salary_nio=Decimal("6000.00"),
        days_in_period=14, days_worked=Decimal("12.00"), seventh_day_days=Decimal("2.00"),
    )
    compute_entry(entry=entry)
    entry.refresh_from_db()
    assert entry.seventh_day_amount == Decimal("0.00")  # embebido, no se paga aparte
    expected_inss = (entry.quincenal_salary * config.inss_laboral_rate).quantize(Decimal("0.01"))
    assert entry.inss_laboral == expected_inss


@pytest.mark.django_db
def test_holiday_worked_paid_double_for_daily():
    company, branch = _mk_scope()
    actor = _actor()
    _config(company, actor)
    period = _period(company)
    sheet = PayrollSheet.objects.create(period=period, branch=branch, sheet_name="EVENTUAL", has_inss=False)
    emp = _employee(company)
    entry = PayrollEntry.objects.create(
        sheet=sheet, employee=emp, full_name="Jornalero F", has_inss=False,
        salary_type=SalaryType.DAILY, base_salary_nio=Decimal("6000.00"),  # diario = 200
        days_in_period=14, days_worked=Decimal("10.00"), holiday_worked_days=Decimal("1.00"),
    )
    compute_entry(entry=entry)
    entry.refresh_from_db()
    assert entry.holiday_amount == Decimal("400.00")  # 200 × 1 × 2.0


# --------------------------------------------------------------------------- #
# Séptimo día desde asistencia (regla injustificada)
# --------------------------------------------------------------------------- #

@pytest.mark.django_db
def test_seventh_day_earned_on_complete_week():
    company, branch = _mk_scope()
    actor = _actor()
    period = _period(company)
    worker = _employee(company)
    for d in range(1, 7):  # Lun(1)..Sáb(6) de la misma semana
        _approve_day(company, branch, actor, period, worker, work_date=date(2026, 6, d))
    agg = aggregate_attendance_for_employee(period=period, employee=worker)
    assert agg["days_worked"] == Decimal("6.00")
    assert agg["seventh_day_days"] == Decimal("1.00")


@pytest.mark.django_db
def test_seventh_day_lost_on_unjustified_absence():
    company, branch = _mk_scope()
    actor = _actor()
    period = _period(company)
    worker = _employee(company)
    _approve_day(company, branch, actor, period, worker, work_date=date(2026, 6, 1))
    _approve_day(company, branch, actor, period, worker, work_date=date(2026, 6, 2))
    _approve_day(company, branch, actor, period, worker, work_date=date(2026, 6, 3), status="ABSENT")  # injustificada
    _approve_day(company, branch, actor, period, worker, work_date=date(2026, 6, 4))
    agg = aggregate_attendance_for_employee(period=period, employee=worker)
    assert agg["seventh_day_days"] == Decimal("0.00")  # perdió el domingo de esa semana


@pytest.mark.django_db
def test_seventh_day_kept_with_justified_absence():
    company, branch = _mk_scope()
    actor = _actor()
    period = _period(company)
    worker = _employee(company)
    _approve_day(company, branch, actor, period, worker, work_date=date(2026, 6, 1))
    _approve_day(company, branch, actor, period, worker, work_date=date(2026, 6, 2))
    _approve_day(company, branch, actor, period, worker, work_date=date(2026, 6, 3), sick=True)  # justificada
    _approve_day(company, branch, actor, period, worker, work_date=date(2026, 6, 4))
    agg = aggregate_attendance_for_employee(period=period, employee=worker)
    assert agg["days_subsidy"] == Decimal("1.00")
    assert agg["seventh_day_days"] == Decimal("1.00")  # enfermedad NO rompe la semana


@pytest.mark.django_db
def test_apply_attendance_sets_seventh_day_on_daily_entry():
    company, branch = _mk_scope()
    actor = _actor()
    _config(company, actor)
    period = _period(company)
    worker = _employee(company)
    for d in range(1, 7):
        _approve_day(company, branch, actor, period, worker, work_date=date(2026, 6, d))
    sheet = PayrollSheet.objects.create(period=period, branch=branch, sheet_name="EVENTUAL", has_inss=True)
    entry = PayrollEntry.objects.create(
        sheet=sheet, employee=worker, full_name="Jornalero Y", has_inss=True,
        salary_type=SalaryType.DAILY, base_salary_nio=Decimal("6000.00"), days_in_period=14,
    )
    apply_field_attendance_to_entry(request=_req(actor, company=company, branch=branch), actor=actor, entry=entry)
    entry.refresh_from_db()
    assert entry.days_worked == Decimal("6.00")
    assert entry.seventh_day_days == Decimal("1.00")
    assert entry.seventh_day_amount == Decimal("200.00")  # 200 × 1 × 1.0
