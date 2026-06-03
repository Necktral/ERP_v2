"""
Tests del módulo iam — identidad, organización y contexto.

Modelo: jerarquía OrgUnit (HOLDING/COMPANY/BRANCH), closure table automática,
bloqueo de cambio de parent, invariantes de CompanyLink/LinkGrant.
Selectores: has_intercompany_grant, accesibilidad de companies/branches,
snapshot de capacidades admin y build_acl_snapshot. API: ContextEchoView.
"""
from __future__ import annotations

import uuid

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from rest_framework.test import APIClient

from apps.modulos.iam.models import (
    AdminGrant,
    CompanyLink,
    LinkGrant,
    OrgClosure,
    OrgUnit,
    UserMembership,
)
from apps.modulos.iam.selectors import (
    build_acl_snapshot,
    get_accessible_branches,
    get_accessible_companies,
    get_admin_caps_snapshot,
    has_intercompany_grant,
)
from apps.modulos.rbac.models import Permission

User = get_user_model()
UT = OrgUnit.UnitType


def _mk_org():
    s = uuid.uuid4().hex[:6]
    holding = OrgUnit.objects.create(unit_type=UT.HOLDING, name=f"H_{s}")
    company = OrgUnit.objects.create(unit_type=UT.COMPANY, name=f"C_{s}", parent=holding)
    branch = OrgUnit.objects.create(unit_type=UT.BRANCH, name=f"B_{s}", parent=company)
    return holding, company, branch


def _mk_user(prefix="iam"):
    username = f"{prefix}_{uuid.uuid4().hex[:8]}"
    return User.objects.create_user(username=username, email=f"{username}@test.local", password="pass12345")


# ---------------------------------------------------------------------------
# Modelo: OrgUnit jerarquía y closure
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_orgunit_clean_enforces_hierarchy():
    holding, company, _ = _mk_org()
    # HOLDING no puede tener parent.
    with pytest.raises(ValidationError):
        OrgUnit(unit_type=UT.HOLDING, name="x", parent=holding).clean()
    # COMPANY requiere parent HOLDING.
    with pytest.raises(ValidationError):
        OrgUnit(unit_type=UT.COMPANY, name="x").clean()
    OrgUnit(unit_type=UT.COMPANY, name="ok", parent=holding).clean()
    # BRANCH requiere parent COMPANY.
    with pytest.raises(ValidationError):
        OrgUnit(unit_type=UT.BRANCH, name="x", parent=holding).clean()
    OrgUnit(unit_type=UT.BRANCH, name="ok", parent=company).clean()


@pytest.mark.django_db
def test_orgunit_closure_built_on_create():
    holding, company, branch = _mk_org()
    rows = {(r.ancestor_id, r.depth) for r in OrgClosure.objects.filter(descendant=branch)}
    assert (branch.id, 0) in rows
    assert (company.id, 1) in rows
    assert (holding.id, 2) in rows


@pytest.mark.django_db
def test_orgunit_parent_change_blocked():
    holding, company, _ = _mk_org()
    other_holding = OrgUnit.objects.create(unit_type=UT.HOLDING, name=f"H2_{uuid.uuid4().hex[:4]}")
    company.parent = other_holding
    with pytest.raises(ValidationError):
        company.save()


@pytest.mark.django_db
def test_companylink_clean_invariants():
    _, c1, _ = _mk_org()
    _, c2, _ = _mk_org()
    _, _, branch = _mk_org()
    with pytest.raises(ValidationError):
        CompanyLink(from_company=c1, to_company=c1).clean()  # from == to
    with pytest.raises(ValidationError):
        CompanyLink(from_company=c1, to_company=branch).clean()  # to no es COMPANY
    CompanyLink(from_company=c1, to_company=c2).clean()  # válido


@pytest.mark.django_db
def test_linkgrant_clean_scope_branch():
    _, c1, b1 = _mk_org()
    _, c2, _ = _mk_org()
    _, _, b3 = _mk_org()  # branch de otra company
    link = CompanyLink.objects.create(from_company=c1, to_company=c2)
    perm = Permission.objects.create(code=f"p_{uuid.uuid4().hex[:6]}", is_active=True)

    LinkGrant(link=link, permission=perm, scope_org_unit=None).clean()  # company-wide ok
    with pytest.raises(ValidationError):
        LinkGrant(link=link, permission=perm, scope_org_unit=c1).clean()  # no es BRANCH
    LinkGrant(link=link, permission=perm, scope_org_unit=b1).clean()  # BRANCH de from_company
    with pytest.raises(ValidationError):
        LinkGrant(link=link, permission=perm, scope_org_unit=b3).clean()  # BRANCH de otra company


# ---------------------------------------------------------------------------
# Selectores: intercompany
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_has_intercompany_grant_same_company_is_true():
    _, c1, _ = _mk_org()
    assert has_intercompany_grant(from_company=c1, to_company=c1, permission_code="anything") is True


