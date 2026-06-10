"""Helpers compartidos para tests de `diagnostics` (no se colecta como test)."""
from __future__ import annotations

import uuid

from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.modulos.iam.models import OrgUnit, UserMembership
from apps.modulos.rbac.models import Permission, Role, RoleAssignment, RolePermission

User = get_user_model()


def mk_scope() -> tuple[OrgUnit, OrgUnit]:
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="H")
    company = OrgUnit.objects.create(
        unit_type=OrgUnit.UnitType.COMPANY, name="C", parent=holding
    )
    branch = OrgUnit.objects.create(
        unit_type=OrgUnit.UnitType.BRANCH, name="B", parent=company
    )
    return company, branch


def mk_client(*, company: OrgUnit, branch: OrgUnit, perm_codes: list[str]) -> APIClient:
    username = f"diag_{uuid.uuid4().hex[:8]}"
    user = User.objects.create_user(
        username=username, email=f"{username}@test.local", password="pass12345"
    )
    UserMembership.objects.create(user=user, org_unit=company, is_active=True)
    UserMembership.objects.create(user=user, org_unit=branch, is_active=True)
    role = Role.objects.create(name=f"diag_role_{uuid.uuid4().hex[:8]}", is_active=True)
    for code in perm_codes:
        perm, _ = Permission.objects.get_or_create(
            code=code, defaults={"description": code, "is_active": True}
        )
        RolePermission.objects.get_or_create(role=role, permission=perm)
    RoleAssignment.objects.create(user=user, role=role, org_unit=company, is_active=True)
    RoleAssignment.objects.create(user=user, role=role, org_unit=branch, is_active=True)
    client = APIClient()
    login = client.post(
        "/api/auth/login/", {"username": username, "password": "pass12345"}, format="json"
    )
    assert login.status_code == 200, login.data
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
    client.defaults["HTTP_X_COMPANY_ID"] = str(company.id)
    client.defaults["HTTP_X_BRANCH_ID"] = str(branch.id)
    return client
