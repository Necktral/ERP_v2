"""
Tests del módulo estacion_servicios (Fuel).

Conversiones canónicas (litros / precio por litro, cuantización de dinero y
volumen), helpers de inventario y backoff de compensación, y los flujos
autocontenidos de turno y despacho (open/close shift idempotente, record_dispense
con cálculo de montos canónicos y delta, reporte de cierre de turno). El flujo de
venta (integración billing+inventory) queda fuera de alcance aquí.
"""
from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.exceptions import ValidationError as DRFValidationError

from apps.modulos.estacion_servicios.models import (
    GALLON_TO_LITER,
    FuelDispense,
    FuelPriceUOM,
    FuelProduct,
    FuelShiftStatus,
    FuelVolumeUOM,
)
from apps.modulos.estacion_servicios.services import (
    _dt_range_from_query,
    _fuel_inventory_name,
    _fuel_inventory_sku,
    _gallons_from_liters,
    _money,
    _next_compensation_retry_at,
    _to_liters,
    _to_unit_price_per_liter,
    _volume,
    build_shift_close_report,
    close_shift,
    open_shift,
    record_dispense,
    run_fuel_compensation_cycle,
)
from apps.modulos.iam.models import OrgUnit

User = get_user_model()
UT = OrgUnit.UnitType


def _mk_scope():
    s = uuid.uuid4().hex[:6]
    holding = OrgUnit.objects.create(unit_type=UT.HOLDING, name=f"H_{s}")
    company = OrgUnit.objects.create(unit_type=UT.COMPANY, name=f"C_{s}", parent=holding)
    branch = OrgUnit.objects.create(unit_type=UT.BRANCH, name=f"B_{s}", parent=company)
    user = User.objects.create_user(username=f"fuel_{s}", email=f"{s}@test.local", password="pass12345")
    return company, branch, user


# ---------------------------------------------------------------------------
# Conversiones puras
# ---------------------------------------------------------------------------

def test_to_liters_conversions():
    assert _to_liters(volume_entered=Decimal("10"), volume_uom=FuelVolumeUOM.LITER) == Decimal("10.0000")
    assert _to_liters(volume_entered=Decimal("1"), volume_uom=FuelVolumeUOM.GALLON) == _volume(GALLON_TO_LITER)
    with pytest.raises(DRFValidationError):
        _to_liters(volume_entered=Decimal("1"), volume_uom="BARREL")


def test_to_unit_price_per_liter_conversions():
    assert _to_unit_price_per_liter(unit_price_entered=Decimal("5"), unit_price_uom=FuelPriceUOM.PER_LITER) == Decimal("5.0000")
    expected = _volume(Decimal("10") / GALLON_TO_LITER)
    assert _to_unit_price_per_liter(unit_price_entered=Decimal("10"), unit_price_uom=FuelPriceUOM.PER_GALLON) == expected
    with pytest.raises(DRFValidationError):
        _to_unit_price_per_liter(unit_price_entered=Decimal("1"), unit_price_uom="PER_BARREL")


def test_money_and_volume_quantization():
    assert _money(Decimal("1.005")) == Decimal("1.01")
    assert _volume(Decimal("1.00005")) == Decimal("1.0001")


def test_gallons_from_liters_roundtrip():
    assert _gallons_from_liters(GALLON_TO_LITER) == Decimal("1.0000")


def test_fuel_inventory_sku_and_name():
    assert _fuel_inventory_sku("diesel") == "FUEL-DIESEL"
    assert _fuel_inventory_name("diesel") == "Fuel Diesel"


def test_next_compensation_retry_backoff():
    now = timezone.now()
    assert _next_compensation_retry_at(now=now, attempt=1) == now + timedelta(minutes=2)
    # Tope de backoff en 60 minutos.
    assert _next_compensation_retry_at(now=now, attempt=10) == now + timedelta(minutes=60)


