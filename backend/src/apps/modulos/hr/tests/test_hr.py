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
    set_employee_role_maps,
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


# ---------------------------------------------------------------------------
# API: onboarding summary
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_set_employee_role_maps_grants_direct_roles():
    _, company, branch = _mk_org()
    user = _mk_user()
    emp = _mk_employee(company, linked_user=user)
    r1 = _mk_role()
    r2 = _mk_role()

    set_employee_role_maps(employee=emp, role_ids=[r1.id, r2.id])
    active = set(
        RoleAssignment.objects.filter(user=user, is_active=True, org_unit=company).values_list(
            "role_id", flat=True
        )
    )
    assert active == {r1.id, r2.id}

    # quitar uno → reemplazo total + reconcilia
    set_employee_role_maps(employee=emp, role_ids=[r1.id])
    active = set(
        RoleAssignment.objects.filter(user=user, is_active=True, org_unit=company).values_list(
            "role_id", flat=True
        )
    )
    assert active == {r1.id}


@pytest.mark.django_db
def test_employee_roles_api_get_put():
    _, company, branch = _mk_org()
    client = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=["hr.employee.read", "hr.employee.update", "hr.employee.create"],
    )
    emp_id = client.post("/api/hr/employees/", {"first_name": "Ana"}, format="json").data["id"]
    role = _mk_role()

    resp = client.put(f"/api/hr/employees/{emp_id}/roles/", {"role_ids": [role.id]}, format="json")
    assert resp.status_code == 200, resp.data

    got = client.get(f"/api/hr/employees/{emp_id}/roles/")
    assert got.status_code == 200
    assert [m["role_id"] for m in got.data["results"]] == [role.id]


@pytest.mark.django_db
def test_onboarding_summary_requires_permission():
    _, company, branch = _mk_org()
    # Sin hr.employee.read → 403
    client = _client_with_perms(company=company, branch=branch, perm_codes=["hr.position.read"])
    resp = client.get("/api/hr/onboarding/summary/")
    assert resp.status_code == 403


@pytest.mark.django_db
def test_onboarding_summary_progresses_through_steps():
    _, company, branch = _mk_org()
    client = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=[
            "hr.employee.read",
            "hr.position.create",
            "hr.position.roles.update",
            "hr.employee.create",
            "hr.assignment.create",
        ],
    )

    # 0) Empresa vacía → primer paso = POSITIONS
    resp = client.get("/api/hr/onboarding/summary/")
    assert resp.status_code == 200, resp.data
    assert resp.data["next_step"] == "POSITIONS"
    assert resp.data["complete"] is False
    assert resp.data["positions_count"] == 0

    # 1) Crear puesto (sin roles) → falta el mapeo de roles
    pos_id = client.post("/api/hr/positions/", {"name": "Cajero"}, format="json").data["id"]
    resp = client.get("/api/hr/onboarding/summary/")
    assert resp.data["positions_count"] == 1
    assert resp.data["positions_with_roles"] == 0
    assert resp.data["next_step"] == "POSITION_ROLES"

    # 2) Mapear puesto -> rol → siguiente paso = EMPLOYEES
    role = _mk_role()
    client.put(
        f"/api/hr/positions/{pos_id}/roles/",
        {"maps": [{"role_id": role.id, "scope_mode": "BRANCH"}]},
        format="json",
    )
    resp = client.get("/api/hr/onboarding/summary/")
    assert resp.data["positions_with_roles"] == 1
    assert resp.data["next_step"] == "EMPLOYEES"

    # 3) Crear trabajador → falta asignar
    emp_id = client.post("/api/hr/employees/", {"first_name": "Ana"}, format="json").data["id"]
    resp = client.get("/api/hr/onboarding/summary/")
    assert resp.data["employees_count"] == 1
    assert resp.data["employees_assigned"] == 0
    assert resp.data["next_step"] == "ASSIGNMENTS"

    # 4) Asignar trabajador -> puesto + sucursal → falta provisionar
    client.post(
        f"/api/hr/employees/{emp_id}/assignments/",
        {"position_id": pos_id, "branch_id": branch.id},
        format="json",
    )
    resp = client.get("/api/hr/onboarding/summary/")
    assert resp.data["employees_assigned"] == 1
    assert resp.data["next_step"] == "PROVISIONING"
    assert resp.data["complete"] is False

    # 5) Provisionar usuario (vía servicio) → recorrido completo
    emp = Employee.objects.get(id=emp_id)
    provision_user_for_employee(employee=emp, username=f"ana_{uuid.uuid4().hex[:6]}", email="")
    resp = client.get("/api/hr/onboarding/summary/")
    assert resp.data["employees_provisioned"] == 1
    assert resp.data["next_step"] == "DONE"
    assert resp.data["complete"] is True


