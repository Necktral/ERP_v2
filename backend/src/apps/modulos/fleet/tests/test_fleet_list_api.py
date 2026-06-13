"""Tests de los listados GET de flota (conductores, tipos y planes de mantenimiento)."""
from __future__ import annotations

import uuid

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.modulos.fleet.models import Driver, MaintenancePlan, MaintenanceType
from apps.modulos.iam.models import OrgUnit, UserMembership
from apps.modulos.rbac.models import Permission, Role, RoleAssignment, RolePermission

User = get_user_model()


def _mk_org():
    s = uuid.uuid4().hex[:6]
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name=f"H_{s}")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name=f"C_{s}", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name=f"B_{s}", parent=company)
    return holding, company, branch


def _client(*, company, branch, perms):
    username = f"fl_{uuid.uuid4().hex[:8]}"
    user = User.objects.create_user(username=username, email=f"{username}@test.local", password="pass12345")
    UserMembership.objects.create(user=user, org_unit=company, is_active=True)
    role = Role.objects.create(name=f"role_{uuid.uuid4().hex[:8]}", is_active=True)
    for code in perms:
        perm, _ = Permission.objects.get_or_create(code=code, defaults={"description": code, "is_active": True})
        RolePermission.objects.get_or_create(role=role, permission=perm)
    RoleAssignment.objects.create(user=user, role=role, org_unit=company, is_active=True)
    client = APIClient()
    login = client.post("/api/auth/login/", {"username": user.username, "password": "pass12345"}, format="json")
    assert login.status_code == 200
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data.get('access')}")
    client.defaults["HTTP_X_COMPANY_ID"] = str(company.id)
    client.defaults["HTTP_X_BRANCH_ID"] = str(branch.id)
    return client


@pytest.mark.django_db
def test_list_drivers_and_maintenance_catalogs_scoped():
    _, company, branch = _mk_org()
    _, other, _ = _mk_org()
    client = _client(
        company=company, branch=branch, perms=("fleet.driver.read", "fleet.maintenance.read")
    )

    Driver.objects.create(company=company, full_name="Carlos Conductor", license_number="A123")
    Driver.objects.create(company=other, full_name="Ajeno", license_number="B999")
    MaintenanceType.objects.create(company=company, code="OIL", name="Cambio de aceite")
    MaintenancePlan.objects.create(company=company, name="Plan camiones")

    r = client.get("/api/fleet/drivers/")
    assert r.status_code == 200 and len(r.data) == 1
    assert r.data[0]["full_name"] == "Carlos Conductor"

    r = client.get("/api/fleet/maintenance/types/")
    assert r.status_code == 200 and len(r.data) == 1 and r.data[0]["code"] == "OIL"

    r = client.get("/api/fleet/maintenance/plans/")
    assert r.status_code == 200 and len(r.data) == 1 and r.data[0]["name"] == "Plan camiones"


@pytest.mark.django_db
def test_list_drivers_requires_read_perm():
    _, company, branch = _mk_org()
    sin_perm = _client(company=company, branch=branch, perms=("fleet.asset.read",))
    assert sin_perm.get("/api/fleet/drivers/").status_code == 403
    assert sin_perm.get("/api/fleet/maintenance/types/").status_code == 403