def test_dt_range_from_query_dates_and_invalid():
    dt_from, dt_to = _dt_range_from_query(from_s="2026-01-01", to_s="2026-01-03")
    assert dt_from is not None and dt_to is not None
    assert dt_from < dt_to
    assert dt_from.date().isoformat() == "2026-01-01"
    # ISO datetime con hora explícita se respeta.
    dt_h, _ = _dt_range_from_query(from_s="2026-01-01T08:30:00", to_s=None)
    assert dt_h.hour == 8 and dt_h.minute == 30
    assert _dt_range_from_query(from_s=None, to_s=None) == (None, None)
    with pytest.raises(DRFValidationError):
        _dt_range_from_query(from_s="not-a-date", to_s=None)


# ---------------------------------------------------------------------------
# Turnos (shift)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_open_shift_creates_and_dedupes():
    company, branch, user = _mk_scope()
    res = open_shift(company=company, branch=branch, actor_user=user)
    assert res.duplicate is False
    assert res.shift.status == FuelShiftStatus.OPEN

    res2 = open_shift(company=company, branch=branch, actor_user=user)
    assert res2.duplicate is True
    assert res2.shift.id == res.shift.id


@pytest.mark.django_db
def test_open_shift_requires_branch():
    company, branch, user = _mk_scope()
    with pytest.raises(DRFValidationError):
        open_shift(company=company, branch=None, actor_user=user)


@pytest.mark.django_db
def test_close_shift_and_double_close():
    company, branch, user = _mk_scope()
    shift = open_shift(company=company, branch=branch, actor_user=user).shift
    closed = close_shift(shift=shift, actor_user=user)
    assert closed.status == FuelShiftStatus.CLOSED
    assert closed.closed_at is not None
    with pytest.raises(DRFValidationError):
        close_shift(shift=closed, actor_user=user)


# ---------------------------------------------------------------------------
# Despachos (dispense)
# ---------------------------------------------------------------------------

def _record(company, branch, user, shift, **over):
    params = dict(
        company=company,
        branch=branch,
        shift=shift,
        actor_user=user,
        product=FuelProduct.DIESEL,
        volume_entered=Decimal("10"),
        volume_uom=FuelVolumeUOM.LITER,
        unit_price_entered=Decimal("5"),
        unit_price_uom=FuelPriceUOM.PER_LITER,
    )
    params.update(over)
    return record_dispense(**params)


@pytest.mark.django_db
def test_record_dispense_computes_canonical_amounts():
    company, branch, user = _mk_scope()
    shift = open_shift(company=company, branch=branch, actor_user=user).shift
    d = _record(company, branch, user, shift)
    assert d.liters == Decimal("10.0000")
    assert d.amount == Decimal("50.00")
    assert d.amount_canonical == Decimal("50.00")
    assert d.amount_delta == Decimal("0.00")
    assert FuelDispense.objects.filter(pk=d.pk).exists()


@pytest.mark.django_db
def test_record_dispense_rejected_on_closed_shift():
    company, branch, user = _mk_scope()
    shift = open_shift(company=company, branch=branch, actor_user=user).shift
    close_shift(shift=shift, actor_user=user)
    with pytest.raises(DRFValidationError):
        _record(company, branch, user, shift)


# ---------------------------------------------------------------------------
# Reportes y ciclo de compensación
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_build_shift_close_report_aggregates():
    company, branch, user = _mk_scope()
    shift = open_shift(company=company, branch=branch, actor_user=user).shift
    _record(company, branch, user, shift)
    report = build_shift_close_report(company=company, branch=branch, shift=shift)
    assert report["counts"]["dispenses"] == 1
    assert any(row["key"] == FuelProduct.DIESEL for row in report["totals_by_product"])


@pytest.mark.django_db
def test_run_fuel_compensation_cycle_with_nothing_due():
    company, branch, _user = _mk_scope()
    res = run_fuel_compensation_cycle(company=company, branch=branch)
    assert (res.attempted, res.succeeded, res.failed, res.still_pending) == (0, 0, 0, 0)
    assert res.errors == []