# ---------------------------------------------------------------------------
# Ciclo de vida laboral: suspensión / reintegro / baja / reingreso
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_suspend_blocks_login_and_reinstate_restores():
    from datetime import date

    from apps.modulos.hr.models import EmployeeLifecycleEvent
    from apps.modulos.hr.services import reinstate_employee, suspend_employee

    _, company, _ = _mk_org()
    user = _mk_user()
    emp = _mk_employee(company, linked_user=user)

    ev = suspend_employee(
        employee=emp,
        reason_code="DISCIPLINARIA",
        reason_detail="3 días sin goce",
        effective_date=date(2026, 6, 10),
        end_date=date(2026, 6, 13),
        suspend_access=True,
    )
    emp.refresh_from_db()
    user.refresh_from_db()
    assert emp.employment_status == Employee.EmploymentStatus.SUSPENDIDO
    assert user.is_active is False
    assert ev.access_suspended is True

    # No se puede suspender dos veces
    with pytest.raises(ValueError):
        suspend_employee(employee=emp, reason_code="MEDICA", effective_date=date(2026, 6, 11))

    reinstate_employee(employee=emp, effective_date=date(2026, 6, 13))
    emp.refresh_from_db()
    user.refresh_from_db()
    assert emp.employment_status == Employee.EmploymentStatus.ACTIVO
    assert user.is_active is True
    assert emp.lifecycle_events.filter(event_type=EmployeeLifecycleEvent.EventType.REINTEGRO).exists()


@pytest.mark.django_db
def test_terminate_revokes_all_and_rehire_restores_record():
    from datetime import date

    from apps.modulos.hr.services import rehire_employee, terminate_employee

    _, company, branch = _mk_org()
    user = _mk_user()
    emp = _mk_employee(company, linked_user=user)
    role = _mk_role()
    set_employee_role_maps(employee=emp, role_ids=[role.id])

    pos = JobPosition.objects.create(company=company, name=f"P_{uuid.uuid4().hex[:4]}")
    EmploymentAssignment.objects.create(employee=emp, position=pos, branch=branch)

    assert RoleAssignment.objects.filter(user=user, is_active=True, org_unit=company).exists()

    terminate_employee(
        employee=emp,
        reason_code="RENUNCIA",
        reason_detail="renuncia voluntaria",
        effective_date=date(2026, 6, 10),
    )
    emp.refresh_from_db()
    user.refresh_from_db()
    assert emp.employment_status == Employee.EmploymentStatus.BAJA
    assert emp.is_active is False
    assert not EmploymentAssignment.objects.filter(employee=emp, is_active=True).exists()
    assert not RoleAssignment.objects.filter(
        user=user, is_active=True, origin=RoleAssignment.Origin.POSITION
    ).exists()
    assert not UserMembership.objects.filter(user=user, is_active=True).exists()
    assert user.is_active is False  # no pertenece a otra empresa → deshabilitado

    # Motivo inválido rechazado
    with pytest.raises(ValueError):
        terminate_employee(employee=emp, reason_code="INVALIDO", effective_date=date(2026, 6, 10))

    # Reingreso (temporada siguiente): la ficha vuelve a ACTIVO, acceso se gestiona aparte
    rehire_employee(employee=emp, reason_detail="nueva cosecha", effective_date=date(2026, 11, 1))
    emp.refresh_from_db()
    assert emp.employment_status == Employee.EmploymentStatus.ACTIVO
    assert emp.is_active is True


