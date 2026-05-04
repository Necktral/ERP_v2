from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.kernels.payments.models import CashMovement, CashSession
from apps.kernels.payments.services import PaymentsDomainError
from apps.modulos.audit.models import AuditEvent
from apps.modulos.iam.models import OrgUnit, UserMembership
from apps.modulos.integration.models import OutboxEvent
from apps.modulos.rbac.models import Permission, Role, RoleAssignment, RolePermission

User = get_user_model()


def _mk_org():
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="H")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="C", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name="B", parent=company)
    return company, branch


def _client_with_perms(*, company: OrgUnit, branch: OrgUnit, perm_codes: list[str]) -> APIClient:
    username = f"u_{uuid.uuid4().hex[:10]}"
    user = User.objects.create_user(username=username, email="payments@test.com", password="pass12345")

    UserMembership.objects.create(user=user, org_unit=company, is_active=True)
    UserMembership.objects.create(user=user, org_unit=branch, is_active=True)

    role = Role.objects.create(name=f"role_{uuid.uuid4().hex[:8]}", is_active=True)
    for code in perm_codes:
        perm, _ = Permission.objects.get_or_create(code=code, defaults={"description": code, "is_active": True})
        RolePermission.objects.get_or_create(role=role, permission=perm)

    RoleAssignment.objects.create(user=user, role=role, org_unit=company, is_active=True)
    RoleAssignment.objects.create(user=user, role=role, org_unit=branch, is_active=True)

    client = APIClient()
    resp = client.post(
        "/api/auth/login/",
        {"username": username, "password": "pass12345"},
        format="json",
        HTTP_X_AUTH_TRANSPORT="header",
    )
    assert resp.status_code == 200
    access = resp.data.get("access") if isinstance(resp.data, dict) else None
    if isinstance(access, str) and access:
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        client.defaults["HTTP_AUTHORIZATION"] = f"Bearer {access}"
    client.defaults["HTTP_X_AUTH_TRANSPORT"] = "header"
    client.defaults["HTTP_X_COMPANY_ID"] = str(company.id)
    client.defaults["HTTP_X_BRANCH_ID"] = str(branch.id)
    return client


@pytest.mark.django_db
def test_payments_intent_cash_session_and_outbox():
    company, branch = _mk_org()
    client = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=[
            "payments.intent.read",
            "payments.intent.create",
            "payments.cash_session.read",
            "payments.cash_session.open",
            "payments.cash_session.close",
            "payments.cash_movement.create",
        ],
    )

    idem_key = f"intent-{uuid.uuid4().hex[:8]}"
    r = client.post(
        "/api/payments/intents/",
        {"amount": "100.00", "currency": "NIO", "idempotency_key": idem_key, "external_ref": "INV-1"},
        format="json",
    )
    assert r.status_code == 201
    assert r.data["idempotent"] is False
    payment_id = r.data["payment_id"]

    r2 = client.post(
        "/api/payments/intents/",
        {"amount": "100.00", "currency": "NIO", "idempotency_key": idem_key, "external_ref": "INV-1"},
        format="json",
    )
    assert r2.status_code == 200
    assert r2.data["idempotent"] is True
    assert r2.data["payment_id"] == payment_id

    ropen = client.post("/api/payments/cash-sessions/open/", {"opening_amount": "50.00"}, format="json")
    assert ropen.status_code == 201
    session_id = ropen.data["id"]

    rmov = client.post(
        f"/api/payments/cash-sessions/{session_id}/movements/",
        {"movement_type": "INCOME", "amount": "25.00", "reference": "ticket-1"},
        format="json",
    )
    assert rmov.status_code == 201
    assert rmov.data["idempotent"] is False

    rclose = client.post(
        f"/api/payments/cash-sessions/{session_id}/close/",
        {"counted_amount": "75.00"},
        format="json",
    )
    assert rclose.status_code == 200
    assert rclose.data["status"] == "CLOSED"

    emitted = set(
        OutboxEvent.objects.filter(source_module="PAYMENTS").values_list("event_type", flat=True)
    )
    assert "PaymentIntentCreated" in emitted
    assert "CashSessionOpened" in emitted
    assert "CashMovementPosted" in emitted
    assert "CashSessionClosed" in emitted


@pytest.mark.django_db
def test_payments_close_returns_404_for_nonexistent_session():
    company, branch = _mk_org()
    client = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=["payments.cash_session.close"],
    )

    resp = client.post(
        "/api/payments/cash-sessions/999999/close/",
        {"counted_amount": "0.00"},
        format="json",
    )
    assert resp.status_code == 404


@pytest.mark.django_db
def test_payments_open_returns_409_when_session_is_already_open():
    company, branch = _mk_org()
    client = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=["payments.cash_session.open"],
    )

    first = client.post("/api/payments/cash-sessions/open/", {"opening_amount": "10.00"}, format="json")
    assert first.status_code == 201
    second = client.post("/api/payments/cash-sessions/open/", {"opening_amount": "10.00"}, format="json")
    assert second.status_code == 409


