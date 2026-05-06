from __future__ import annotations

import base64
import copy
import json
import uuid
from typing import Any

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from apps.modulos.audit.contracts import validate_reason_code
from apps.modulos.audit.models import AuditEvent
from apps.modulos.iam.models import OrgUnit, UserMembership
from apps.modulos.rbac.models import Permission, Role, RoleAssignment, RolePermission
from apps.modulos.estacion_servicios import services as fuel_services
from apps.modulos.retail_pos.models import PosTicket, PosTicketStatus
from apps.modulos.sync_engine.models import Device
from apps.modulos.sync_engine.signing import build_request_signing_message, canon_json

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


def _client_with_perms(*, company: OrgUnit, branch: OrgUnit, perm_codes: list[str]) -> tuple[APIClient, Any]:
    username = f"u_{uuid.uuid4().hex[:10]}"
    user = User.objects.create_user(username=username, email="sync-pos@test.com", password="pass12345")

    UserMembership.objects.create(user=user, org_unit=company, is_active=True)
    UserMembership.objects.create(user=user, org_unit=branch, is_active=True)

    role = Role.objects.create(name=f"role_{uuid.uuid4().hex[:8]}", is_active=True)
    for code in perm_codes:
        perm, _ = Permission.objects.get_or_create(code=code, defaults={"description": code, "is_active": True})
        if not perm.is_active:
            perm.is_active = True
            perm.save(update_fields=["is_active"])
        RolePermission.objects.get_or_create(role=role, permission=perm)
    RoleAssignment.objects.create(user=user, role=role, org_unit=company, is_active=True)
    RoleAssignment.objects.create(user=user, role=role, org_unit=branch, is_active=True)

    client = APIClient(raise_request_exception=True)
    login = client.post(
        "/api/auth/login/",
        {"username": username, "password": "pass12345"},
        format="json",
        HTTP_X_AUTH_TRANSPORT="header",
    )
    assert login.status_code == 200
    access = login.data.get("access") if isinstance(login.data, dict) else None
    if isinstance(access, str) and access:
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        client.defaults["HTTP_AUTHORIZATION"] = f"Bearer {access}"
    client.defaults["HTTP_X_AUTH_TRANSPORT"] = "header"
    client.defaults["HTTP_X_COMPANY_ID"] = str(company.id)
    client.defaults["HTTP_X_BRANCH_ID"] = str(branch.id)
    return client, user


def _sign_v2_ed25519(body: dict[str, Any], private_key: Ed25519PrivateKey) -> str:
    payload = copy.deepcopy(body)
    payload["auth"]["signature"] = ""
    signing_body = canon_json(payload).encode("utf-8")
    msg = build_request_signing_message(
        ts=int(body["ts"]),
        nonce=str(body["nonce"]),
        canonical_body_bytes=signing_body,
    )
    return base64.b64encode(private_key.sign(msg)).decode("utf-8")


POS_SYNC_REJECTION_CODES = (
    "POS_INVALID_SCOPE",
    "POS_SCHEMA_INVALID",
    "POS_ACTOR_REQUIRED",
    "POS_COMPENSATION_PENDING",
)


def _assert_pos_command_rejected_audit(*, reason_code: str, command_id: str) -> AuditEvent:
    events = AuditEvent.objects.filter(
        event_type="SYNC_COMMAND_REJECTED",
        reason_code=reason_code,
        metadata__command_id=str(command_id),
    )
    assert events.count() == 1
    ev = events.get()
    assert ev.subject_type == "DEVICE"

    metadata_json = json.dumps(ev.metadata, sort_keys=True).lower()
    assert "signature" not in metadata_json
    assert "nonce" not in metadata_json
    assert "public_key" not in metadata_json
    assert "private_key" not in metadata_json
    assert "secret" not in metadata_json
    return ev


def test_pos_sync_reason_codes_are_contractual() -> None:
    for reason_code in POS_SYNC_REJECTION_CODES:
        validate_reason_code(reason_code)


