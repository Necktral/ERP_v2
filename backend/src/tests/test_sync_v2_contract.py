from __future__ import annotations

import base64
import copy
import hashlib
import hmac
import logging
import os
import uuid

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from django.conf import settings
from django.test import override_settings
from django.utils import timezone
from rest_framework.renderers import JSONRenderer
from rest_framework.test import APIClient

from apps.modulos.audit.models import AuditEvent
from apps.modulos.iam.models import OrgUnit
from apps.modulos.sync.models import DeviceEnrollment
from apps.modulos.sync.signing import canonical_string, hmac_signature_b64
from apps.modulos.sync_engine.models import Device
from apps.modulos.sync_engine.signing import build_request_signing_message, canon_json


def _mk_scope() -> tuple[OrgUnit, OrgUnit]:
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


def _build_v2_body(*, device_id: uuid.UUID, company_id: int, branch_id: int | None, nonce: str, ts: int) -> dict:
    return {
        "protocol_version": "2",
        "device_id": str(device_id),
        "ts": ts,
        "nonce": nonce,
        "auth": {"scheme": "ed25519", "signature": ""},
        "batch_id": str(uuid.uuid4()),
        "batch": [
            {
                "command_id": str(uuid.uuid4()),
                "type": "DEMO_PING",
                "scope": {"company_id": company_id, "branch_id": branch_id},
                "occurred_at": timezone.now().isoformat(),
                "payload": {"msg": "ok"},
            }
        ],
    }


def _sign_v2_ed25519(body: dict, private_key: Ed25519PrivateKey) -> str:
    payload = copy.deepcopy(body)
    payload["auth"]["signature"] = ""
    signing_body = canon_json(payload).encode("utf-8")
    msg = build_request_signing_message(
        ts=int(body["ts"]),
        nonce=str(body["nonce"]),
        canonical_body_bytes=signing_body,
    )
    return base64.b64encode(private_key.sign(msg)).decode("utf-8")


def _assert_sync_auth_rejected(*, reason_code: str, wire_reason: str) -> AuditEvent:
    ev = AuditEvent.objects.filter(event_type="SYNC_AUTH_REJECTED", reason_code=reason_code).latest(
        "timestamp_server"
    )
    metadata = ev.metadata or {}
    assert metadata["wire_reason"] == wire_reason
    assert metadata["channel"] == "sync_v2"
    assert "signature" not in metadata
    assert "nonce" not in metadata
    assert "enrollment_code" not in metadata
    assert "public_key_b64" not in metadata
    return ev


@pytest.mark.django_db
def test_sync_batch_v2_ed25519_happy_and_replay():
    client = APIClient()
    company, branch = _mk_scope()

    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    device = Device.objects.create(
        company=company,
        branch=branch,
        label="v2-ed",
        status=Device.Status.ACTIVE,
        public_key=public,
    )

    ts = int(timezone.now().timestamp())
    body = _build_v2_body(
        device_id=device.id,
        company_id=company.id,
        branch_id=branch.id,
        nonce="n-v2-ed-1",
        ts=ts,
    )
    body["auth"]["signature"] = _sign_v2_ed25519(body, private)

    r1 = client.post("/api/sync/batch/", data=body, format="json", HTTP_X_DEVICE_ID=str(device.id))
    assert r1.status_code == 200
    assert r1.data["device_id"] == str(device.id)
    assert r1.data["results"][0]["status"] == "APPLIED"
    assert r1.data["results"][0]["refs"]["pong"] is True
    assert isinstance(r1.data.get("trace"), dict)
    assert r1.data["trace"]["request_id"] == r1["X-Request-Id"]
    assert r1.data["trace"]["channel"] == "sync_v2"

    r2 = client.post("/api/sync/batch/", data=body, format="json", HTTP_X_DEVICE_ID=str(device.id))
    assert r2.status_code == 401
    payload = r2.json()
    assert payload["error"]["message"] == "REPLAY_DETECTED"
    ev = _assert_sync_auth_rejected(reason_code="SYNC_REPLAY_DETECTED", wire_reason="REPLAY_DETECTED")
    assert ev.subject_id == str(device.id)
    assert ev.device_id == str(device.id)


