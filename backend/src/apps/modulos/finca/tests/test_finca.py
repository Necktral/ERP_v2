"""Tests de Manejo de Fincas (Capa 6, básico).

Master-data + bitácora + costeo (por lote y consolidado multi-finca por zona) +
endpoints con RBAC.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from rest_framework.test import APIClient

from apps.modulos.audit.models import AuditEvent
from apps.modulos.finca.models import FincaProfile, InsumoApplication, Labor, Plot, WorkOrder
from apps.modulos.finca.services import company_cost_summary, plot_cost_summary, upsert_finca_profile
from apps.modulos.iam.models import OrgUnit, UserMembership
from apps.modulos.rbac.models import Permission, Role, RoleAssignment, RolePermission

User = get_user_model()
UT = OrgUnit.UnitType


def _mk_company():
    s = uuid.uuid4().hex[:6]
    holding = OrgUnit.objects.create(unit_type=UT.HOLDING, name=f"H_{s}")
    company = OrgUnit.objects.create(unit_type=UT.COMPANY, name=f"C_{s}", parent=holding)
    return company


def _mk_finca(company, name="Finca"):
    return OrgUnit.objects.create(unit_type=UT.BRANCH, name=name, parent=company)


def _grant(user, company, branch, perm_codes):
    UserMembership.objects.get_or_create(user=user, org_unit=company, defaults={"is_active": True})
    UserMembership.objects.get_or_create(user=user, org_unit=branch, defaults={"is_active": True})
    role = Role.objects.create(name=f"role_{uuid.uuid4().hex[:8]}", is_active=True)
    for code in perm_codes:
        perm, _ = Permission.objects.get_or_create(code=code, defaults={"description": code, "is_active": True})
        RolePermission.objects.get_or_create(role=role, permission=perm)
    RoleAssignment.objects.create(user=user, role=role, org_unit=company, is_active=True)
    RoleAssignment.objects.create(user=user, role=role, org_unit=branch, is_active=True)
    return user


def _mk_user(prefix="u"):
    username = f"{prefix}_{uuid.uuid4().hex[:8]}"
    return User.objects.create_user(username=username, email=f"{username}@t.local", password="pass12345")


def _client(user, company, branch):
    c = APIClient()
    login = c.post("/api/auth/login/", {"username": user.username, "password": "pass12345"}, format="json")
    assert login.status_code == 200, login.data
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data.get('access')}")
    c.defaults["HTTP_X_COMPANY_ID"] = str(company.id)
    c.defaults["HTTP_X_BRANCH_ID"] = str(branch.id)
    return c


# ---------------------------------------------------------------------------
# Catálogo / modelo
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_labors_seeded():
    codes = set(Labor.objects.filter(company__isnull=True, is_active=True).values_list("code", flat=True))
    assert {"chapia", "fertilizacion", "control_roya", "corte"} <= codes
    assert Labor.objects.get(code="corte").is_piecework is True


@pytest.mark.django_db
def test_clean_requires_branch():
    company = _mk_company()
    with pytest.raises(ValidationError):
        FincaProfile(finca=company).full_clean()
    with pytest.raises(ValidationError):
        Plot(finca=company, code="x").full_clean()


# ---------------------------------------------------------------------------
# Costeo por lote
# ---------------------------------------------------------------------------

def _labor(company, code="chapia_c", rate="200.00"):
    return Labor.objects.create(
        company=company, code=code, name="L", category="MANTENIMIENTO", unit="JORNAL",
        default_rate=Decimal(rate),
    )


@pytest.mark.django_db
def test_plot_cost_summary():
    company = _mk_company()
    finca = _mk_finca(company)
    plot = Plot.objects.create(finca=finca, code="L1", area_manzanas=Decimal("10.00"))
    labor = _labor(company)
    wo = WorkOrder.objects.create(
        finca=finca, plot=plot, labor=labor, status=WorkOrder.Status.DONE, jornales=Decimal("5.00")
    )
    InsumoApplication.objects.create(work_order=wo, item_name="Urea", quantity=Decimal("2.00"), unit_cost=Decimal("50.00"))

    rows = plot_cost_summary(finca)
    assert len(rows) == 1
    r = rows[0]
    assert r["jornales"] == "5.00"
    assert r["labor_cost"] == "1000.00"   # 5 * 200
    assert r["insumo_cost"] == "100.00"   # 2 * 50
    assert r["total_cost"] == "1100.00"
    assert r["cost_per_manzana"] == "110.00"  # 1100 / 10


@pytest.mark.django_db
def test_company_cost_summary_by_finca_and_zona():
    company = _mk_company()
    fa = _mk_finca(company, "Santa Isabel")
    fb = _mk_finca(company, "Satelite")
    upsert_finca_profile(fa, data={"zona": "Nucleo"})
    upsert_finca_profile(fb, data={"zona": "Matagalpa"})
    labor = _labor(company)
    for f in (fa, fb):
        p = Plot.objects.create(finca=f, code="L1", area_manzanas=Decimal("5.00"))
        WorkOrder.objects.create(finca=f, plot=p, labor=labor, status=WorkOrder.Status.DONE, jornales=Decimal("3.00"))

    summary = company_cost_summary(company)
    assert len(summary["by_finca"]) == 2
    zonas = {z["zona"]: z["total_cost"] for z in summary["by_zona"]}
    assert zonas["Nucleo"] == "600.00"      # 3 * 200
    assert zonas["Matagalpa"] == "600.00"


# ---------------------------------------------------------------------------
# HTTP + RBAC
# ---------------------------------------------------------------------------

_ALL_FINCA_PERMS = [
    "finca.finca.read", "finca.finca.manage", "finca.plot.read", "finca.plot.manage",
    "finca.labor.read", "finca.labor.manage", "finca.work.read", "finca.work.capture", "finca.report.read",
]


@pytest.mark.django_db
def test_plots_forbidden_without_perm():
    company = _mk_company()
    finca = _mk_finca(company)
    user = _grant(_mk_user("n"), company, finca, ["org.company.read"])
    r = _client(user, company, finca).get("/api/finca/plots/")
    assert r.status_code == 403


@pytest.mark.django_db
def test_finca_full_flow():
    company = _mk_company()
    finca = _mk_finca(company, "Santa Isabel")
    user = _grant(_mk_user("mand"), company, finca, _ALL_FINCA_PERMS)
    api = _client(user, company, finca)

    # perfil/geografía
    r = api.put(f"/api/finca/fincas/{finca.id}/profile/", {"zona": "Nucleo", "department": "Matagalpa", "area_manzanas": "700.00"}, format="json")
    assert r.status_code == 200, r.data
    assert r.data["zona"] == "Nucleo"

    # lote
    r = api.post("/api/finca/plots/", {"finca_id": finca.id, "code": "L1", "area_manzanas": "120.00"}, format="json")
    assert r.status_code == 201, r.data
    plot_id = r.data["id"]
    assert AuditEvent.objects.filter(event_type="FINCA_PLOT_CREATED", subject_id=str(plot_id)).exists()

    # labor de empresa con tarifa
    r = api.post("/api/finca/labors/", {"code": "chapia_emp", "name": "Chapia", "category": "MANTENIMIENTO", "unit": "JORNAL", "default_rate": "250.00"}, format="json")
    assert r.status_code == 201, r.data
    labor_id = r.data["id"]

    # orden de trabajo (idempotente por external_ref)
    body = {"plot_id": plot_id, "labor_id": labor_id, "jornales": "8.00", "status": "DONE", "external_ref": "wo-001"}
    r = api.post("/api/finca/work-orders/", body, format="json")
    assert r.status_code == 201, r.data
    wo_id = r.data["id"]
    r2 = api.post("/api/finca/work-orders/", body, format="json")
    assert r2.data["id"] == wo_id  # idempotente

    # insumo
    r = api.post(f"/api/finca/work-orders/{wo_id}/insumos/", {"item_name": "Urea", "quantity": "3.00", "unit_cost": "40.00"}, format="json")
    assert r.status_code == 201, r.data

    # reporte por lote
    r = api.get(f"/api/finca/reports/plot-cost/?finca_id={finca.id}")
    assert r.status_code == 200, r.data
    row = r.data["results"][0]
    assert row["labor_cost"] == "2000.00"   # 8 * 250
    assert row["insumo_cost"] == "120.00"   # 3 * 40

    # reporte consolidado por empresa/zona
    r = api.get("/api/finca/reports/company-cost/")
    assert r.status_code == 200, r.data
    assert any(z["zona"] == "Nucleo" for z in r.data["by_zona"])