@pytest.mark.django_db
def test_sync_v2_pos_ticket_command_happy_path() -> None:
    company, branch = _mk_org()
    setup_client, enrolled_by = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=[
            "fuel.shift.open",
            "retail.pos.session.open",
        ],
    )

    r_shift = setup_client.post("/api/fuel/shifts/open/", {"note": "sync-v2-pos"}, format="json")
    assert r_shift.status_code == 201
    shift_id = int(r_shift.data["id"])

    r_session = setup_client.post(
        "/api/retail/pos/sessions/open/",
        {"opening_amount": "100.00", "note": "sync-v2-pos"},
        format="json",
    )
    assert r_session.status_code == 201
    session_id = int(r_session.data["id"])

    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    device = Device.objects.create(
        company=company,
        branch=branch,
        label="pos-sync-device",
        status=Device.Status.ACTIVE,
        public_key=public,
        enrolled_by_user=enrolled_by,
    )

    command_id = str(uuid.uuid4())
    ts = int(timezone.now().timestamp())
    body: dict[str, Any] = {
        "protocol_version": "2",
        "device_id": str(device.id),
        "ts": ts,
        "nonce": "nonce-pos-ticket-001",
        "auth": {"scheme": "ed25519", "signature": ""},
        "batch_id": str(uuid.uuid4()),
        "batch": [
            {
                "command_id": command_id,
                "type": "POS_TICKET",
                "scope": {"company_id": company.id, "branch_id": branch.id},
                "occurred_at": timezone.now().isoformat(),
                "payload": {
                    "session_id": session_id,
                    "shift_id": shift_id,
                    "idempotency_key": "sync-pos-ticket-001",
                    "external_ref": "SYNC-POS-001",
                    "product": "DIESEL",
                    "volume": "5.0000",
                    "volume_uom": "LITER",
                    "unit_price_entered": "42.5000",
                    "unit_price_uom": "PER_LITER",
                    "sale_type": "PUBLIC",
                    "payment_method": "CASH",
                    "metadata": {"source": "sync-v2"},
                },
            }
        ],
    }
    body["auth"]["signature"] = _sign_v2_ed25519(body, private)

    sync_client = APIClient(raise_request_exception=True)
    response = sync_client.post(
        "/api/sync/batch/",
        data=body,
        format="json",
        HTTP_X_DEVICE_ID=str(device.id),
    )
    assert response.status_code == 200
    assert response.data["results"][0]["status"] == "APPLIED"
    refs = response.data["results"][0]["refs"]
    ticket_id = int(refs["ticket_id"])
    assert refs["status"] == "CLOSED"
    assert refs["sale_id"] is not None
    assert refs["payment_id"] != ""

    ticket = PosTicket.objects.get(id=ticket_id)
    assert ticket.status == PosTicketStatus.CLOSED
    assert ticket.sale_id is not None
    assert ticket.payment_intent_id is not None
    assert not AuditEvent.objects.filter(
        event_type="SYNC_COMMAND_REJECTED",
        reason_code__in=POS_SYNC_REJECTION_CODES,
    ).exists()