@pytest.mark.django_db
def test_terminated_employee_reconcile_keeps_grants_revoked():
    """Tras la BAJA, reconcile NO debe re-materializar roles aunque queden maps en historial."""
    from datetime import date

    from apps.modulos.hr.services import terminate_employee

    _, company, _ = _mk_org()
    user = _mk_user()
    emp = _mk_employee(company, linked_user=user)
    role = _mk_role()
    set_employee_role_maps(employee=emp, role_ids=[role.id])

    terminate_employee(employee=emp, reason_code="DESPIDO_JUSTIFICADO", effective_date=date(2026, 6, 10))
    emp.refresh_from_db()

    # reconcile explícito (p.ej. disparado por otro flujo) no debe revivir grants
    reconcile_employee_roles(employee=emp)
    assert not RoleAssignment.objects.filter(
        user=user, is_active=True, origin=RoleAssignment.Origin.POSITION
    ).exists()


@pytest.mark.django_db
def test_lifecycle_api_terminate_and_history():
    from datetime import date  # noqa: F401

    _, company, branch = _mk_org()
    client = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=["hr.employee.read", "hr.employee.update", "hr.employee.create"],
    )
    emp_id = client.post("/api/hr/employees/", {"first_name": "Pedro"}, format="json").data["id"]

    resp = client.post(
        f"/api/hr/employees/{emp_id}/terminate/",
        {"reason_code": "FIN_CONTRATO", "reason_detail": "fin de temporada", "effective_date": "2026-06-10"},
        format="json",
    )
    assert resp.status_code == 200, resp.data
    assert resp.data["event"]["event_type"] == "BAJA"

    # Repetir la baja → 409
    resp = client.post(
        f"/api/hr/employees/{emp_id}/terminate/",
        {"reason_code": "RENUNCIA", "effective_date": "2026-06-11"},
        format="json",
    )
    assert resp.status_code == 409

    hist = client.get(f"/api/hr/employees/{emp_id}/lifecycle/")
    assert hist.status_code == 200
    assert [e["event_type"] for e in hist.data["results"]] == ["BAJA"]

    # El listado refleja el estado laboral
    listed = client.get("/api/hr/employees/")
    row = next(r for r in listed.data["results"] if r["id"] == emp_id)
    assert row["employment_status"] == "BAJA"


# ---------------------------------------------------------------------------
# Contratos laborales
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_contract_draft_renders_real_data_and_issue_freezes():
    from datetime import date

    from apps.modulos.hr.models import EmploymentContract
    from apps.modulos.hr.services import annul_contract, create_contract_draft, issue_contract

    _, company, _ = _mk_org()
    emp = Employee.objects.create(company=company, first_name="María", last_name="López")
    pos = JobPosition.objects.create(company=company, name="Capataz")

    contract = create_contract_draft(
        employee=emp,
        contract_type="TEMPORADA",
        start_date=date(2026, 11, 1),
        end_date=date(2027, 2, 28),
        position=pos,
        salary_amount=9000,
        salary_period="MENSUAL",
        extra_context={"season_description": "corte de café 2026-2027"},
    )
    assert contract.status == EmploymentContract.Status.BORRADOR
    assert "María López" in contract.body
    assert "Capataz" in contract.body
    assert "corte de café 2026-2027" in contract.body
    assert "1 de noviembre de 2026" in contract.body
    assert company.name in contract.body  # sin CompanyProfile usa el nombre del OrgUnit

    issued = issue_contract(contract=contract)
    assert issued.status == EmploymentContract.Status.EMITIDO
    assert issued.issued_at is not None

    # No se puede emitir dos veces
    with pytest.raises(ValueError):
        issue_contract(contract=issued)

    annulled = annul_contract(contract=issued, reason="error de datos")
    assert annulled.status == EmploymentContract.Status.ANULADO


@pytest.mark.django_db
def test_contract_plazo_fijo_requires_end_date():
    from datetime import date

    from apps.modulos.hr.services import create_contract_draft

    _, company, _ = _mk_org()
    emp = _mk_employee(company)
    with pytest.raises(ValidationError):
        create_contract_draft(employee=emp, contract_type="PLAZO_FIJO", start_date=date(2026, 6, 10))


