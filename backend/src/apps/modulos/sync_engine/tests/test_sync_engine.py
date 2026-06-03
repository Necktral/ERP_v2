"""
Tests del módulo sync_engine — motor offline/sync.

Firma (signing): canonicalización de tiempo, JSON canónico, hashes, decodificación
base64 estricta, mensaje de firma de comandos/requests, verificación Ed25519 y
HMAC. Registry de handlers (alta/lookup/duplicado). Errores tipados de rechazo.
API: listado de dispositivos protegido por permiso rbac.
"""
from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac
import uuid

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.modulos.iam.models import OrgUnit, UserMembership
from apps.modulos.rbac.models import Permission, Role, RoleAssignment, RolePermission
from apps.modulos.sync_engine.errors import SyncRejectError
from apps.modulos.sync_engine.registry import get_handler, register
from apps.modulos.sync_engine.signing import (
    b64decode_strict,
    build_command_signing_message,
    build_request_signing_message,
    canon_json,
    occurred_at_canonical,
    public_key_from_b64,
    sha256_hex,
    sha256_hex_bytes,
    verify_ed25519_signature,
    verify_hmac_signature_b64,
)

User = get_user_model()


# ---------------------------------------------------------------------------
# signing: helpers deterministas
# ---------------------------------------------------------------------------

def test_occurred_at_canonical_naive_assumed_utc():
    naive = dt.datetime(2026, 1, 1, 12, 0, 0, 123456)
    assert occurred_at_canonical(naive) == "2026-01-01T12:00:00.123456+00:00"


def test_occurred_at_canonical_converts_to_utc():
    aware = dt.datetime(2026, 1, 1, 12, 0, 0, tzinfo=dt.timezone(dt.timedelta(hours=5)))
    assert occurred_at_canonical(aware) == "2026-01-01T07:00:00.000000+00:00"


def test_canon_json_sorts_keys():
    assert canon_json({"b": 1, "a": 2}) == '{"a":2,"b":1}'


def test_sha256_helpers_match_hashlib():
    assert sha256_hex("abc") == hashlib.sha256(b"abc").hexdigest()
    assert sha256_hex_bytes(b"abc") == hashlib.sha256(b"abc").hexdigest()


def test_b64decode_strict_roundtrip_and_invalid():
    assert b64decode_strict(base64.b64encode(b"hi").decode()) == b"hi"
    with pytest.raises(Exception):
        b64decode_strict("!!!notbase64!!!")


def test_public_key_from_b64_length_check():
    raw = bytes(range(32))
    assert public_key_from_b64(base64.b64encode(raw).decode()) == raw
    with pytest.raises(ValueError):
        public_key_from_b64(base64.b64encode(b"short").decode())


def test_build_command_signing_message_format():
    msg = build_command_signing_message(
        command_id="c1",
        command_type="T",
        company_id=1,
        branch_id=None,
        occurred_at="2026",
        sequence=None,
        payload_hash="ph",
        prev_hash="prev",
    )
    assert msg == b"c1|T|1||2026||ph|prev"
    msg2 = build_command_signing_message(
        command_id="c1",
        command_type="T",
        company_id=1,
        branch_id=2,
        occurred_at="2026",
        sequence=5,
        payload_hash="ph",
        prev_hash="prev",
    )
    assert msg2 == b"c1|T|1|2|2026|5|ph|prev"


def test_build_request_signing_message_format():
    m = build_request_signing_message(ts=123, nonce="n", canonical_body_bytes=b"body")
    assert m == f"123.n.{sha256_hex_bytes(b'body')}".encode("utf-8")


# ---------------------------------------------------------------------------
# signing: verificación de firmas
# ---------------------------------------------------------------------------

