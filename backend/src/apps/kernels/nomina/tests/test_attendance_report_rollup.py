from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model

from apps.kernels.nomina.models import (
    AttendanceReport,
    AttendanceSource,
    AttendanceStatus,
    FieldAttendanceConsolidation,
    FieldAttendanceConsolidationStatus,
    FieldWorkDay,
    FieldWorkDayStatus,
    FieldWorkerEventType,
    PayrollPeriod,
    PeriodType,
)
from apps.kernels.nomina.services import (
    FieldAttendanceError,
    aggregate_attendance_for_employee,
    rollup_field_attendance_report,
    rollup_field_attendance_reports_for_period,
)
from apps.modulos.hr.models import Employee
from apps.modulos.iam.models import OrgUnit

User = get_user_model()


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _scope(suffix=""):
    tag = suffix or uuid.uuid4().hex[:6]
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name=f"H_{tag}")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name=f"C_{tag}", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name=f"B_{tag}", parent=company)
    return company, branch


def _actor():
    username = f"planillero_{uuid.uuid4().hex[:8]}"
    return User.objects.create_user(username=username, email=f"{username}@test.local", password="x")


def _request(actor, company=None, branch=None):
    return SimpleNamespace(
        user=actor, META={}, company=company, branch=branch, _request=None,
        ctx=None, request_id=f"req_{uuid.uuid4().hex[:8]}", path="", method="POST",
    )


def _period(company):
    # CATORCENA junio 2026: 1-14. Junio 7 = domingo.
    return PayrollPeriod.objects.create(
        company=company, year=2026, month=6, period_type=PeriodType.CATORCENA,
        start_date=date(2026, 6, 1), end_date=date(2026, 6, 14), working_days=14,
    )


def _employee(company, first_name="Trabajador"):
    return Employee.objects.create(
        company=company, employee_code=f"E-{uuid.uuid4().hex[:6]}",
        first_name=first_name, last_name="Campo", is_active=True,
    )


def _consolidation(company, branch, period, employee, *, work_date, event_type,
                   day_value="1.00", status=FieldAttendanceConsolidationStatus.APPROVED):
    # Un FieldWorkDay por (company, branch, fecha) agrupa las consolidaciones de
    # todos los empleados de ese día (uq_fwd_c_branch_date).
    work_day, _ = FieldWorkDay.objects.get_or_create(
        company=company, branch=branch, work_date=work_date,
        defaults={"payroll_period": period, "status": FieldWorkDayStatus.APPROVED},
    )
    return FieldAttendanceConsolidation.objects.create(
        work_day=work_day, payroll_period=period, employee=employee, status=status,
        day_value=Decimal(day_value), primary_event_type=event_type,
    )


# ---------------------------------------------------------------------------
# rollup_field_attendance_report — desglose detallado
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_rollup_creates_report_with_breakdown():
    company, branch = _scope()
    actor = _actor()
    period = _period(company)
    worker = _employee(company, "Luis")

    _consolidation(company, branch, period, worker, work_date=date(2026, 6, 2), event_type=FieldWorkerEventType.PRESENT)
    _consolidation(company, branch, period, worker, work_date=date(2026, 6, 3), event_type=FieldWorkerEventType.PRESENT)
    _consolidation(company, branch, period, worker, work_date=date(2026, 6, 4), event_type=FieldWorkerEventType.SICK, day_value="0.00")
    _consolidation(company, branch, period, worker, work_date=date(2026, 6, 5), event_type=FieldWorkerEventType.ACCIDENT, day_value="0.00")
    _consolidation(company, branch, period, worker, work_date=date(2026, 6, 6), event_type=FieldWorkerEventType.ABSENT, day_value="0.00")
    _consolidation(company, branch, period, worker, work_date=date(2026, 6, 7), event_type=FieldWorkerEventType.PRESENT)  # domingo

    report = rollup_field_attendance_report(request=_request(actor, company), actor=actor, period=period, employee=worker)

    assert report.source == AttendanceSource.FIELD
    assert report.status == AttendanceStatus.SUBMITTED
    assert report.company == company
    assert report.branch == branch
    assert report.employee == worker
    assert report.days_worked == Decimal("3.00")  # Jun 2, 3, 7
    assert report.days_sick == Decimal("1.00")
    assert report.days_accident == Decimal("1.00")
    assert report.days_subsidy == Decimal("2.00")
    assert report.days_absent == Decimal("1.00")
    assert report.sunday_worked_days == 1  # Jun 7
    assert report.has_conflict is False
    assert report.submitted_by == actor


