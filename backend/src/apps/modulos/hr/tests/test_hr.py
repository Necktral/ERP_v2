"""
Tests del módulo hr — puestos, empleados, asignaciones y automatización RBAC.

Modelo: Employee.clean (party de la misma company). Servicios: reconcile de
RoleAssignment origin=POSITION (scope BRANCH/COMPANY, desactivación de obsoletos),
end_assignment, set_position_role_maps (reemplazo + validación), provisioning de
usuario, reset de contraseña temporal, revoke de acceso y link a Party.
API: positions list/create con permisos rbac.
"""
from __future__ import annotations

import uuid

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from rest_framework.test import APIClient

from apps.modulos.hr.models import Employee, EmploymentAssignment, JobPosition, PositionRoleMap
from apps.modulos.hr.services import (
    end_assignment,
    link_employee_to_party,
    provision_user_for_employee,
    reconcile_employee_roles,
    reset_temp_password_for_employee,
    revoke_employee_access,
    set_position_role_maps,
)
from apps.modulos.iam.models import OrgUnit, UserMembership
from apps.modulos.parties.models import Party, PartyRole
from apps.modulos.rbac.models import Permission, Role, RoleAssignment, RolePermission

User = get_user_model()
UT = OrgUnit.UnitType


def _mk_org():
    s = uuid.uuid4().hex[:6]
    holding = OrgUnit.objects.create(unit_type=UT.HOLDING, name=f"H_{s}")
    company = OrgUnit.objects.create(unit_type=UT.COMPANY, name=f"C_{s}", parent=holding)
    branch = OrgUnit.objects.create(unit_type=UT.BRANCH, name=f"B_{s}", parent=company)
    return holding, company, branch


def _mk_user(prefix="hr"):
    username = f"{prefix}_{uuid.uuid4().hex[:8]}"
    return User.objects.create_user(username=username, email=f"{username}@test.local", password="pass12345")


def _mk_role():
    return Role.objects.create(name=f"role_{uuid.uuid4().hex[:8]}", is_active=True)


def _mk_employee(company, *, linked_user=None):
    return Employee.objects.create(
        company=company, first_name=f"E_{uuid.uuid4().hex[:4]}", linked_user=linked_user
    )


# ---------------------------------------------------------------------------
# Modelo: Employee.clean
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_employee_party_must_belong_to_company():
    _, c1, _ = _mk_org()
    _, c2, _ = _mk_org()
    party = Party(company=c2, party_type=Party.PartyType.NATURAL, display_name="X")
    party.save()
    emp = Employee(company=c1, first_name="E", party=party)
    with pytest.raises(ValidationError):
        emp.save()


# ---------------------------------------------------------------------------
# Servicios: reconcile_employee_roles
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_reconcile_creates_position_role_assignment_branch_scope():
    _, company, branch = _mk_org()
    user = _mk_user()
    employee = _mk_employee(company, linked_user=user)
    position = JobPosition.objects.create(company=company, name=f"pos_{uuid.uuid4().hex[:4]}")
    role = _mk_role()
    PositionRoleMap.objects.create(position=position, role=role, scope_mode=PositionRoleMap.ScopeMode.BRANCH)
    EmploymentAssignment.objects.create(employee=employee, position=position, branch=branch, is_active=True)

    result = reconcile_employee_roles(employee=employee)
    assert result.created == 1
    assert RoleAssignment.objects.filter(
        user=user, role=role, org_unit=branch, origin=RoleAssignment.Origin.POSITION, is_active=True
    ).exists()
    # Membership a la branch garantizada.
    assert UserMembership.objects.filter(user=user, org_unit=branch, is_active=True).exists()


@pytest.mark.django_db
def test_reconcile_company_scope_grants_on_company():
    _, company, branch = _mk_org()
    user = _mk_user()
    employee = _mk_employee(company, linked_user=user)
    position = JobPosition.objects.create(company=company, name=f"pos_{uuid.uuid4().hex[:4]}")
    role = _mk_role()
    PositionRoleMap.objects.create(position=position, role=role, scope_mode=PositionRoleMap.ScopeMode.COMPANY)
    EmploymentAssignment.objects.create(employee=employee, position=position, branch=branch, is_active=True)

    reconcile_employee_roles(employee=employee)
    assert RoleAssignment.objects.filter(
        user=user, role=role, org_unit=company, origin=RoleAssignment.Origin.POSITION, is_active=True
    ).exists()


@pytest.mark.django_db
def test_reconcile_without_linked_user_is_noop():
    _, company, branch = _mk_org()
    employee = _mk_employee(company, linked_user=None)
    result = reconcile_employee_roles(employee=employee)
    assert (result.created, result.reactivated, result.deactivated) == (0, 0, 0)


