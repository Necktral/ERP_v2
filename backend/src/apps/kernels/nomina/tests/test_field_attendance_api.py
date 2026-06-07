"""Endpoints HTTP del flujo diario de asistencia de campo (capa delgada sobre services).

Cubre: RBAC por acción (nomina.field.*), el flujo completo abrir→lista→cuadrilla→
reporte→evento→consolidar→aprobar (SoD maker-checker), y aplicar a planilla.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.kernels.nomina.models import (
    PayrollEntry,
    PayrollPeriod,
    PayrollSheet,
    PeriodType,
)
from apps.kernels.nomina.services import create_default_nicaragua_config
from apps.modulos.hr.models import Employee
from apps.modulos.iam.models import OrgUnit, UserMembership
from apps.modulos.rbac.models import Permission, Role, RoleAssignment, RolePermission

User = get_user_model()

BASE = "/api/nomina/field"


def _scope():
    t = uuid.uuid4().hex[:8]
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name=f"H{t}", code=f"H-{t}")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, parent=holding, name=f"C{t}", code=f"C-{t}")
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, parent=company, name=f"B{t}", code=f"B-{t}")
    return company, branch


def _client(*, company, branch, perms):
    u = User.objects.create_user(username=f"u_{uuid.uuid4().hex[:8]}", email=f"e_{uuid.uuid4().hex[:8]}@t.com", password="x")
    UserMembership.objects.create(user=u, org_unit=company, is_active=True)
    UserMembership.objects.create(user=u, org_unit=branch, is_active=True)
    role = Role.objects.create(name=f"r_{uuid.uuid4().hex[:8]}", is_active=True)
    for p in perms:
        perm, _ = Permission.objects.get_or_create(code=p, defaults={"description": p, "is_active": True})
        RolePermission.objects.get_or_create(role=role, permission=perm)
    RoleAssignment.objects.create(user=u, role=role, org_unit=company, is_active=True)
    RoleAssignment.objects.create(user=u, role=role, org_unit=branch, is_active=True)
    c = APIClient()
    login = c.post("/api/auth/login/", {"username": u.username, "password": "x"}, format="json")
    assert login.status_code == 200, login.data
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
    c.defaults["HTTP_X_COMPANY_ID"] = str(company.id)
    c.defaults["HTTP_X_BRANCH_ID"] = str(branch.id)
    c.user = u
    return c


def _emp(company, first_name="Trabajador"):
    return Employee.objects.create(
        company=company, employee_code=f"E-{uuid.uuid4().hex[:6]}",
        first_name=first_name, last_name="Campo", is_active=True,
    )


def _period(company):
    return PayrollPeriod.objects.create(
        company=company, year=2026, month=6, period_type=PeriodType.CATORCENA,
        start_date=date(2026, 6, 1), end_date=date(2026, 6, 14), working_days=14,
    )


def _config(company, actor):
    req = SimpleNamespace(user=actor, META={}, company=company, branch=None, _request=None,
                          ctx=None, request_id="", path="", method="POST")
    return create_default_nicaragua_config(request=req, actor=actor, company=company, fiscal_year=2026)


CAPTURE_PERMS = [
    "nomina.field.capture", "nomina.field.consolidate",
    "nomina.field.approve.request", "nomina.field.apply", "nomina.field.read",
]


def _open_consolidated_day(maker, company, branch, period, e1, e2):
    """Corre el flujo hasta consolidar y devuelve el work_day_id."""
    r = maker.post(f"{BASE}/work-days/", {
        "work_date": "2026-06-02", "branch_id": branch.id, "payroll_period_id": period.id,
    }, format="json")
    assert r.status_code == 201, r.data
    wd = r.data["id"]

    r = maker.post(f"{BASE}/work-days/{wd}/rollcall/", {
        "lines": [{"employee_id": e1.id, "status": "PRESENT"}, {"employee_id": e2.id, "status": "PRESENT"}],
    }, format="json")
    assert r.status_code == 201, r.data

    r = maker.post(f"{BASE}/work-days/{wd}/crews/", {"name": "Cuadrilla A", "supervisor_employee_id": e2.id}, format="json")
    assert r.status_code == 201, r.data
    crew_id = r.data["id"]

    r = maker.post(f"{BASE}/crews/{crew_id}/report/", {
        "lines": [{"employee_id": e1.id, "event_type": "PRESENT", "day_value": "1.00"}],
        "labor_code": "COSECHA",
    }, format="json")
    assert r.status_code == 201, r.data

    r = maker.post(f"{BASE}/work-days/{wd}/events/", {"employee_id": e1.id, "event_type": "PRESENT"}, format="json")
    assert r.status_code == 201, r.data

    r = maker.post(f"{BASE}/work-days/{wd}/consolidate/", {}, format="json")
    assert r.status_code == 200, r.data
    assert len(r.data["consolidations"]) >= 1
    return wd


@pytest.mark.django_db
def test_open_work_day_requires_capture_permission():
    company, branch = _scope()
    no_perm = _client(company=company, branch=branch, perms=["nomina.field.read"])
    r = no_perm.post(f"{BASE}/work-days/", {"work_date": "2026-06-02", "branch_id": branch.id}, format="json")
    assert r.status_code == 403, r.status_code

    ok = _client(company=company, branch=branch, perms=["nomina.field.capture"])
    r = ok.post(f"{BASE}/work-days/", {"work_date": "2026-06-02", "branch_id": branch.id}, format="json")
    assert r.status_code == 201, r.data
    assert r.data["status"] == "OPEN"


@pytest.mark.django_db
def test_full_field_flow_through_sod_approval():
    company, branch = _scope()
    maker = _client(company=company, branch=branch, perms=CAPTURE_PERMS)
    checker = _client(company=company, branch=branch, perms=["nomina.field.approve", "nomina.field.read"])
    _config(company, maker.user)
    period = _period(company)
    e1, e2 = _emp(company, "Juan"), _emp(company, "Maria")

    wd = _open_consolidated_day(maker, company, branch, period, e1, e2)

    # Maker solicita aprobación (SoD)
    r = maker.post(f"{BASE}/work-days/{wd}/approve-request/", {"reason": "cierre del día"}, format="json")
    assert r.status_code == 202, r.data
    approval_id = r.data["approval_request_id"]

    # Checker (usuario distinto) aprueba
    r = checker.post(f"{BASE}/approvals/{approval_id}/approve/", {}, format="json")
    assert r.status_code == 200, r.data
    assert r.data["status"] == "APPROVED"

    # Las consolidaciones quedan aprobadas
    r = maker.get(f"{BASE}/work-days/{wd}/consolidations/")
    assert r.status_code == 200, r.data
    assert all(c["status"] == "APPROVED" for c in r.data["results"])


@pytest.mark.django_db
def test_sod_blocks_self_approval():
    company, branch = _scope()
    # Un único usuario con permiso de solicitar Y aprobar: no puede aprobar su propia solicitud.
    both = _client(company=company, branch=branch, perms=CAPTURE_PERMS + ["nomina.field.approve"])
    _config(company, both.user)
    period = _period(company)
    e1, e2 = _emp(company, "Ana"), _emp(company, "Luis")

    wd = _open_consolidated_day(both, company, branch, period, e1, e2)
    r = both.post(f"{BASE}/work-days/{wd}/approve-request/", {}, format="json")
    assert r.status_code == 202, r.data
    approval_id = r.data["approval_request_id"]

    r = both.post(f"{BASE}/approvals/{approval_id}/approve/", {}, format="json")
    assert r.status_code == 403, r.data  # SelfApprovalError


@pytest.mark.django_db
def test_apply_approved_attendance_to_sheet():
    company, branch = _scope()
    maker = _client(company=company, branch=branch, perms=CAPTURE_PERMS)
    checker = _client(company=company, branch=branch, perms=["nomina.field.approve", "nomina.field.read"])
    _config(company, maker.user)
    period = _period(company)
    e1, e2 = _emp(company, "Pedro"), _emp(company, "Sara")

    wd = _open_consolidated_day(maker, company, branch, period, e1, e2)
    r = maker.post(f"{BASE}/work-days/{wd}/approve-request/", {}, format="json")
    approval_id = r.data["approval_request_id"]
    checker.post(f"{BASE}/approvals/{approval_id}/approve/", {}, format="json")

    # Planilla con la línea de e1
    sheet = PayrollSheet.objects.create(period=period, branch=branch, sheet_name="Finca", has_inss=True)
    entry = PayrollEntry.objects.create(
        sheet=sheet, employee=e1, full_name="Pedro Campo", has_inss=True,
        base_salary_nio=Decimal("14000.00"), days_in_period=14, days_worked=Decimal("0.00"),
    )

    r = maker.post(f"{BASE}/sheets/{sheet.id}/apply-field-attendance/", {}, format="json")
    assert r.status_code == 200, r.data
    assert entry.id in r.data["applied"]

    entry.refresh_from_db()
    assert entry.days_worked > Decimal("0.00")
