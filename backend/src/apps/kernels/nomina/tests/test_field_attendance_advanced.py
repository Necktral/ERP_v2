"""Tests de los controles avanzados sobre la fundación de asistencia de campo (PR-A).

Cubre: SoD maker-checker en la aprobación, IR catorcenal correcto (×26), resolución
real de `has_inss` (no el getattr siempre-None), `day_value` sumado en traslados, y el
seed RBAC de `nomina.field.*` / `nomina.*`.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model

from apps.kernels.nomina.field_sod import (
    approve_field_attendance_with_sod,
    request_field_attendance_approval,
)
from apps.kernels.nomina.models import (
    FieldWorkDayStatus,
    IRBracket,
    PayrollEntry,
    PayrollPeriod,
    PayrollSheet,
    PeriodType,
    periods_per_year,
)
from apps.kernels.nomina.services import (
    _calculate_day_value,
    consolidate_field_attendance,
    create_default_nicaragua_config,
    open_field_work_day,
    resolve_worker_inss,
    submit_rollcall,
)
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
        user=actor,
        META={},
        company=company,
        branch=branch,
        _request=None,
        ctx=None,
        request_id=f"req_{uuid.uuid4().hex[:8]}",
        path="",
        method="POST",
    )


def _period(company, *, period_type=PeriodType.CATORCENA):
    return PayrollPeriod.objects.create(
        company=company,
        year=2026,
        month=6,
        period_type=period_type,
        start_date=date(2026, 6, 1),
        end_date=date(2026, 6, 14),
        working_days=14,
    )


def _employee(company, first_name="Trabajador"):
    return Employee.objects.create(
        company=company,
        employee_code=f"E-{uuid.uuid4().hex[:6]}",
        first_name=first_name,
        last_name="Campo",
        is_active=True,
    )


def _consolidated_day(company, branch, maker, worker):
    """Abre día, pasa lista PRESENTE y consolida → consolidación aprobable (WARNING)."""
    period = _period(company)
    work_day = open_field_work_day(
        request=_request(maker, company=company, branch=branch),
        actor=maker,
        company=company,
        branch=branch,
        payroll_period=period,
        work_date=date(2026, 6, 5),
    )
    submit_rollcall(
        request=_request(maker, company=company, branch=branch),
        actor=maker,
        work_day=work_day,
        lines=[{"employee": worker, "status": "PRESENT"}],
    )
    consolidate_field_attendance(
        request=_request(maker, company=company, branch=branch),
        actor=maker,
        work_day=work_day,
    )
    return work_day


# --------------------------------------------------------------------------- #
# SoD maker-checker en la aprobación
# --------------------------------------------------------------------------- #

@pytest.mark.django_db
def test_field_sod_happy_path_checker_distinct_from_maker():
    company, branch = _mk_scope()
    maker = _actor()
    checker = _superuser()  # superuser satisface el permiso nomina.field.approve en el scope
    worker = _employee(company, "Marta")
    work_day = _consolidated_day(company, branch, maker, worker)

    approval = request_field_attendance_approval(
        request=_request(maker, company=company, branch=branch), actor=maker, work_day=work_day
    )
    assert approval.status == ApprovalRequest.Status.PENDING

    approve_field_attendance_with_sod(
        request=_request(checker, company=company, branch=branch), approver=checker, approval=approval
    )

    work_day.refresh_from_db()
    approval.refresh_from_db()
    assert work_day.status == FieldWorkDayStatus.APPROVED
    assert work_day.approved_by_id == checker.id
    assert approval.status == ApprovalRequest.Status.EXECUTED


@pytest.mark.django_db
def test_field_sod_blocks_self_approval():
    company, branch = _mk_scope()
    maker = _actor()
    worker = _employee(company, "Ramon")
    work_day = _consolidated_day(company, branch, maker, worker)

    approval = request_field_attendance_approval(
        request=_request(maker, company=company, branch=branch), actor=maker, work_day=work_day
    )
    with pytest.raises(SelfApprovalError):
        approve_field_attendance_with_sod(
            request=_request(maker, company=company, branch=branch), approver=maker, approval=approval
        )

    work_day.refresh_from_db()
    assert work_day.status != FieldWorkDayStatus.APPROVED


@pytest.mark.django_db
def test_field_sod_requires_approve_permission():
    company, branch = _mk_scope()
    maker = _actor()
    other = _actor("sin_permiso")  # usuario normal, sin nomina.field.approve
    worker = _employee(company, "Elena")
    work_day = _consolidated_day(company, branch, maker, worker)

    approval = request_field_attendance_approval(
        request=_request(maker, company=company, branch=branch), actor=maker, work_day=work_day
    )
    with pytest.raises(ApproverNotAuthorizedError):
        approve_field_attendance_with_sod(
            request=_request(other, company=company, branch=branch), approver=other, approval=approval
        )


# --------------------------------------------------------------------------- #
# IR catorcenal correcto (×26 vs ×24)
# --------------------------------------------------------------------------- #

@pytest.mark.django_db
def test_catorcena_ir_differs_from_quincena_for_same_income():
    company, _ = _mk_scope()
    actor = _actor()
    config = create_default_nicaragua_config(
        request=_request(actor, company=company), actor=actor, company=company, fiscal_year=2026
    )
    income = Decimal("25000.00")  # ingreso del período en rango gravable

    ir_quincena = IRBracket.calculate_period_ir(config=config, period_income=income, periods_per_year=24)
    ir_catorcena = IRBracket.calculate_period_ir(config=config, period_income=income, periods_per_year=26)

    assert ir_quincena > 0 and ir_catorcena > 0
    assert ir_quincena != ir_catorcena
    assert periods_per_year(PeriodType.CATORCENA) == 26
    assert periods_per_year(PeriodType.FIRST_HALF) == 24
    assert periods_per_year(PeriodType.MONTHLY) == 12
    # Compat: el wrapper quincenal sigue siendo ×24.
    assert IRBracket.calculate_quincenal_ir(config=config, quincenal_income=income) == ir_quincena


# --------------------------------------------------------------------------- #
# has_inss real (no getattr siempre-None)
# --------------------------------------------------------------------------- #

@pytest.mark.django_db
def test_resolve_worker_inss_uses_last_payroll_entry():
    company, branch = _mk_scope()
    worker = _employee(company, "Pedro")

    # Sin planilla previa → desconocido (None), no None-por-bug.
    assert resolve_worker_inss(worker) is None

    period = _period(company)
    sheet = PayrollSheet.objects.create(period=period, branch=branch, sheet_name="S CON INSS", has_inss=True)
    PayrollEntry.objects.create(
        sheet=sheet, employee=worker, full_name="Pedro Campo", has_inss=True, days_worked=Decimal("14")
    )

    # Continuidad: toma la última decisión registrada del planillero.
    assert resolve_worker_inss(worker, period=period) is True


# --------------------------------------------------------------------------- #
# day_value sumado en traslados (anti sub-pago) y tope 1.0
# --------------------------------------------------------------------------- #

@pytest.mark.django_db
def test_day_value_sums_for_transfer_but_caps_at_one():
    lines = [SimpleNamespace(day_value=Decimal("0.50")), SimpleNamespace(day_value=Decimal("0.50"))]
    # Traslado: suma las porciones (0.5 + 0.5 = 1.0) en vez de max (0.5).
    assert _calculate_day_value(
        primary_event_type="PRESENT", rollcall_status=None, crew_lines=lines, is_split_transfer=True
    ) == Decimal("1.00")
    # Sin traslado: máximo (anti-doble-pago).
    assert _calculate_day_value(
        primary_event_type="PRESENT", rollcall_status=None, crew_lines=lines, is_split_transfer=False
    ) == Decimal("0.50")
    # Tope 1.0 aunque la suma exceda.
    big = [SimpleNamespace(day_value=Decimal("0.80")), SimpleNamespace(day_value=Decimal("0.80"))]
    assert _calculate_day_value(
        primary_event_type="PRESENT", rollcall_status=None, crew_lines=big, is_split_transfer=True
    ) == Decimal("1.00")


# --------------------------------------------------------------------------- #
# RBAC seed nomina.field.* / nomina.* (SoD: planillero ≠ aprobador)
# --------------------------------------------------------------------------- #

@pytest.mark.django_db
def test_rbac_seed_includes_nomina_field_perms_and_sod_roles():
    from apps.modulos.rbac.models import Permission, Role, RolePermission
    from apps.modulos.rbac.seed_v01 import seed_rbac_v01

    seed_rbac_v01()

    # Permisos sembrados (antes faltaban → solo superadmin operaba nómina).
    for code in ("nomina.config.read", "nomina.entry.create", "nomina.field.capture", "nomina.field.approve"):
        assert Permission.objects.filter(code=code).exists(), f"perm faltante: {code}"

    payroll = Role.objects.get(name="payroll_manager")
    supervisor = Role.objects.get(name="field_supervisor")

    payroll_perms = set(RolePermission.objects.filter(role=payroll).values_list("permission__code", flat=True))
    supervisor_perms = set(RolePermission.objects.filter(role=supervisor).values_list("permission__code", flat=True))

    # SoD: el planillero captura/consolida/solicita pero NO aprueba.
    assert "nomina.field.capture" in payroll_perms
    assert "nomina.field.approve.request" in payroll_perms
    assert "nomina.field.approve" not in payroll_perms
    # El jefe de área aprueba.
    assert "nomina.field.approve" in supervisor_perms
