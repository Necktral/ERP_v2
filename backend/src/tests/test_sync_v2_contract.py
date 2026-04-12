from __future__ import annotations

import base64
import copy
import hashlib
import hmac
import os
import uuid

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from django.test import override_settings
from django.utils import timezone
from rest_framework.renderers import JSONRenderer
from rest_framework.test import APIClient

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

    r2 = client.post("/api/sync/batch/", data=body, format="json", HTTP_X_DEVICE_ID=str(device.id))
    assert r2.status_code == 401
    payload = r2.json()
    assert payload["error"]["message"] == "REPLAY_DETECTED"


@pytest.mark.django_db
def test_sync_batch_v2_rejects_bad_signature():
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

    res = client.post("/api/sync/batch/", data=body, format="json", HTTP_X_DEVICE_ID=str(device.id))
    assert res.status_code == 401
    payload = res.json()
    assert payload["error"]["message"] == "BAD_SIGNATURE"


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
@override_settings(SYNC_HMAC_WRAPPER_ENABLED=True)
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
    assert res["Deprecation"] == "true"
    assert "Sunset" in res
    assert "deprecation" in res["Link"]
