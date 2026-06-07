"""Endpoints HTTP del régimen INSS (afiliación fechada + elección por período).

Cubre: RBAC (nomina.inss.manage/read), afiliación maestra con cierre de la previa,
override por período, resolución por afiliación y auto-clasificación CON/SIN INSS.
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
    EmployeeInssEnrollment,
    InssElectionSource,
    InssRegime,
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

BASE = "/api/nomina"


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
        first_name=first_name, last_name="INSS", is_active=True,
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


def _entry(sheet, employee, *, has_inss=True):
    return PayrollEntry.objects.create(
        sheet=sheet, employee=employee, full_name=f"{employee.first_name} INSS",
        has_inss=has_inss, base_salary_nio=Decimal("14000.00"),
        days_in_period=14, days_worked=Decimal("14.00"),
    )


# ---------------------------------------------------------------------------
# Afiliación maestra fechada
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_create_enrollment_requires_manage_permission():
    company, branch = _scope()
    e = _emp(company)
    no_perm = _client(company=company, branch=branch, perms=["nomina.inss.read"])
    r = no_perm.post(f"{BASE}/inss/employees/{e.id}/enrollments/",
                     {"regime": "AFFILIATED", "effective_from": "2026-01-01"}, format="json")
    assert r.status_code == 403, r.status_code


@pytest.mark.django_db
def test_create_enrollment_closes_previous():
    company, branch = _scope()
    e = _emp(company)
    c = _client(company=company, branch=branch, perms=["nomina.inss.manage", "nomina.inss.read"])

    r1 = c.post(f"{BASE}/inss/employees/{e.id}/enrollments/",
                {"regime": "AFFILIATED", "effective_from": "2026-01-01"}, format="json")
    assert r1.status_code == 201, r1.data
    r2 = c.post(f"{BASE}/inss/employees/{e.id}/enrollments/",
                {"regime": "NOT_AFFILIATED", "effective_from": "2026-06-01", "reason": "dejó de cotizar"}, format="json")
    assert r2.status_code == 201, r2.data

    # La afiliación previa quedó cerrada el día anterior; la nueva abierta.
    prev = EmployeeInssEnrollment.objects.get(id=r1.data["id"])
    assert prev.effective_to == date(2026, 5, 31)
    nueva = EmployeeInssEnrollment.objects.get(id=r2.data["id"])
    assert nueva.effective_to is None

    r = c.get(f"{BASE}/inss/employees/{e.id}/enrollments/")
    assert r.status_code == 200, r.data
    assert len(r.data["results"]) == 2


# ---------------------------------------------------------------------------
# Elección por período (override) + resolución
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_set_period_election_override():
    company, branch = _scope()
    e = _emp(company)
    period = _period(company)
    c = _client(company=company, branch=branch, perms=["nomina.inss.manage", "nomina.inss.read"])

    r = c.post(f"{BASE}/periods/{period.id}/inss/elections/",
               {"employee_id": e.id, "elected_has_inss": False, "reason": "eventual"}, format="json")
    assert r.status_code == 201, r.data
    assert r.data["elected_has_inss"] is False
    assert r.data["source"] == InssElectionSource.OVERRIDE

    r = c.get(f"{BASE}/periods/{period.id}/inss/elections/")
    assert r.status_code == 200, r.data
    assert len(r.data["results"]) == 1


@pytest.mark.django_db
def test_election_requires_employee_or_cedula():
    company, branch = _scope()
    period = _period(company)
    c = _client(company=company, branch=branch, perms=["nomina.inss.manage"])
    r = c.post(f"{BASE}/periods/{period.id}/inss/elections/", {"elected_has_inss": True}, format="json")
    assert r.status_code == 422, r.data  # validación de serializer del proyecto


@pytest.mark.django_db
def test_resolve_period_elections_from_enrollment():
    company, branch = _scope()
    period = _period(company)
    e_si, e_no = _emp(company, "Afiliado"), _emp(company, "NoAfiliado")
    EmployeeInssEnrollment.objects.create(company=company, employee=e_si, regime=InssRegime.AFFILIATED, effective_from=date(2026, 1, 1))
    EmployeeInssEnrollment.objects.create(company=company, employee=e_no, regime=InssRegime.NOT_AFFILIATED, effective_from=date(2026, 1, 1))
    sheet = PayrollSheet.objects.create(period=period, branch=branch, sheet_name="Finca", has_inss=True)
    _entry(sheet, e_si)
    _entry(sheet, e_no)

    c = _client(company=company, branch=branch, perms=["nomina.inss.manage"])
    r = c.post(f"{BASE}/periods/{period.id}/inss/resolve/", {}, format="json")
    assert r.status_code == 200, r.data
    elections = r.data["elections"]  # dict Python en memoria: claves enteras
    assert elections[e_si.id] is True
    assert elections[e_no.id] is False


# ---------------------------------------------------------------------------
# Auto-clasificación CON/SIN INSS
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_classify_moves_entry_to_sibling_sheet():
    company, branch = _scope()
    c = _client(company=company, branch=branch, perms=["nomina.inss.manage"])
    _config(company, c.user)
    period = _period(company)
    e = _emp(company, "Eventual")
    # No afiliado, pero su entry está en la planilla CON INSS → debe moverse.
    EmployeeInssEnrollment.objects.create(company=company, employee=e, regime=InssRegime.NOT_AFFILIATED, effective_from=date(2026, 1, 1))
    sheet_con = PayrollSheet.objects.create(period=period, branch=branch, sheet_name="Finca CON INSS", has_inss=True)
    entry = _entry(sheet_con, e, has_inss=True)

    r = c.post(f"{BASE}/periods/{period.id}/inss/classify/", {}, format="json")
    assert r.status_code == 200, r.data
    assert r.data["moved"] >= 1

    entry.refresh_from_db()
    assert entry.has_inss is False
    assert entry.sheet.has_inss is False
    assert entry.sheet_id != sheet_con.id
