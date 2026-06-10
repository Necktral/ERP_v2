"""Tests del seed de puestos agrícolas v0.1 (idempotencia, mapeos, habilitar/deshabilitar, multi-cargo).

Fijan el contrato: el catálogo se siembra por empresa, los jornaleros NO reciben rol, los flags
controlan `is_active` sin pisar toggles manuales, y un empleado con MÁS DE UN CARGO acumula los
permisos de todos sus puestos (vía reconcile). Detectan drift si alguien afloja alguna regla.
"""
from __future__ import annotations

import uuid

import pytest
from django.core.management import call_command

from apps.modulos.hr import seed_positions_v01 as seedmod
from apps.modulos.hr.models import Employee, EmploymentAssignment, JobPosition, PositionRoleMap
from apps.modulos.hr.seed_positions_v01 import (
    POSITION_CATALOG,
    PositionSpec,
    seed_hr_positions_v01,
)
from apps.modulos.hr.services import reconcile_employee_roles
from apps.modulos.iam.models import OrgUnit
from apps.modulos.rbac.models import Role, RoleAssignment, RolePermission
from apps.modulos.rbac.seed_v01 import seed_rbac_v01

UT = OrgUnit.UnitType
_NAME_BY_CODE = {s.code: s.name for s in POSITION_CATALOG}


def _mk_company():
    s = uuid.uuid4().hex[:6]
    holding = OrgUnit.objects.create(unit_type=UT.HOLDING, name=f"H_{s}")
    company = OrgUnit.objects.create(unit_type=UT.COMPANY, name=f"C_{s}", parent=holding, code=f"CO_{s}")
    branch = OrgUnit.objects.create(unit_type=UT.BRANCH, name=f"B_{s}", parent=company)
    return company, branch


def _pos(company, code):
    return JobPosition.objects.get(company=company, name=_NAME_BY_CODE[code])


# --- Creación + mapeos ----------------------------------------------------------

@pytest.mark.django_db
def test_seed_creates_full_catalog_with_maps():
    seed_rbac_v01()
    company, _ = _mk_company()
    result = seed_hr_positions_v01(company)
    assert result.created == len(POSITION_CATALOG) == 14
    assert JobPosition.objects.filter(company=company).count() == 14
    # 9 puestos del catálogo tienen rol => 9 maps.
    assert result.maps_created == 9
    assert all(p.is_active for p in JobPosition.objects.filter(company=company))


@pytest.mark.django_db
def test_position_role_mappings_are_correct():
    seed_rbac_v01()
    company, _ = _mk_company()
    seed_hr_positions_v01(company)
    B = PositionRoleMap.ScopeMode.BRANCH
    C = PositionRoleMap.ScopeMode.COMPANY

    def _maps(code):
        return {
            (m.role.name, m.scope_mode)
            for m in PositionRoleMap.objects.filter(position=_pos(company, code), is_active=True)
        }

    assert ("company_admin", C) in _maps("FNC-N1-010")  # Gerente Agrícola = superusuario
    assert ("company_admin", C) in _maps("FNC-N1-020")  # Asistente de Gerencia (mismos permisos)
    assert ("finca_mandador", C) in _maps("FNC-N2-010")  # Administrador de Fincas (todas => COMPANY)
    assert ("finca_mandador", B) in _maps("FNC-N2-020")  # Mandador (una finca => BRANCH)
    assert ("finca_capataz", B) in _maps("FNC-N2-025")  # Capataz en Jefe
    assert ("finca_capataz", B) in _maps("FNC-N2-030")  # Capataz
    assert ("finca_tecnico", B) in _maps("FNC-N3-010")  # Ingeniero Agrónomo (NO capataz)
    assert ("warehouse_operator", B) in _maps("FNC-N3-020")  # Encargado de Insumos
    # El Agrónomo NO comparte rol con el capataz.
    assert ("finca_capataz", B) not in _maps("FNC-N3-010")
    # El Administrador de Fincas manda TODAS las fincas (COMPANY), por encima del Mandador (BRANCH).
    assert ("finca_mandador", B) not in _maps("FNC-N2-010")


@pytest.mark.django_db
def test_finca_tecnico_role_is_advisor_not_capataz_nor_mandador():
    """El rol del Agrónomo: define el plan de labores pero NO ejecuta ni postea costos (SoD)."""
    seed_rbac_v01()
    role = Role.objects.get(name="finca_tecnico")
    perms = set(
        RolePermission.objects.filter(role=role).values_list("permission__code", flat=True)
    )
    assert {"finca.labor.manage", "finca.report.read", "finca.work.read"} <= perms
    # NO captura la ejecución diaria (eso es del capataz) ni postea costos (del mandador).
    assert "finca.work.capture" not in perms
    assert "finca.cost.post" not in perms
    assert "finca.finca.manage" not in perms


@pytest.mark.django_db
def test_jornalero_and_field_workers_get_no_role():
    seed_rbac_v01()
    company, _ = _mk_company()
    seed_hr_positions_v01(company)
    for code in ("FNC-N4-020", "FNC-N5-010", "FNC-N5-020", "FNC-N5-030", "FNC-N5-040"):
        assert not PositionRoleMap.objects.filter(position=_pos(company, code)).exists()


# --- Idempotencia ---------------------------------------------------------------

