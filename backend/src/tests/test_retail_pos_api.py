from __future__ import annotations

import base64
from datetime import timedelta
import hashlib
import hmac
import io
import json
import uuid

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import override_settings
from rest_framework.test import APIClient

from apps.modulos.iam.models import OrgUnit, UserMembership
from apps.modulos.integration.models import OutboxEvent
from apps.modulos.rbac.models import Permission, Role, RoleAssignment, RolePermission
from apps.modulos.estacion_servicios import services as fuel_services
from apps.modulos.retail_pos.models import PosSession, PosSessionStatus, PosTicket, PosTicketStatus

User = get_user_model()


def _mk_org() -> tuple[OrgUnit, OrgUnit]:
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="H")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="C", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name="B", parent=company)
    return company, branch


def _client_with_perms(*, company: OrgUnit, branch: OrgUnit, perm_codes: list[str]) -> APIClient:
    username = f"u_{uuid.uuid4().hex[:10]}"
    user = User.objects.create_user(username=username, email="retail-pos@test.com", password="pass12345")

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
    login = client.post("/api/auth/login/", {"username": username, "password": "pass12345"}, format="json")
    assert login.status_code == 200
    access = login.data.get("access") if isinstance(login.data, dict) else None
    if isinstance(access, str) and access:
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        client.defaults["HTTP_AUTHORIZATION"] = f"Bearer {access}"
    client.defaults["HTTP_X_COMPANY_ID"] = str(company.id)
    client.defaults["HTTP_X_BRANCH_ID"] = str(branch.id)
    return client


