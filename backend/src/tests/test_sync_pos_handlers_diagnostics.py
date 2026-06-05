from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.kernels.payments.models import PaymentIntent
from apps.modulos.iam.models import OrgUnit, UserMembership
from apps.modulos.rbac.models import Permission, Role, RoleAssignment, RolePermission
from apps.modulos.retail_pos.models import PosSession, PosSessionStatus, PosTicket, PosTicketStatus
from apps.modulos.sync_engine import handlers_pos
from apps.modulos.sync_engine.errors import SyncRejectError

User = get_user_model()


def _mk_scope() -> tuple[OrgUnit, OrgUnit]:
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="H")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="C", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name="B", parent=company)
    return company, branch


def _client_with_perms(*, company: OrgUnit, branch: OrgUnit, perm_codes: list[str]) -> tuple[APIClient, object]:
    token = uuid.uuid4().hex[:10]
    user = User.objects.create_user(username=f"pos_diag_{token}", email=f"pos_diag_{token}@test.local", password="pass12345")
    UserMembership.objects.create(user=user, org_unit=company, is_active=True)
    UserMembership.objects.create(user=user, org_unit=branch, is_active=True)
    role = Role.objects.create(name=f"role_{uuid.uuid4().hex[:8]}", is_active=True)
    for code in perm_codes:
        perm, _ = Permission.objects.get_or_create(code=code, defaults={"description": code, "is_active": True})
        RolePermission.objects.get_or_create(role=role, permission=perm)
    RoleAssignment.objects.create(user=user, role=role, org_unit=company, is_active=True)
    RoleAssignment.objects.create(user=user, role=role, org_unit=branch, is_active=True)

    client = APIClient(raise_request_exception=True)
    login = client.post(
        "/api/auth/login/",
        {"username": user.username, "password": "pass12345"},
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


def _request(company: OrgUnit, branch: OrgUnit | None):
    return SimpleNamespace(
        company=company,
        branch=branch,
        META={"REMOTE_ADDR": "127.0.0.1", "HTTP_USER_AGENT": "pytest"},
        path="/api/sync/batch/",
        method="POST",
        request_id="pytest-sync-pos",
    )


def _ctx(*, request, company: OrgUnit, branch: OrgUnit | None, actor) -> dict:
    return {
        "request": request,
        "company_id": company.id,
        "branch_id": branch.id if branch else None,
        "command_id": str(uuid.uuid4()),
        "actor_user": actor,
    }


def _open_shift_session_ticket(*, client: APIClient, payment_method: str = "CASH") -> tuple[int, int, int]:
    shift = client.post("/api/fuel/shifts/open/", {"note": "pos-handler-diag"}, format="json")
    assert shift.status_code == 201
    session = client.post(
        "/api/retail/pos/sessions/open/",
        {"opening_amount": "30.00", "note": "pos-handler-diag"},
        format="json",
    )
    assert session.status_code == 201
    ticket = client.post(
        "/api/retail/pos/tickets/",
        {"shift_id": int(shift.data["id"]), "idempotency_key": f"ticket-{uuid.uuid4()}", "payment_method": payment_method},
        format="json",
    )
    assert ticket.status_code == 201
    return int(shift.data["id"]), int(session.data["id"]), int(ticket.data["id"])


def _checkout_ticket(*, client: APIClient, ticket_id: int) -> None:
    checkout = client.post(
        f"/api/retail/pos/tickets/{ticket_id}/checkout/",
        {
            "line": {
                "product": "DIESEL",
                "volume": "2.0000",
                "volume_uom": "LITER",
                "unit_price_entered": "40.0000",
                "unit_price_uom": "PER_LITER",
            }
        },
        format="json",
    )
    assert checkout.status_code == 200, checkout.content.decode()
    assert checkout.data["status"] == PosTicketStatus.CLOSED


@pytest.mark.django_db
def test_pos_handlers_payment_intent_is_idempotent_and_captures() -> None:
    company, branch = _mk_scope()
    client, actor = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=["fuel.shift.open", "retail.pos.session.open", "retail.pos.ticket.open"],
    )
    _, _, ticket_id = _open_shift_session_ticket(client=client, payment_method="TRANSFER")
    req = _request(company, branch)

    first = handlers_pos.handle_pos_payment_intent(
        _ctx(request=req, company=company, branch=branch, actor=actor),
        {"ticket_id": ticket_id, "amount": "80.00", "currency": "NIO", "provider_txn_id": "txn-1"},
    )
    payment_id = first["refs"]["payment_id"]
    intent = PaymentIntent.objects.get(payment_id=payment_id)
    assert intent.status == PaymentIntent.Status.CAPTURED
    assert intent.amount == Decimal("80.00")

    second = handlers_pos.handle_pos_payment_intent(
        _ctx(request=req, company=company, branch=branch, actor=actor),
        {"ticket_id": ticket_id, "amount": "999.00", "currency": "NIO", "provider_txn_id": "txn-ignored"},
    )
    assert second["refs"]["payment_id"] == payment_id
    assert PaymentIntent.objects.filter(payment_id=payment_id).count() == 1