@pytest.mark.django_db
def test_reconcile_deactivates_obsolete_position_grant():
    _, company, branch = _mk_org()
    user = _mk_user()
    employee = _mk_employee(company, linked_user=user)
    position = JobPosition.objects.create(company=company, name=f"pos_{uuid.uuid4().hex[:4]}")
    role = _mk_role()
    PositionRoleMap.objects.create(position=position, role=role, scope_mode=PositionRoleMap.ScopeMode.BRANCH)
    assignment = EmploymentAssignment.objects.create(
        employee=employee, position=position, branch=branch, is_active=True
    )
    reconcile_employee_roles(employee=employee)

    # Al desactivar el assignment, el grant POSITION debe desactivarse en el reconcile.
    assignment.is_active = False
    assignment.save(update_fields=["is_active"])
    result = reconcile_employee_roles(employee=employee)
    assert result.deactivated == 1
    assert not RoleAssignment.objects.filter(
        user=user, role=role, org_unit=branch, origin=RoleAssignment.Origin.POSITION, is_active=True
    ).exists()


@pytest.mark.django_db
def test_end_assignment_deactivates_and_reconciles():
    _, company, branch = _mk_org()
    user = _mk_user()
    employee = _mk_employee(company, linked_user=user)
    position = JobPosition.objects.create(company=company, name=f"pos_{uuid.uuid4().hex[:4]}")
    role = _mk_role()
    PositionRoleMap.objects.create(position=position, role=role, scope_mode=PositionRoleMap.ScopeMode.BRANCH)
    assignment = EmploymentAssignment.objects.create(
        employee=employee, position=position, branch=branch, is_active=True
    )
    reconcile_employee_roles(employee=employee)

    end_assignment(assignment=assignment)
    assignment.refresh_from_db()
    assert assignment.is_active is False
    assert assignment.ended_at is not None
    assert not RoleAssignment.objects.filter(
        user=user, role=role, org_unit=branch, origin=RoleAssignment.Origin.POSITION, is_active=True
    ).exists()


# ---------------------------------------------------------------------------
# Servicios: set_position_role_maps
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_set_position_role_maps_replaces_and_validates():
    _, company, _ = _mk_org()
    position = JobPosition.objects.create(company=company, name=f"pos_{uuid.uuid4().hex[:4]}")
    role = _mk_role()

    set_position_role_maps(position=position, maps=[{"role_id": role.id, "scope_mode": "BRANCH"}])
    assert PositionRoleMap.objects.filter(position=position, role=role, is_active=True).count() == 1

    with pytest.raises(ValueError):
        set_position_role_maps(position=position, maps=[{"role_id": role.id, "scope_mode": "INVALID"}])
    with pytest.raises(ValueError):
        set_position_role_maps(position=position, maps=[{"role_id": 999999, "scope_mode": "BRANCH"}])

    # Reemplazo: nuevo map deja inactivo el anterior.
    role2 = _mk_role()
    set_position_role_maps(position=position, maps=[{"role_id": role2.id, "scope_mode": "COMPANY"}])
    assert PositionRoleMap.objects.filter(position=position, role=role, is_active=True).count() == 0
    assert PositionRoleMap.objects.filter(position=position, role=role2, is_active=True).count() == 1


# ---------------------------------------------------------------------------
# Servicios: provisioning / reset / revoke
# ---------------------------------------------------------------------------

def _provisioned_employee_with_role():
    _, company, branch = _mk_org()
    employee = _mk_employee(company, linked_user=None)
    position = JobPosition.objects.create(company=company, name=f"pos_{uuid.uuid4().hex[:4]}")
    role = _mk_role()
    PositionRoleMap.objects.create(position=position, role=role, scope_mode=PositionRoleMap.ScopeMode.BRANCH)
    EmploymentAssignment.objects.create(employee=employee, position=position, branch=branch, is_active=True)
    info = provision_user_for_employee(
        employee=employee, username=f"u_{uuid.uuid4().hex[:8]}", email=None
    )
    employee = Employee.objects.select_related("linked_user", "company").get(pk=employee.pk)
    return employee, company, branch, role, info


@pytest.mark.django_db
def test_provision_user_creates_links_and_reconciles():
    employee, company, branch, role, info = _provisioned_employee_with_role()
    assert info["user_id"]
    assert employee.linked_user_id == info["user_id"]
    user = employee.linked_user
    assert user.must_change_password is True
    # El reconcile durante provisioning otorgó el rol POSITION en la branch.
    assert RoleAssignment.objects.filter(
        user=user, role=role, org_unit=branch, origin=RoleAssignment.Origin.POSITION, is_active=True
    ).exists()


