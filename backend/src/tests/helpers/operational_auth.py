from __future__ import annotations

import uuid
from typing import Any

from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.modulos.iam.models import OrgUnit, UserMembership
from apps.modulos.rbac.models import Permission, Role, RoleAssignment, RolePermission

User = get_user_model()


def create_operational_api_actor(
    *,
    company: OrgUnit,
    branch: OrgUnit | None = None,
    perm_codes: list[str],
    email_prefix: str = "operational",
    password: str = "pass12345",
) -> tuple[APIClient, Any]:
    username = f"{email_prefix}_{uuid.uuid4().hex[:10]}"
    user = User.objects.create_user(
        username=username,
        email=f"{username}@test.local",
        password=password,
    )

    UserMembership.objects.create(user=user, org_unit=company, is_active=True)
    if branch is not None:
        UserMembership.objects.create(user=user, org_unit=branch, is_active=True)

    role = Role.objects.create(name=f"role_{uuid.uuid4().hex[:8]}", is_active=True)
    for code in perm_codes:
        perm, _ = Permission.objects.get_or_create(
            code=code,
            defaults={"description": code, "is_active": True},
        )
        RolePermission.objects.get_or_create(role=role, permission=perm)

    RoleAssignment.objects.create(user=user, role=role, org_unit=company, is_active=True)
    if branch is not None:
        RoleAssignment.objects.create(user=user, role=role, org_unit=branch, is_active=True)

    auth_transport = getattr(settings, "AUTH_TOKEN_TRANSPORT", "header")
    allow_transport_override = bool(getattr(settings, "AUTH_ALLOW_TRANSPORT_OVERRIDE", False))
    assert auth_transport == "header" or allow_transport_override, (
        "Operational API tests require header auth transport or AUTH_ALLOW_TRANSPORT_OVERRIDE=True"
    )

    client = APIClient()
    resp = client.post(
        "/api/auth/login/",
        {"username": username, "password": password},
        format="json",
        HTTP_X_AUTH_TRANSPORT="header",
    )
    assert resp.status_code == 200
    access = resp.data.get("access") if isinstance(resp.data, dict) else None
    assert isinstance(access, str) and access

    bearer = f"Bearer {access}"
    client.cookies.clear()
    client.credentials(HTTP_AUTHORIZATION=bearer)
    client.defaults["HTTP_AUTHORIZATION"] = bearer
    client.defaults["HTTP_X_COMPANY_ID"] = str(company.id)
    client.defaults["HTTP_X_AUTH_TRANSPORT"] = "header"
    if branch is not None:
        client.defaults["HTTP_X_BRANCH_ID"] = str(branch.id)

    return client, user
