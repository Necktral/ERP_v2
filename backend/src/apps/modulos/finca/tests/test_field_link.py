"""Tests del puente Asistencia de campo (nómina) → Labores → costeo real (Fase 2).

Verifica que finca **lee** la captura de campo (`FieldCrewReport`/líneas) sin
recapturar nada: rollup de jornales reales por labor/zona, reconciliación del
`labor_code` contra el catálogo, y costeo real (jornales×tarifa + insumos).
"""
from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.kernels.nomina.models import (
    FieldCrew,
    FieldCrewReport,
    FieldCrewReportLine,
    FieldCrewReportStatus,
    FieldWorkDay,
)
from apps.modulos.finca.field_link import (
    field_labor_rollup,
    finca_real_cost_summary,
    reconcile_field_catalog,
)
from apps.modulos.finca.models import InsumoApplication, Labor, Plot, WorkOrder
from apps.modulos.finca.services import upsert_finca_profile
from apps.modulos.hr.models import Employee
from apps.modulos.iam.models import OrgUnit, UserMembership
from apps.modulos.rbac.models import Permission, Role, RoleAssignment, RolePermission

User = get_user_model()
UT = OrgUnit.UnitType


# --------------------------------------------------------------------------- #
# Fixtures helpers
# --------------------------------------------------------------------------- #

def _mk_company():
    s = uuid.uuid4().hex[:6]
    holding = OrgUnit.objects.create(unit_type=UT.HOLDING, name=f"H_{s}")
    return OrgUnit.objects.create(unit_type=UT.COMPANY, name=f"C_{s}", parent=holding)


def _mk_finca(company, name="Finca"):
    return OrgUnit.objects.create(unit_type=UT.BRANCH, name=name, parent=company)


def _emp(company, name="Trab"):
    return Employee.objects.create(company=company, first_name=f"{name}_{uuid.uuid4().hex[:4]}")


_DAY = [0]


def _capture(finca, company, *, labor_code, zone, day_values, status=FieldCrewReportStatus.SUBMITTED):
    """Crea un día-laboral con una cuadrilla, su reporte y líneas (day_value)."""
    _DAY[0] += 1
    work_day = FieldWorkDay.objects.create(
        company=company, branch=finca, work_date=dt.date(2026, 1, 1) + dt.timedelta(days=_DAY[0])
    )
    crew = FieldCrew.objects.create(
        work_day=work_day, name=f"Cuadrilla {_DAY[0]}", supervisor_employee=_emp(company, "Capataz")
    )
    report = FieldCrewReport.objects.create(
        crew=crew, status=status, labor_code=labor_code, labor_name=labor_code, zone_label=zone
    )
    for dv in day_values:
        FieldCrewReportLine.objects.create(
            report=report, employee=_emp(company), day_value=Decimal(str(dv))
        )
    return report


def _labor(company, code, rate="200.00"):
    return Labor.objects.create(
        company=company, code=code, name=code, category="MANTENIMIENTO", unit="JORNAL",
        default_rate=Decimal(rate),
    )


# --------------------------------------------------------------------------- #
# Rollup de jornales reales
# --------------------------------------------------------------------------- #

@pytest.mark.django_db
def test_field_labor_rollup_sums_day_value():
    company = _mk_company()
    finca = _mk_finca(company)
    _labor(company, "chapia_t", "200.00")
    # 1.00 + 1.00 + 0.50 = 2.50 jornales reales
    _capture(finca, company, labor_code="chapia_t", zone="Sector A", day_values=["1.00", "1.00", "0.50"])
    # un reporte en DRAFT no debe contar para costeo
    _capture(finca, company, labor_code="chapia_t", zone="Sector A",
             day_values=["1.00"], status=FieldCrewReportStatus.DRAFT)

    rows = field_labor_rollup(finca)
    assert len(rows) == 1
    r = rows[0]
    assert r["labor_code"] == "chapia_t"
    assert r["matched"] is True
    assert r["jornales"] == "2.50"
    assert r["workers"] == 3
    assert r["labor_cost"] == "500.00"   # 2.50 * 200


@pytest.mark.django_db
def test_unmatched_labor_has_no_cost():
    company = _mk_company()
    finca = _mk_finca(company)
    _capture(finca, company, labor_code="labor_fantasma", zone="X", day_values=["1.00", "1.00"])
    rows = field_labor_rollup(finca)
    assert rows[0]["matched"] is False
    assert rows[0]["labor_cost"] is None
    assert rows[0]["jornales"] == "2.00"


# --------------------------------------------------------------------------- #
# Reconciliación catálogo
# --------------------------------------------------------------------------- #