def test_verify_ed25519_signature_valid_and_tampered():
    priv = Ed25519PrivateKey.generate()
    pub_raw = priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    message = b"hello-sync"
    sig_b64 = base64.b64encode(priv.sign(message)).decode("utf-8")

    assert verify_ed25519_signature(public_key_raw=pub_raw, signature_b64=sig_b64, message=message) is True
    assert verify_ed25519_signature(public_key_raw=pub_raw, signature_b64=sig_b64, message=b"tampered") is False
    # Firma con longitud inválida => rechazada sin excepción.
    bad = base64.b64encode(b"short").decode("utf-8")
    assert verify_ed25519_signature(public_key_raw=pub_raw, signature_b64=bad, message=message) is False


def test_verify_hmac_signature_b64_valid_and_invalid():
    secret = b"0123456789abcdef"
    secret_b64 = base64.b64encode(secret).decode("utf-8")
    message = b"the-message"
    sig_b64 = base64.b64encode(hmac.new(secret, message, hashlib.sha256).digest()).decode("utf-8")

    assert verify_hmac_signature_b64(secret_b64=secret_b64, message=message, signature_b64=sig_b64) is True
    assert verify_hmac_signature_b64(secret_b64=secret_b64, message=b"other", signature_b64=sig_b64) is False


# ---------------------------------------------------------------------------
# registry
# ---------------------------------------------------------------------------

def test_registry_register_lookup_and_duplicate():
    name = f"TEST_CMD_{uuid.uuid4().hex[:10]}"

    def handler(command, ctx):
        return {"refs": {}}

    register(name)(handler)
    assert get_handler(name) is handler
    assert get_handler(f"unknown_{uuid.uuid4().hex[:6]}") is None
    with pytest.raises(RuntimeError):
        register(name)(handler)  # command_type duplicado


# ---------------------------------------------------------------------------
# errors
# ---------------------------------------------------------------------------

def test_sync_reject_error_str_is_reason_code():
    e = SyncRejectError(reason_code="INVENTORY_NEGATIVE_STOCK_BLOCKED", details={"item_id": 1})
    assert str(e) == "INVENTORY_NEGATIVE_STOCK_BLOCKED"
    assert e.reason_code == "INVENTORY_NEGATIVE_STOCK_BLOCKED"
    assert e.details == {"item_id": 1}
    assert isinstance(e, Exception)


# ---------------------------------------------------------------------------
# API: DeviceListView
# ---------------------------------------------------------------------------

def _mk_org():
    s = uuid.uuid4().hex[:6]
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name=f"H_{s}")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name=f"C_{s}", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name=f"B_{s}", parent=company)
    return company, branch


def _client_with_perms(*, company, branch, perm_codes):
    username = f"api_{uuid.uuid4().hex[:8]}"
    user = User.objects.create_user(username=username, email=f"{username}@test.local", password="pass12345")
    UserMembership.objects.create(user=user, org_unit=company, is_active=True)
    UserMembership.objects.create(user=user, org_unit=branch, is_active=True)
    role = Role.objects.create(name=f"role_{uuid.uuid4().hex[:8]}", is_active=True)
    for code in perm_codes:
        perm, _ = Permission.objects.get_or_create(code=code, defaults={"description": code, "is_active": True})
        RolePermission.objects.get_or_create(role=role, permission=perm)
    RoleAssignment.objects.create(user=user, role=role, org_unit=company, is_active=True)
    RoleAssignment.objects.create(user=user, role=role, org_unit=branch, is_active=True)

    client = APIClient()
    login = client.post("/api/auth/login/", {"username": username, "password": "pass12345"}, format="json")
    assert login.status_code == 200, login.data
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data.get('access')}")
    client.defaults["HTTP_X_COMPANY_ID"] = str(company.id)
    client.defaults["HTTP_X_BRANCH_ID"] = str(branch.id)
    return client


@pytest.mark.django_db
def test_device_list_forbidden_without_permission():
    company, branch = _mk_org()
    client = _client_with_perms(company=company, branch=branch, perm_codes=[])
    assert client.get("/api/sync/devices/").status_code == 403


@pytest.mark.django_db
def test_device_list_ok_with_permission():
    company, branch = _mk_org()
    client = _client_with_perms(company=company, branch=branch, perm_codes=["sync.device.revoke"])
    assert client.get("/api/sync/devices/").status_code == 200
