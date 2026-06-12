"""Tests de la API REST de terceros (/api/parties/) — directorio multi-empresa."""
from __future__ import annotations

import uuid

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.modulos.iam.models import OrgUnit, UserMembership
from apps.modulos.parties.models import Party, PartyRole
from apps.modulos.rbac.models import Permission, Role, RoleAssignment, RolePermission

User = get_user_model()

ALL_PERMS = (
    "parties.party.read",
    "parties.party.create",
    "parties.party.update",
    "parties.role.manage",
)


def _mk_org():
    s = uuid.uuid4().hex[:6]
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name=f"H_{s}")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name=f"C_{s}", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name=f"B_{s}", parent=company)
    return holding, company, branch


def _client_with_perms(*, company, branch, perm_codes):
    username = f"pt_{uuid.uuid4().hex[:8]}"
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


@pytest.mark.django_db
def test_create_party_with_roles_and_list_filters():
    _, company, branch = _mk_org()
    client = _client_with_perms(company=company, branch=branch, perm_codes=ALL_PERMS)

    r = client.post(
        "/api/parties/",
        {
            "party_type": "JURIDICAL",
            "display_name": "Agroinsumos del Norte",
            "tax_id": "J0310000000001",
            "roles": ["SUPPLIER"],
        },
        format="json",
    )
    assert r.status_code == 201, r.data
    assert r.data["roles"] == ["SUPPLIER"]
    assert r.data["tax_id"] == "J0310000000001"

    client.post(
        "/api/parties/",
        {"party_type": "NATURAL", "display_name": "Rosa Centeno", "roles": ["CUSTOMER"]},
        format="json",
    )

    # filtro por texto
    r = client.get("/api/parties/", {"q": "agroinsumos"})
    assert r.status_code == 200
    assert r.data["count"] == 1
    assert r.data["results"][0]["display_name"] == "Agroinsumos del Norte"

    # filtro por rol activo
    r = client.get("/api/parties/", {"role": "CUSTOMER"})
    assert r.data["count"] == 1
    assert r.data["results"][0]["display_name"] == "Rosa Centeno"


@pytest.mark.django_db
def test_update_party_and_duplicate_tax_id_422():
    _, company, branch = _mk_org()
    client = _client_with_perms(company=company, branch=branch, perm_codes=ALL_PERMS)

    a = client.post(
        "/api/parties/", {"party_type": "JURIDICAL", "display_name": "Uno", "tax_id": "J111"}, format="json"
    ).data
    client.post("/api/parties/", {"party_type": "JURIDICAL", "display_name": "Dos"}, format="json")

    r = client.patch(f"/api/parties/{a['id']}/", {"status": "BLOCKED", "phone": "88001122"}, format="json")
    assert r.status_code == 200, r.data
    assert r.data["status"] == "BLOCKED"
    assert r.data["phone"] == "88001122"

    # tax_id duplicado (case-insensitive por normalización) → 422 del envelope
    r = client.post(
        "/api/parties/", {"party_type": "JURIDICAL", "display_name": "Tres", "tax_id": "j111"}, format="json"
    )
    assert r.status_code == 422, r.data


@pytest.mark.django_db
def test_assign_and_revoke_role():
    _, company, branch = _mk_org()
    client = _client_with_perms(company=company, branch=branch, perm_codes=ALL_PERMS)
    p = client.post("/api/parties/", {"party_type": "NATURAL", "display_name": "Pedro"}, format="json").data

    r = client.post(f"/api/parties/{p['id']}/roles/", {"role": "PRODUCER"}, format="json")
    assert r.status_code == 200 and r.data["roles"] == ["PRODUCER"]

    # asignar el mismo rol activo otra vez → 422
    r = client.post(f"/api/parties/{p['id']}/roles/", {"role": "PRODUCER"}, format="json")
    assert r.status_code == 422

    r = client.post(f"/api/parties/{p['id']}/roles/revoke/", {"role": "PRODUCER"}, format="json")
    assert r.status_code == 200 and r.data["roles"] == []
    assert PartyRole.objects.filter(party_id=p["id"], is_active=True).count() == 0


@pytest.mark.django_db
def test_party_scoped_by_company_and_permissions():
    _, company, branch = _mk_org()
    _, other_company, _ = _mk_org()
    client = _client_with_perms(company=company, branch=branch, perm_codes=ALL_PERMS)

    foreign = Party.objects.create(
        company=other_company, party_type=Party.PartyType.NATURAL, display_name="Ajeno"
    )
    # tercero de otra empresa: invisible (404)
    assert client.get(f"/api/parties/{foreign.id}/").status_code == 404
    assert client.patch(f"/api/parties/{foreign.id}/", {"phone": "1"}, format="json").status_code == 404

    # solo lectura: crear/actualizar/roles → 403
    reader = _client_with_perms(company=company, branch=branch, perm_codes=("parties.party.read",))
    own = client.post("/api/parties/", {"party_type": "NATURAL", "display_name": "Local"}, format="json").data
    assert reader.get("/api/parties/").status_code == 200
    assert (
        reader.post("/api/parties/", {"party_type": "NATURAL", "display_name": "X"}, format="json").status_code
        == 403
    )
    assert reader.patch(f"/api/parties/{own['id']}/", {"phone": "2"}, format="json").status_code == 403
    assert (
        reader.post(f"/api/parties/{own['id']}/roles/", {"role": "CUSTOMER"}, format="json").status_code == 403
    )
