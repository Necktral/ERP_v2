"""
Tests del módulo audit — redacción de PII, integridad criptográfica y keyring.

Redacción: claves sensibles -> REDACTED (case-insensitive, anidado, listas) y
truncado de payloads grandes. Integridad: verify_events recalcula event_hash y
HMAC y detecta alteraciones; verify_queryset valida el encadenamiento por
partición. Keyring: derivación de la clave activa. API: bitácora protegida.
"""
from __future__ import annotations

import uuid

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.modulos.audit.integrity import (
    _canon_json,
    _hmac_hex,
    _payload_for_event,
    _sha256_hex,
    verify_events,
    verify_queryset,
)
from apps.modulos.audit.keyring import (
    _parse_keyring_raw,
    get_active_audit_hmac_key,
    get_audit_hmac_keyring,
)
from apps.modulos.audit.models import AuditChainHeadV2, AuditEvent
from apps.modulos.audit.redaction import REDACTED, sanitize_metadata, sanitize_snapshot


# ---------------------------------------------------------------------------
# Redacción
# ---------------------------------------------------------------------------

def test_redact_sensitive_keys():
    out = sanitize_metadata(
        {"password": "x", "token": "y", "user": "bob", "nested": {"api_key": "z"}}
    )
    assert out["password"] == REDACTED
    assert out["token"] == REDACTED
    assert out["user"] == "bob"
    assert out["nested"]["api_key"] == REDACTED


def test_redact_is_case_insensitive_and_substring_based():
    out = sanitize_metadata({"Authorization": "Bearer x", "X-Refresh-Token": "r", "normal": 1})
    assert out["Authorization"] == REDACTED
    assert out["X-Refresh-Token"] == REDACTED
    assert out["normal"] == 1


def test_redact_handles_lists_and_primitives():
    out = sanitize_metadata({"items": [{"secret": "s"}, {"ok": 1}], "flag": True, "n": 3})
    assert out["items"][0]["secret"] == REDACTED
    assert out["items"][1]["ok"] == 1
    assert out["flag"] is True
    assert out["n"] == 3


def test_sanitize_snapshot_none_passthrough():
    assert sanitize_snapshot(None) is None


def test_sanitize_metadata_none_returns_empty_dict():
    assert sanitize_metadata(None) == {}


def test_truncate_large_metadata():
    out = sanitize_metadata({"data": "x" * 30000})
    assert out.get("_truncated") is True
    assert "_sha256" in out
    assert out["_bytes"] > 24000


# ---------------------------------------------------------------------------
# Integridad: verify_events (sin DB)
# ---------------------------------------------------------------------------

def _signed_event(*, partition_key="TEST:1", prev=""):
    ev = AuditEvent(
        module="TEST",
        event_type="X",
        partition_key=partition_key,
        timestamp_server=timezone.now(),
        before_snapshot={},
        after_snapshot={},
        metadata={},
        prev_event_hash=prev,
    )
    kid, key = get_active_audit_hmac_key()
    h = _sha256_hex(_canon_json(_payload_for_event(ev)))
    ev.event_hash = h
    ev.signature = _hmac_hex(h, key=key)
    ev.signature_key_id = kid
    return ev


def test_verify_events_valid_event_passes():
    report = verify_events([_signed_event()])
    assert report.ok is True
    assert report.events_scanned == 1
    assert report.errors == []


def test_verify_events_detects_hash_mismatch():
    ev = _signed_event()
    ev.metadata = {"tampered": True}  # cambia el payload sin recalcular el hash
    report = verify_events([ev])
    assert report.ok is False
    assert any(e.code == "EVENT_HASH_MISMATCH" for e in report.errors)


def test_verify_events_detects_signature_mismatch():
    ev = _signed_event()
    ev.signature = "deadbeef" * 8  # firma inválida, hash intacto
    report = verify_events([ev])
    assert report.ok is False
    assert any(e.code == "SIGNATURE_MISMATCH" for e in report.errors)


def test_verify_events_detects_missing_hash():
    ev = _signed_event()
    ev.event_hash = ""
    report = verify_events([ev])
    assert report.ok is False
    assert any(e.code == "MISSING_EVENT_HASH" for e in report.errors)


# ---------------------------------------------------------------------------
# Keyring
# ---------------------------------------------------------------------------

def test_keyring_has_active_key():
    keyring = get_audit_hmac_keyring()
    assert len(keyring) >= 1
    kid, key = get_active_audit_hmac_key()
    assert kid and key
    assert (kid, key) == keyring[0]


def test_parse_keyring_raw_string_format():
    parsed = _parse_keyring_raw("k1:secret1,k2:secret2")
    assert parsed == [("k1", "secret1"), ("k2", "secret2")]


# ---------------------------------------------------------------------------
# Integridad: verify_queryset (encadenamiento, con DB)
# ---------------------------------------------------------------------------