@pytest.mark.django_db
def test_sync_batch_v2_rejects_bad_signature(caplog):
    client = APIClient()
    company, branch = _mk_scope()

    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    device = Device.objects.create(
        company=company,
        branch=branch,
        label="v2-ed-bad-sig",
        status=Device.Status.ACTIVE,
        public_key=public,
    )

    body = _build_v2_body(
        device_id=device.id,
        company_id=company.id,
        branch_id=branch.id,
        nonce="n-v2-ed-bad-sig",
        ts=int(timezone.now().timestamp()),
    )
    body["auth"]["signature"] = base64.b64encode(os.urandom(64)).decode("utf-8")

    caplog.set_level(logging.WARNING, logger="apps.modulos.sync.trace")
    res = client.post("/api/sync/batch/", data=body, format="json", HTTP_X_DEVICE_ID=str(device.id))
    assert res.status_code == 401
    payload = res.json()
    assert payload["error"]["message"] == "BAD_SIGNATURE"
    warning_logs = [r for r in caplog.records if r.name == "apps.modulos.sync.trace" and r.msg == "sync_batch_auth_rejected"]
    assert warning_logs
    assert any(getattr(r, "reason", "") == "BAD_SIGNATURE" for r in warning_logs)
    assert not any(hasattr(r, "signature") for r in warning_logs)
    ev = _assert_sync_auth_rejected(reason_code="SYNC_BAD_SIGNATURE", wire_reason="BAD_SIGNATURE")
    assert ev.subject_id == str(device.id)


@pytest.mark.django_db
def test_sync_batch_v2_ignores_accidental_invalid_jwt_on_valid_device_auth():
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION="Bearer invalid.jwt.token")
    company, branch = _mk_scope()

    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    device = Device.objects.create(
        company=company,
        branch=branch,
        label="v2-jwt-noise",
        status=Device.Status.ACTIVE,
        public_key=public,
    )

    body = _build_v2_body(
        device_id=device.id,
        company_id=company.id,
        branch_id=branch.id,
        nonce="n-v2-jwt-noise",
        ts=int(timezone.now().timestamp()),
    )
    body["auth"]["signature"] = _sign_v2_ed25519(body, private)

    res = client.post("/api/sync/batch/", data=body, format="json", HTTP_X_DEVICE_ID=str(device.id))

    assert res.status_code == 200
    assert res.data["device_id"] == str(device.id)
    assert res.data["results"][0]["status"] == "APPLIED"
    assert not AuditEvent.objects.filter(event_type="SYNC_AUTH_REJECTED").exists()


@pytest.mark.django_db
@override_settings(AUTH_TOKEN_TRANSPORT="cookie")
def test_sync_batch_v2_ignores_cookie_csrf_noise_on_valid_device_auth():
    client = APIClient()
    client.cookies[settings.AUTH_COOKIE_ACCESS_NAME] = "stale-access-token"
    company, branch = _mk_scope()

    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    device = Device.objects.create(
        company=company,
        branch=branch,
        label="v2-cookie-noise",
        status=Device.Status.ACTIVE,
        public_key=public,
    )

    body = _build_v2_body(
        device_id=device.id,
        company_id=company.id,
        branch_id=branch.id,
        nonce="n-v2-cookie-noise",
        ts=int(timezone.now().timestamp()),
    )
    body["auth"]["signature"] = _sign_v2_ed25519(body, private)

    res = client.post("/api/sync/batch/", data=body, format="json", HTTP_X_DEVICE_ID=str(device.id))

    assert res.status_code == 200
    assert res.data["device_id"] == str(device.id)
    assert res.data["results"][0]["status"] == "APPLIED"


@pytest.mark.django_db
def test_sync_batch_v2_bad_signature_with_accidental_jwt_uses_device_auth_audit():
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION="Bearer invalid.jwt.token")
    company, branch = _mk_scope()

    public = Ed25519PrivateKey.generate().public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    device = Device.objects.create(
        company=company,
        branch=branch,
        label="v2-bad-sig-jwt-noise",
        status=Device.Status.ACTIVE,
        public_key=public,
    )

    body = _build_v2_body(
        device_id=device.id,
        company_id=company.id,
        branch_id=branch.id,
        nonce="n-v2-bad-sig-jwt-noise",
        ts=int(timezone.now().timestamp()),
    )
    body["auth"]["signature"] = base64.b64encode(os.urandom(64)).decode("utf-8")

    res = client.post("/api/sync/batch/", data=body, format="json", HTTP_X_DEVICE_ID=str(device.id))

    assert res.status_code == 401
    assert res.json()["error"]["message"] == "BAD_SIGNATURE"
    _assert_sync_auth_rejected(reason_code="SYNC_BAD_SIGNATURE", wire_reason="BAD_SIGNATURE")