def _edge_signature(*, secret_b64: str, challenge_id: str, nonce: str, company_id: int, branch_id: int, connector_id: str) -> str:
    secret = base64.b64decode(secret_b64.encode("utf-8"), validate=True)
    msg = f"{challenge_id}.{nonce}.{company_id}.{branch_id}.{connector_id}".encode("utf-8")
    digest = hmac.new(secret, msg, hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


def _error_code(resp) -> str:
    data = resp.data if isinstance(resp.data, dict) else {}
    if isinstance(data.get("error_code"), str):
        return str(data["error_code"])
    err = data.get("error")
    if isinstance(err, dict) and isinstance(err.get("message"), str):
        return str(err["message"])
    if isinstance(data.get("detail"), str):
        return str(data["detail"])
    return ""


@pytest.mark.django_db
def test_retail_pos_end_to_end_checkout_void_and_cockpit() -> None:
    company, branch = _mk_org()
    client = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=[
            "fuel.shift.open",
            "retail.pos.session.open",
            "retail.pos.session.read",
            "retail.pos.session.close",
            "retail.pos.ticket.open",
            "retail.pos.ticket.read",
            "retail.pos.ticket.checkout",
            "retail.pos.ticket.void",
            "retail.pos.peripherals.read",
            "retail.pos.peripherals.manage",
        ],
    )

    r_shift = client.post("/api/fuel/shifts/open/", {"note": "turno-pos"}, format="json")
    assert r_shift.status_code == 201
    shift_id = int(r_shift.data["id"])

    r_session = client.post(
        "/api/retail/pos/sessions/open/",
        {"opening_amount": "50.00", "note": "apertura-pos"},
        format="json",
    )
    assert r_session.status_code == 201
    session_id = int(r_session.data["id"])
    assert r_session.data["status"] == "OPEN"
    assert r_session.data["cash_session_id"] is not None

    r_current = client.get("/api/retail/pos/sessions/current/")
    assert r_current.status_code == 200
    assert r_current.data["session"]["id"] == session_id
    assert r_current.data["session"]["status"] == "OPEN"

    open_payload = {
        "shift_id": shift_id,
        "idempotency_key": "ticket-pos-001",
        "external_ref": "POS-001",
        "customer_name": "CONSUMIDOR FINAL",
        "sale_type": "PUBLIC",
        "payment_method": "CASH",
    }
    r_ticket = client.post("/api/retail/pos/tickets/", open_payload, format="json")
    assert r_ticket.status_code == 201, r_ticket.content.decode()
    ticket_id = int(r_ticket.data["id"])
    assert r_ticket.data["status"] == "CART_OPEN"

    r_ticket_dup = client.post("/api/retail/pos/tickets/", open_payload, format="json")
    assert r_ticket_dup.status_code == 200
    assert r_ticket_dup.data["id"] == ticket_id
    assert r_ticket_dup.data["idempotency_status"] == "DUPLICATE_PROCESSED"

    r_checkout = client.post(
        f"/api/retail/pos/tickets/{ticket_id}/checkout/",
        {
            "line": {
                "product": "DIESEL",
                "volume": "10.0000",
                "volume_uom": "LITER",
                "unit_price_entered": "42.5000",
                "unit_price_uom": "PER_LITER",
                "metadata": {"pump": "P1"},
            }
        },
        format="json",
    )
    assert r_checkout.status_code == 200
    assert r_checkout.data["status"] == "CLOSED"
    assert r_checkout.data["sale_id"] is not None
    assert r_checkout.data["payment_intent_id"] != ""

    r_cockpit = client.get("/api/retail/pos/cockpit/")
    assert r_cockpit.status_code == 200
    assert r_cockpit.data["session"]["status"] == "OPEN"
    assert int(r_cockpit.data["tickets"]["closed"]) >= 1

    r_void = client.post(f"/api/retail/pos/voids/{ticket_id}/", {"reason": "CUSTOMER_VOID"}, format="json")
    assert r_void.status_code == 200
    assert r_void.data["status"] == "VOIDED"
    assert r_void.data["void_reason"] == "CUSTOMER_VOID"

    r_close = client.post(
        f"/api/retail/pos/sessions/{session_id}/close/",
        {"counted_amount": "50.00", "note": "cierre-pos"},
        format="json",
    )
    assert r_close.status_code == 200
    assert r_close.data["status"] == "CLOSED"

    session = PosSession.objects.get(id=session_id)
    assert session.status == PosSessionStatus.CLOSED
    ticket = PosTicket.objects.get(id=ticket_id)
    assert ticket.status == PosTicketStatus.VOIDED

    emitted = set(OutboxEvent.objects.filter(source_module="POS").values_list("event_type", flat=True))
    assert "POSSessionOpened" in emitted
    assert "POSTicketOpened" in emitted
    assert "POSPaymentCaptured" in emitted
    assert "POSTicketClosed" in emitted
    assert "POSVoidRequested" in emitted
    assert "POSSessionClosed" in emitted


@pytest.mark.django_db
def test_retail_pos_peripherals_upsert_and_list() -> None:
    company, branch = _mk_org()
    client = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=["retail.pos.peripherals.read", "retail.pos.peripherals.manage"],
    )

    r_upsert = client.post(
        "/api/retail/pos/peripherals/status/",
        {
            "connector_id": "edge-001",
            "connector_version": "0.1.0",
            "device_key": "printer-01",
            "device_kind": "THERMAL_PRINTER",
            "capability_level": "supported",
            "status": "ONLINE",
            "metadata": {"driver": "escpos"},
        },
        format="json",
    )
    assert r_upsert.status_code == 200
    row_id = int(r_upsert.data["id"])
    assert r_upsert.data["status"] == "ONLINE"

    r_list = client.get("/api/retail/pos/peripherals/status/")
    assert r_list.status_code == 200
    assert r_list.data["count"] == 1
    row = r_list.data["results"][0]
    assert int(row["id"]) == row_id
    assert row["device_key"] == "printer-01"
    assert row["capability_level"] == "supported"

    r_upsert_2 = client.post(
        "/api/retail/pos/peripherals/status/",
        {
            "connector_id": "edge-001",
            "connector_version": "0.1.1",
            "device_key": "printer-01",
            "device_kind": "THERMAL_PRINTER",
            "capability_level": "experimental",
            "status": "DEGRADED",
            "metadata": {"driver": "escpos", "paper": "low"},
        },
        format="json",
    )
    assert r_upsert_2.status_code == 200
    assert int(r_upsert_2.data["id"]) == row_id
    assert r_upsert_2.data["status"] == "DEGRADED"