@pytest.mark.django_db
def test_payments_movement_returns_409_for_closed_session_state():
    company, branch = _mk_org()
    client = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=["payments.cash_movement.create"],
    )
    user = User.objects.create_user(username=f"closed_sess_{uuid.uuid4().hex[:8]}", password="pass12345")

    session = CashSession.objects.create(
        company=company,
        branch=branch,
        opened_by=user,
        status=CashSession.Status.CLOSED,
        opening_amount="0.00",
        expected_amount="0.00",
        counted_amount="0.00",
        difference_amount="0.00",
        closed_by=user,
    )

    resp = client.post(
        f"/api/payments/cash-sessions/{session.id}/movements/",
        {"movement_type": "INCOME", "amount": "5.00"},
        format="json",
    )
    assert resp.status_code == 409


@pytest.mark.django_db
def test_payments_domain_error_fallback_stays_400_for_unknown_subtype(monkeypatch, caplog):
    company, branch = _mk_org()
    client = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=["payments.cash_session.open"],
    )

    class UnknownPaymentsDomainError(PaymentsDomainError):
        pass

    def _raise_unknown(*args, **kwargs):
        raise UnknownPaymentsDomainError("unknown")

    caplog.set_level("WARNING", logger="apps.kernels.payments.views")
    monkeypatch.setattr("apps.kernels.payments.views.open_cash_session", _raise_unknown)
    resp = client.post("/api/payments/cash-sessions/open/", {"opening_amount": "1.00"}, format="json")
    assert resp.status_code == 400
    assert any(
        bool(getattr(record, "payments_error_unclassified", False))
        and str(getattr(record, "error_class", "")) == "UnknownPaymentsDomainError"
        and str(getattr(record, "view_name", "")) == "CashSessionOpenView.post"
        for record in caplog.records
    )


@pytest.mark.django_db
def test_payments_cash_movement_api_is_idempotent_and_audited():
    company, branch = _mk_org()
    client = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=[
            "payments.cash_session.open",
            "payments.cash_movement.create",
        ],
    )

    opened = client.post("/api/payments/cash-sessions/open/", {"opening_amount": "50.00"}, format="json")
    assert opened.status_code == 201
    session_id = opened.data["id"]
    payload = {
        "movement_type": "INCOME",
        "amount": "25.00",
        "reference": "ticket-1",
        "reason": "sale",
        "idempotency_key": "cash-api-1",
    }

    first = client.post(f"/api/payments/cash-sessions/{session_id}/movements/", payload, format="json")
    second = client.post(f"/api/payments/cash-sessions/{session_id}/movements/", payload, format="json")
    mismatch = client.post(
        f"/api/payments/cash-sessions/{session_id}/movements/",
        {**payload, "amount": "30.00"},
        format="json",
    )

    session = CashSession.objects.get(id=session_id)
    assert first.status_code == 201
    assert first.data["idempotent"] is False
    assert second.status_code == 200
    assert second.data["idempotent"] is True
    assert second.data["id"] == first.data["id"]
    assert mismatch.status_code == 409
    assert CashMovement.objects.filter(session=session, idempotency_key="cash-api-1").count() == 1
    assert session.expected_amount == Decimal("75.00")
    movement_outbox_events = [
        event
        for event in OutboxEvent.objects.filter(source_module="PAYMENTS", event_type="CashMovementPosted")
        if event.payload.get("data", {}).get("movement_id") == first.data["id"]
    ]
    assert len(movement_outbox_events) == 1
    audit_event = AuditEvent.objects.get(
        event_type="PAYMENTS_CASH_MOVEMENT_POSTED",
        subject_type="CASH_MOVEMENT",
        subject_id=str(first.data["id"]),
    )
    assert audit_event.reason_code == "OK"
    assert audit_event.metadata["idempotency_key"] == "cash-api-1"


@pytest.mark.django_db
def test_payments_cash_movement_api_without_idempotency_key_preserves_duplicate_behavior():
    company, branch = _mk_org()
    client = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=[
            "payments.cash_session.open",
            "payments.cash_movement.create",
        ],
    )

    opened = client.post("/api/payments/cash-sessions/open/", {"opening_amount": "10.00"}, format="json")
    assert opened.status_code == 201
    session_id = opened.data["id"]
    payload = {"movement_type": "INCOME", "amount": "5.00", "reference": "manual"}

    first = client.post(f"/api/payments/cash-sessions/{session_id}/movements/", payload, format="json")
    second = client.post(f"/api/payments/cash-sessions/{session_id}/movements/", payload, format="json")

    session = CashSession.objects.get(id=session_id)
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.data["idempotent"] is False
    assert second.data["idempotent"] is False
    assert first.data["id"] != second.data["id"]
    assert CashMovement.objects.filter(session=session, idempotency_key="").count() == 2
    assert session.expected_amount == Decimal("20.00")