@pytest.mark.django_db
@override_settings(SYNC_V2_MAX_SKEW_SECONDS=10)
def test_sync_batch_v2_audits_timestamp_skew():
    client = APIClient()
    company, branch = _mk_scope()

    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    device = Device.objects.create(
        company=company,
        branch=branch,
        label="v2-skew",
        status=Device.Status.ACTIVE,
        public_key=public,
    )

    body = _build_v2_body(
        device_id=device.id,
        company_id=company.id,
        branch_id=branch.id,
        nonce="n-v2-skew",
        ts=int(timezone.now().timestamp()) - 120,
    )
    body["auth"]["signature"] = _sign_v2_ed25519(body, private)

    res = client.post("/api/sync/batch/", data=body, format="json", HTTP_X_DEVICE_ID=str(device.id))
    assert res.status_code == 401
    assert res.json()["error"]["message"] == "TS_OUT_OF_WINDOW"
    ev = _assert_sync_auth_rejected(reason_code="SYNC_TS_OUT_OF_WINDOW", wire_reason="TS_OUT_OF_WINDOW")
    assert ev.subject_id == str(device.id)
    assert int(ev.metadata["ts_delta_seconds"]) >= 10


@pytest.mark.django_db
def test_sync_batch_v2_audits_device_id_mismatch():
    client = APIClient()
    company, branch = _mk_scope()
    body_device_id = uuid.uuid4()
    header_device_id = uuid.uuid4()
    body = _build_v2_body(
        device_id=body_device_id,
        company_id=company.id,
        branch_id=branch.id,
        nonce="n-v2-mismatch",
        ts=int(timezone.now().timestamp()),
    )
    body["auth"]["signature"] = "placeholder"

    res = client.post("/api/sync/batch/", data=body, format="json", HTTP_X_DEVICE_ID=str(header_device_id))
    assert res.status_code == 401
    assert res.json()["error"]["message"] == "DEVICE_ID_MISMATCH"
    ev = _assert_sync_auth_rejected(reason_code="SYNC_DEVICE_ID_MISMATCH", wire_reason="DEVICE_ID_MISMATCH")
    assert ev.subject_id == ""
    assert ev.device_id == ""
    assert ev.metadata["header_device_id"] == str(header_device_id)
    assert ev.metadata["body_device_id"] == str(body_device_id)


@pytest.mark.django_db
def test_sync_batch_v2_audits_unknown_device():
    client = APIClient()
    company, branch = _mk_scope()
    unknown_device_id = uuid.uuid4()
    body = _build_v2_body(
        device_id=unknown_device_id,
        company_id=company.id,
        branch_id=branch.id,
        nonce="n-v2-unknown-device",
        ts=int(timezone.now().timestamp()),
    )
    body["auth"]["signature"] = "placeholder"

    res = client.post("/api/sync/batch/", data=body, format="json")
    assert res.status_code == 403
    ev = _assert_sync_auth_rejected(reason_code="SYNC_UNKNOWN_DEVICE", wire_reason="SYNC_UNKNOWN_DEVICE")
    assert ev.subject_id == ""
    assert ev.device_id == ""
    assert ev.metadata["presented_device_id"] == str(unknown_device_id)


@pytest.mark.django_db
def test_sync_batch_v2_audits_missing_request_auth_material():
    client = APIClient()
    company, branch = _mk_scope()

    missing_public_key_device = Device.objects.create(
        company=company,
        branch=branch,
        label="v2-no-pubkey",
        status=Device.Status.ACTIVE,
        public_key=b"",
    )
    ed_body = _build_v2_body(
        device_id=missing_public_key_device.id,
        company_id=company.id,
        branch_id=branch.id,
        nonce="n-v2-no-pubkey",
        ts=int(timezone.now().timestamp()),
    )
    ed_body["auth"]["signature"] = "placeholder"
    ed_res = client.post(
        "/api/sync/batch/",
        data=ed_body,
        format="json",
        HTTP_X_DEVICE_ID=str(missing_public_key_device.id),
    )
    assert ed_res.status_code == 401
    _assert_sync_auth_rejected(
        reason_code="SYNC_DEVICE_NO_PUBLIC_KEY",
        wire_reason="SYNC_DEVICE_NO_PUBLIC_KEY",
    )

    missing_hmac_device = Device.objects.create(
        company=company,
        branch=branch,
        label="v2-no-hmac",
        status=Device.Status.ACTIVE,
        public_key=b"\x01" * 32,
    )
    hmac_body = _build_v2_body(
        device_id=missing_hmac_device.id,
        company_id=company.id,
        branch_id=branch.id,
        nonce="n-v2-no-hmac",
        ts=int(timezone.now().timestamp()),
    )
    hmac_body["auth"]["scheme"] = "hmac"
    hmac_body["auth"]["signature"] = "placeholder"
    hmac_res = client.post(
        "/api/sync/batch/",
        data=hmac_body,
        format="json",
        HTTP_X_DEVICE_ID=str(missing_hmac_device.id),
    )
    assert hmac_res.status_code == 401
    _assert_sync_auth_rejected(
        reason_code="SYNC_DEVICE_NO_HMAC_SECRET",
        wire_reason="SYNC_DEVICE_NO_HMAC_SECRET",
    )