@pytest.mark.django_db
@override_settings(
    POS_EDGE_CONNECTOR_SHARED_SECRET=base64.b64encode(b"edge-secret").decode("utf-8"),
    POS_EDGE_CHALLENGE_TTL_SEC=120,
    POS_EDGE_SESSION_TTL_SEC=600,
)
def test_retail_pos_edge_handshake_and_capability_registry() -> None:
    company, branch = _mk_org()
    client = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=["retail.pos.peripherals.read", "retail.pos.peripherals.manage"],
    )

    r_challenge = client.post(
        "/api/retail/pos/peripherals/edge/challenge/",
        {
            "connector_id": "edge-local-1",
            "connector_version": "0.2.0",
            "metadata": {"os": "linux"},
        },
        format="json",
    )
    assert r_challenge.status_code == 201
    challenge_id = str(r_challenge.data["challenge_id"])
    nonce = str(r_challenge.data["nonce"])

    signature = _edge_signature(
        secret_b64=base64.b64encode(b"edge-secret").decode("utf-8"),
        challenge_id=challenge_id,
        nonce=nonce,
        company_id=int(company.id),
        branch_id=int(branch.id),
        connector_id="edge-local-1",
    )

    r_handshake = client.post(
        "/api/retail/pos/peripherals/edge/handshake/",
        {
            "challenge_id": challenge_id,
            "connector_id": "edge-local-1",
            "connector_version": "0.2.0",
            "signature": signature,
            "capability_registry": {"THERMAL_PRINTER": "supported"},
            "devices": [
                {
                    "device_key": "printer-main",
                    "device_kind": "THERMAL_PRINTER",
                    "capability_level": "supported",
                    "status": "ONLINE",
                    "metadata": {"driver": "escpos"},
                },
                {
                    "device_key": "scanner-main",
                    "device_kind": "SCANNER",
                    "capability_level": "experimental",
                    "status": "DEGRADED",
                    "metadata": {"driver": "usb-hid"},
                },
            ],
            "metadata": {"site": "fuel-branch-1"},
        },
        format="json",
    )
    assert r_handshake.status_code == 201, r_handshake.content.decode()
    assert r_handshake.data["status"] == "ACTIVE"
    assert int(r_handshake.data["devices_synced"]) == 2
    assert r_handshake.data["capability_registry"]["THERMAL_PRINTER"] == "supported"
    assert r_handshake.data["capability_registry"]["SCANNER"] == "experimental"

    r_cap = client.get("/api/retail/pos/peripherals/capabilities/")
    assert r_cap.status_code == 200
    assert r_cap.data["count"] == 2
    assert r_cap.data["registry"]["THERMAL_PRINTER"] == "supported"
    assert r_cap.data["registry"]["SCANNER"] == "experimental"
    assert r_cap.data["session"]["status"] == "ACTIVE"
    assert r_cap.data["session"]["connector_id"] == "edge-local-1"

    r_replay = client.post(
        "/api/retail/pos/peripherals/edge/handshake/",
        {
            "challenge_id": challenge_id,
            "connector_id": "edge-local-1",
            "connector_version": "0.2.0",
            "signature": signature,
        },
        format="json",
    )
    assert r_replay.status_code == 409
    assert _error_code(r_replay) == "REPLAY_DETECTED"


