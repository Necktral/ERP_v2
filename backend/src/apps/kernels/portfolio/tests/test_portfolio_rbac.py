"""PR-6: RBAC en endpoints de portfolio (cierra rbac=0 — vector de fraude).

Antes, las ViewSets de cartera usaban solo IsAuthenticated: cualquier usuario autenticado
podía leer/ajustar/castigar CxC/CxP. Ahora cada acción exige su permiso `portfolio.*`,
con permiso propio para las operaciones sensibles (adjust/writeoff/disburse).
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.kernels.portfolio.services import create_receivable
from apps.modulos.iam.models import OrgUnit, UserMembership
from apps.modulos.parties.models import Party
from apps.modulos.rbac.models import Permission, Role, RoleAssignment, RolePermission

User = get_user_model()


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
    return c


def _party(company):
    t = uuid.uuid4().hex[:8]
    return Party.objects.create(
        company=company, party_type=Party.PartyType.JURIDICAL, display_name=f"Cliente {t}", tax_id=f"RUC-{t}",
    )


def _receivable(company, branch, party):
    return create_receivable(
        company=company, branch=branch, party=party,
        reference_type="BILLING_DOC", reference_id=int(uuid.uuid4().int % 1_000_000),
        principal_amount=Decimal("100.00"), currency="NIO", issue_date=date.today(), due_date=date.today(),
    )


@pytest.mark.django_db
def test_list_receivables_denied_without_permission():
    company, branch = _scope()
    c = _client(company=company, branch=branch, perms=[])  # autenticado pero sin permisos
    r = c.get("/api/portfolio/receivables/")
    assert r.status_code == 403, r.status_code


@pytest.mark.django_db
def test_list_receivables_allowed_with_read_permission():
    company, branch = _scope()
    c = _client(company=company, branch=branch, perms=["portfolio.receivable.read"])
    r = c.get("/api/portfolio/receivables/")
    assert r.status_code == 200, r.data


@pytest.mark.django_db
def test_writeoff_denied_without_writeoff_permission():
    # Tiene read pero NO writeoff: la acción sensible debe ser 403.
    company, branch = _scope()
    party = _party(company)
    rec = _receivable(company, branch, party)
    c = _client(company=company, branch=branch, perms=["portfolio.receivable.read"])
    r = c.post(f"/api/portfolio/receivables/{rec.id}/writeoff/", {"reason": "incobrable"}, format="json")
    assert r.status_code == 403, r.status_code


@pytest.mark.django_db
def test_writeoff_allowed_with_writeoff_permission():
    company, branch = _scope()
    party = _party(company)
    rec = _receivable(company, branch, party)
    c = _client(
        company=company, branch=branch,
        perms=["portfolio.receivable.read", "portfolio.receivable.writeoff"],
    )
    r = c.post(f"/api/portfolio/receivables/{rec.id}/writeoff/", {"reason": "incobrable"}, format="json")
    # Pasa el gate de permisos (no 403). El resultado de negocio puede ser 200 o 400.
    assert r.status_code != 403, r.status_code