@pytest.mark.django_db
def test_sync_batch_v2_hmac_happy_path():
    client = APIClient()
    company, branch = _mk_scope()
    secret = base64.b64encode(os.urandom(32)).decode("utf-8")

    device = Device.objects.create(
        company=company,
        branch=branch,
        label="v2-hmac",
        status=Device.Status.ACTIVE,
        public_key=b"\x01" * 32,
        hmac_secret_b64=secret,
    )

    body = _build_v2_body(
        device_id=device.id,
        company_id=company.id,
        branch_id=branch.id,
        nonce="n-v2-hmac-1",
        ts=int(timezone.now().timestamp()),
    )
    body["auth"]["scheme"] = "hmac"
    payload_for_sign = copy.deepcopy(body)
    payload_for_sign["auth"]["signature"] = ""
    signing_body = canon_json(payload_for_sign).encode("utf-8")
    msg = build_request_signing_message(
        ts=int(body["ts"]),
        nonce=str(body["nonce"]),
        canonical_body_bytes=signing_body,
    )
    mac = hmac.new(base64.b64decode(secret.encode("utf-8")), msg, hashlib.sha256).digest()
    body["auth"]["signature"] = base64.b64encode(mac).decode("utf-8")

    res = client.post("/api/sync/batch/", data=body, format="json", HTTP_X_DEVICE_ID=str(device.id))
    assert res.status_code == 200
    assert res.data["results"][0]["status"] == "APPLIED"


@pytest.mark.django_db
@override_settings(SYNC_LEGACY_HMAC_ENABLED=True, SYNC_HMAC_WRAPPER_ENABLED=True)
def test_sync_hmac_wrapper_mode_executes_core_and_keeps_legacy_shape():
    client = APIClient()
    company, branch = _mk_scope()

    secret = base64.b64encode(os.urandom(32)).decode("utf-8")
    legacy_id = uuid.uuid4()
    DeviceEnrollment.objects.create(id=legacy_id, secret_b64=secret, device_name="legacy-wrapper")
    Device.objects.create(
        id=legacy_id,
        company=company,
        branch=branch,
        label="core-wrapper",
        status=Device.Status.ACTIVE,
        public_key=b"\x02" * 32,
        hmac_secret_b64=secret,
    )

    body = {
        "commands": [
            {
                "command_id": str(uuid.uuid4()),
                "type": "PING",
                "payload": {"msg": "qa-auth-sync-smoke"},
            }
        ]
    }
    raw = JSONRenderer().render(body)
    ts = int(timezone.now().timestamp())
    nonce = "nonce-wrapper-1"
    sig = hmac_signature_b64(secret, canonical_string(ts=ts, nonce=nonce, raw_body=raw))

    res = client.post(
        "/api/sync-hmac/batch/",
        data=body,
        format="json",
        HTTP_X_DEVICE_ID=str(legacy_id),
        HTTP_X_DEVICE_TS=str(ts),
        HTTP_X_DEVICE_NONCE=nonce,
        HTTP_X_DEVICE_SIGNATURE=sig,
    )
    assert res.status_code == 200
    payload = res.json()
    assert payload["device_id"] == str(legacy_id)
    assert payload["results"][0]["result"]["status"] == "OK"
    assert payload["results"][0]["result"]["data"]["pong"] is True
    assert isinstance(payload.get("trace"), dict)
    assert payload["trace"]["request_id"] == res["X-Request-Id"]
    assert payload["trace"]["channel"] == "sync_legacy"
    assert payload["trace"]["legacy_wrapper"] is True
    assert res["Deprecation"] == "true"
    assert "Sunset" in res
    assert "deprecation" in res["Link"]