@pytest.mark.django_db
def test_reconcile_field_catalog():
    company = _mk_company()
    finca = _mk_finca(company)
    _labor(company, "chapia_t")
    _capture(finca, company, labor_code="chapia_t", zone="Sector A", day_values=["1.00"])
    _capture(finca, company, labor_code="labor_fantasma", zone="Sector B", day_values=["1.00"])
    _capture(finca, company, labor_code="chapia_t", zone="Sector A",
             day_values=["1.00"], status=FieldCrewReportStatus.DRAFT)

    rec = reconcile_field_catalog(finca)
    assert rec["reports_total"] == 3
    assert rec["reports_countable"] == 2      # DRAFT no cuenta como countable
    assert "chapia_t" in rec["labors_matched"]
    assert rec["labors_unmatched"] == ["labor_fantasma"]
    assert set(rec["zones_seen"]) == {"Sector A", "Sector B"}


# --------------------------------------------------------------------------- #
# Costeo real
# --------------------------------------------------------------------------- #

@pytest.mark.django_db
def test_finca_real_cost_summary():
    company = _mk_company()
    finca = _mk_finca(company, "Santa Isabel")
    upsert_finca_profile(finca, data={"zona": "Nucleo", "area_manzanas": "120.00"})
    _labor(company, "chapia_t", "200.00")
    _capture(finca, company, labor_code="chapia_t", zone="Sector A", day_values=["1.00", "1.00", "0.50"])
    # insumo vía orden de trabajo (otro spine)
    plot = Plot.objects.create(finca=finca, code="L1", area_manzanas=Decimal("10.00"))
    wo = WorkOrder.objects.create(finca=finca, plot=plot, labor=Labor.objects.get(company=company, code="chapia_t"),
                                  status=WorkOrder.Status.DONE)
    InsumoApplication.objects.create(work_order=wo, item_name="Urea", quantity=Decimal("2.00"), unit_cost=Decimal("50.00"))

    s = finca_real_cost_summary(finca)
    assert s["jornales"] == "2.50"
    assert s["real_labor_cost"] == "500.00"   # 2.5 * 200
    assert s["insumo_cost"] == "100.00"       # 2 * 50
    assert s["total_cost"] == "600.00"
    assert s["cost_per_manzana"] == "5.00"    # 600 / 120
    assert s["uncosted_labors"] == []


# --------------------------------------------------------------------------- #
# HTTP + RBAC
# --------------------------------------------------------------------------- #

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


def _client(user, company, branch):
    c = APIClient()
    login = c.post("/api/auth/login/", {"username": user.username, "password": "pass12345"}, format="json")
    assert login.status_code == 200, login.data
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data.get('access')}")
    c.defaults["HTTP_X_COMPANY_ID"] = str(company.id)
    c.defaults["HTTP_X_BRANCH_ID"] = str(branch.id)
    return c


def _mk_user(prefix="u"):
    username = f"{prefix}_{uuid.uuid4().hex[:8]}"
    return User.objects.create_user(username=username, email=f"{username}@t.local", password="pass12345")


@pytest.mark.django_db
def test_field_reports_forbidden_without_perm():
    company = _mk_company()
    finca = _mk_finca(company)
    user = _grant(_mk_user("n"), company, finca, ["finca.report.read"])  # tiene report pero NO field
    r = _client(user, company, finca).get(f"/api/finca/reports/field-labor-cost/?finca_id={finca.id}")
    assert r.status_code == 403


@pytest.mark.django_db
def test_field_reports_flow():
    company = _mk_company()
    finca = _mk_finca(company, "Santa Isabel")
    upsert_finca_profile(finca, data={"zona": "Nucleo", "area_manzanas": "120.00"})
    _labor(company, "chapia_t", "250.00")
    _capture(finca, company, labor_code="chapia_t", zone="Sector A", day_values=["1.00", "1.00"])
    _capture(finca, company, labor_code="desconocida", zone="Sector B", day_values=["1.00"])
    api = _client(_grant(_mk_user("m"), company, finca, ["finca.field.read"]), company, finca)

    r = api.get(f"/api/finca/reports/field-labor-cost/?finca_id={finca.id}")
    assert r.status_code == 200, r.data
    by_labor = {row["labor_code"]: row for row in r.data["by_labor"]}
    assert by_labor["chapia_t"]["labor_cost"] == "500.00"   # 2 * 250
    assert by_labor["desconocida"]["matched"] is False

    r = api.get(f"/api/finca/reports/field-reconciliation/?finca_id={finca.id}")
    assert r.status_code == 200, r.data
    assert "desconocida" in r.data["labors_unmatched"]

    r = api.get(f"/api/finca/reports/finca-cost/?finca_id={finca.id}")
    assert r.status_code == 200, r.data
    assert r.data["real_labor_cost"] == "500.00"
    assert "desconocida" in r.data["uncosted_labors"]

    r = api.get("/api/finca/reports/company-real-cost/")
    assert r.status_code == 200, r.data
    assert any(z["zona"] == "Nucleo" for z in r.data["by_zona"])