@pytest.mark.django_db
def test_contract_api_create_edit_issue_blocks_edit():
    _, company, branch = _mk_org()
    client = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=["hr.employee.read", "hr.employee.update", "hr.employee.create"],
    )
    emp_id = client.post("/api/hr/employees/", {"first_name": "Luis"}, format="json").data["id"]

    created = client.post(
        f"/api/hr/employees/{emp_id}/contracts/",
        {"contract_type": "INDEFINIDO", "start_date": "2026-06-10", "salary_amount": "7500.00"},
        format="json",
    )
    assert created.status_code == 201, created.data
    cid = created.data["id"]
    assert "Luis" in created.data["body"]

    # Editar el texto en borrador
    patched = client.patch(f"/api/hr/contracts/{cid}/", {"body": "TEXTO AJUSTADO POR RRHH"}, format="json")
    assert patched.status_code == 200, patched.data
    assert patched.data["body"] == "TEXTO AJUSTADO POR RRHH"

    issued = client.post(f"/api/hr/contracts/{cid}/issue/")
    assert issued.status_code == 200
    assert issued.data["status"] == "EMITIDO"

    # Emitido → ya no se edita
    blocked = client.patch(f"/api/hr/contracts/{cid}/", {"body": "no debería"}, format="json")
    assert blocked.status_code == 409

    listed = client.get(f"/api/hr/employees/{emp_id}/contracts/")
    assert listed.status_code == 200
    assert len(listed.data["results"]) == 1


# ---------------------------------------------------------------------------
# Memorandos / relaciones laborales
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_memo_api_create_list_annul_and_profile():
    _, company, branch = _mk_org()
    client = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=["hr.employee.read", "hr.employee.update", "hr.employee.create"],
    )
    emp_id = client.post("/api/hr/employees/", {"first_name": "Rosa"}, format="json").data["id"]

    memo = client.post(
        f"/api/hr/employees/{emp_id}/memos/",
        {
            "memo_type": "AMONESTACION_ESCRITA",
            "subject": "Inasistencia sin justificar",
            "body": "Se le llama la atención por inasistencia el 8 de junio.",
        },
        format="json",
    )
    assert memo.status_code == 201, memo.data
    memo_id = memo.data["id"]
    assert memo.data["status"] == "EMITIDO"

    annulled = client.post(f"/api/hr/memos/{memo_id}/annul/", {"reason": "emitido por error"}, format="json")
    assert annulled.status_code == 200
    assert annulled.data["status"] == "ANULADO"

    # Perfil (expediente) integra todo
    profile = client.get(f"/api/hr/employees/{emp_id}/profile/")
    assert profile.status_code == 200, profile.data
    assert profile.data["employment_status"] == "ACTIVO"
    assert len(profile.data["memos"]) == 1
    assert profile.data["memos"][0]["status"] == "ANULADO"
    assert profile.data["contracts"] == []
    assert profile.data["lifecycle_events"] == []

    # Catálogos para la UI
    cats = client.get("/api/hr/catalogs/")
    assert cats.status_code == 200
    assert any(c["value"] == "TEMPORADA" for c in cats.data["contract_types"])
    assert any(r["value"] == "RENUNCIA" for r in cats.data["baja_reasons"])


# ---------------------------------------------------------------------------
# API: datos de planilla en el expediente (cédula, INSS, género, salario)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_employee_api_campos_de_planilla():
    """El expediente guarda los datos que la nómina copia a la planilla."""
    _, company, branch = _mk_org()
    client = _client_with_perms(
        company=company, branch=branch,
        perm_codes=["hr.employee.create", "hr.employee.read", "hr.employee.update"],
    )

    created = client.post(
        "/api/hr/employees/",
        {
            "first_name": "Maria", "last_name": "Garcia",
            "cedula": "241-150590-0003B", "inss_number": "7305067",
            "gender": "F", "salary_type": "DAILY", "daily_rate_nio": "250.00",
        },
        format="json",
    )
    assert created.status_code == 201, created.data
    emp_id = created.data["id"]

    listed = client.get("/api/hr/employees/")
    row = next(r for r in listed.data["results"] if r["id"] == emp_id)
    assert row["cedula"] == "241-150590-0003B"
    assert row["inss_number"] == "7305067"
    assert row["gender"] == "F"
    assert row["salary_type"] == "DAILY"
    assert row["daily_rate_nio"] == "250.00"

    patched = client.patch(
        f"/api/hr/employees/{emp_id}/",
        {"salary_type": "MONTHLY", "monthly_salary_nio": "9450.00"},
        format="json",
    )
    assert patched.status_code == 200, patched.data

    profile = client.get(f"/api/hr/employees/{emp_id}/profile/")
    assert profile.status_code == 200
    assert profile.data["cedula"] == "241-150590-0003B"
    assert profile.data["salary_type"] == "MONTHLY"
    assert profile.data["monthly_salary_nio"] == "9450.00"


