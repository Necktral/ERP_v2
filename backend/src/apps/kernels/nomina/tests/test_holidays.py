from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from apps.kernels.nomina.models import (
    Holiday,
    HolidayDateKind,
    HolidayLegalType,
    PayrollPeriod,
    PeriodType,
    easter_sunday,
)
from apps.kernels.nomina.services import (
    holiday_dates_for_period,
    holidays_for_period,
)
from apps.modulos.iam.models import OrgUnit


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _company(suffix=""):
    s = suffix or uuid.uuid4().hex[:6]
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name=f"H_{s}")
    return OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name=f"C_{s}", parent=holding)


def _period(company, *, year=2026, month=5, start=(2026, 5, 1), end=(2026, 5, 15)):
    return PayrollPeriod.objects.create(
        company=company, year=year, month=month, period_type=PeriodType.FIRST_HALF,
        start_date=date(*start), end_date=date(*end), working_days=15,
    )


# ---------------------------------------------------------------------------
# easter_sunday — fechas conocidas del Domingo de Resurrección
# ---------------------------------------------------------------------------

def test_easter_sunday_known_years():
    assert easter_sunday(2024) == date(2024, 3, 31)
    assert easter_sunday(2025) == date(2025, 4, 20)
    assert easter_sunday(2026) == date(2026, 4, 5)
    assert easter_sunday(2027) == date(2027, 3, 28)


# ---------------------------------------------------------------------------
# Holiday.date_for_year — materialización de la fecha concreta
# ---------------------------------------------------------------------------

def test_date_for_year_fixed():
    h = Holiday(name="x", legal_type=HolidayLegalType.NACIONAL_OBLIGATORIO,
                date_kind=HolidayDateKind.FIXED, month=5, day=1)
    assert h.date_for_year(2026) == date(2026, 5, 1)
    assert h.date_for_year(2030) == date(2030, 5, 1)


def test_date_for_year_easter():
    jueves = Holiday(name="Jueves Santo", legal_type=HolidayLegalType.NACIONAL_OBLIGATORIO,
                     date_kind=HolidayDateKind.EASTER, easter_offset=-3)
    viernes = Holiday(name="Viernes Santo", legal_type=HolidayLegalType.NACIONAL_OBLIGATORIO,
                      date_kind=HolidayDateKind.EASTER, easter_offset=-2)
    # Pascua 2026 = 5 de abril
    assert jueves.date_for_year(2026) == date(2026, 4, 2)
    assert viernes.date_for_year(2026) == date(2026, 4, 3)


def test_date_for_year_one_off():
    h = Holiday(name="Decreto puntual", legal_type=HolidayLegalType.EMPRESA,
                date_kind=HolidayDateKind.ONE_OFF, specific_date=date(2026, 6, 15))
    assert h.date_for_year(2026) == date(2026, 6, 15)
    assert h.date_for_year(2027) is None


# ---------------------------------------------------------------------------
# Holiday.clean — validación cruzada por date_kind
# ---------------------------------------------------------------------------

def test_clean_fixed_requires_month_day():
    with pytest.raises(ValidationError):
        Holiday(name="x", legal_type=HolidayLegalType.NACIONAL_OBLIGATORIO,
                date_kind=HolidayDateKind.FIXED).clean()


def test_clean_easter_requires_offset():
    with pytest.raises(ValidationError):
        Holiday(name="x", legal_type=HolidayLegalType.NACIONAL_OBLIGATORIO,
                date_kind=HolidayDateKind.EASTER).clean()


def test_clean_one_off_requires_date():
    with pytest.raises(ValidationError):
        Holiday(name="x", legal_type=HolidayLegalType.EMPRESA,
                date_kind=HolidayDateKind.ONE_OFF).clean()


def test_clean_fixed_rejects_easter_offset():
    with pytest.raises(ValidationError):
        Holiday(name="x", legal_type=HolidayLegalType.NACIONAL_OBLIGATORIO,
                date_kind=HolidayDateKind.FIXED, month=5, day=1, easter_offset=-3).clean()


