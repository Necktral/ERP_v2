from __future__ import annotations

import base64
import logging
import threading
import uuid
from datetime import timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connection
from django.db import close_old_connections
from django.db import connections
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.modulos.audit.models import AuditEvent
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


def _client_with_permission(*, company: OrgUnit, perm_code: str, branch: OrgUnit | None = None) -> APIClient:
    username = f"sync_enroll_{uuid.uuid4().hex[:10]}"
    user = User.objects.create_user(
        username=username,
        email=f"{username}@test.local",
        password="pass12345",
    )
    if branch is None:
        UserMembership.objects.create(user=user, org_unit=company, is_active=True)
    else:
        UserMembership.objects.create(user=user, org_unit=branch, is_active=True)

    role = Role.objects.create(name=f"role_{uuid.uuid4().hex[:8]}", is_active=True)
    perm, _ = Permission.objects.get_or_create(code=perm_code, defaults={"description": perm_code, "is_active": True})
    if not perm.is_active:
        perm.is_active = True
        perm.save(update_fields=["is_active"])
    RolePermission.objects.get_or_create(role=role, permission=perm)
    RoleAssignment.objects.create(user=user, role=role, org_unit=branch or company, is_active=True)

    client = APIClient(raise_request_exception=True)
    with override_settings(AUTH_TOKEN_TRANSPORT="header", AUTH_ALLOW_TRANSPORT_OVERRIDE=True):
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
    if branch is not None:
        client.defaults["HTTP_X_BRANCH_ID"] = str(branch.id)
    return client


def _public_key_b64() -> str:
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return base64.b64encode(public).decode("utf-8")


def _assert_enrollment_auth_rejected(*, reason_code: str) -> AuditEvent:
    ev = AuditEvent.objects.filter(event_type="SYNC_AUTH_REJECTED", reason_code=reason_code).latest(
        "timestamp_server"
    )
    metadata = ev.metadata or {}
    assert metadata["channel"] == "sync_enrollment"
    assert metadata["failure_stage"] == "enrollment"
    assert "signature" not in metadata
    assert "nonce" not in metadata
    assert "enrollment_code" not in metadata
    assert "public_key_b64" not in metadata
    return ev


@pytest.mark.django_db
@override_settings(SYNC_ENROLL_WEB_BASE_URL="https://pwa.example.test")
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
    assert "enrollment_uri" in ok.data
    assert "enrollment_deep_link" in ok.data
    enrollment_uri = str(ok.data["enrollment_uri"])
    parsed = urlparse(enrollment_uri)
    assert parsed.scheme == "https"
    assert parsed.netloc == "pwa.example.test"
    # Ruta pública del frontend reconstruido (router: /enrolar, AuthLayout).
    assert parsed.fragment.startswith("/enrolar?code=")
    fragment_query = parsed.fragment.split("?", 1)[1]
    assert parse_qs(fragment_query).get("code") == [ok.data["enrollment_code"]]
    parsed_deep = urlparse(str(ok.data["enrollment_deep_link"]))
    assert parsed_deep.scheme == "necktral-sync"
    assert parsed_deep.netloc == "enroll"
    assert parse_qs(parsed_deep.query).get("code") == [ok.data["enrollment_code"]]
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
def test_enrollment_challenge_respects_branch_scope():
    company, branch_a = _mk_org()
    branch_b = OrgUnit.objects.create(
        unit_type=OrgUnit.UnitType.BRANCH,
        parent=company,
        name=f"Branch B {uuid.uuid4().hex[:8]}",
        code=f"B2-{uuid.uuid4().hex[:8]}",
    )
    client = _client_with_permission(company=company, branch=branch_a, perm_code="sync.device.enroll")

    implicit = client.post(
        "/api/sync/enrollment/challenges/",
        {"company_id": company.id, "label_hint": "Branch A"},
        format="json",
    )
    assert implicit.status_code == 201
    assert implicit.data["branch_id"] == branch_a.id
    ch = DeviceEnrollmentChallenge.objects.get(id=implicit.data["challenge_id"])
    assert ch.branch_id == branch_a.id

    cross_branch = client.post(
        "/api/sync/enrollment/challenges/",
        {"company_id": company.id, "branch_id": branch_b.id},
        format="json",
    )
    assert cross_branch.status_code == 403