@pytest.mark.django_db
@override_settings(
    POS_EDGE_CONNECTOR_SHARED_SECRET=base64.b64encode(b"edge-secret").decode("utf-8"),
)
def test_retail_pos_edge_handshake_rejects_bad_signature() -> None:
    company, branch = _mk_org()
    client = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=["retail.pos.peripherals.read", "retail.pos.peripherals.manage"],
    )

    r_challenge = client.post(
        "/api/retail/pos/peripherals/edge/challenge/",
        {
            "connector_id": "edge-local-2",
            "connector_version": "0.2.0",
        },
        format="json",
    )
    assert r_challenge.status_code == 201
    challenge_id = str(r_challenge.data["challenge_id"])

    r_handshake = client.post(
        "/api/retail/pos/peripherals/edge/handshake/",
        {
            "challenge_id": challenge_id,
            "connector_id": "edge-local-2",
            "connector_version": "0.2.0",
            "signature": base64.b64encode(b"bad-signature").decode("utf-8"),
        },
        format="json",
    )
    assert r_handshake.status_code == 401
    assert _error_code(r_handshake) == "BAD_SIGNATURE"


@pytest.mark.django_db
def test_retail_pos_checkout_compensation_retry_flow(monkeypatch) -> None:
    company, branch = _mk_org()
    client = _client_with_perms(
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

    r_shift = client.post("/api/fuel/shifts/open/", {"note": "turno-comp"}, format="json")
    assert r_shift.status_code == 201
    shift_id = int(r_shift.data["id"])

    r_session = client.post(
        "/api/retail/pos/sessions/open/",
        {"opening_amount": "10.00", "note": "apertura-comp"},
        format="json",
    )
    assert r_session.status_code == 201

    r_ticket = client.post(
        "/api/retail/pos/tickets/",
        {"shift_id": shift_id, "idempotency_key": "ticket-comp-1", "payment_method": "CASH"},
        format="json",
    )
    assert r_ticket.status_code == 201
    ticket_id = int(r_ticket.data["id"])

    attempts = {"count": 0}
    real_create_sale = fuel_services.create_sale

    def flaky_create_sale(*args, **kwargs):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RuntimeError("forced-create-sale-failure")
        return real_create_sale(*args, **kwargs)

    monkeypatch.setattr("apps.modulos.retail_pos.services.create_sale", flaky_create_sale)

    r_checkout = client.post(
        f"/api/retail/pos/tickets/{ticket_id}/checkout/",
        {
            "line": {
                "product": "DIESEL",
                "volume": "3.0000",
                "volume_uom": "LITER",
                "unit_price_entered": "40.0000",
                "unit_price_uom": "PER_LITER",
                "metadata": {"source": "comp-test"},
            }
        },
        format="json",
    )
    assert r_checkout.status_code == 409
    assert _error_code(r_checkout) == "POS_COMPENSATION_PENDING"

    pending = PosTicket.objects.get(id=ticket_id)
    assert pending.status == PosTicketStatus.CHECKOUT_PENDING
    assert pending.compensation_pending is True
    assert int(pending.compensation_attempts) == 1
    assert pending.compensation_next_retry_at is not None
    assert "forced-create-sale-failure" in pending.compensation_last_error

    r_retry = client.post(
        f"/api/retail/pos/tickets/{ticket_id}/compensate/retry/",
        {"reason": "manual-retry"},
        format="json",
    )
    assert r_retry.status_code == 200, r_retry.content.decode()
    assert r_retry.data["status"] == "CLOSED"
    assert r_retry.data["compensation_pending"] is False
    assert int(r_retry.data["compensation_attempts"]) >= 1

    recovered = PosTicket.objects.get(id=ticket_id)
    assert recovered.status == PosTicketStatus.CLOSED
    assert recovered.compensation_pending is False
    assert recovered.compensation_next_retry_at is None
    assert recovered.payment_intent_id is not None
    assert recovered.sale_id is not None


@pytest.mark.django_db
def test_retail_pos_compensation_retry_error_codes() -> None:
    company, branch = _mk_org()
    client = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=[
            "fuel.shift.open",
            "retail.pos.session.open",
            "retail.pos.ticket.open",
            "retail.pos.ticket.checkout",
        ],
    )

    r_shift = client.post("/api/fuel/shifts/open/", {"note": "turno-codes"}, format="json")
    assert r_shift.status_code == 201
    shift_id = int(r_shift.data["id"])

    r_session = client.post("/api/retail/pos/sessions/open/", {"opening_amount": "15.00"}, format="json")
    assert r_session.status_code == 201

    r_ticket = client.post(
        "/api/retail/pos/tickets/",
        {"shift_id": shift_id, "idempotency_key": "ticket-codes-1", "payment_method": "CASH"},
        format="json",
    )
    assert r_ticket.status_code == 201
    ticket_id = int(r_ticket.data["id"])

    # Retry sin estado CHECKOUT_PENDING debe devolver código estable de schema.
    r_retry_schema = client.post(
        f"/api/retail/pos/tickets/{ticket_id}/compensate/retry/",
        {"reason": "manual-schema"},
        format="json",
    )
    assert r_retry_schema.status_code == 409
    assert _error_code(r_retry_schema) == "POS_SCHEMA_INVALID"

    # Ticket fuera de alcance/scope debe devolver código estable.
    r_retry_scope = client.post(
        "/api/retail/pos/tickets/999999/compensate/retry/",
        {"reason": "manual-scope"},
        format="json",
    )
    assert r_retry_scope.status_code == 404
    assert _error_code(r_retry_scope) == "POS_INVALID_SCOPE"