# ---------------------------------------------------------------------------
# Seed — catálogo nacional precargado por la data migration
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_seed_national_catalog_loaded():
    obligatorios = Holiday.objects.filter(
        company__isnull=True, legal_type=HolidayLegalType.NACIONAL_OBLIGATORIO,
    )
    # 9 obligatorios: año nuevo, jueves/viernes santo, trabajo, revolución,
    # san jacinto, independencia, purísima, navidad.
    assert obligatorios.count() == 9
    assert obligatorios.filter(code="ni-ano-nuevo", month=1, day=1).exists()
    assert obligatorios.filter(code="ni-jueves-santo", easter_offset=-3).exists()


@pytest.mark.django_db
def test_seed_estatal_not_payroll_by_default():
    difuntos = Holiday.objects.get(company__isnull=True, code="ni-difuntos")
    assert difuntos.legal_type == HolidayLegalType.ASUETO_ESTATAL
    assert difuntos.applies_to_payroll is False


# ---------------------------------------------------------------------------
# holidays_for_period — el revisor ubica los feriados del período
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_holidays_for_period_fixed_in_range():
    company = _company()
    period = _period(company, month=5, start=(2026, 5, 1), end=(2026, 5, 15))
    resolved = holidays_for_period(period)
    dates = {r.date for r in resolved}
    assert date(2026, 5, 1) in dates  # Día del Trabajo
    names = {r.name for r in resolved}
    assert any("Trabajo" in n for n in names)


@pytest.mark.django_db
def test_holidays_for_period_semana_santa():
    company = _company()
    # Abril 2026: Pascua = 5 abril → Jueves Santo 2 abr, Viernes Santo 3 abr
    period = _period(company, month=4, start=(2026, 4, 1), end=(2026, 4, 15))
    dates = holiday_dates_for_period(period)
    assert date(2026, 4, 2) in dates
    assert date(2026, 4, 3) in dates


@pytest.mark.django_db
def test_holidays_for_period_only_payroll_excludes_estatal():
    company = _company()
    # Noviembre 2026 cubre el 2 (Día de los Difuntos, asueto estatal)
    period = _period(company, month=11, start=(2026, 11, 1), end=(2026, 11, 15))
    all_dates = holiday_dates_for_period(period, only_payroll=False)
    payroll_dates = holiday_dates_for_period(period, only_payroll=True)
    assert date(2026, 11, 2) in all_dates
    assert date(2026, 11, 2) not in payroll_dates


@pytest.mark.django_db
def test_holidays_for_period_company_specific():
    company = _company()
    Holiday.objects.create(
        company=company, code=f"emp-aniv-{uuid.uuid4().hex[:6]}",
        name="Aniversario de la empresa", legal_type=HolidayLegalType.EMPRESA,
        date_kind=HolidayDateKind.FIXED, month=5, day=10,
        applies_to_payroll=True, pays_premium=False, premium_rate=Decimal("1.50"),
    )
    period = _period(company, month=5, start=(2026, 5, 1), end=(2026, 5, 15))

    with_company = holiday_dates_for_period(period, only_payroll=False)
    assert date(2026, 5, 10) in with_company

    national_only = {
        r.date for r in holidays_for_period(period, include_company_specific=False)
    }
    assert date(2026, 5, 10) not in national_only


@pytest.mark.django_db
def test_holidays_for_period_sorted_by_date():
    company = _company()
    # Septiembre cubre 14 (San Jacinto) y 15 (Independencia)
    period = _period(company, month=9, start=(2026, 9, 1), end=(2026, 9, 15))
    resolved = holidays_for_period(period)
    dates = [r.date for r in resolved]
    assert dates == sorted(dates)
    assert date(2026, 9, 14) in dates
    assert date(2026, 9, 15) in dates
