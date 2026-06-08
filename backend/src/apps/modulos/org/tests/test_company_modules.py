"""Tests del registro de módulos por empresa (catálogo, servicio, API y ACL).

Cubre: integridad del catálogo, resolución híbrida por defecto, endpoints
GET/PUT con RBAC, validación de dependencias, traza de auditoría y la
integración con el snapshot ACL (`me/acl`, `bootstrap/session`).
"""
from __future__ import annotations

import uuid

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.modulos.audit.models import AuditEvent
from apps.modulos.iam.models import OrgUnit, UserMembership
from apps.modulos.org import services_modules
from apps.modulos.org.models import CompanyModule
from apps.modulos.org.module_catalog import all_codes, core_codes, get_catalog, is_known
from apps.modulos.org.permissions import require_module
from apps.modulos.org.services_modules import (
    ModuleDependencyError,
    allowed_module_codes,
    resolve_company_modules,
)
from apps.modulos.rbac.models import Permission, Role, RoleAssignment, RolePermission

User = get_user_model()
UT = OrgUnit.UnitType


def _mk_org():
    s = uuid.uuid4().hex[:6]
    holding = OrgUnit.objects.create(unit_type=UT.HOLDING, name=f"H_{s}")
    company = OrgUnit.objects.create(unit_type=UT.COMPANY, name=f"C_{s}", parent=holding)
    branch = OrgUnit.objects.create(unit_type=UT.BRANCH, name=f"B_{s}", parent=company)
    return holding, company, branch


def _client_with_perms(*, company, branch, perm_codes):
    username = f"mod_{uuid.uuid4().hex[:8]}"
    user = User.objects.create_user(username=username, email=f"{username}@test.local", password="pass12345")
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


# ---------------------------------------------------------------------------
# Catálogo (puro)
# ---------------------------------------------------------------------------

def test_catalog_codes_unique_and_core_default_enabled():
    catalog = get_catalog()
    codes = [s.code for s in catalog]
    assert len(codes) == len(set(codes)), "códigos de módulo duplicados"
    for spec in catalog:
        if spec.core:
            assert spec.default_enabled, f"core '{spec.code}' debe default_enabled"


def test_catalog_dependencies_resolvable():
    for spec in get_catalog():
        for dep in spec.depends_on:
            assert is_known(dep), f"'{spec.code}' depende de '{dep}' desconocido"


def test_allowed_modules_legacy_contract_preserved():
    """DRY: allowed_modules deriva del catálogo SIN cambiar el contrato del front."""
    from apps.modulos.accounts.views import _allowed_modules_for_permissions

    perms = {
        "org.company.read",
        "hr.employee.read",
        "audit.read",
        "fuel.shift.read",
        "retail.pos.ticket.read",
        "report.dashboard.read",
        "sync.device.enroll",
        "inventory.item.read",
        "billing.customer.read",
        "nomina.config.read",  # nómina NO participa del contrato legacy
    }
    allowed = set(_allowed_modules_for_permissions(perms))
    assert allowed == {
        "dashboard",
        "organization",
        "human_resources",
        "audit",
        "fuel",
        "retail_pos",
        "analytics",
        "reporting",
        "synchronization",
        "inventory",
        "billing",
    }
    # nómina sí existe en el catálogo (espacio completo), solo no en allowed_modules
    assert "payroll" not in allowed
    assert "payroll" in allowed_module_codes(perms)


# ---------------------------------------------------------------------------
# Servicio: resolución híbrida por defecto
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_resolve_defaults_hybrid():
    _, company, _ = _mk_org()
    state = resolve_company_modules(company)
    # core siempre ON
    for code in core_codes():
        assert state[code] is True
    # set base ON
    assert state["payroll"] is True
    assert state["billing"] is True
    # verticales OFF hasta activar
    assert state["inventory"] is False
    assert state["fuel"] is False
    assert state["retail_pos"] is False


# ---------------------------------------------------------------------------
# API: GET / PUT
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_get_modules_lists_catalog_with_state():
    _, company, branch = _mk_org()
    client = _client_with_perms(company=company, branch=branch, perm_codes=["org.module.read"])
    resp = client.get("/api/org/modules/")
    assert resp.status_code == 200, resp.data
    rows = {r["code"]: r for r in resp.data["results"]}
    assert set(rows) == set(all_codes())
    assert rows["payroll"]["is_enabled"] is True
    assert rows["inventory"]["is_enabled"] is False
    assert rows["organization"]["core"] is True


@pytest.mark.django_db
def test_get_modules_forbidden_without_read():
    _, company, branch = _mk_org()
    client = _client_with_perms(company=company, branch=branch, perm_codes=["org.company.read"])
    resp = client.get("/api/org/modules/")
    assert resp.status_code == 403


@pytest.mark.django_db
def test_put_enable_disable_persists_and_idempotent():
    _, company, branch = _mk_org()
    client = _client_with_perms(
        company=company, branch=branch, perm_codes=["org.module.read", "org.module.manage"]
    )
    # activar inventario, desactivar nómina
    resp = client.put(
        "/api/org/modules/",
        {"modules": [{"code": "inventory", "is_enabled": True}, {"code": "payroll", "is_enabled": False}]},
        format="json",
    )
    assert resp.status_code == 200, resp.data
    rows = {r["code"]: r for r in resp.data["results"]}
    assert rows["inventory"]["is_enabled"] is True
    assert rows["payroll"]["is_enabled"] is False

    assert CompanyModule.objects.filter(company=company, module_code="inventory", is_enabled=True).exists()
    assert CompanyModule.objects.filter(company=company, module_code="payroll", is_enabled=False).exists()

    # idempotente: repetir no duplica filas
    again = client.put(
        "/api/org/modules/", {"modules": [{"code": "inventory", "is_enabled": True}]}, format="json"
    )
    assert again.status_code == 200
    assert CompanyModule.objects.filter(company=company, module_code="inventory").count() == 1