@pytest.mark.django_db
def test_seed_is_idempotent():
    seed_rbac_v01()
    company, _ = _mk_company()
    seed_hr_positions_v01(company)
    pos_before = JobPosition.objects.filter(company=company).count()
    map_before = PositionRoleMap.objects.filter(position__company=company).count()

    second = seed_hr_positions_v01(company)
    assert second.created == 0
    assert second.maps_created == 0
    assert JobPosition.objects.filter(company=company).count() == pos_before
    assert PositionRoleMap.objects.filter(position__company=company).count() == map_before


@pytest.mark.django_db
def test_seed_does_not_touch_custom_positions():
    seed_rbac_v01()
    company, _ = _mk_company()
    custom = JobPosition.objects.create(company=company, name="Puesto Personalizado", is_active=True)
    seed_hr_positions_v01(company)
    custom.refresh_from_db()
    assert custom.is_active is True  # intacto
    assert JobPosition.objects.filter(company=company).count() == 14 + 1


# --- Habilitar / deshabilitar ---------------------------------------------------

@pytest.mark.django_db
def test_disable_creates_inactive_and_respects_manual_toggle():
    seed_rbac_v01()
    company, _ = _mk_company()
    seed_hr_positions_v01(company, disable_codes=["FNC-N5-030"])  # Cortador de Café
    assert _pos(company, "FNC-N5-030").is_active is False

    # Re-correr SIN flag no lo reactiva (respeta el toggle).
    seed_hr_positions_v01(company)
    assert _pos(company, "FNC-N5-030").is_active is False

    # --enable lo vuelve a activar.
    res = seed_hr_positions_v01(company, enable_codes=["FNC-N5-030"])
    assert res.activated == 1
    assert _pos(company, "FNC-N5-030").is_active is True


@pytest.mark.django_db
def test_manual_disable_is_not_overwritten_by_seed():
    seed_rbac_v01()
    company, _ = _mk_company()
    seed_hr_positions_v01(company)
    # El operador apaga un puesto a mano (fuera del seed).
    pos = _pos(company, "FNC-N4-010")
    pos.is_active = False
    pos.save(update_fields=["is_active"])
    # Re-correr el seed sin flags NO lo vuelve a encender.
    seed_hr_positions_v01(company)
    pos.refresh_from_db()
    assert pos.is_active is False


@pytest.mark.django_db
def test_only_restricts_scope():
    seed_rbac_v01()
    company, _ = _mk_company()
    result = seed_hr_positions_v01(company, only_codes=["FNC-N2-020"])  # solo Mandador
    assert result.created == 1
    assert result.skipped == 13
    assert JobPosition.objects.filter(company=company).count() == 1
    assert _pos(company, "FNC-N2-020").name == "Mandador"


@pytest.mark.django_db
def test_disable_and_enable_overlap_raises():
    seed_rbac_v01()
    company, _ = _mk_company()
    with pytest.raises(ValueError):
        seed_hr_positions_v01(company, disable_codes=["FNC-N2-020"], enable_codes=["FNC-N2-020"])


# --- Rol inexistente: falla claro ----------------------------------------------

@pytest.mark.django_db
def test_missing_role_raises_clear(monkeypatch):
    seed_rbac_v01()
    company, _ = _mk_company()
    monkeypatch.setattr(
        seedmod,
        "POSITION_CATALOG",
        (PositionSpec("X-001", "Puesto Fantasma", "rol_inexistente_xyz", "BRANCH"),),
    )
    with pytest.raises(ValueError, match="rol_inexistente_xyz"):
        seed_hr_positions_v01(company)


# --- Multi-cargo: el corazón del pedido ----------------------------------------

@pytest.mark.django_db
def test_employee_with_two_positions_gets_union_of_roles():
    seed_rbac_v01()
    company, branch = _mk_company()
    seed_hr_positions_v01(company)

    from django.contrib.auth import get_user_model

    User = get_user_model()
    user = User.objects.create_user(username=f"u_{uuid.uuid4().hex[:8]}", password="pass12345")
    employee = Employee.objects.create(company=company, first_name="Multi", linked_user=user)

    capataz = _pos(company, "FNC-N2-030")  # finca_capataz BRANCH
    insumos = _pos(company, "FNC-N3-020")  # warehouse_operator BRANCH
    EmploymentAssignment.objects.create(employee=employee, position=capataz, branch=branch, is_active=True)
    EmploymentAssignment.objects.create(employee=employee, position=insumos, branch=branch, is_active=True)

    reconcile_employee_roles(employee=employee)

    capataz_role = Role.objects.get(name="finca_capataz")
    insumos_role = Role.objects.get(name="warehouse_operator")
    assert RoleAssignment.objects.filter(
        user=user, role=capataz_role, org_unit=branch,
        origin=RoleAssignment.Origin.POSITION, is_active=True,
    ).exists()
    assert RoleAssignment.objects.filter(
        user=user, role=insumos_role, org_unit=branch,
        origin=RoleAssignment.Origin.POSITION, is_active=True,
    ).exists()


# --- Comando --------------------------------------------------------------------

@pytest.mark.django_db
def test_command_seeds_by_company_code():
    seed_rbac_v01()
    company, _ = _mk_company()
    call_command("seed_hr_positions_v01", "--company-code", company.code)
    assert JobPosition.objects.filter(company=company).count() == 14
    call_command("seed_hr_positions_v01", "--company-code", company.code, "--json")  # no debe lanzar


@pytest.mark.django_db
def test_command_unknown_company_code_fails():
    from django.core.management.base import CommandError

    with pytest.raises(CommandError):
        call_command("seed_hr_positions_v01", "--company-code", "NO_EXISTE_XYZ")
