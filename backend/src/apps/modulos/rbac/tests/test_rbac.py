"""
Tests del módulo rbac — modelo, selectores de permisos efectivos, seed v0.1 y API.

Selectores: get_effective_permissions_for_scope (alcance company/branch, legacy
global, exclusión de inactivos) y get_effective_permissions (superuser='*',
catálogo desde UserRole). Modelo: RoleAssignment.clean exige COMPANY/BRANCH.
Seed: idempotencia y mapeo conocido. API: listados protegidos y demo 403/200.
"""
from __future__ import annotations

import uuid

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from rest_framework.test import APIClient

from apps.modulos.iam.models import OrgUnit, UserMembership
from apps.modulos.rbac.models import (
    Permission,
    Role,
    RoleAssignment,
    RolePermission,
    UserRole,
)
from apps.modulos.rbac.seed_v01 import seed_rbac_v01
from apps.modulos.rbac.selectors import (
    get_effective_permissions,
    get_effective_permissions_for_scope,
)

User = get_user_model()


def _mk_org():
    s = uuid.uuid4().hex[:6]
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name=f"H_{s}")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name=f"C_{s}", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name=f"B_{s}", parent=company)
    return holding, company, branch


def _mk_user(prefix="rbac"):
    username = f"{prefix}_{uuid.uuid4().hex[:8]}"
    return User.objects.create_user(username=username, email=f"{username}@test.local", password="pass12345")


def _mk_role_with_perm(code):
    role = Role.objects.create(name=f"role_{uuid.uuid4().hex[:8]}", is_active=True)
    perm = Permission.objects.create(code=code, is_active=True)
    RolePermission.objects.create(role=role, permission=perm)
    return role, perm


# ---------------------------------------------------------------------------
# selectors: get_effective_permissions_for_scope
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_effective_perms_company_scope():
    _, company, branch = _mk_org()
    user = _mk_user()
    role = Role.objects.create(name=f"r_{uuid.uuid4().hex[:8]}", is_active=True)
    c1 = f"x.read_{uuid.uuid4().hex[:6]}"
    c2 = f"x.write_{uuid.uuid4().hex[:6]}"
    for code in (c1, c2):
        RolePermission.objects.create(role=role, permission=Permission.objects.create(code=code, is_active=True))
    RoleAssignment.objects.create(user=user, role=role, org_unit=company, is_active=True)

    perms = get_effective_permissions_for_scope(user, company=company, branch=branch, include_global=False)
    assert perms == {c1, c2}


@pytest.mark.django_db
def test_effective_perms_branch_assignment_requires_branch_arg():
    _, company, branch = _mk_org()
    user = _mk_user()
    role, perm = _mk_role_with_perm(f"b.read_{uuid.uuid4().hex[:6]}")
    RoleAssignment.objects.create(user=user, role=role, org_unit=branch, is_active=True)

    # Sin pasar branch, una asignación a BRANCH no aplica.
    assert get_effective_permissions_for_scope(user, company=company, include_global=False) == set()
    # Pasando la branch sí aplica.
    assert perm.code in get_effective_permissions_for_scope(
        user, company=company, branch=branch, include_global=False
    )


@pytest.mark.django_db
def test_effective_perms_inactive_assignment_excluded():
    _, company, _ = _mk_org()
    user = _mk_user()
    role, _perm = _mk_role_with_perm(f"i.read_{uuid.uuid4().hex[:6]}")
    RoleAssignment.objects.create(user=user, role=role, org_unit=company, is_active=False)
    assert get_effective_permissions_for_scope(user, company=company, include_global=False) == set()


@pytest.mark.django_db
def test_effective_perms_inactive_permission_excluded():
    """RBAC-01: un permiso desactivado NO concede acceso en la ruta scoped."""
    _, company, _ = _mk_org()
    user = _mk_user()
    role = Role.objects.create(name=f"r_{uuid.uuid4().hex[:8]}", is_active=True)
    code = f"z.read_{uuid.uuid4().hex[:6]}"
    RolePermission.objects.create(role=role, permission=Permission.objects.create(code=code, is_active=False))
    RoleAssignment.objects.create(user=user, role=role, org_unit=company, is_active=True)
    assert get_effective_permissions_for_scope(user, company=company, include_global=False) == set()


@pytest.mark.django_db
def test_effective_perms_include_global_userrole():
    _, company, _ = _mk_org()
    user = _mk_user()
    role, perm = _mk_role_with_perm(f"g.read_{uuid.uuid4().hex[:6]}")
    UserRole.objects.create(user=user, role=role)

    assert perm.code in get_effective_permissions_for_scope(user, company=company, include_global=True)
    assert perm.code not in get_effective_permissions_for_scope(user, company=company, include_global=False)


