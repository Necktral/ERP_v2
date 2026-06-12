"""Tests de la API de administración RBAC por usuario (asignar/revocar/preview)."""
from __future__ import annotations

import uuid

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from rest_framework.test import APIClient

from apps.modulos.iam.models import OrgUnit, UserMembership
from apps.modulos.rbac.models import Permission, Role, RoleAssignment, RolePermission
from apps.modulos.rbac.services import assign_role, revoke_role_assignment

User = get_user_model()


def _mk_org():
    s = uuid.uuid4().hex[:6]
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name=f"H_{s}")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name=f"C_{s}", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name=f"B_{s}", parent=company)
    return holding, company, branch


def _mk_user(prefix="rb"):
    username = f"{prefix}_{uuid.uuid4().hex[:8]}"
    return User.objects.create_user(username=username, email=f"{username}@test.local", password="pass12345")


def _role_with_perm(code):
    role = Role.objects.create(name=f"role_{uuid.uuid4().hex[:8]}", is_active=True)
    perm, _ = Permission.objects.get_or_create(code=code, defaults={"description": code, "is_active": True})
    RolePermission.objects.create(role=role, permission=perm)
    return role


# --- Servicio ---------------------------------------------------------------

@pytest.mark.django_db
def test_assign_role_creates_idempotent_and_reactivates():
    _, company, _ = _mk_org()
    admin = _mk_user("admin")
    target = _mk_user("target")
    role = _role_with_perm("inventory.read")

    ra1 = assign_role(user=target, role=role, org_unit=company, granted_by=admin, scope_company=company)
    assert ra1.is_active is True
    ra2 = assign_role(user=target, role=role, org_unit=company, granted_by=admin, scope_company=company)
    assert ra2.id == ra1.id  # idempotente

    revoke_role_assignment(assignment=ra2, actor=admin, scope_company=company)
    ra2.refresh_from_db()
    assert ra2.is_active is False
    ra3 = assign_role(user=target, role=role, org_unit=company, granted_by=admin, scope_company=company)
    assert ra3.id == ra1.id and ra3.is_active is True  # reactivado


@pytest.mark.django_db
def test_assign_role_rejects_org_out_of_scope():
    _, company, _ = _mk_org()
    _, other_company, _ = _mk_org()
    admin = _mk_user("admin")
    target = _mk_user("target")
    role = _role_with_perm("inventory.read")
    with pytest.raises(ValidationError):
        assign_role(user=target, role=role, org_unit=other_company, granted_by=admin, scope_company=company)


# --- API --------------------------------------------------------------------

def _client_with_perms(*, company, branch, perm_codes):
    user = _mk_user("api")
    UserMembership.objects.create(user=user, org_unit=company, is_active=True)
    UserMembership.objects.create(user=user, org_unit=branch, is_active=True)
    role = Role.objects.create(name=f"role_{uuid.uuid4().hex[:8]}", is_active=True)
    for code in perm_codes:
        perm, _ = Permission.objects.get_or_create(code=code, defaults={"description": code, "is_active": True})
        RolePermission.objects.get_or_create(role=role, permission=perm)
    RoleAssignment.objects.create(user=user, role=role, org_unit=company, is_active=True)
    RoleAssignment.objects.create(user=user, role=role, org_unit=branch, is_active=True)

    client = APIClient()
    login = client.post("/api/auth/login/", {"username": user.username, "password": "pass12345"}, format="json")
    assert login.status_code == 200, login.data
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data.get('access')}")
    client.defaults["HTTP_X_COMPANY_ID"] = str(company.id)
    client.defaults["HTTP_X_BRANCH_ID"] = str(branch.id)
    return client


@pytest.mark.django_db
def test_assignment_create_forbidden_without_permission():
    _, company, branch = _mk_org()
    client = _client_with_perms(company=company, branch=branch, perm_codes=["rbac.assignments.read"])
    target = _mk_user("target")
    role = _role_with_perm("inventory.read")
    resp = client.post(
        "/api/rbac/assignments/",
        {"user_id": target.id, "role_id": role.id, "org_unit_id": company.id},
        format="json",
    )
    assert resp.status_code == 403


@pytest.mark.django_db
def test_assignment_create_list_and_effective_permissions():
    _, company, branch = _mk_org()
    client = _client_with_perms(
        company=company, branch=branch, perm_codes=["rbac.assignments.update", "rbac.assignments.read"]
    )
    target = _mk_user("target")
    role = _role_with_perm("inventory.read")

    created = client.post(
        "/api/rbac/assignments/",
        {"user_id": target.id, "role_id": role.id, "org_unit_id": company.id},
        format="json",
    )
    assert created.status_code == 201, created.data
    assert RoleAssignment.objects.filter(user=target, role=role, org_unit=company, is_active=True).exists()

    listed = client.get(f"/api/rbac/assignments/?user_id={target.id}&active=1")
    assert listed.status_code == 200
    assert listed.data["count"] >= 1

    eff = client.get(f"/api/rbac/users/{target.id}/effective-permissions/")
    assert eff.status_code == 200
    assert "inventory.read" in eff.data["permissions"]


@pytest.mark.django_db
def test_assignment_revoke_via_api():
    _, company, branch = _mk_org()
    client = _client_with_perms(
        company=company, branch=branch, perm_codes=["rbac.assignments.update", "rbac.assignments.read"]
    )
    target = _mk_user("target")
    role = _role_with_perm("inventory.read")
    ra = assign_role(user=target, role=role, org_unit=company, granted_by=target, scope_company=company)

    resp = client.post(f"/api/rbac/assignments/{ra.id}/revoke/", {}, format="json")
    assert resp.status_code == 200
    ra.refresh_from_db()
    assert ra.is_active is False


# --- Usuarios del scope (pantalla "Usuarios y acceso") -----------------------

@pytest.mark.django_db
def test_scope_users_lista_con_roles_del_scope():
    _, company, branch = _mk_org()
    _, other_company, _ = _mk_org()
    client = _client_with_perms(company=company, branch=branch, perm_codes=["rbac.assignments.read"])

    target = _mk_user("target")
    UserMembership.objects.create(user=target, org_unit=company, is_active=True)
    role = _role_with_perm("inventory.read")
    RoleAssignment.objects.create(user=target, role=role, org_unit=company, is_active=True)

    ajeno = _mk_user("ajeno")
    UserMembership.objects.create(user=ajeno, org_unit=other_company, is_active=True)

    resp = client.get("/api/rbac/users/")
    assert resp.status_code == 200, resp.data
    ids = {row["id"] for row in resp.data["results"]}
    assert target.id in ids
    assert ajeno.id not in ids  # otra empresa no se mezcla

    row = next(r for r in resp.data["results"] if r["id"] == target.id)
    assert row["username"] == target.username
    assert [r["role_name"] for r in row["roles"]] == [role.name]
    assert row["roles"][0]["org_unit_id"] == company.id


@pytest.mark.django_db
def test_scope_users_busqueda_y_permiso():
    _, company, branch = _mk_org()
    client = _client_with_perms(company=company, branch=branch, perm_codes=["rbac.assignments.read"])
    juan = _mk_user("juanbuscable")
    UserMembership.objects.create(user=juan, org_unit=branch, is_active=True)

    resp = client.get("/api/rbac/users/?search=juanbuscable")
    assert resp.status_code == 200
    assert {r["id"] for r in resp.data["results"]} == {juan.id}

    sin_permiso = _client_with_perms(company=company, branch=branch, perm_codes=["inventory.read"])
    assert sin_permiso.get("/api/rbac/users/").status_code == 403