@pytest.mark.django_db
def test_sync_v2_pos_compensation_retry_command(monkeypatch) -> None:
    company, branch = _mk_org()
    setup_client, enrolled_by = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=[
            "fuel.shift.open",
            "retail.pos.session.open",
            "retail.pos.ticket.open",
            "retail.pos.ticket.checkout",
            "retail.pos.ticket.read",
        ],
    )

    r_shift = setup_client.post("/api/fuel/shifts/open/", {"note": "sync-v2-comp"}, format="json")
    assert r_shift.status_code == 201
    shift_id = int(r_shift.data["id"])

    r_session = setup_client.post(
        "/api/retail/pos/sessions/open/",
        {"opening_amount": "25.00", "note": "sync-v2-comp"},
        format="json",
    )
    assert r_session.status_code == 201
    session_id = int(r_session.data["id"])

    r_ticket = setup_client.post(
        "/api/retail/pos/tickets/",
        {"shift_id": shift_id, "idempotency_key": "sync-v2-comp-ticket", "payment_method": "CASH"},
        format="json",
    )
    assert r_ticket.status_code == 201
    ticket_id = int(r_ticket.data["id"])

    attempts = {"count": 0}
    real_create_sale = fuel_services.create_sale

    def flaky_create_sale(*args, **kwargs):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RuntimeError("forced-sync-comp-failure")
        return real_create_sale(*args, **kwargs)

    monkeypatch.setattr("apps.modulos.retail_pos.services.create_sale", flaky_create_sale)

    r_checkout = setup_client.post(
        f"/api/retail/pos/tickets/{ticket_id}/checkout/",
        {
            "line": {
                "product": "DIESEL",
                "volume": "2.0000",
                "volume_uom": "LITER",
                "unit_price_entered": "41.0000",
                "unit_price_uom": "PER_LITER",
            }
        },
        format="json",
    )
    assert r_checkout.status_code == 409
    pending_ticket = PosTicket.objects.get(id=ticket_id)
    assert pending_ticket.status == PosTicketStatus.CHECKOUT_PENDING
    assert pending_ticket.compensation_pending is True
    assert pending_ticket.session_id == session_id

    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    device = Device.objects.create(
        company=company,
        branch=branch,
        label="pos-sync-comp-device",
        status=Device.Status.ACTIVE,
        public_key=public,
        enrolled_by_user=enrolled_by,
    )

    command_id = str(uuid.uuid4())
    ts = int(timezone.now().timestamp())
    body: dict[str, Any] = {
        "protocol_version": "2",
        "device_id": str(device.id),
        "ts": ts,
        "nonce": "nonce-pos-comp-retry-001",
        "auth": {"scheme": "ed25519", "signature": ""},
        "batch_id": str(uuid.uuid4()),
        "batch": [
            {
                "command_id": command_id,
                "type": "POS_COMPENSATION_RETRY",
                "scope": {"company_id": company.id, "branch_id": branch.id},
                "occurred_at": timezone.now().isoformat(),
                "payload": {
                    "ticket_id": ticket_id,
                    "reason": "SYNC_RETRY",
                },
            }
        ],
    }
    body["auth"]["signature"] = _sign_v2_ed25519(body, private)

    sync_client = APIClient(raise_request_exception=True)
    response = sync_client.post(
        "/api/sync/batch/",
        data=body,
        format="json",
        HTTP_X_DEVICE_ID=str(device.id),
    )
    assert response.status_code == 200
    assert response.data["results"][0]["status"] == "APPLIED"
    refs = response.data["results"][0]["refs"]
    assert int(refs["ticket_id"]) == ticket_id
    assert refs["status"] == "CLOSED"
    assert refs["compensation_pending"] is False

    recovered = PosTicket.objects.get(id=ticket_id)
    assert recovered.status == PosTicketStatus.CLOSED
    assert recovered.compensation_pending is False


