"""Tests de Flota Fase A: activos, conductores, documentos con vencimiento → notificación,
mantenimiento vencido → notificación (con guarda de salto de odómetro), y HTTP/RBAC.
"""
from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from apps.modulos.fleet.alerts import run_fleet_alerts
from apps.modulos.fleet.models import (
    AssetMaintenanceState,
    AssetStatus,
    AssetType,
    DocumentType,
    FleetAsset,
    TriggerBasis,
)
from apps.modulos.fleet.services import (
    add_rule,
    apply_plan_to_asset,
    assign_driver,
    create_plan,
    record_meter_reading,
    register_document,
    upsert_asset,
    upsert_driver,
    upsert_maintenance_type,
)
from apps.modulos.notifications.models import NotificationRecord
from apps.modulos.notifications.services import dispatch_fleet_notifications
from apps.modulos.iam.models import OrgUnit, UserMembership
from apps.modulos.rbac.models import Permission, Role, RoleAssignment, RolePermission

User = get_user_model()
UT = OrgUnit.UnitType


def _scope():
    t = uuid.uuid4().hex[:6]
    holding = OrgUnit.objects.create(unit_type=UT.HOLDING, name=f"H{t}", code=f"H-{t}")
    company = OrgUnit.objects.create(unit_type=UT.COMPANY, parent=holding, name=f"C{t}", code=f"C-{t}")
    branch = OrgUnit.objects.create(unit_type=UT.BRANCH, parent=company, name=f"B{t}", code=f"B-{t}")
    return holding, company, branch


def _user():
    t = uuid.uuid4().hex[:8]
    return User.objects.create_user(username=f"u_{t}", email=f"u_{t}@t.local", password="pass12345")


def _req(company, branch, user):
    return SimpleNamespace(
        company=company, branch=branch, user=user, META={}, headers={},
        path="/test/fleet/", method="POST", request_id=f"req-{uuid.uuid4().hex[:8]}",
    )


def _supervisor(company):
    """Usuario con rol fleet_supervisor en la empresa (destinatario de alertas)."""
    u = _user()
    role, _ = Role.objects.get_or_create(name="fleet_supervisor", defaults={"is_active": True})
    RoleAssignment.objects.create(user=u, role=role, org_unit=company, is_active=True)
    return u


def _asset(req, company, *, code="V1", asset_type=AssetType.VEHICLE, **extra):
    return upsert_asset(
        request=req, actor=req.user, company=company, code=code, name="Land Cruiser",
        asset_type=asset_type, **extra,
    )


# ---------------------------------------------------------------------------
# Activos / conductores
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_asset_upsert_each_type_and_obd_persists():
    _h, company, branch = _scope()
    req = _req(company, branch, _user())
    veh = _asset(req, company, code="LC1", asset_type=AssetType.VEHICLE, has_obd=True, obd_protocol="OBD2_12V")
    mach = _asset(req, company, code="MX1", asset_type=AssetType.MACHINERY)
    stat = _asset(req, company, code="GEN1", asset_type=AssetType.STATIONARY)
    assert {veh.asset_type, mach.asset_type, stat.asset_type} == {"VEHICLE", "MACHINERY", "STATIONARY"}
    veh.refresh_from_db()
    assert veh.has_obd is True and veh.obd_protocol == "OBD2_12V"
    # upsert idempotente por (company, code)
    again = _asset(req, company, code="LC1", asset_type=AssetType.VEHICLE)
    assert again.id == veh.id
    assert FleetAsset.objects.filter(company=company).count() == 3


@pytest.mark.django_db
def test_driver_and_assignment():
    _h, company, branch = _scope()
    req = _req(company, branch, _user())
    asset = _asset(req, company, code="LC2")
    driver = upsert_driver(
        request=req, actor=req.user, company=company, full_name="Juan Pérez",
        license_number="LIC-001", license_category="C",
    )
    asg = assign_driver(request=req, actor=req.user, asset=asset, driver=driver)
    assert asg.is_active is True
    assert driver.assignments.filter(is_active=True).count() == 1


