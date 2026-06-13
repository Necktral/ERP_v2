"""Tests del listado de cuentas de crédito del comisariato (GET /api/comisariato/accounts/)."""
from __future__ import annotations

import uuid

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.modulos.comisariato.models import CustomerCreditAccount
from apps.modulos.iam.models import OrgUnit, UserMembership
from apps.modulos.parties.models import Party
from apps.modulos.rbac.models import Permission, Role, RoleAssignment, RolePermission

User = get_user_model()


def _mk_org():
    s = uuid.uuid4().hex[:6]
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name=f"H_{s}")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name=f"C_{s}", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name=f"B_{s}", parent=company)
    return holding, company, branch


def _client(*, company, branch, perms):
    username = f"cm_{uuid.uuid4().hex[:8]}"
    user = User.objects.create_user(username=username, email=f"{username}@test.local", password="pass12345")
    UserMembership.objects.create(user=user, org_unit=company, is_active=True)
    role = Role.objects.create(name=f"role_{uuid.uuid4().hex[:8]}", is_active=True)
    for code in perms:
        perm, _ = Permission.objects.get_or_create(code=code, defaults={"description": code, "is_active": True})
        RolePermission.objects.get_or_create(role=role, permission=perm)
    RoleAssignment.objects.create(user=user, role=role, org_unit=company, is_active=True)
    client = APIClient()
    login = client.post("/api/auth/login/", {"username": user.username, "password": "pass12345"}, format="json")
    assert login.status_code == 200
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data.get('access')}")
    client.defaults["HTTP_X_COMPANY_ID"] = str(company.id)
    client.defaults["HTTP_X_BRANCH_ID"] = str(branch.id)
    return client


def _party(company, nombre):
    return Party.objects.create(company=company, party_type=Party.PartyType.NATURAL, display_name=nombre)


@pytest.mark.django_db
def test_list_accounts_with_filters_and_scope():
    _, company, branch = _mk_org()
    _, other_company, _ = _mk_org()
    client = _client(company=company, branch=branch, perms=("comisariato.read",))

    CustomerCreditAccount.objects.create(
        company=company, party=_party(company, "Rosa Centeno"), segment="EMPLOYEE", credit_limit=2000
    )
    CustomerCreditAccount.objects.create(
        company=company, party=_party(company, "Pedro Productor"), segment="PRODUCER", credit_limit=0,
        is_active=False,
    )
    # cuenta de OTRA empresa: invisible
    CustomerCreditAccount.objects.create(
        company=other_company, party=_party(other_company, "Ajeno"), segment="PUBLIC", credit_limit=0
    )

    r = client.get("/api/comisariato/accounts/")
    assert r.status_code == 200 and r.data["count"] == 2
    nombres = {row["party_display_name"] for row in r.data["results"]}
    assert nombres == {"Rosa Centeno", "Pedro Productor"}
    fila = next(x for x in r.data["results"] if x["party_display_name"] == "Rosa Centeno")
    assert fila["segment"] == "EMPLOYEE" and fila["outstanding"] == "0.00"

    r = client.get("/api/comisariato/accounts/", {"segment": "PRODUCER"})
    assert r.data["count"] == 1
    r = client.get("/api/comisariato/accounts/", {"q": "rosa"})
    assert r.data["count"] == 1
    r = client.get("/api/comisariato/accounts/", {"is_active": "true"})
    assert r.data["count"] == 1


@pytest.mark.django_db
def test_list_accounts_requires_read_perm_and_upsert_still_works():
    _, company, branch = _mk_org()
    sin_perm = _client(company=company, branch=branch, perms=("comisariato.sell",))
    assert sin_perm.get("/api/comisariato/accounts/").status_code == 403

    gestor = _client(
        company=company, branch=branch, perms=("comisariato.read", "comisariato.account.manage")
    )
    p = _party(company, "Nuevo Cliente")
    r = gestor.post(
        "/api/comisariato/accounts/",
        {"party_id": p.id, "segment": "PUBLIC", "credit_limit": "500.00"},
        format="json",
    )
    assert r.status_code == 200, r.data
    assert r.data["party_display_name"] == "Nuevo Cliente"
    r = gestor.get("/api/comisariato/accounts/")
    assert r.data["count"] == 1
