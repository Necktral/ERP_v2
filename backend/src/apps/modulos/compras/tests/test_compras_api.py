"""Tests de la API de compras: listado paginado con filtros + flujo crear→postear→anular."""
from __future__ import annotations

import uuid

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.modulos.iam.models import OrgUnit, UserMembership
from apps.modulos.rbac.models import Permission, Role, RoleAssignment, RolePermission

User = get_user_model()

PERMS = (
    "procurement.doc.read",
    "procurement.doc.create",
    "procurement.doc.post",
    "procurement.doc.void",
)


def _mk_org():
    s = uuid.uuid4().hex[:6]
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name=f"H_{s}")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name=f"C_{s}", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name=f"B_{s}", parent=company)
    return holding, company, branch


def _client_with_perms(*, company, branch, perm_codes=PERMS):
    username = f"pc_{uuid.uuid4().hex[:8]}"
    user = User.objects.create_user(username=username, email=f"{username}@test.local", password="pass12345")
    UserMembership.objects.create(user=user, org_unit=company, is_active=True)
    UserMembership.objects.create(user=user, org_unit=branch, is_active=True)
    role = Role.objects.create(name=f"role_{uuid.uuid4().hex[:8]}", is_active=True)
    for code in perm_codes:
        perm, _ = Permission.objects.get_or_create(code=code, defaults={"description": code, "is_active": True})
        RolePermission.objects.get_or_create(role=role, permission=perm)
    RoleAssignment.objects.create(user=user, role=role, org_unit=company, is_active=True)

    client = APIClient()
    login = client.post("/api/auth/login/", {"username": user.username, "password": "pass12345"}, format="json")
    assert login.status_code == 200, login.data
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data.get('access')}")
    client.defaults["HTTP_X_COMPANY_ID"] = str(company.id)
    client.defaults["HTTP_X_BRANCH_ID"] = str(branch.id)
    return client


def _draft(client, **extra):
    body = {
        "doc_type": "SUPPLIER_INVOICE",
        "supplier_name": "Proveedor Norte",
        "subtotal": "100.00",
        "tax_total": "15.00",
        "total": "115.00",
        **extra,
    }
    r = client.post("/api/procurement/docs/", body, format="json")
    assert r.status_code == 201, r.data
    return r.data["id"]


@pytest.mark.django_db
def test_list_docs_with_filters_and_lifecycle():
    _, company, branch = _mk_org()
    client = _client_with_perms(company=company, branch=branch)

    d1 = _draft(client)
    d2 = _draft(client, doc_type="GOODS_RECEIPT", supplier_name="Agroinsumos Sur")

    # postear d1 → status POSTED con número asignado
    r = client.post(f"/api/procurement/docs/{d1}/post/")
    assert r.status_code == 200 and r.data["status"] == "POSTED" and r.data["number"] >= 1

    # listado completo
    r = client.get("/api/procurement/docs/")
    assert r.status_code == 200 and r.data["count"] == 2
    por_id = {row["id"]: row for row in r.data["results"]}
    assert por_id[d1]["status"] == "POSTED"
    assert por_id[d2]["status"] == "DRAFT"

    # filtro por status y por texto
    r = client.get("/api/procurement/docs/", {"status": "DRAFT"})
    assert r.data["count"] == 1 and r.data["results"][0]["id"] == d2
    r = client.get("/api/procurement/docs/", {"q": "agroinsumos"})
    assert r.data["count"] == 1 and r.data["results"][0]["id"] == d2
    r = client.get("/api/procurement/docs/", {"doc_type": "SUPPLIER_INVOICE"})
    assert r.data["count"] == 1 and r.data["results"][0]["id"] == d1

    # anular el posteado
    r = client.post(f"/api/procurement/docs/{d1}/void/", {"reason": "duplicado"}, format="json")
    assert r.status_code == 200 and r.data["status"] == "VOIDED"
    r = client.get("/api/procurement/docs/", {"status": "VOIDED"})
    assert r.data["count"] == 1


@pytest.mark.django_db
def test_list_docs_scoped_by_branch_and_permission():
    _, company, branch = _mk_org()
    client = _client_with_perms(company=company, branch=branch)
    _draft(client)

    # otra sucursal de la MISMA empresa: no ve los docs de la primera
    s = uuid.uuid4().hex[:6]
    branch2 = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name=f"B2_{s}", parent=company)
    client2 = _client_with_perms(company=company, branch=branch2)
    r = client2.get("/api/procurement/docs/")
    assert r.status_code == 200 and r.data["count"] == 0

    # sin permiso read → 403
    sin_read = _client_with_perms(company=company, branch=branch, perm_codes=("procurement.doc.create",))
    assert sin_read.get("/api/procurement/docs/").status_code == 403