@pytest.mark.django_db
def test_has_intercompany_grant_company_wide():
    _, c1, b1 = _mk_org()
    _, c2, _ = _mk_org()
    perm = Permission.objects.create(code=f"inv.read_{uuid.uuid4().hex[:6]}", is_active=True)

    assert has_intercompany_grant(from_company=c1, to_company=c2, permission_code=perm.code) is False
    link = CompanyLink.objects.create(from_company=c1, to_company=c2)
    assert has_intercompany_grant(from_company=c1, to_company=c2, permission_code=perm.code) is False  # link sin grant
    LinkGrant.objects.create(link=link, permission=perm, access_mode="READ", scope_org_unit=None, is_active=True)
    assert has_intercompany_grant(from_company=c1, to_company=c2, permission_code=perm.code, mode="READ") is True
    # Grant company-wide también satisface una consulta scoped a branch.
    assert (
        has_intercompany_grant(
            from_company=c1, to_company=c2, permission_code=perm.code, mode="READ", scope_branch=b1
        )
        is True
    )


@pytest.mark.django_db
def test_has_intercompany_grant_branch_specific():
    _, c1, b1 = _mk_org()
    _, c2, _ = _mk_org()
    perm = Permission.objects.create(code=f"p_{uuid.uuid4().hex[:6]}", is_active=True)
    link = CompanyLink.objects.create(from_company=c1, to_company=c2)
    LinkGrant.objects.create(link=link, permission=perm, access_mode="READ", scope_org_unit=b1, is_active=True)

    # Un grant branch-específico NO satisface la consulta company-wide.
    assert has_intercompany_grant(from_company=c1, to_company=c2, permission_code=perm.code) is False
    assert (
        has_intercompany_grant(from_company=c1, to_company=c2, permission_code=perm.code, scope_branch=b1) is True
    )


# ---------------------------------------------------------------------------
# Selectores: accesibilidad
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_get_accessible_companies_direct_and_via_branch():
    _, c1, _ = _mk_org()
    _, c2, b2 = _mk_org()
    user = _mk_user()
    UserMembership.objects.create(user=user, org_unit=c1, is_active=True)  # company directa
    UserMembership.objects.create(user=user, org_unit=b2, is_active=True)  # branch -> eleva a c2

    ids = {c.id for c in get_accessible_companies(user)}
    assert ids == {c1.id, c2.id}


@pytest.mark.django_db
def test_get_accessible_branches_company_membership_gives_all():
    _, c1, b1 = _mk_org()
    b1b = OrgUnit.objects.create(unit_type=UT.BRANCH, name=f"B2_{uuid.uuid4().hex[:4]}", parent=c1)
    user = _mk_user()
    UserMembership.objects.create(user=user, org_unit=c1, is_active=True)
    assert {b.id for b in get_accessible_branches(user, c1)} == {b1.id, b1b.id}


@pytest.mark.django_db
def test_get_accessible_branches_branch_membership_only_that_branch():
    _, c1, b1 = _mk_org()
    OrgUnit.objects.create(unit_type=UT.BRANCH, name=f"B2_{uuid.uuid4().hex[:4]}", parent=c1)
    user = _mk_user()
    UserMembership.objects.create(user=user, org_unit=b1, is_active=True)
    assert {b.id for b in get_accessible_branches(user, c1)} == {b1.id}


# ---------------------------------------------------------------------------
# Selectores: admin caps y ACL snapshot
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_admin_caps_snapshot_company_grant_and_defaults():
    _, c1, _ = _mk_org()
    user = _mk_user()
    AdminGrant.objects.create(
        user=user, org_unit=c1, capability=AdminGrant.Capability.MANAGE_USERS, is_active=True
    )
    entry = get_admin_caps_snapshot(user, [c1])[str(c1.id)]
    assert entry["MANAGE_USERS"] is True
    assert entry["VIEW_AUDIT"] is False  # default rellenado


@pytest.mark.django_db
def test_admin_caps_snapshot_holding_grant_applies_to_all_companies():
    holding, c1, _ = _mk_org()
    user = _mk_user()
    AdminGrant.objects.create(
        user=user, org_unit=holding, capability=AdminGrant.Capability.VIEW_REPORTS, is_active=True
    )
    assert get_admin_caps_snapshot(user, [c1])[str(c1.id)]["VIEW_REPORTS"] is True


@pytest.mark.django_db
def test_build_acl_snapshot_single_company_recommends_context():
    _, c1, b1 = _mk_org()
    user = _mk_user()
    UserMembership.objects.create(user=user, org_unit=c1, is_active=True)

    snap = build_acl_snapshot(user)
    assert snap["user_id"] == user.id
    assert len(snap["companies"]) == 1
    assert snap["companies"][0]["company_id"] == c1.id
    assert snap["recommended_company_id"] == c1.id
    assert snap["recommended_branch_id"] == b1.id
    assert snap["acl_version"]


# ---------------------------------------------------------------------------
# API: ContextEchoView
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_context_echo_returns_resolved_scope():
    _, company, branch = _mk_org()
    user = _mk_user()
    UserMembership.objects.create(user=user, org_unit=company, is_active=True)
    UserMembership.objects.create(user=user, org_unit=branch, is_active=True)

    client = APIClient()
    login = client.post("/api/auth/login/", {"username": user.username, "password": "pass12345"}, format="json")
    assert login.status_code == 200, login.data
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data.get('access')}")
    client.defaults["HTTP_X_COMPANY_ID"] = str(company.id)
    client.defaults["HTTP_X_BRANCH_ID"] = str(branch.id)

    resp = client.get("/api/iam/context/")
    assert resp.status_code == 200
    assert resp.data == {"company_id": company.id, "branch_id": branch.id}
