"""Tests del régimen INSS (el "dolor de cabeza") + SoD de aprobación de período.

Cubre: afiliación fechada y resolución por fecha, override por período, auto-clasificación
CON/SIN INSS con recálculo, wiring de resolve_worker_inss, y SoD de aprobación de período.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model

from apps.kernels.nomina.models import (
    EmployeeInssEnrollment,
    InssElectionSource,
    InssRegime,
    PayrollEntry,
    PayrollPeriod,
    PayrollSheet,
    PeriodStatus,
    PeriodType,
)
from apps.kernels.nomina.period_sod import approve_period, request_period_approval
from apps.kernels.nomina.services import (
    compute_entry,
    create_default_nicaragua_config,
    resolve_worker_inss,
)
from apps.kernels.nomina.services_inss import (
    classify_entries_by_inss,
    resolve_period_inss_elections,
    set_employee_inss_enrollment,
    set_period_inss_election,
)
from apps.modulos.audit.models import AuditEvent
from apps.modulos.hr.models import Employee
from apps.modulos.iam.approvals import ApproverNotAuthorizedError, SelfApprovalError
from apps.modulos.iam.models import ApprovalRequest, OrgUnit

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


def _superuser(prefix: str = "jefe"):
    username = f"{prefix}_{uuid.uuid4().hex[:8]}"
    return User.objects.create_superuser(username=username, email=f"{username}@test.local", password="x")


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


def _entry(sheet, employee, *, has_inss=True, base="14000.00", days="14"):
    return PayrollEntry.objects.create(
        sheet=sheet, employee=employee, full_name=f"{employee.first_name} Campo",
        has_inss=has_inss, base_salary_nio=Decimal(base), days_in_period=14, days_worked=Decimal(days),
    )


# --------------------------------------------------------------------------- #
# Afiliación fechada + resolución por fecha
# --------------------------------------------------------------------------- #

@pytest.mark.django_db
def test_enrollment_change_closes_previous_and_resolves_by_date():
    company, _ = _mk_scope()
    actor = _actor()
    emp = _employee(company)
    req = _request(actor, company=company)

    set_employee_inss_enrollment(
        request=req, actor=actor, employee=emp, regime=InssRegime.AFFILIATED, effective_from=date(2026, 1, 1)
    )
    e2 = set_employee_inss_enrollment(
        request=req, actor=actor, employee=emp, regime=InssRegime.NOT_AFFILIATED, effective_from=date(2026, 4, 1),
        reason="Pidió salir del INSS",
    )

    # la afiliación previa quedó cerrada el día anterior
    prev = EmployeeInssEnrollment.objects.get(employee=emp, regime=InssRegime.AFFILIATED)
    assert prev.effective_to == date(2026, 3, 31)
    # resolución por fecha
    assert EmployeeInssEnrollment.resolve_for(emp, date(2026, 3, 15)) == InssRegime.AFFILIATED
    assert EmployeeInssEnrollment.resolve_for(emp, date(2026, 5, 1)) == InssRegime.NOT_AFFILIATED
    # sin afiliación → AFFILIATED por defecto
    assert EmployeeInssEnrollment.resolve_for(_employee(company), date(2026, 5, 1)) == InssRegime.AFFILIATED
    assert AuditEvent.objects.filter(
        event_type="NOMINA_EMPLOYEE_INSS_REGIME_CHANGED", subject_id=str(e2.id)
    ).exists()


@pytest.mark.django_db
def test_period_election_override_upserts_and_audits():
    company, _ = _mk_scope()
    actor = _actor()
    emp = _employee(company)
    period = _period(company)
    req = _request(actor, company=company)

    el = set_period_inss_election(request=req, actor=actor, period=period, employee=emp, elected_has_inss=False, reason="x")
    assert el.elected_has_inss is False
    assert el.source == InssElectionSource.OVERRIDE
    el2 = set_period_inss_election(request=req, actor=actor, period=period, employee=emp, elected_has_inss=True)
    assert el2.id == el.id and el2.elected_has_inss is True
    assert AuditEvent.objects.filter(event_type="NOMINA_INSS_ELECTION_SET").count() == 2


# --------------------------------------------------------------------------- #
# Auto-clasificación CON/SIN INSS + recálculo
# --------------------------------------------------------------------------- #

@pytest.mark.django_db
def test_classify_moves_entry_to_sin_inss_and_recomputes():
    company, branch = _mk_scope()
    actor = _actor()
    create_default_nicaragua_config(request=_request(actor, company=company), actor=actor, company=company, fiscal_year=2026)
    emp = _employee(company, "Jose")
    req = _request(actor, company=company, branch=branch)
    # afiliación NOT_AFFILIATED vigente
    set_employee_inss_enrollment(request=req, actor=actor, employee=emp, regime=InssRegime.NOT_AFFILIATED, effective_from=date(2026, 1, 1))

    period = _period(company)
    sheet_con = PayrollSheet.objects.create(period=period, branch=branch, sheet_name="Finca CON INSS", has_inss=True)
    entry = _entry(sheet_con, emp, has_inss=True)
    compute_entry(entry=entry)
    assert entry.inss_laboral > Decimal("0.00")  # arrancó cotizando

    result = classify_entries_by_inss(request=req, actor=actor, period=period)

    entry.refresh_from_db()
    assert entry.has_inss is False
    assert entry.sheet.has_inss is False
    assert "SIN INSS" in entry.sheet.sheet_name
    assert entry.inss_laboral == Decimal("0.00")  # recalculado sin INSS
    assert result["moved"] >= 1
    assert AuditEvent.objects.filter(event_type="NOMINA_ENTRIES_RECLASSIFIED", subject_id=str(period.id)).exists()


@pytest.mark.django_db
def test_resolve_period_inss_elections_creates_from_enrollment():
    company, branch = _mk_scope()
    actor = _actor()
    emp = _employee(company)
    set_employee_inss_enrollment(
        request=_request(actor, company=company), actor=actor, employee=emp,
        regime=InssRegime.NOT_AFFILIATED, effective_from=date(2026, 1, 1),
    )
    period = _period(company)
    sheet = PayrollSheet.objects.create(period=period, branch=branch, sheet_name="S", has_inss=True)
    _entry(sheet, emp)

    elections = resolve_period_inss_elections(request=_request(actor, company=company), actor=actor, period=period)
    assert elections[emp.id] is False  # NOT_AFFILIATED → no cotiza


@pytest.mark.django_db
def test_resolve_worker_inss_prefers_election_then_enrollment():
    company, _ = _mk_scope()
    actor = _actor()
    emp = _employee(company)
    period = _period(company)
    req = _request(actor, company=company)
    set_employee_inss_enrollment(request=req, actor=actor, employee=emp, regime=InssRegime.NOT_AFFILIATED, effective_from=date(2026, 1, 1))
    # afiliación dice NO cotiza
    assert resolve_worker_inss(emp, period=period) is False
    # override del período dice SÍ cotiza → gana
    set_period_inss_election(request=req, actor=actor, period=period, employee=emp, elected_has_inss=True)
    assert resolve_worker_inss(emp, period=period) is True


# --------------------------------------------------------------------------- #
# SoD aprobación de período
# --------------------------------------------------------------------------- #

@pytest.mark.django_db
def test_period_sod_happy_path():
    company, _ = _mk_scope()
    maker = _actor()
    checker = _superuser()
    period = _period(company)

    approval = request_period_approval(request=_request(maker, company=company), actor=maker, period=period)
    assert approval.status == ApprovalRequest.Status.PENDING

    approve_period(request=_request(checker, company=company), approver=checker, approval=approval)

    period.refresh_from_db()
    approval.refresh_from_db()
    assert period.status == PeriodStatus.APPROVED
    assert period.approved_by_id == checker.id
    assert approval.status == ApprovalRequest.Status.EXECUTED


@pytest.mark.django_db
def test_period_sod_blocks_self_approval():
    company, _ = _mk_scope()
    maker = _actor()
    period = _period(company)
    approval = request_period_approval(request=_request(maker, company=company), actor=maker, period=period)
    with pytest.raises(SelfApprovalError):
        approve_period(request=_request(maker, company=company), approver=maker, approval=approval)
    period.refresh_from_db()
    assert period.status != PeriodStatus.APPROVED


@pytest.mark.django_db
def test_period_sod_requires_permission():
    company, _ = _mk_scope()
    maker = _actor()
    other = _actor("sin_permiso")
    period = _period(company)
    approval = request_period_approval(request=_request(maker, company=company), actor=maker, period=period)
    with pytest.raises(ApproverNotAuthorizedError):
        approve_period(request=_request(other, company=company), approver=other, approval=approval)
