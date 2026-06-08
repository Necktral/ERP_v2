import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.modulos.iam.models import OrgUnit
from apps.modulos.rbac.models import Permission, Role, RoleAssignment, RolePermission

User = get_user_model()


@pytest.mark.django_db
def test_me_returns_roles_and_permissions():
    user = User.objects.create_user(username="u3", password="pass12345")
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="H_me")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="C_me", parent=holding)

    role = Role.objects.create(name="warehouse")
    perm = Permission.objects.create(code="inventory.read")
    RolePermission.objects.create(role=role, permission=perm)
    RoleAssignment.objects.create(user=user, role=role, org_unit=company, is_active=True)

    client = APIClient()
    login = client.post("/api/auth/login/", {"username": "u3", "password": "pass12345"}, format="json")
    access = login.data["access"]

    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    client.defaults["HTTP_AUTHORIZATION"] = f"Bearer {access}"
    me = client.get("/api/auth/me/")
    assert me.status_code == 200
    assert "warehouse" in me.data["roles"]
    assert "inventory.read" in me.data["permissions"]
