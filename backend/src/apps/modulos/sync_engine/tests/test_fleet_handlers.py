"""Tests del handler de sync_engine para captura de campo de flota (lectura de medidor)."""
from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest

from apps.modulos.fleet.models import AssetType, FleetAsset
from apps.modulos.iam.models import OrgUnit
from apps.modulos.sync_engine.errors import SyncRejectError
from apps.modulos.sync_engine.handlers_fleet import handle_fleet_record_meter

UT = OrgUnit.UnitType


def _scope():
    t = uuid.uuid4().hex[:6]
    holding = OrgUnit.objects.create(unit_type=UT.HOLDING, name=f"H{t}", code=f"H-{t}")
    company = OrgUnit.objects.create(unit_type=UT.COMPANY, parent=holding, name=f"C{t}", code=f"C-{t}")
    branch = OrgUnit.objects.create(unit_type=UT.BRANCH, parent=company, name=f"B{t}", code=f"B-{t}")
    return company, branch


def _req():
    return SimpleNamespace(
        company=None, branch=None, user=None, META={}, headers={},
        path="/sync/", method="POST", request_id=f"req-{uuid.uuid4().hex[:8]}",
    )


def _ctx(company, branch):
    return {
        "request": _req(), "company_id": company.id, "branch_id": branch.id,
        "command_id": str(uuid.uuid4()), "command_type": "FLEET_RECORD_METER", "actor_user": None,
    }


def _asset(company):
    return FleetAsset.objects.create(
        company=company, asset_type=AssetType.VEHICLE, code=f"V{uuid.uuid4().hex[:4]}", name="LC",
    )


@pytest.mark.django_db
def test_record_meter_command_updates_asset():
    company, branch = _scope()
    asset = _asset(company)
    res = handle_fleet_record_meter(_ctx(company, branch), {"asset_id": asset.id, "odometer_km": "120"})
    assert res["refs"]["asset_id"] == asset.id
    assert res["refs"]["verified"] is True
    asset.refresh_from_db()
    assert asset.current_odometer_km == Decimal("120.00")


@pytest.mark.django_db
def test_record_meter_unknown_asset_rejected():
    company, branch = _scope()
    with pytest.raises(SyncRejectError) as ei:
        handle_fleet_record_meter(_ctx(company, branch), {"asset_id": 999999, "odometer_km": "10"})
    assert ei.value.reason_code == "FLEET_NOT_FOUND"


@pytest.mark.django_db
def test_record_meter_requires_a_meter_value():
    company, branch = _scope()
    asset = _asset(company)
    with pytest.raises(SyncRejectError) as ei:
        handle_fleet_record_meter(_ctx(company, branch), {"asset_id": asset.id})
    assert ei.value.reason_code == "FLEET_SCHEMA_INVALID"


@pytest.mark.django_db
def test_record_meter_invalid_scope_rejected():
    company, branch = _scope()
    asset = _asset(company)
    ctx = _ctx(company, branch)
    ctx["company_id"] = 999999  # empresa inexistente
    with pytest.raises(SyncRejectError) as ei:
        handle_fleet_record_meter(ctx, {"asset_id": asset.id, "odometer_km": "10"})
    assert ei.value.reason_code == "FLEET_INVALID_SCOPE"


@pytest.mark.django_db
def test_record_meter_missing_and_invalid_asset_id():
    company, branch = _scope()
    with pytest.raises(SyncRejectError) as e1:
        handle_fleet_record_meter(_ctx(company, branch), {"odometer_km": "10"})  # sin asset_id
    assert e1.value.reason_code == "FLEET_SCHEMA_INVALID"
    with pytest.raises(SyncRejectError) as e2:
        handle_fleet_record_meter(_ctx(company, branch), {"asset_id": "abc", "odometer_km": "10"})
    assert e2.value.reason_code == "FLEET_SCHEMA_INVALID"


@pytest.mark.django_db
def test_record_meter_unknown_branch_rejected():
    company, branch = _scope()
    asset = _asset(company)
    ctx = _ctx(company, branch)
    ctx["branch_id"] = 999999  # sucursal inexistente bajo la empresa
    with pytest.raises(SyncRejectError) as ei:
        handle_fleet_record_meter(ctx, {"asset_id": asset.id, "odometer_km": "10"})
    assert ei.value.reason_code == "FLEET_INVALID_SCOPE"