@pytest.mark.django_db
def test_enrollment_challenge_company_scope_can_target_company_or_branch():
    company, branch = _mk_org()
    client = _client_with_permission(company=company, perm_code="sync.device.enroll")

    company_level = client.post(
        "/api/sync/enrollment/challenges/",
        {"company_id": company.id, "label_hint": "Company Device"},
        format="json",
    )
    assert company_level.status_code == 201
    assert company_level.data["branch_id"] is None
    assert DeviceEnrollmentChallenge.objects.get(id=company_level.data["challenge_id"]).branch_id is None

    branch_level = client.post(
        "/api/sync/enrollment/challenges/",
        {"company_id": company.id, "branch_id": branch.id},
        format="json",
    )
    assert branch_level.status_code == 201
    assert branch_level.data["branch_id"] == branch.id


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
    used_event = _assert_enrollment_auth_rejected(reason_code="SYNC_ENROLL_USED_CODE")
    assert used_event.metadata["challenge_id"] == str(challenge.id)

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
    invalid_event = _assert_enrollment_auth_rejected(reason_code="SYNC_ENROLL_INVALID_CODE")
    assert "challenge_id" not in invalid_event.metadata

    expired_code = "qa-enroll-expired-code"
    expired_challenge = DeviceEnrollmentChallenge.objects.create(
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
    expired_event = _assert_enrollment_auth_rejected(reason_code="SYNC_ENROLL_EXPIRED_CODE")
    assert expired_event.metadata["challenge_id"] == str(expired_challenge.id)


@pytest.mark.django_db
def test_device_enroll_invalid_public_key_is_audited():
    client = APIClient(raise_request_exception=True)
    res = client.post(
        "/api/sync/enroll/",
        {
            "enrollment_code": "qa-enroll-public-key-invalid",
            "public_key_b64": "@@not-a-key@@",
        },
        format="json",
    )
    assert res.status_code == 400
    ev = _assert_enrollment_auth_rejected(reason_code="SYNC_INVALID_PUBLIC_KEY")
    assert ev.subject_id == ""
    assert ev.device_id == ""


@pytest.mark.django_db
def test_device_enroll_ignores_accidental_invalid_jwt():
    company, branch = _mk_org()
    creator = User.objects.create_user(username=f"creator_jwt_{uuid.uuid4().hex[:8]}", password="x")
    enrollment_code = "qa-enroll-ignores-invalid-jwt"
    DeviceEnrollmentChallenge.objects.create(
        company=company,
        branch=branch,
        enrollment_code_hash=DeviceEnrollmentChallenge.sha256_hex(enrollment_code),
        expires_at=timezone.now() + timedelta(minutes=10),
        created_by_user=creator,
        label_hint="JWT Noise",
    )

    client = APIClient(raise_request_exception=True)
    client.credentials(HTTP_AUTHORIZATION="Bearer invalid.jwt.token")
    res = client.post(
        "/api/sync/enroll/",
        {
            "enrollment_code": enrollment_code,
            "public_key_b64": _public_key_b64(),
            "label": "JWT-noise-device",
        },
        format="json",
    )

    assert res.status_code == 201
    assert res.data["company_id"] == company.id
    assert res.data["branch_id"] == branch.id


@pytest.mark.django_db
def test_device_enroll_invalid_code_with_accidental_jwt_keeps_enrollment_audit():
    client = APIClient(raise_request_exception=True)
    client.credentials(HTTP_AUTHORIZATION="Bearer invalid.jwt.token")

    res = client.post(
        "/api/sync/enroll/",
        {
            "enrollment_code": "qa-enroll-invalid-code-with-jwt",
            "public_key_b64": _public_key_b64(),
        },
        format="json",
    )

    assert res.status_code == 403
    _assert_enrollment_auth_rejected(reason_code="SYNC_ENROLL_INVALID_CODE")


@pytest.mark.django_db
@override_settings(AUTH_TOKEN_TRANSPORT="cookie")
def test_device_enroll_ignores_cookie_csrf_noise():
    company, branch = _mk_org()
    creator = User.objects.create_user(username=f"creator_cookie_{uuid.uuid4().hex[:8]}", password="x")
    enrollment_code = "qa-enroll-cookie-noise"
    DeviceEnrollmentChallenge.objects.create(
        company=company,
        branch=branch,
        enrollment_code_hash=DeviceEnrollmentChallenge.sha256_hex(enrollment_code),
        expires_at=timezone.now() + timedelta(minutes=10),
        created_by_user=creator,
    )

    client = APIClient(raise_request_exception=True)
    client.cookies[settings.AUTH_COOKIE_ACCESS_NAME] = "stale-access-token"
    res = client.post(
        "/api/sync/enroll/",
        {
            "enrollment_code": enrollment_code,
            "public_key_b64": _public_key_b64(),
        },
        format="json",
    )

    assert res.status_code == 201
    assert res.data["device_status"] == Device.Status.ACTIVE


@pytest.mark.django_db
def test_enrollment_challenge_admin_endpoint_still_rejects_invalid_jwt():
    company, branch = _mk_org()
    client = APIClient(raise_request_exception=True)
    client.credentials(HTTP_AUTHORIZATION="Bearer invalid.jwt.token")

    res = client.post(
        "/api/sync/enrollment/challenges/",
        {
            "company_id": company.id,
            "branch_id": branch.id,
            "expires_in_minutes": 10,
        },
        format="json",
    )

    assert res.status_code == 401


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