@pytest.mark.django_db
def test_put_unknown_code_400():
    _, company, branch = _mk_org()
    client = _client_with_perms(
        company=company, branch=branch, perm_codes=["org.module.read", "org.module.manage"]
    )
    resp = client.put(
        "/api/org/modules/", {"modules": [{"code": "nope", "is_enabled": True}]}, format="json"
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_put_core_module_rejected_400():
    _, company, branch = _mk_org()
    client = _client_with_perms(
        company=company, branch=branch, perm_codes=["org.module.read", "org.module.manage"]
    )
    resp = client.put(
        "/api/org/modules/", {"modules": [{"code": "organization", "is_enabled": False}]}, format="json"
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_put_forbidden_without_manage():
    _, company, branch = _mk_org()
    client = _client_with_perms(company=company, branch=branch, perm_codes=["org.module.read"])
    resp = client.put(
        "/api/org/modules/", {"modules": [{"code": "inventory", "is_enabled": True}]}, format="json"
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Servicio: validación del grafo de dependencias (mecanismo)
# ---------------------------------------------------------------------------

class _FakeSpec:
    def __init__(self, code, depends_on=()):
        self.code = code
        self.depends_on = tuple(depends_on)


def test_dependency_validation_raises(monkeypatch):
    specs = {"a": _FakeSpec("a", depends_on=("b",)), "b": _FakeSpec("b")}
    monkeypatch.setattr(services_modules, "get_spec", lambda c: specs.get(c))
    # 'a' habilitado pero 'b' apagado -> conflicto
    with pytest.raises(ModuleDependencyError):
        services_modules._validate_dependency_integrity({"a": True, "b": False})
    # ambos coherentes -> ok
    services_modules._validate_dependency_integrity({"a": True, "b": True})


# ---------------------------------------------------------------------------
# Enforcement: require_module
# ---------------------------------------------------------------------------

class _Req:
    def __init__(self, company):
        self.company = company


def test_require_module_factory_rejects_unknown_code():
    with pytest.raises(ValueError):
        require_module("nope")


@pytest.mark.django_db
def test_require_module_respects_default_state():
    _, company, _ = _mk_org()
    req = _Req(company)
    # base ON
    assert require_module("payroll")().has_permission(req, None) is True
    # core siempre ON
    assert require_module("organization")().has_permission(req, None) is True
    # vertical OFF por defecto
    assert require_module("fuel")().has_permission(req, None) is False


@pytest.mark.django_db
def test_require_module_reflects_company_override():
    _, company, _ = _mk_org()
    req = _Req(company)
    CompanyModule.objects.create(company=company, module_code="fuel", is_enabled=True)
    CompanyModule.objects.create(company=company, module_code="payroll", is_enabled=False)
    assert require_module("fuel")().has_permission(req, None) is True
    assert require_module("payroll")().has_permission(req, None) is False


def test_require_module_without_company_denies():
    assert require_module("payroll")().has_permission(_Req(None), None) is False


# ---------------------------------------------------------------------------
# Auditoría
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_put_writes_audit_event():
    _, company, branch = _mk_org()
    client = _client_with_perms(
        company=company, branch=branch, perm_codes=["org.module.read", "org.module.manage"]
    )
    resp = client.put(
        "/api/org/modules/", {"modules": [{"code": "fuel", "is_enabled": True}]}, format="json"
    )
    assert resp.status_code == 200
    assert AuditEvent.objects.filter(
        event_type="ORG_MODULES_UPDATED", subject_type="COMPANY_MODULE", subject_id=str(company.id)
    ).exists()


# ---------------------------------------------------------------------------
# Integración ACL
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_me_acl_includes_enabled_modules_per_company():
    _, company, branch = _mk_org()
    client = _client_with_perms(company=company, branch=branch, perm_codes=["org.module.read"])
    resp = client.get("/api/auth/me/acl/")
    assert resp.status_code == 200, resp.data
    companies = resp.data.get("companies") or []
    assert companies, "el snapshot debe traer la empresa accesible"
    target = next(c for c in companies if str(c["company_id"]) == str(company.id))
    assert "payroll" in target["enabled_modules"]
    assert "inventory" not in target["enabled_modules"]


@pytest.mark.django_db
def test_bootstrap_session_effective_modules():
    _, company, branch = _mk_org()
    client = _client_with_perms(
        company=company, branch=branch, perm_codes=["org.module.read", "nomina.config.read"]
    )
    resp = client.get("/api/auth/bootstrap/session/")
    assert resp.status_code == 200, resp.data
    enabled = resp.data["enabled_modules"]
    effective = resp.data["effective_modules"]
    assert "payroll" in enabled
    # effective = allowed(catálogo) ∩ enabled; el usuario tiene nomina.* y org.*
    assert "payroll" in effective
    assert "organization" in effective
    assert set(effective).issubset(set(enabled))
    assert "fuel" not in effective