@pytest.mark.django_db
def test_provision_user_validations():
    _, company, branch = _mk_org()
    employee = _mk_employee(company, linked_user=None)
    # Sin asignación activa no se puede provisionar.
    with pytest.raises(ValueError):
        provision_user_for_employee(employee=employee, username=f"u_{uuid.uuid4().hex[:6]}", email=None)

    position = JobPosition.objects.create(company=company, name=f"pos_{uuid.uuid4().hex[:4]}")
    EmploymentAssignment.objects.create(employee=employee, position=position, branch=branch, is_active=True)
    provision_user_for_employee(employee=employee, username=f"u_{uuid.uuid4().hex[:6]}", email=None)
    # Ya tiene usuario vinculado.
    employee.refresh_from_db()
    with pytest.raises(ValueError):
        provision_user_for_employee(employee=employee, username=f"u2_{uuid.uuid4().hex[:6]}", email=None)


@pytest.mark.django_db
def test_reset_temp_password_requires_linked_user():
    _, company, branch = _mk_org()
    employee = _mk_employee(company, linked_user=None)
    with pytest.raises(ValueError):
        reset_temp_password_for_employee(employee=employee)

    employee, company, branch, role, _info = _provisioned_employee_with_role()
    out = reset_temp_password_for_employee(employee=employee)
    assert out["temp_password"]
    employee.linked_user.refresh_from_db()
    assert employee.linked_user.must_change_password is True


@pytest.mark.django_db
def test_revoke_employee_access_deactivates_grants_and_memberships():
    employee, company, branch, role, _info = _provisioned_employee_with_role()
    user = employee.linked_user
    assert UserMembership.objects.filter(user=user, org_unit=branch, is_active=True).exists()

    result = revoke_employee_access(employee=employee, disable_user=True)
    assert result["role_assignments_deactivated"] >= 1
    assert result["memberships_deactivated"] >= 1
    assert not RoleAssignment.objects.filter(
        user=user, org_unit=branch, origin=RoleAssignment.Origin.POSITION, is_active=True
    ).exists()
    assert not UserMembership.objects.filter(user=user, org_unit=branch, is_active=True).exists()
    user.refresh_from_db()
    assert user.is_active is False  # no quedaban otras memberships activas


# ---------------------------------------------------------------------------
# Servicios: link a Party
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_link_employee_to_party_ensures_employee_role():
    _, company, _ = _mk_org()
    party = Party(company=company, party_type=Party.PartyType.NATURAL, display_name="P")
    party.save()
    employee = _mk_employee(company, linked_user=None)

    out = link_employee_to_party(employee=employee, party=party)
    assert out.party_id == party.id
    assert PartyRole.objects.filter(party=party, role=PartyRole.Role.EMPLOYEE, is_active=True).exists()


@pytest.mark.django_db
def test_link_employee_to_party_rejects_other_company():
    _, c1, _ = _mk_org()
    _, c2, _ = _mk_org()
    party = Party(company=c2, party_type=Party.PartyType.NATURAL, display_name="P")
    party.save()
    employee = _mk_employee(c1, linked_user=None)
    with pytest.raises(ValidationError):
        link_employee_to_party(employee=employee, party=party)


# ---------------------------------------------------------------------------
# API: positions
# ---------------------------------------------------------------------------

def _client_with_perms(*, company, branch, perm_codes):
    user = _mk_user("api")
    UserMembership.objects.create(user=user, org_unit=company, is_active=True)
    UserMembership.objects.create(user=user, org_unit=branch, is_active=True)
    role = _mk_role()
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
def test_positions_api_create_and_list():
    _, company, branch = _mk_org()
    client = _client_with_perms(
        company=company, branch=branch, perm_codes=["hr.position.create", "hr.position.read"]
    )
    created = client.post("/api/hr/positions/", {"name": "Cajero", "code": "CAJ"}, format="json")
    assert created.status_code == 201, created.data
    assert created.data["id"]

    listed = client.get("/api/hr/positions/")
    assert listed.status_code == 200
    assert listed.data["count"] >= 1
    assert any(row["name"] == "Cajero" for row in listed.data["results"])


@pytest.mark.django_db
def test_positions_api_create_forbidden_without_permission():
    _, company, branch = _mk_org()
    client = _client_with_perms(company=company, branch=branch, perm_codes=["hr.position.read"])
    resp = client.post("/api/hr/positions/", {"name": "X"}, format="json")
    assert resp.status_code == 403
