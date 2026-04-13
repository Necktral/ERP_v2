from __future__ import annotations

import base64
import logging
import threading
import uuid
from datetime import timedelta

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from django.contrib.auth import get_user_model
from django.db import connection
from django.db import close_old_connections
from django.db import connections
from django.utils import timezone
from rest_framework.test import APIClient

from apps.modulos.iam.models import OrgUnit, UserMembership
from apps.modulos.rbac.models import Permission, Role, RoleAssignment, RolePermission
from apps.modulos.sync_engine.models import Device, DeviceEnrollmentChallenge

User = get_user_model()


def _mk_org() -> tuple[OrgUnit, OrgUnit]:
    token = uuid.uuid4().hex[:8]
    holding = OrgUnit.objects.create(
        unit_type=OrgUnit.UnitType.HOLDING,
        name=f"Holding {token}",
        code=f"H-{token}",
    )
    company = OrgUnit.objects.create(
        unit_type=OrgUnit.UnitType.COMPANY,
        parent=holding,
        name=f"Company {token}",
        code=f"C-{token}",
    )
    branch = OrgUnit.objects.create(
        unit_type=OrgUnit.UnitType.BRANCH,
        parent=company,
        name=f"Branch {token}",
        code=f"B-{token}",
    )
    return company, branch


def _client_with_permission(*, company: OrgUnit, perm_code: str) -> APIClient:
    username = f"sync_enroll_{uuid.uuid4().hex[:10]}"
    user = User.objects.create_user(
        username=username,
        email=f"{username}@test.local",
        password="pass12345",
    )
    UserMembership.objects.create(user=user, org_unit=company, is_active=True)

    role = Role.objects.create(name=f"role_{uuid.uuid4().hex[:8]}", is_active=True)
    perm, _ = Permission.objects.get_or_create(code=perm_code, defaults={"description": perm_code, "is_active": True})
    if not perm.is_active:
        perm.is_active = True
        perm.save(update_fields=["is_active"])
    RolePermission.objects.get_or_create(role=role, permission=perm)
    RoleAssignment.objects.create(user=user, role=role, org_unit=company, is_active=True)

    client = APIClient(raise_request_exception=True)
    login = client.post(
        "/api/auth/login/",
        {"username": username, "password": "pass12345"},
        format="json",
        HTTP_X_AUTH_TRANSPORT="header",
    )
    assert login.status_code == 200
    access = login.data["access"]
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    client.defaults["HTTP_X_COMPANY_ID"] = str(company.id)
    return client


def _public_key_b64() -> str:
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return base64.b64encode(public).decode("utf-8")


@pytest.mark.django_db
def test_enrollment_challenge_create_requires_permission_and_context():
    company, branch = _mk_org()
    client_with_perm = _client_with_permission(company=company, perm_code="sync.device.enroll")
    client_without_perm = _client_with_permission(company=company, perm_code="sync.device.revoke")

    ok = client_with_perm.post(
        "/api/sync/enrollment/challenges/",
        {
            "company_id": company.id,
            "branch_id": branch.id,
            "label_hint": "Tablet QA",
            "expires_in_minutes": 15,
        },
        format="json",
    )
    assert ok.status_code == 201
    assert "challenge_id" in ok.data
    assert "enrollment_code" in ok.data
    assert isinstance(ok.data.get("trace"), dict)
    assert ok.data["trace"]["request_id"] == ok["X-Request-Id"]
    uuid.UUID(str(ok.data["trace"]["audit_event_id"]))
    assert DeviceEnrollmentChallenge.objects.filter(id=ok.data["challenge_id"]).exists()

    forbidden = client_without_perm.post(
        "/api/sync/enrollment/challenges/",
        {
            "company_id": company.id,
            "branch_id": branch.id,
        },
        format="json",
    )
    assert forbidden.status_code == 403


