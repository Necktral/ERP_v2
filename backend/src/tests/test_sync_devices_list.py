import uuid

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.modulos.audit.models import AuditEvent
from apps.modulos.iam.models import OrgUnit, UserMembership
from apps.modulos.rbac.models import Permission, Role, RoleAssignment, RolePermission
from apps.modulos.sync_engine.models import Device

User = get_user_model()


def _mk_company_with_branches() -> tuple[OrgUnit, OrgUnit, OrgUnit]:
    token = uuid.uuid4().hex[:8]
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name=f"H-{token}")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name=f"C-{token}", parent=holding)
    branch_a = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name=f"B1-{token}", parent=company)
    branch_b = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name=f"B2-{token}", parent=company)
    return company, branch_a, branch_b


def _client_with_revoke_permission(*, company: OrgUnit, branch: OrgUnit | None = None) -> APIClient:
    username = f"sync_admin_{uuid.uuid4().hex[:10]}"
    user = User.objects.create_user(username=username, email=f"{username}@test.local", password="pass12345")
    UserMembership.objects.create(user=user, org_unit=branch or company, is_active=True)

    role = Role.objects.create(name=f"sync_admin_{uuid.uuid4().hex}", is_active=True)
    perm, _ = Permission.objects.get_or_create(
        code="sync.device.revoke",
        defaults={"is_active": True, "description": "sync.device.revoke"},
    )
    if not perm.is_active:
        perm.is_active = True
        perm.save(update_fields=["is_active"])
    RolePermission.objects.get_or_create(role=role, permission=perm)
    RoleAssignment.objects.create(user=user, role=role, org_unit=branch or company, is_active=True)

    client = APIClient()
    login = client.post(
        "/api/auth/login/",
        {"username": username, "password": "pass12345"},
        format="json",
        HTTP_X_AUTH_TRANSPORT="header",
    )
    assert login.status_code == 200
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
    client.defaults["HTTP_X_COMPANY_ID"] = str(company.id)
    if branch is not None:
        client.defaults["HTTP_X_BRANCH_ID"] = str(branch.id)
    return client


def _device(*, company: OrgUnit, branch: OrgUnit | None, label: str) -> Device:
    return Device.objects.create(
        company=company,
        branch=branch,
        label=label,
        status=Device.Status.ACTIVE,
        public_key=b"\x01" * 32,
        meta={},
    )


@pytest.mark.django_db
def test_sync_devices_list_returns_devices_for_company():
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="H")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="C", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name="B1", parent=company)

    user = User.objects.create_user(username="owner_list", password="pass12345")
    UserMembership.objects.create(user=user, org_unit=company, is_active=True)

    role = Role.objects.create(name=f"admin_{uuid.uuid4().hex}", is_active=True)
    p, _ = Permission.objects.get_or_create(code="sync.device.revoke", defaults={"is_active": True, "description": ""})
    if not p.is_active:
        p.is_active = True
        p.save(update_fields=["is_active"])
    RolePermission.objects.get_or_create(role=role, permission=p)
    RoleAssignment.objects.get_or_create(user=user, role=role, org_unit=company, defaults={"is_active": True})

    device = Device.objects.create(
        company=company,
        branch=branch,
        label="Tablet-01",
        status=Device.Status.ACTIVE,
        public_key=b"\x01" * 32,
        meta={},
        enrolled_by_user=user,
    )

    client = APIClient()
    login = client.post(
        "/api/auth/login/",
        {"username": "owner_list", "password": "pass12345"},
        format="json",
        HTTP_X_AUTH_TRANSPORT="header",
    )
    assert login.status_code == 200
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")

    r = client.get("/api/sync/devices/?q=Tablet&status=ACTIVE", HTTP_X_COMPANY_ID=str(company.id))
    assert r.status_code == 200

    ids = [x["id"] for x in r.data["results"]]
    assert str(device.id) in ids


@pytest.mark.django_db
def test_sync_devices_list_respects_branch_scope():
    company, branch_a, branch_b = _mk_company_with_branches()
    device_a = _device(company=company, branch=branch_a, label="Tablet A")
    device_b = _device(company=company, branch=branch_b, label="Tablet B")
    company_device = _device(company=company, branch=None, label="Company Tablet")

    branch_client = _client_with_revoke_permission(company=company, branch=branch_a)
    branch_response = branch_client.get("/api/sync/devices/")
    assert branch_response.status_code == 200
    branch_ids = {row["id"] for row in branch_response.data["results"]}
    assert str(device_a.id) in branch_ids
    assert str(device_b.id) not in branch_ids
    assert str(company_device.id) not in branch_ids

    company_client = _client_with_revoke_permission(company=company)
    company_response = company_client.get("/api/sync/devices/")
    assert company_response.status_code == 200
    company_ids = {row["id"] for row in company_response.data["results"]}
    assert {str(device_a.id), str(device_b.id), str(company_device.id)} <= company_ids


@pytest.mark.django_db
def test_sync_device_revoke_respects_branch_scope():
    company, branch_a, branch_b = _mk_company_with_branches()
    device_a = _device(company=company, branch=branch_a, label="Tablet A")
    device_b = _device(company=company, branch=branch_b, label="Tablet B")
    company_device = _device(company=company, branch=None, label="Company Tablet")

    branch_client = _client_with_revoke_permission(company=company, branch=branch_a)
    own = branch_client.post(f"/api/sync/devices/{device_a.id}/revoke/")
    assert own.status_code == 200
    device_a.refresh_from_db()
    assert device_a.status == Device.Status.REVOKED

    cross_branch = branch_client.post(f"/api/sync/devices/{device_b.id}/revoke/")
    assert cross_branch.status_code == 404
    device_b.refresh_from_db()
    assert device_b.status == Device.Status.ACTIVE

    company_level = branch_client.post(f"/api/sync/devices/{company_device.id}/revoke/")
    assert company_level.status_code == 404
    company_device.refresh_from_db()
    assert company_device.status == Device.Status.ACTIVE

    company_client = _client_with_revoke_permission(company=company)
    company_revoke = company_client.post(f"/api/sync/devices/{device_b.id}/revoke/")
    assert company_revoke.status_code == 200
    device_b.refresh_from_db()
    assert device_b.status == Device.Status.REVOKED


@pytest.mark.django_db
def test_sync_devices_list_denied_without_permission_is_audited():
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="H")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="C", parent=holding)

    user = User.objects.create_user(username="owner_no_list", password="pass12345")
    UserMembership.objects.create(user=user, org_unit=company, is_active=True)

    role = Role.objects.create(name=f"r_{uuid.uuid4().hex}", is_active=True)
    # permiso distinto (no list/revoke)
    p, _ = Permission.objects.get_or_create(code="sync.device.enroll", defaults={"is_active": True, "description": ""})
    RolePermission.objects.get_or_create(role=role, permission=p)
    RoleAssignment.objects.get_or_create(user=user, role=role, org_unit=company, defaults={"is_active": True})

    client = APIClient()
    login = client.post(
        "/api/auth/login/",
        {"username": "owner_no_list", "password": "pass12345"},
        format="json",
        HTTP_X_AUTH_TRANSPORT="header",
    )
    assert login.status_code == 200
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")

    r = client.get("/api/sync/devices/", HTTP_X_COMPANY_ID=str(company.id))
    assert r.status_code == 403

    ev = AuditEvent.objects.filter(
        event_type="AUTH_ACCESS_DENIED",
        path="/api/sync/devices/",
        method="GET",
    ).latest("timestamp_server")
    assert ev.reason_code == "RBAC_FORBIDDEN"
    assert ev.metadata.get("required_permission") == "sync.device.revoke"