@pytest.mark.django_db
def test_sync_v2_pos_compensation_retry_rejects_invalid_scope_code() -> None:
    company, branch = _mk_org()
    _, enrolled_by = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=[],
    )

    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    device = Device.objects.create(
        company=company,
        branch=branch,
        label="pos-sync-invalid-scope",
        status=Device.Status.ACTIVE,
        public_key=public,
        enrolled_by_user=enrolled_by,
    )

    command_id = str(uuid.uuid4())
    ts = int(timezone.now().timestamp())
    body: dict[str, Any] = {
        "protocol_version": "2",
        "device_id": str(device.id),
        "ts": ts,
        "nonce": "nonce-pos-invalid-scope-001",
        "auth": {"scheme": "ed25519", "signature": ""},
        "batch_id": str(uuid.uuid4()),
        "batch": [
            {
                "command_id": command_id,
                "type": "POS_COMPENSATION_RETRY",
                "scope": {"company_id": company.id, "branch_id": branch.id},
                "occurred_at": timezone.now().isoformat(),
                "payload": {"ticket_id": 999999},
            }
        ],
    }
    body["auth"]["signature"] = _sign_v2_ed25519(body, private)

    sync_client = APIClient(raise_request_exception=True)
    response = sync_client.post(
        "/api/sync/batch/",
        data=body,
        format="json",
        HTTP_X_DEVICE_ID=str(device.id),
    )
    assert response.status_code == 200
    assert response.data["results"][0]["status"] == "REJECTED"
    assert response.data["results"][0]["reason"] == "POS_INVALID_SCOPE"
    _assert_pos_command_rejected_audit(reason_code="POS_INVALID_SCOPE", command_id=command_id)


@pytest.mark.django_db
def test_sync_v2_pos_compensation_retry_rejects_schema_invalid_code() -> None:
    company, branch = _mk_org()
    _, enrolled_by = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=[],
    )

    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    device = Device.objects.create(
        company=company,
        branch=branch,
        label="pos-sync-schema-invalid",
        status=Device.Status.ACTIVE,
        public_key=public,
        enrolled_by_user=enrolled_by,
    )

    ts = int(timezone.now().timestamp())
    command_id = str(uuid.uuid4())
    body: dict[str, Any] = {
        "protocol_version": "2",
        "device_id": str(device.id),
        "ts": ts,
        "nonce": "nonce-pos-schema-invalid-001",
        "auth": {"scheme": "ed25519", "signature": ""},
        "batch_id": str(uuid.uuid4()),
        "batch": [
            {
                "command_id": command_id,
                "type": "POS_COMPENSATION_RETRY",
                "scope": {"company_id": company.id, "branch_id": branch.id},
                "occurred_at": timezone.now().isoformat(),
                "payload": {},
            }
        ],
    }
    body["auth"]["signature"] = _sign_v2_ed25519(body, private)

    sync_client = APIClient(raise_request_exception=True)
    response = sync_client.post(
        "/api/sync/batch/",
        data=body,
        format="json",
        HTTP_X_DEVICE_ID=str(device.id),
    )
    assert response.status_code == 200
    assert response.data["results"][0]["status"] == "REJECTED"
    assert response.data["results"][0]["reason"] == "POS_SCHEMA_INVALID"
    _assert_pos_command_rejected_audit(reason_code="POS_SCHEMA_INVALID", command_id=command_id)


@pytest.mark.django_db
def test_sync_v2_pos_cash_count_rejects_actor_required_with_audit() -> None:
    company, branch = _mk_org()

    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    device = Device.objects.create(
        company=company,
        branch=branch,
        label="pos-sync-actor-required",
        status=Device.Status.ACTIVE,
        public_key=public,
        enrolled_by_user=None,
    )

    command_id = str(uuid.uuid4())
    ts = int(timezone.now().timestamp())
    body: dict[str, Any] = {
        "protocol_version": "2",
        "device_id": str(device.id),
        "ts": ts,
        "nonce": "nonce-pos-actor-required-001",
        "auth": {"scheme": "ed25519", "signature": ""},
        "batch_id": str(uuid.uuid4()),
        "batch": [
            {
                "command_id": command_id,
                "type": "POS_CASH_COUNT",
                "scope": {"company_id": company.id, "branch_id": branch.id},
                "occurred_at": timezone.now().isoformat(),
                "payload": {},
            }
        ],
    }
    body["auth"]["signature"] = _sign_v2_ed25519(body, private)

    sync_client = APIClient(raise_request_exception=True)
    response = sync_client.post(
        "/api/sync/batch/",
        data=body,
        format="json",
        HTTP_X_DEVICE_ID=str(device.id),
    )
    assert response.status_code == 200
    assert response.data["results"][0]["status"] == "REJECTED"
    assert response.data["results"][0]["reason"] == "POS_ACTOR_REQUIRED"
    _assert_pos_command_rejected_audit(reason_code="POS_ACTOR_REQUIRED", command_id=command_id)