@pytest.mark.django_db
def test_effective_perms_do_not_include_global_userrole_by_default():
    _, company, _ = _mk_org()
    user = _mk_user()
    role, perm = _mk_role_with_perm(f"g.default_{uuid.uuid4().hex[:6]}")
    UserRole.objects.create(user=user, role=role)

    assert perm.code not in get_effective_permissions_for_scope(user, company=company)


# ---------------------------------------------------------------------------
# selectors: get_effective_permissions
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_get_effective_permissions_superuser_is_wildcard():
    su = User.objects.create_superuser(
        username=f"su_{uuid.uuid4().hex[:8]}", email="su@test.local", password="pass12345"
    )
    assert get_effective_permissions(su) == ["*"]


@pytest.mark.django_db
def test_get_effective_permissions_excludes_inactive_and_sorts():
    user = _mk_user()
    role = Role.objects.create(name=f"r_{uuid.uuid4().hex[:8]}", is_active=True)
    p_active = Permission.objects.create(code=f"z.active_{uuid.uuid4().hex[:6]}", is_active=True)
    p_inactive = Permission.objects.create(code=f"a.inactive_{uuid.uuid4().hex[:6]}", is_active=False)
    RolePermission.objects.create(role=role, permission=p_active)
    RolePermission.objects.create(role=role, permission=p_inactive)
    UserRole.objects.create(user=user, role=role)

    result = get_effective_permissions(user)
    assert p_active.code in result
    assert p_inactive.code not in result
    assert result == sorted(result)


# ---------------------------------------------------------------------------
# modelo: RoleAssignment.clean
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_role_assignment_clean_requires_company_or_branch():
    holding, company, branch = _mk_org()
    user = _mk_user()
    role = Role.objects.create(name=f"r_{uuid.uuid4().hex[:8]}", is_active=True)

    with pytest.raises(ValidationError):
        RoleAssignment(user=user, role=role, org_unit=holding).clean()

    # COMPANY y BRANCH son válidos (no levantan).
    RoleAssignment(user=user, role=role, org_unit=company).clean()
    RoleAssignment(user=user, role=role, org_unit=branch).clean()


# ---------------------------------------------------------------------------
# seed v0.1
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_seed_rbac_is_idempotent_and_maps_known_role():
    seed_rbac_v01()
    # Tras sembrar, el catálogo de roles está presente.
    assert Role.objects.filter(name="company_admin").exists()
    assert Role.objects.filter(name="sync_admin").exists()

    # Segunda corrida no crea nada nuevo (idempotente).
    again = seed_rbac_v01()
    assert again.roles_created == 0
    assert again.perms_created == 0
    assert again.roleperms_created == 0

    # Mapeo conocido y acotado: sync_admin -> enroll/revoke.
    sync_admin = Role.objects.get(name="sync_admin")
    codes = set(RolePermission.objects.filter(role=sync_admin).values_list("permission__code", flat=True))
    assert codes == {"sync.device.enroll", "sync.device.revoke"}


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

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
def test_role_list_forbidden_without_permission():
    _, company, branch = _mk_org()
    client = _client_with_perms(company=company, branch=branch, perm_codes=[])
    assert client.get("/api/rbac/roles/").status_code == 403


@pytest.mark.django_db
def test_role_list_ok_with_permission():
    _, company, branch = _mk_org()
    client = _client_with_perms(company=company, branch=branch, perm_codes=["rbac.roles.read"])
    Role.objects.create(name=f"extra_{uuid.uuid4().hex[:8]}", is_active=True)
    resp = client.get("/api/rbac/roles/")
    assert resp.status_code == 200
    assert resp.data["count"] >= 1
    assert all({"id", "name", "is_active"} <= set(row) for row in resp.data["results"])


@pytest.mark.django_db
def test_permission_list_ok_with_permission():
    _, company, branch = _mk_org()
    client = _client_with_perms(company=company, branch=branch, perm_codes=["rbac.permissions.read"])
    resp = client.get("/api/rbac/permissions/")
    assert resp.status_code == 200
    assert resp.data["count"] >= 1


@pytest.mark.django_db
def test_demo_inventory_read_enforced_403_and_200():
    _, c1, b1 = _mk_org()
    denied = _client_with_perms(company=c1, branch=b1, perm_codes=[])
    assert denied.get("/api/rbac/demo/inventory-read/").status_code == 403

    _, c2, b2 = _mk_org()
    allowed = _client_with_perms(company=c2, branch=b2, perm_codes=["inventory.read"])
    resp = allowed.get("/api/rbac/demo/inventory-read/")
    assert resp.status_code == 200
    assert resp.data == {"ok": True, "required_permission": "inventory.read"}