@pytest.mark.django_db
def test_rollup_transferred_counts_worked_and_transferred():
    company, branch = _scope()
    actor = _actor()
    period = _period(company)
    worker = _employee(company, "Ana")

    _consolidation(company, branch, period, worker, work_date=date(2026, 6, 2), event_type=FieldWorkerEventType.PRESENT)
    _consolidation(company, branch, period, worker, work_date=date(2026, 6, 3), event_type=FieldWorkerEventType.TRANSFERRED)

    report = rollup_field_attendance_report(request=_request(actor, company), actor=actor, period=period, employee=worker)
    assert report.days_worked == Decimal("2.00")
    assert report.days_transferred == Decimal("1.00")


@pytest.mark.django_db
def test_rollup_is_idempotent():
    company, branch = _scope()
    actor = _actor()
    period = _period(company)
    worker = _employee(company, "Pedro")
    _consolidation(company, branch, period, worker, work_date=date(2026, 6, 2), event_type=FieldWorkerEventType.PRESENT)

    r1 = rollup_field_attendance_report(request=_request(actor, company), actor=actor, period=period, employee=worker)
    r2 = rollup_field_attendance_report(request=_request(actor, company), actor=actor, period=period, employee=worker)

    assert r1.id == r2.id
    assert AttendanceReport.objects.filter(
        period=period, employee=worker, source=AttendanceSource.FIELD
    ).count() == 1


@pytest.mark.django_db
def test_rollup_no_attendance_raises():
    company, _branch = _scope()
    actor = _actor()
    period = _period(company)
    worker = _employee(company, "Sin")
    with pytest.raises(FieldAttendanceError):
        rollup_field_attendance_report(request=_request(actor, company), actor=actor, period=period, employee=worker)


@pytest.mark.django_db
def test_rollup_consistent_with_payroll_aggregate():
    """El reporte legal no debe desviarse de lo que la planilla calcula."""
    company, branch = _scope()
    actor = _actor()
    period = _period(company)
    worker = _employee(company, "Marta")
    _consolidation(company, branch, period, worker, work_date=date(2026, 6, 2), event_type=FieldWorkerEventType.PRESENT)
    _consolidation(company, branch, period, worker, work_date=date(2026, 6, 3), event_type=FieldWorkerEventType.SICK, day_value="0.00")

    report = rollup_field_attendance_report(request=_request(actor, company), actor=actor, period=period, employee=worker)
    agg = aggregate_attendance_for_employee(period=period, employee=worker)

    assert report.days_worked == agg["days_worked"]
    assert report.days_subsidy == agg["days_subsidy"]
    assert report.sunday_worked_days == agg["sunday_worked_days"]


@pytest.mark.django_db
def test_rollup_for_period_all_employees():
    company, branch = _scope()
    actor = _actor()
    period = _period(company)
    w1 = _employee(company, "Uno")
    w2 = _employee(company, "Dos")
    _consolidation(company, branch, period, w1, work_date=date(2026, 6, 2), event_type=FieldWorkerEventType.PRESENT)
    _consolidation(company, branch, period, w2, work_date=date(2026, 6, 2), event_type=FieldWorkerEventType.PRESENT)

    reports = rollup_field_attendance_reports_for_period(request=_request(actor, company), actor=actor, period=period)
    assert len(reports) == 2
    assert {r.employee_id for r in reports} == {w1.id, w2.id}


@pytest.mark.django_db
def test_rollup_ignores_unapproved_consolidations():
    company, branch = _scope()
    actor = _actor()
    period = _period(company)
    worker = _employee(company, "Borrador")
    # Una aprobada y una en estado OK (no aprobada) → solo cuenta la aprobada.
    _consolidation(company, branch, period, worker, work_date=date(2026, 6, 2), event_type=FieldWorkerEventType.PRESENT)
    _consolidation(company, branch, period, worker, work_date=date(2026, 6, 3), event_type=FieldWorkerEventType.PRESENT,
                   status=FieldAttendanceConsolidationStatus.OK)

    report = rollup_field_attendance_report(request=_request(actor, company), actor=actor, period=period, employee=worker)
    assert report.days_worked == Decimal("1.00")