@pytest.mark.django_db
def test_pos_handlers_void_and_cash_count_update_operational_state() -> None:
    company, branch = _mk_scope()
    client, actor = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=[
            "fuel.shift.open",
            "retail.pos.session.open",
            "retail.pos.session.close",
            "retail.pos.ticket.open",
            "retail.pos.ticket.checkout",
            "retail.pos.ticket.void",
        ],
    )
    _, session_id, ticket_id = _open_shift_session_ticket(client=client, payment_method="CASH")
    _checkout_ticket(client=client, ticket_id=ticket_id)
    req = _request(company, branch)

    voided = handlers_pos.handle_pos_void(
        _ctx(request=req, company=company, branch=branch, actor=actor),
        {"ticket_id": ticket_id, "reason": "SYNC_VOID"},
    )
    assert voided["refs"]["status"] == PosTicketStatus.VOIDED
    ticket = PosTicket.objects.get(id=ticket_id)
    assert ticket.status == PosTicketStatus.VOIDED
    assert ticket.void_reason == "SYNC_VOID"

    closed = handlers_pos.handle_pos_cash_count(
        _ctx(request=req, company=company, branch=branch, actor=actor),
        {"session_id": session_id, "counted_amount": "25.00", "note": "sync close"},
    )
    assert closed["refs"]["status"] == PosSessionStatus.CLOSED
    session = PosSession.objects.get(id=session_id)
    assert session.status == PosSessionStatus.CLOSED
    assert session.difference_amount == Decimal("-5.00")


@pytest.mark.django_db
def test_pos_handlers_reject_actor_scope_and_schema_before_side_effects() -> None:
    company, branch = _mk_scope()
    other_holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="H2")
    other_company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="C2", parent=other_holding)
    actor = User.objects.create_user(username="pos_actor_scope", email="pos_actor_scope@test.local", password="x")
    req = _request(company, branch)

    with pytest.raises(SyncRejectError) as exc:
        handlers_pos.handle_pos_payment_intent(
            _ctx(request=req, company=company, branch=None, actor=actor),
            {"ticket_id": 1, "amount": "1.00"},
        )
    assert exc.value.reason_code == "POS_INVALID_SCOPE"
    assert exc.value.details == {"branch_id": "required"}

    with pytest.raises(SyncRejectError) as exc:
        handlers_pos.handle_pos_payment_intent(
            {
                "request": req,
                "company_id": other_company.id,
                "branch_id": branch.id,
                "command_id": str(uuid.uuid4()),
                "actor_user": actor,
            },
            {"ticket_id": 1, "amount": "1.00"},
        )
    assert exc.value.reason_code == "POS_INVALID_SCOPE"
    # Current contract reports a cross-company branch mismatch as an unknown branch.
    assert exc.value.details == {"branch_id": "unknown"}

    with pytest.raises(SyncRejectError) as exc:
        handlers_pos.handle_pos_payment_intent(
            _ctx(request=req, company=company, branch=branch, actor=SimpleNamespace(is_authenticated=False)),
            {"ticket_id": 1, "amount": "1.00"},
        )
    assert exc.value.reason_code == "POS_ACTOR_REQUIRED"

    with pytest.raises(SyncRejectError) as exc:
        handlers_pos.handle_pos_payment_intent(
            _ctx(request=req, company=company, branch=branch, actor=actor),
            {"ticket_id": "bad", "amount": "1.00"},
        )
    assert exc.value.reason_code == "POS_SCHEMA_INVALID"
    assert exc.value.details == {"ticket_id": "invalid"}

    with pytest.raises(SyncRejectError) as exc:
        handlers_pos.handle_pos_payment_intent(
            _ctx(request=req, company=company, branch=branch, actor=actor),
            {"ticket_id": 999999, "amount": "not-decimal"},
        )
    assert exc.value.reason_code == "POS_INVALID_SCOPE"