# ---------------------------------------------------------------------------
# Documento por vencer → notificación
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_document_expiry_emits_notification_idempotent():
    _h, company, branch = _scope()
    req = _req(company, branch, _user())
    recipient = _supervisor(company)
    asset = _asset(req, company, code="LC3")
    register_document(
        request=req, actor=req.user, company=company, doc_type=DocumentType.INSURANCE,
        asset=asset, number="SEG-1", expiry_date=timezone.localdate() + timedelta(days=10),
    )

    run_fleet_alerts(company=company, horizon_days=30)
    dispatch_fleet_notifications()

    recs = NotificationRecord.objects.filter(recipient_user=recipient, event_type="DocumentExpiring")
    assert recs.count() == 1
    assert recs.first().status == "SENT"

    # Idempotente: re-correr no duplica (doc ya EXPIRING + dedupe_key).
    run_fleet_alerts(company=company, horizon_days=30)
    dispatch_fleet_notifications()
    assert NotificationRecord.objects.filter(recipient_user=recipient, event_type="DocumentExpiring").count() == 1


# ---------------------------------------------------------------------------
# Mantenimiento vencido → notificación + guarda de salto
# ---------------------------------------------------------------------------

def _plan_with_km_rule(company, *, interval_km):
    mt = upsert_maintenance_type(company=company, code="OIL", name="Cambio de aceite", trigger_basis=TriggerBasis.KM)
    plan = create_plan(company=company, name="Plan liviano")
    add_rule(plan=plan, maintenance_type=mt, trigger_basis=TriggerBasis.KM, interval_km=Decimal(interval_km))
    return plan


@pytest.mark.django_db
def test_maintenance_due_emits_notification():
    _h, company, branch = _scope()
    req = _req(company, branch, _user())
    recipient = _supervisor(company)
    asset = _asset(req, company, code="LC4")

    record_meter_reading(request=req, actor=req.user, asset=asset, odometer_km="200")
    asset.refresh_from_db()
    plan = _plan_with_km_rule(company, interval_km="300")
    apply_plan_to_asset(asset=asset, plan=plan)  # next_due_km = 200 + 300 = 500

    res = record_meter_reading(request=req, actor=req.user, asset=asset, odometer_km="500")  # salto 300, ok
    assert res["verified"] is True

    run_fleet_alerts(company=company)
    dispatch_fleet_notifications()

    asset.refresh_from_db()
    assert asset.status == AssetStatus.MAINTENANCE_DUE
    assert NotificationRecord.objects.filter(recipient_user=recipient, event_type="MaintenanceDue").count() == 1


@pytest.mark.django_db
def test_meter_jump_over_500_does_not_advance_or_trigger():
    _h, company, branch = _scope()
    req = _req(company, branch, _user())
    _supervisor(company)
    asset = _asset(req, company, code="LC5")
    record_meter_reading(request=req, actor=req.user, asset=asset, odometer_km="200")
    asset.refresh_from_db()
    plan = _plan_with_km_rule(company, interval_km="300")
    apply_plan_to_asset(asset=asset, plan=plan)  # next_due_km = 500

    res = record_meter_reading(request=req, actor=req.user, asset=asset, odometer_km="2000")  # salto 1800 > 500
    assert res["verified"] is False
    asset.refresh_from_db()
    assert asset.current_odometer_km == Decimal("200.00")  # no avanzó

    run_fleet_alerts(company=company)
    dispatch_fleet_notifications()
    asset.refresh_from_db()
    assert asset.status == AssetStatus.ACTIVE  # no se marcó vencido
    assert NotificationRecord.objects.filter(event_type="MaintenanceDue").count() == 0