# ---------------------------------------------------------------------------
# API: foto del trabajador
# ---------------------------------------------------------------------------

def _png_bytes(size=(1200, 900), color=(120, 30, 30)) -> bytes:
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


@pytest.mark.django_db
def test_employee_photo_subir_normaliza_y_servir():
    import io

    _, company, branch = _mk_org()
    client = _client_with_perms(
        company=company, branch=branch,
        perm_codes=["hr.employee.create", "hr.employee.read", "hr.employee.update"],
    )
    emp_id = client.post("/api/hr/employees/", {"first_name": "Foto"}, format="json").data["id"]

    up = client.post(
        f"/api/hr/employees/{emp_id}/photo/",
        {"file": io.BytesIO(_png_bytes())},
        format="multipart",
    )
    assert up.status_code == 201, up.data
    # 1200x900 → normalizada a máx. 512px por lado
    assert up.data["width"] <= 512 and up.data["height"] <= 512
    assert up.data["byte_size"] > 0

    got = client.get(f"/api/hr/employees/{emp_id}/photo/")
    assert got.status_code == 200
    assert got["Content-Type"] == "image/jpeg"
    assert got.content[:3] == b"\xff\xd8\xff"  # firma JPEG

    listed = client.get("/api/hr/employees/")
    row = next(r for r in listed.data["results"] if r["id"] == emp_id)
    assert row["has_photo"] is True

    profile = client.get(f"/api/hr/employees/{emp_id}/profile/")
    assert profile.data["has_photo"] is True

    deleted = client.delete(f"/api/hr/employees/{emp_id}/photo/")
    assert deleted.status_code == 200
    assert client.get(f"/api/hr/employees/{emp_id}/photo/").status_code == 404


@pytest.mark.django_db
def test_employee_photo_visible_con_permiso_de_asistencia():
    """El capataz (nomina.field.read, sin hr.employee.read) puede VER la foto, no subirla."""
    import io

    _, company, branch = _mk_org()
    rh = _client_with_perms(
        company=company, branch=branch,
        perm_codes=["hr.employee.create", "hr.employee.update"],
    )
    emp_id = rh.post("/api/hr/employees/", {"first_name": "Campo"}, format="json").data["id"]
    up = rh.post(
        f"/api/hr/employees/{emp_id}/photo/",
        {"file": io.BytesIO(_png_bytes(size=(300, 400)))},
        format="multipart",
    )
    assert up.status_code == 201, up.data

    capataz = _client_with_perms(company=company, branch=branch, perm_codes=["nomina.field.read"])
    assert capataz.get(f"/api/hr/employees/{emp_id}/photo/").status_code == 200
    subir = capataz.post(
        f"/api/hr/employees/{emp_id}/photo/",
        {"file": io.BytesIO(_png_bytes(size=(64, 64)))},
        format="multipart",
    )
    assert subir.status_code == 403


@pytest.mark.django_db
def test_employee_photo_rechaza_no_imagen():
    import io

    _, company, branch = _mk_org()
    client = _client_with_perms(
        company=company, branch=branch,
        perm_codes=["hr.employee.create", "hr.employee.update"],
    )
    emp_id = client.post("/api/hr/employees/", {"first_name": "Basura"}, format="json").data["id"]
    bad = client.post(
        f"/api/hr/employees/{emp_id}/photo/",
        {"file": io.BytesIO(b"esto no es una imagen")},
        format="multipart",
    )
    assert bad.status_code == 400