@pytest.mark.django_db
def test_sync_v2_pos_compensation_retry_rejects_pending_with_audit(monkeypatch) -> None:
    company, branch = _mk_org()
    setup_client, enrolled_by = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=[
            "fuel.shift.open",
            "retail.pos.session.open",
            "retail.pos.ticket.open",
            "retail.pos.ticket.checkout",
            "retail.pos.ticket.read",
        ],
    )

    r_shift = setup_client.post("/api/fuel/shifts/open/", {"note": "sync-v2-pending"}, format="json")
    assert r_shift.status_code == 201
    shift_id = int(r_shift.data["id"])

    r_session = setup_client.post(
        "/api/retail/pos/sessions/open/",
        {"opening_amount": "25.00", "note": "sync-v2-pending"},
        format="json",
    )
    assert r_session.status_code == 201

    r_ticket = setup_client.post(
        "/api/retail/pos/tickets/",
        {"shift_id": shift_id, "idempotency_key": "sync-v2-pending-ticket", "payment_method": "CASH"},
        format="json",
    )
    assert r_ticket.status_code == 201
    ticket_id = int(r_ticket.data["id"])

    def fail_create_sale(*args, **kwargs):
        raise RuntimeError("forced-sync-pending-failure")

    monkeypatch.setattr("apps.modulos.retail_pos.services.create_sale", fail_create_sale)
    r_checkout = setup_client.post(
        f"/api/retail/pos/tickets/{ticket_id}/checkout/",
        {
            "line": {
                "product": "DIESEL",
                "volume": "2.0000",
                "volume_uom": "LITER",
                "unit_price_entered": "41.0000",
                "unit_price_uom": "PER_LITER",
            }
        },
        format="json",
    )
    assert r_checkout.status_code == 409
    pending_ticket = PosTicket.objects.get(id=ticket_id)
    assert pending_ticket.status == PosTicketStatus.CHECKOUT_PENDING

    def keep_pending(*args, **kwargs):
        return PosTicket.objects.get(id=ticket_id)

    monkeypatch.setattr("apps.modulos.sync_engine.handlers_pos.retry_ticket_compensation", keep_pending)

    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    device = Device.objects.create(
        company=company,
        branch=branch,
        label="pos-sync-comp-pending-device",
        status=Device.Status.ACTIVE,
        public_key=public,
        enrolled_by_user=enrolled_by,
    )

    command_id = str(uuid.uuid4())
    ts = int(timezone.now().timestamp())
    body: dict[str, Any] = {
        "protocol_version": "2",
        "device_id": str(device.id),
        "ts": ts,
        "nonce": "nonce-pos-comp-pending-001",
        "auth": {"scheme": "ed25519", "signature": ""},
        "batch_id": str(uuid.uuid4()),
        "batch": [
            {
                "command_id": command_id,
                "type": "POS_COMPENSATION_RETRY",
                "scope": {"company_id": company.id, "branch_id": branch.id},
                "occurred_at": timezone.now().isoformat(),
                "payload": {
                    "ticket_id": ticket_id,
                    "reason": "SYNC_RETRY",
                },
            }
        ],
    }
    body["auth"]["signature"] = _sign_v2_ed25519(body, private)

    sync_client = APIClient(raise_request_exception=True)
    response = sync_client.post(
        "/api/sync/batch/",
        data=body,
        format="json",
        HTTP_X_DEVICE_ID=str(device.id),
    )
    assert response.status_code == 200
    assert response.data["results"][0]["status"] == "REJECTED"
    assert response.data["results"][0]["reason"] == "POS_COMPENSATION_PENDING"
    _assert_pos_command_rejected_audit(reason_code="POS_COMPENSATION_PENDING", command_id=command_id)
