"""
Tests del kernel nómina — Nicaragua sector agrícola.
Cubre: configuración INSS/IR, cálculo de entrada, ciclo de planilla.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
import pytest
from django.contrib.auth import get_user_model
from types import SimpleNamespace

from apps.kernels.nomina.models import (
    DEFAULT_INSS_LABORAL,
    DEFAULT_INATEC,
    IRBracket,
    PayrollEntry,
    PeriodType,
    SheetStatus,
    SalaryType,
)
from apps.kernels.nomina.services import (
    approve_sheet,
    compute_all_entries_in_sheet,
    compute_entry,
    create_default_nicaragua_config,
    create_period,
    create_sheet,
    submit_sheet,
)
from apps.modulos.iam.models import OrgUnit

User = get_user_model()


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _mk_scope(suffix=""):
    s = suffix or uuid.uuid4().hex[:6]
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name=f"H_{s}")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name=f"C_{s}", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name=f"B_{s}", parent=company)
    return company, branch


def _actor(suffix=""):
    uid = uuid.uuid4().hex[:8]
    name = f"nom_{suffix}_{uid}" if suffix else f"nom_{uid}"
    return User.objects.create_user(username=name, email=f"{name}@test.com", password="x")


def _mock_request(actor):
    # SimpleNamespace evita que _request devuelva MagicMock con .company.id enorme
    return SimpleNamespace(
        user=actor,
        META={},
        company=None,
        branch=None,
        _request=None,
        ctx=None,
        request_id="",
        path="",
        method="GET",
    )


def _mk_config(company, actor):
    req = _mock_request(actor)
    return create_default_nicaragua_config(request=req, actor=actor, company=company, fiscal_year=2026)


def _mk_period(company, actor, *, month=1, period_type=PeriodType.FIRST_HALF):
    req = _mock_request(actor)
    return create_period(
        request=req, actor=actor, company=company,
        year=2026, month=month, period_type=period_type,
        start_date=date(2026, month, 1),
        end_date=date(2026, month, 15),
        working_days=15,
    )


def _mk_sheet(period, actor, *, sheet_name="Planilla General", has_inss=True):
    req = _mock_request(actor)
    return create_sheet(
        request=req, actor=actor, period=period,
        sheet_name=sheet_name, has_inss=has_inss,
    )


def _mk_entry(sheet, *, full_name="Juan Pérez", base_salary_nio="6000.00",
               days_worked="15", has_inss=True, salary_type=SalaryType.MONTHLY):
    return PayrollEntry.objects.create(
        sheet=sheet,
        full_name=full_name,
        base_salary_nio=Decimal(base_salary_nio),
        days_in_period=15,
        days_worked=Decimal(days_worked),
        has_inss=has_inss,
        salary_type=salary_type,
    )


# ---------------------------------------------------------------------------
# NominaConfig — crear y validar defaults Nicaragua
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_create_default_nicaragua_config():
    company, _ = _mk_scope()
    actor = _actor()
    cfg = _mk_config(company, actor)

    assert cfg.company == company
    assert cfg.fiscal_year == 2026
    assert cfg.is_active is True
    assert cfg.inss_laboral_rate == DEFAULT_INSS_LABORAL
    assert cfg.inatec_rate == DEFAULT_INATEC
    # Tabla IR creada
    assert IRBracket.objects.filter(config=cfg).count() == 5


@pytest.mark.django_db
def test_create_default_config_idempotent():
    company, _ = _mk_scope()
    actor = _actor()
    cfg1 = _mk_config(company, actor)
    cfg2 = _mk_config(company, actor)
    assert cfg1.id == cfg2.id


@pytest.mark.django_db
def test_create_config_two_companies_independent():
    company1, _ = _mk_scope("a")
    company2, _ = _mk_scope("b")
    actor = _actor()
    cfg1 = _mk_config(company1, actor)
    cfg2 = _mk_config(company2, actor)
    assert cfg1.id != cfg2.id
    assert cfg1.company == company1
    assert cfg2.company == company2


# ---------------------------------------------------------------------------
# IRBracket — cálculo de IR quincenal
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_ir_zero_for_income_below_threshold():
    company, _ = _mk_scope()
    actor = _actor()
    cfg = _mk_config(company, actor)
    # Salario mensual C$6,000 → quincenal C$3,000 → anual C$72,000 → IR = 0
    ir = IRBracket.calculate_quincenal_ir(config=cfg, quincenal_income=Decimal("3000.00"))
    assert ir == Decimal("0.00")


@pytest.mark.django_db
def test_ir_positive_for_income_above_threshold():
    company, _ = _mk_scope()
    actor = _actor()
    cfg = _mk_config(company, actor)
    # Quincenal C$9,000 → anual C$216,000 → en tramo 2 (100k-200k) + tramo 3
    ir = IRBracket.calculate_quincenal_ir(config=cfg, quincenal_income=Decimal("9000.00"))
    assert ir > Decimal("0.00")


@pytest.mark.django_db
def test_ir_increases_with_income():
    company, _ = _mk_scope()
    actor = _actor()
    cfg = _mk_config(company, actor)
    ir_low = IRBracket.calculate_quincenal_ir(config=cfg, quincenal_income=Decimal("5000.00"))
    ir_high = IRBracket.calculate_quincenal_ir(config=cfg, quincenal_income=Decimal("15000.00"))
    assert ir_high > ir_low


# ---------------------------------------------------------------------------
# compute_entry — cálculos INSS/IR/neto
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_compute_entry_full_period_standard_employee():
    company, _ = _mk_scope()
    actor = _actor()
    _mk_config(company, actor)
    period = _mk_period(company, actor)
    sheet = _mk_sheet(period, actor)
    entry = _mk_entry(sheet, base_salary_nio="6000.00", days_worked="15")

    result = compute_entry(entry=entry)

    # Quincenal base: 6000/2 = 3000
    assert result.quincenal_salary == Decimal("3000.00")
    # INSS laboral: 3000 * 7% = 210 (DEFAULT_INSS_LABORAL = 0.07)
    assert result.inss_laboral == (Decimal("3000.00") * DEFAULT_INSS_LABORAL).quantize(Decimal("0.01"))
    assert result.net_to_pay > Decimal("0.00")
    assert result.net_to_pay < result.quincenal_salary
    # INSS patronal calculado
    assert result.inss_patronal > Decimal("0.00")
    # INATEC calculado
    assert result.inatec > Decimal("0.00")


@pytest.mark.django_db
def test_compute_entry_partial_days():
    company, _ = _mk_scope()
    actor = _actor()
    _mk_config(company, actor)
    period = _mk_period(company, actor)
    sheet = _mk_sheet(period, actor)
    entry = _mk_entry(sheet, base_salary_nio="6000.00", days_worked="10")

    result = compute_entry(entry=entry)

    # 10 días de 15 → salario diario * 10
    daily = Decimal("6000.00") / Decimal("30")
    expected_quincenal = (daily * Decimal("10")).quantize(Decimal("0.01"))
    assert result.quincenal_salary == expected_quincenal
    assert result.net_to_pay < result.quincenal_salary


@pytest.mark.django_db
def test_compute_entry_no_inss():
    company, _ = _mk_scope()
    actor = _actor()
    _mk_config(company, actor)
    period = _mk_period(company, actor)
    sheet = _mk_sheet(period, actor, has_inss=False)
    entry = _mk_entry(sheet, base_salary_nio="6000.00", has_inss=False)

    result = compute_entry(entry=entry)

    assert result.inss_laboral == Decimal("0.00")
    assert result.inss_patronal == Decimal("0.00")
    assert result.inatec == Decimal("0.00")


@pytest.mark.django_db
def test_compute_entry_with_overtime():
    company, _ = _mk_scope()
    actor = _actor()
    _mk_config(company, actor)
    period = _mk_period(company, actor)
    sheet = _mk_sheet(period, actor)
    entry = _mk_entry(sheet, base_salary_nio="6000.00")
    entry.overtime_hours = Decimal("8.00")
    entry.save(update_fields=["overtime_hours"])

    result = compute_entry(entry=entry)

    assert result.overtime_amount > Decimal("0.00")
    assert result.total_income > result.quincenal_salary


@pytest.mark.django_db
def test_compute_entry_with_subsidy_days():
    company, _ = _mk_scope()
    actor = _actor()
    _mk_config(company, actor)
    period = _mk_period(company, actor)
    sheet = _mk_sheet(period, actor)
    entry = _mk_entry(sheet, base_salary_nio="6000.00")
    entry.days_subsidy = Decimal("3.00")
    entry.save(update_fields=["days_subsidy"])

    result = compute_entry(entry=entry)

    assert result.subsidy_amount > Decimal("0.00")


@pytest.mark.django_db
def test_compute_entry_patronal_rate_small_vs_large():
    company, _ = _mk_scope()
    actor = _actor()
    _mk_config(company, actor)
    period = _mk_period(company, actor)
    sheet = _mk_sheet(period, actor)
    entry = _mk_entry(sheet, base_salary_nio="6000.00")

    # < threshold workers → tasa pequeña empresa
    compute_entry(entry=entry, worker_count=3)
    small_patronal = entry.inss_patronal

    # Reset
    entry.refresh_from_db()
    # > threshold workers → tasa grande empresa
    compute_entry(entry=entry, worker_count=999)
    large_patronal = entry.inss_patronal

    assert large_patronal > small_patronal


@pytest.mark.django_db
def test_compute_entry_total_payroll_cost_consistent():
    company, _ = _mk_scope()
    actor = _actor()
    _mk_config(company, actor)
    period = _mk_period(company, actor)
    sheet = _mk_sheet(period, actor)
    entry = _mk_entry(sheet, base_salary_nio="6000.00")

    result = compute_entry(entry=entry)

    expected_employer_cost = (
        result.inss_patronal + result.inatec +
        result.vacation_cost + result.thirteenth_month_cost
    ).quantize(Decimal("0.01"))
    assert result.total_employer_cost == expected_employer_cost
    assert result.total_payroll_cost == (result.net_to_pay + result.total_employer_cost).quantize(Decimal("0.01"))


# ---------------------------------------------------------------------------
# NM-01 — el IR se recalcula en cada compute_all (salvo override manual)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_ir_recomputed_on_recompute_when_not_manual():
    """NM-01: el IR NO queda obsoleto — recalcula contra la base gravable vigente."""
    company, _ = _mk_scope()
    actor = _actor()
    _mk_config(company, actor)
    period = _mk_period(company, actor)
    sheet = _mk_sheet(period, actor)
    # Salario alto → IR > 0 a período completo.
    entry = _mk_entry(sheet, base_salary_nio="18000.00", days_worked="15")
    compute_entry(entry=entry)
    ir_full = entry.ir_amount
    assert ir_full > Decimal("0.00")
    assert entry.ir_manual is False

    # Recompute con menos días → base gravable menor → el IR DEBE bajar.
    # (Antes del fix quedaba == ir_full porque el guard era `not self.ir_amount`.)
    entry.days_worked = Decimal("7")
    entry.save(update_fields=["days_worked"])
    compute_entry(entry=entry)
    assert entry.ir_amount < ir_full


@pytest.mark.django_db
def test_ir_manual_override_preserved_on_recompute():
    """NM-01: un IR fijado manualmente (ir_manual=True) no se recalcula."""
    company, _ = _mk_scope()
    actor = _actor()
    _mk_config(company, actor)
    period = _mk_period(company, actor)
    sheet = _mk_sheet(period, actor)
    entry = _mk_entry(sheet, base_salary_nio="18000.00", days_worked="15")
    entry.ir_amount = Decimal("123.45")
    entry.ir_manual = True
    entry.save(update_fields=["ir_amount", "ir_manual"])

    compute_entry(entry=entry)
    assert entry.ir_amount == Decimal("123.45")


# ---------------------------------------------------------------------------
# compute_all_entries_in_sheet
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_compute_all_entries_processes_multiple():
    company, _ = _mk_scope()
    actor = _actor()
    _mk_config(company, actor)
    period = _mk_period(company, actor)
    sheet = _mk_sheet(period, actor)

    _mk_entry(sheet, full_name="Empleado A", base_salary_nio="5000.00")
    _mk_entry(sheet, full_name="Empleado B", base_salary_nio="8000.00")
    _mk_entry(sheet, full_name="Empleado C", base_salary_nio="12000.00")

    count = compute_all_entries_in_sheet(sheet=sheet)

    assert count == 3
    for e in sheet.entries.all():
        assert e.quincenal_salary > Decimal("0.00")
        assert e.net_to_pay > Decimal("0.00")


# ---------------------------------------------------------------------------
# Ciclo de planilla: DRAFT → SUBMITTED → APPROVED
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_sheet_lifecycle_draft_submit_approve():
    company, _ = _mk_scope()
    actor = _actor()
    _mk_config(company, actor)
    period = _mk_period(company, actor)
    sheet = _mk_sheet(period, actor)
    req = _mock_request(actor)

    assert sheet.status == SheetStatus.DRAFT

    sheet = submit_sheet(request=req, actor=actor, sheet=sheet)
    assert sheet.status == SheetStatus.SUBMITTED

    sheet = approve_sheet(request=req, actor=actor, sheet=sheet)
    assert sheet.status == SheetStatus.APPROVED


@pytest.mark.django_db
def test_submit_sheet_from_non_draft_raises():
    company, _ = _mk_scope()
    actor = _actor()
    _mk_config(company, actor)
    period = _mk_period(company, actor)
    sheet = _mk_sheet(period, actor)
    req = _mock_request(actor)

    submit_sheet(request=req, actor=actor, sheet=sheet)
    # Ya está en SUBMITTED — no se puede enviar de nuevo
    with pytest.raises(ValueError, match="DRAFT"):
        submit_sheet(request=req, actor=actor, sheet=sheet)


@pytest.mark.django_db
def test_approve_sheet_from_non_submitted_raises():
    company, _ = _mk_scope()
    actor = _actor()
    _mk_config(company, actor)
    period = _mk_period(company, actor)
    sheet = _mk_sheet(period, actor)
    req = _mock_request(actor)

    # En DRAFT → no se puede aprobar directamente
    with pytest.raises(ValueError):
        approve_sheet(request=req, actor=actor, sheet=sheet)


# ---------------------------------------------------------------------------
# create_period — validaciones básicas
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_create_period_stores_correct_fields():
    company, _ = _mk_scope()
    actor = _actor()
    _mk_config(company, actor)
    period = _mk_period(company, actor, month=3, period_type=PeriodType.SECOND_HALF)

    assert period.company == company
    assert period.year == 2026
    assert period.month == 3
    assert period.period_type == PeriodType.SECOND_HALF
    assert period.working_days == 15
