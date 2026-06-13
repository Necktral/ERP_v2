"""Tests de costos de flota (Ola G): combustible con consumo, mantenimiento con costo,
gastos y resumen (costo/km, rendimiento)."""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from apps.modulos.fleet.models import AssetType, FleetAsset, MeterBasis
from apps.modulos.fleet.services import FleetError
from apps.modulos.fleet.services_costs import (
    asset_cost_summary,
    record_expense,
    record_fuel_log,
    record_work_order,
)
from apps.modulos.iam.models import OrgUnit

User = get_user_model()
UT = OrgUnit.UnitType


def _mk_company():
    s = uuid.uuid4().hex[:6]
    holding = OrgUnit.objects.create(unit_type=UT.HOLDING, name=f"H_{s}")
    return OrgUnit.objects.create(unit_type=UT.COMPANY, name=f"C_{s}", parent=holding)


def _mk_user():
    u = f"fl_{uuid.uuid4().hex[:8]}"
    return User.objects.create_user(username=u, email=f"{u}@t.local", password="pass12345")


def _mk_asset(company, odo="1000"):
    return FleetAsset.objects.create(
        company=company, asset_type=AssetType.choices[0][0], code=f"A{uuid.uuid4().hex[:4]}",
        name="Camión", meter_basis=MeterBasis.ODOMETER_KM, current_odometer_km=Decimal(odo),
    )


@pytest.mark.django_db
def test_fuel_log_computes_total_and_distance():
    company = _mk_company()
    actor = _mk_user()
    asset = _mk_asset(company, odo="1000")
    log1 = record_fuel_log(company=company, actor=actor, asset_id=asset.id, liters=Decimal("40"), unit_cost=Decimal("1.5"), meter_reading=Decimal("1000"))
    assert log1.total_cost == Decimal("60.00")
    assert log1.distance_since_last == Decimal("0.00")
    log2 = record_fuel_log(company=company, actor=actor, asset_id=asset.id, liters=Decimal("30"), unit_cost=Decimal("1.5"), meter_reading=Decimal("1300"))
    assert log2.distance_since_last == Decimal("300.00")
    asset.refresh_from_db()
    assert asset.current_odometer_km == Decimal("1300.00")


@pytest.mark.django_db
def test_work_order_total_is_labor_plus_parts():
    company = _mk_company()
    actor = _mk_user()
    asset = _mk_asset(company)
    wo = record_work_order(
        company=company, actor=actor, asset_id=asset.id, description="Cambio de aceite",
        labor_cost=Decimal("200"), parts_cost=Decimal("300"),
    )
    assert wo.total_cost == Decimal("500.00")
    assert wo.status == "DONE"
    assert wo.completed_at is not None


@pytest.mark.django_db
def test_cost_summary_aggregates_and_computes_ratios():
    company = _mk_company()
    actor = _mk_user()
    asset = _mk_asset(company, odo="1000")
    record_fuel_log(company=company, actor=actor, asset_id=asset.id, liters=Decimal("40"), unit_cost=Decimal("1.5"), meter_reading=Decimal("1000"))
    record_fuel_log(company=company, actor=actor, asset_id=asset.id, liters=Decimal("30"), unit_cost=Decimal("1.5"), meter_reading=Decimal("1300"))
    record_work_order(company=company, actor=actor, asset_id=asset.id, description="Frenos", labor_cost=Decimal("200"), parts_cost=Decimal("300"))
    record_expense(company=company, actor=actor, asset_id=asset.id, category="TIRES", amount=Decimal("800"))

    s = asset_cost_summary(company=company, asset_id=asset.id)
    assert s["fuel_total"] == "105.00"
    assert s["maintenance_total"] == "500.00"
    assert s["expense_total"] == "800.00"
    assert s["grand_total"] == "1405.00"
    assert s["liters_total"] == "70.00"
    assert s["distance_total"] == "300.00"
    assert s["cost_per_unit"] is not None  # 1405 / 300
    assert s["consumption"] is not None     # 300 / 70 km/L
    assert s["cost_per_unit_label"] == "Costo/km"


@pytest.mark.django_db
def test_invalid_inputs_rejected():
    company = _mk_company()
    actor = _mk_user()
    asset = _mk_asset(company)
    with pytest.raises(FleetError):
        record_fuel_log(company=company, actor=actor, asset_id=asset.id, liters=Decimal("0"), unit_cost=Decimal("1"))
    with pytest.raises(FleetError):
        record_expense(company=company, actor=actor, asset_id=asset.id, category="TIRES", amount=Decimal("0"))
    with pytest.raises(FleetError):
        record_work_order(company=company, actor=actor, asset_id=asset.id, description="  ")


@pytest.mark.django_db
def test_summary_other_company_asset_rejected():
    c1 = _mk_company()
    c2 = _mk_company()
    asset2 = _mk_asset(c2)
    with pytest.raises(FleetError):
        asset_cost_summary(company=c1, asset_id=asset2.id)