def _persist_signed_event(*, partition_key, prev):
    ev = AuditEvent.objects.create(
        module="TEST",
        event_type="X",
        partition_key=partition_key,
        timestamp_server=timezone.now(),
        before_snapshot={},
        after_snapshot={},
        metadata={},
        prev_event_hash=prev,
    )
    ev.refresh_from_db()
    kid, key = get_active_audit_hmac_key()
    h = _sha256_hex(_canon_json(_payload_for_event(ev)))
    ev.event_hash = h
    ev.signature = _hmac_hex(h, key=key)
    ev.signature_key_id = kid
    ev.save(update_fields=["event_hash", "signature", "signature_key_id"])
    ev.refresh_from_db()
    return ev


@pytest.mark.django_db
def test_verify_queryset_valid_chain_is_ok():
    pk = f"TEST:{uuid.uuid4().hex[:6]}"
    genesis = _persist_signed_event(partition_key=pk, prev="")
    tail = _persist_signed_event(partition_key=pk, prev=genesis.event_hash)
    AuditChainHeadV2.objects.create(partition_key=pk, last_event_hash=tail.event_hash)

    report = verify_queryset(AuditEvent.objects.filter(partition_key=pk))
    assert report.ok is True, report.to_dict()
    assert report.events_scanned == 2


@pytest.mark.django_db
def test_verify_queryset_missing_head_is_flagged():
    pk = f"TEST:{uuid.uuid4().hex[:6]}"
    genesis = _persist_signed_event(partition_key=pk, prev="")
    _persist_signed_event(partition_key=pk, prev=genesis.event_hash)
    # Sin AuditChainHeadV2 para la partición.
    report = verify_queryset(AuditEvent.objects.filter(partition_key=pk))
    assert report.ok is False
    assert any(e.code == "MISSING_CHAIN_HEAD" for e in report.errors)


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_audit_bitacora_requires_authentication():
    resp = APIClient().get("/api/audit/bitacora/")
    assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# _client_ip — trazabilidad desde celulares detrás del proxy del frontend
# ---------------------------------------------------------------------------

def test_client_ip_takes_last_xff_value_from_trusted_proxy():
    """El último valor del XFF lo escribe NUESTRO proxy (xfwd); los anteriores
    son alegaciones del cliente. Un XFF falsificado no debe entrar a la bitácora."""
    from types import SimpleNamespace

    from apps.modulos.audit.writer import _client_ip

    # Cel real detrás del proxy del frontend: el proxy agrega la IP verdadera al final
    req = SimpleNamespace(META={"HTTP_X_FORWARDED_FOR": "192.168.1.55", "REMOTE_ADDR": "172.18.0.5"})
    assert _client_ip(req) == "192.168.1.55"

    # Atacante manda un XFF inventado; el proxy appendea la IP real → gana la real
    req = SimpleNamespace(
        META={"HTTP_X_FORWARDED_FOR": "1.2.3.4, 192.168.1.55", "REMOTE_ADDR": "172.18.0.5"}
    )
    assert _client_ip(req) == "192.168.1.55"

    # Acceso directo sin proxy: REMOTE_ADDR
    req = SimpleNamespace(META={"REMOTE_ADDR": "192.168.1.13"})
    assert _client_ip(req) == "192.168.1.13"

    assert _client_ip(None) is None


@pytest.mark.django_db
def test_write_event_takes_device_id_from_header_only_if_enrolled_and_active():
    """X-Device-Id solo entra a la bitácora si es un Device ACTIVO de la company."""
    import uuid as uuid_mod
    from types import SimpleNamespace

    from apps.modulos.audit.writer import write_event
    from apps.modulos.iam.models import OrgUnit
    from apps.modulos.sync_engine.models import Device

    tag = uuid_mod.uuid4().hex[:6]
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name=f"H_{tag}")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name=f"C_{tag}", parent=holding)
    other_company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name=f"C2_{tag}", parent=holding)

    device = Device.objects.create(company=company, label="Cel mandador", public_key=b"\x01" * 32)

    def _req(device_header: str, com=company):
        return SimpleNamespace(
            META={"HTTP_X_DEVICE_ID": device_header} if device_header else {},
            company=com, branch=None, _request=None, ctx=None,
            request_id=f"req_{uuid_mod.uuid4().hex[:8]}", path="/x", method="POST", user=None,
        )

    # Dispositivo enrolado y activo de la misma company → se registra
    ev = write_event(request=_req(str(device.id)), event_type="HR_EMPLOYEE_UPDATED", reason_code="OK",
                     subject_type="EMPLOYEE", subject_id="1")
    assert ev.device_id == str(device.id)

    # Header inventado (UUID que no existe) → vacío
    ev = write_event(request=_req(str(uuid_mod.uuid4())), event_type="HR_EMPLOYEE_UPDATED", reason_code="OK",
                     subject_type="EMPLOYEE", subject_id="1")
    assert ev.device_id == ""

    # Dispositivo de OTRA empresa → vacío
    ev = write_event(request=_req(str(device.id), com=other_company), event_type="HR_EMPLOYEE_UPDATED", reason_code="OK",
                     subject_type="EMPLOYEE", subject_id="1")
    assert ev.device_id == ""

    # Dispositivo revocado → vacío
    device.revoke()
    ev = write_event(request=_req(str(device.id)), event_type="HR_EMPLOYEE_UPDATED", reason_code="OK",
                     subject_type="EMPLOYEE", subject_id="1")
    assert ev.device_id == ""