@pytest.mark.django_db
def test_device_enroll_valid_invalid_expired_and_used_code(caplog):
    company, branch = _mk_org()
    creator = User.objects.create_user(username=f"creator_{uuid.uuid4().hex[:8]}", password="x")

    enrollment_code = "qa-enroll-valid-code"
    challenge = DeviceEnrollmentChallenge.objects.create(
        company=company,
        branch=branch,
        enrollment_code_hash=DeviceEnrollmentChallenge.sha256_hex(enrollment_code),
        expires_at=timezone.now() + timedelta(minutes=10),
        created_by_user=creator,
        label_hint="Kiosk",
    )

    client = APIClient(raise_request_exception=True)
    payload = {
        "enrollment_code": enrollment_code,
        "public_key_b64": _public_key_b64(),
        "label": "Kiosk-01",
        "meta": {"source": "qa"},
    }
    first = client.post("/api/sync/enroll/", payload, format="json")
    assert first.status_code == 201
    assert first.data["company_id"] == company.id
    assert first.data["branch_id"] == branch.id
    assert isinstance(first.data.get("trace"), dict)
    assert first.data["trace"]["request_id"] == first["X-Request-Id"]
    uuid.UUID(str(first.data["trace"]["audit_event_id"]))

    challenge.refresh_from_db()
    assert challenge.used_at is not None
    assert challenge.used_by_device_id is not None

    second = client.post("/api/sync/enroll/", payload, format="json")
    assert second.status_code == 403

    caplog.set_level(logging.WARNING, logger="apps.modulos.sync.trace")
    invalid = client.post(
        "/api/sync/enroll/",
        {
            "enrollment_code": "qa-enroll-invalid-code",
            "public_key_b64": _public_key_b64(),
        },
        format="json",
    )
    assert invalid.status_code == 403
    invalid_logs = [r for r in caplog.records if r.name == "apps.modulos.sync.trace" and r.msg == "sync_device_enroll_rejected"]
    assert invalid_logs
    assert any(getattr(r, "reason", "") == "SYNC_ENROLL_INVALID_CODE" for r in invalid_logs)
    assert not any(hasattr(r, "enrollment_code") for r in invalid_logs)
    assert not any(hasattr(r, "public_key_b64") for r in invalid_logs)

    expired_code = "qa-enroll-expired-code"
    DeviceEnrollmentChallenge.objects.create(
        company=company,
        branch=branch,
        enrollment_code_hash=DeviceEnrollmentChallenge.sha256_hex(expired_code),
        expires_at=timezone.now() - timedelta(minutes=1),
        created_by_user=creator,
    )
    expired = client.post(
        "/api/sync/enroll/",
        {
            "enrollment_code": expired_code,
            "public_key_b64": _public_key_b64(),
        },
        format="json",
    )
    assert expired.status_code == 403


@pytest.mark.django_db(transaction=True)
def test_device_enroll_challenge_is_one_time_under_concurrency(monkeypatch):
    company, branch = _mk_org()
    creator = User.objects.create_user(username=f"creator_race_{uuid.uuid4().hex[:8]}", password="x")
    enrollment_code = "qa-enroll-race-code"

    challenge = DeviceEnrollmentChallenge.objects.create(
        company=company,
        branch=branch,
        enrollment_code_hash=DeviceEnrollmentChallenge.sha256_hex(enrollment_code),
        expires_at=timezone.now() + timedelta(minutes=10),
        created_by_user=creator,
        label_hint="Race Device",
    )

    barrier = threading.Barrier(2)
    original_create = Device.objects.create

    def create_with_barrier(*args, **kwargs):
        try:
            barrier.wait(timeout=0.4)
        except threading.BrokenBarrierError:
            pass
        return original_create(*args, **kwargs)

    monkeypatch.setattr(Device.objects, "create", create_with_barrier)

    statuses: list[int] = []
    lock = threading.Lock()

    def enroll_once(label: str) -> None:
        close_old_connections()
        client = APIClient(raise_request_exception=True)
        response = client.post(
            "/api/sync/enroll/",
            {
                "enrollment_code": enrollment_code,
                "public_key_b64": _public_key_b64(),
                "label": label,
            },
            format="json",
        )
        with lock:
            statuses.append(response.status_code)
        connection.close()

    t1 = threading.Thread(target=enroll_once, args=("Race-1",))
    t2 = threading.Thread(target=enroll_once, args=("Race-2",))
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    connections.close_all()

    assert sorted(statuses) == [201, 403]
    assert Device.objects.filter(company=company, branch=branch).count() == 1
    challenge.refresh_from_db()
    assert challenge.used_at is not None
    assert challenge.used_by_device_id is not None