@pytest.mark.django_db
def test_meter_decreasing_reading_is_unverified():
    """FL-01: una lectura decreciente no retrocede el oficial y queda no verificada."""
    _h, company, branch = _scope()
    req = _req(company, branch, _user())
    asset = _asset(req, company, code="LC6")
    record_meter_reading(request=req, actor=req.user, asset=asset, odometer_km="1000")
    asset.refresh_from_db()

    res = record_meter_reading(request=req, actor=req.user, asset=asset, odometer_km="800")  # decreciente
    assert res["verified"] is False
    asset.refresh_from_db()
    assert asset.current_odometer_km == Decimal("1000.00")  # no retrocedió


@pytest.mark.django_db
def test_apply_plan_does_not_reset_due_flag():
    """FL-03: re-aplicar el plan no oculta un mantenimiento ya marcado vencido."""
    _h, company, branch = _scope()
    req = _req(company, branch, _user())
    asset = _asset(req, company, code="LC7")
    record_meter_reading(request=req, actor=req.user, asset=asset, odometer_km="200")
    asset.refresh_from_db()
    plan = _plan_with_km_rule(company, interval_km="300")
    apply_plan_to_asset(asset=asset, plan=plan)

    # Cruza el umbral → queda vencido.
    record_meter_reading(request=req, actor=req.user, asset=asset, odometer_km="500")
    run_fleet_alerts(company=company)
    state = AssetMaintenanceState.objects.get(asset=asset)
    assert state.is_due is True

    # Re-aplicar el plan NO debe resetear is_due.
    apply_plan_to_asset(asset=asset, plan=plan)
    state.refresh_from_db()
    assert state.is_due is True


# ---------------------------------------------------------------------------
# HTTP + RBAC
# ---------------------------------------------------------------------------

def _client(user, company, branch, perms: list[str]) -> APIClient:
    UserMembership.objects.get_or_create(user=user, org_unit=company, defaults={"is_active": True})
    UserMembership.objects.get_or_create(user=user, org_unit=branch, defaults={"is_active": True})
    role = Role.objects.create(name=f"r_{uuid.uuid4().hex[:8]}", is_active=True)
    for code in perms:
        perm, _ = Permission.objects.get_or_create(code=code, defaults={"description": code, "is_active": True})
        RolePermission.objects.get_or_create(role=role, permission=perm)
    RoleAssignment.objects.create(user=user, role=role, org_unit=company, is_active=True)
    RoleAssignment.objects.create(user=user, role=role, org_unit=branch, is_active=True)
    c = APIClient()
    login = c.post("/api/auth/login/", {"username": user.username, "password": "pass12345"},
                   format="json", HTTP_X_AUTH_TRANSPORT="header")
    assert login.status_code == 200, login.data
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data.get('access')}")
    c.defaults["HTTP_X_AUTH_TRANSPORT"] = "header"
    c.defaults["HTTP_X_COMPANY_ID"] = str(company.id)
    c.defaults["HTTP_X_BRANCH_ID"] = str(branch.id)
    return c


@pytest.mark.django_db
def test_asset_endpoint_forbidden_without_perm():
    _h, company, branch = _scope()
    api = _client(_user(), company, branch, ["fleet.asset.read"])  # sin manage
    r = api.post("/api/fleet/assets/",
                 {"code": "X1", "name": "X", "asset_type": "VEHICLE"}, format="json")
    assert r.status_code == 403


@pytest.mark.django_db
def test_asset_endpoint_create_and_list_http():
    _h, company, branch = _scope()
    api = _client(_user(), company, branch, ["fleet.asset.manage", "fleet.asset.read"])
    r = api.post("/api/fleet/assets/",
                 {"code": "T1", "name": "Tractor", "asset_type": "MACHINERY", "has_obd": False},
                 format="json")
    assert r.status_code == 201, r.data
    assert r.data["asset_type"] == "MACHINERY"
    r2 = api.get("/api/fleet/assets/")
    assert r2.status_code == 200
    assert any(a["code"] == "T1" for a in r2.data)