@pytest.mark.django_db
def test_run_pos_compensation_cycle_command_with_scope_filters(monkeypatch) -> None:
    company, branch = _mk_org()
    client = _client_with_perms(
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

    r_shift = client.post("/api/fuel/shifts/open/", {"note": "turno-cycle"}, format="json")
    assert r_shift.status_code == 201
    shift_id = int(r_shift.data["id"])

    r_session = client.post(
        "/api/retail/pos/sessions/open/",
        {"opening_amount": "20.00", "note": "apertura-cycle"},
        format="json",
    )
    assert r_session.status_code == 201

    r_ticket = client.post(
        "/api/retail/pos/tickets/",
        {"shift_id": shift_id, "idempotency_key": "ticket-cycle-1", "payment_method": "CASH"},
        format="json",
    )
    assert r_ticket.status_code == 201
    ticket_id = int(r_ticket.data["id"])

    attempts = {"count": 0}
    real_create_sale = fuel_services.create_sale

    def flaky_create_sale(*args, **kwargs):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RuntimeError("forced-cycle-failure")
        return real_create_sale(*args, **kwargs)

    monkeypatch.setattr("apps.modulos.retail_pos.services.create_sale", flaky_create_sale)

    r_checkout = client.post(
        f"/api/retail/pos/tickets/{ticket_id}/checkout/",
        {
            "line": {
                "product": "DIESEL",
                "volume": "4.0000",
                "volume_uom": "LITER",
                "unit_price_entered": "39.0000",
                "unit_price_uom": "PER_LITER",
            }
        },
        format="json",
    )
    assert r_checkout.status_code == 409
    assert _error_code(r_checkout) == "POS_COMPENSATION_PENDING"

    pending = PosTicket.objects.get(id=ticket_id)
    assert pending.status == PosTicketStatus.CHECKOUT_PENDING
    assert pending.compensation_pending is True
    previous_attempts = int(pending.compensation_attempts)
    pending.compensation_next_retry_at = pending.updated_at - timedelta(minutes=5)
    pending.save(update_fields=["compensation_next_retry_at", "updated_at"])

    stdout = io.StringIO()
    call_command(
        "run_pos_compensation_cycle",
        company_id=int(company.id),
        branch_id=int(branch.id),
        limit=20,
        stdout=stdout,
    )
    payload = json.loads(stdout.getvalue().strip())
    assert int(payload["attempted"]) >= 1
    assert int(payload["succeeded"]) + int(payload["failed"]) + int(payload["still_pending"]) >= 1
    assert int(payload["company_id"]) == int(company.id)
    assert int(payload["branch_id"]) == int(branch.id)

    recovered = PosTicket.objects.get(id=ticket_id)
    assert int(recovered.compensation_attempts) >= previous_attempts
    if recovered.status == PosTicketStatus.CLOSED:
        assert recovered.compensation_pending is False
