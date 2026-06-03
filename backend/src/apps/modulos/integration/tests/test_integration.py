"""
Tests del módulo integration — patrón outbox/inbox transaccional.

Servicios: publish_outbox_event (payload canónico + normalización de eventos de
contrato operacional/contable), inbox idempotente, mark sent/retry con backoff y
transición a FAILED, salud del outbox y dispatch (envío, reintento, exclusión de
eventos de contrato con sender noop, respeto del next_attempt_at).
API: health pública, listados con permiso rbac y mark-sent / ack.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.modulos.iam.models import OrgUnit, UserMembership
from apps.modulos.integration.models import InboxEvent, OutboxEvent
from apps.modulos.integration.services import (
    collect_outbox_health,
    create_or_get_inbox_event,
    dispatch_outbox_events,
    mark_outbox_event_retry,
    mark_outbox_event_sent,
    publish_outbox_event,
)
from apps.modulos.rbac.models import Permission, Role, RoleAssignment, RolePermission

User = get_user_model()


def _mk_org():
    s = uuid.uuid4().hex[:6]
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name=f"H_{s}")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name=f"C_{s}", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name=f"B_{s}", parent=company)
    return company, branch


def _mk_user(prefix="int"):
    username = f"{prefix}_{uuid.uuid4().hex[:8]}"
    return User.objects.create_user(username=username, email=f"{username}@test.local", password="pass12345")


# ---------------------------------------------------------------------------
# Servicios: publish
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_publish_outbox_event_canonical_payload():
    company, _ = _mk_org()
    ev = publish_outbox_event(
        source_module="POS",
        event_type="SaleCreated",
        payload={"x": 1},
        company=company,
        correlation_id="corr1",
    )
    assert ev.status == OutboxEvent.Status.PENDING
    assert ev.source_module == "POS"
    assert ev.company_id == company.id
    assert ev.correlation_id == "corr1"
    p = ev.payload
    assert p["schema_version"] == 1
    assert p["contract_version"] == "1.0"
    assert p["correlation_id"] == "corr1"
    assert p["causation_id"] == "corr1"  # causation hereda de correlation
    assert p["scope"] == {"company_id": company.id, "branch_id": None}
    assert p["data"] == {"x": 1}


@pytest.mark.django_db
def test_publish_normalizes_operational_contract_event():
    company, _ = _mk_org()
    ev = publish_outbox_event(
        source_module="BILLING",
        event_type="DocumentIssued",
        payload={"source_id": "S1"},
        company=company,
    )
    data = ev.payload["data"]
    for key in (
        "source_module",
        "source_type",
        "source_id",
        "accounting_status",
        "accounting_error",
        "economic_event_id",
        "journal_draft_id",
        "journal_entry_id",
    ):
        assert key in data
    assert data["source_id"] == "S1"
    assert data["economic_event_id"] is None


@pytest.mark.django_db
def test_publish_non_contract_event_payload_unchanged():
    company, _ = _mk_org()
    ev = publish_outbox_event(
        source_module="BILLING",
        event_type="SomethingElse",
        payload={"a": 1},
        company=company,
    )
    assert ev.payload["data"] == {"a": 1}


@pytest.mark.django_db
def test_publish_extracts_context_from_request():
    company, branch = _mk_org()
    user = _mk_user()
    req = SimpleNamespace(
        company=company,
        branch=branch,
        user=user,
        request_id="rid-123",
        headers={"X-Device-Id": "dev-1"},
        META={},
    )
    ev = publish_outbox_event(source_module="POS", event_type="X", payload={}, request=req)
    assert ev.company_id == company.id
    assert ev.branch_id == branch.id
    assert ev.correlation_id == "rid-123"
    assert ev.device_id == "dev-1"
    assert ev.actor_user_id == user.id
    assert ev.payload["actor"] == {"user_id": user.id}


# ---------------------------------------------------------------------------
# Servicios: inbox idempotente
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_create_or_get_inbox_event_idempotent():
    company, _ = _mk_org()
    ev = publish_outbox_event(source_module="POS", event_type="X", payload={}, company=company)
    row1, created1 = create_or_get_inbox_event(event=ev, consumer="accounting")
    assert created1 is True
    row2, created2 = create_or_get_inbox_event(event=ev, consumer="accounting")
    assert created2 is False
    assert row1.id == row2.id
    assert row1.event_id == ev.event_id
    # Distinto consumer => fila nueva.
    row3, created3 = create_or_get_inbox_event(event=ev, consumer="reporting")
    assert created3 is True
    assert row3.id != row1.id


# ---------------------------------------------------------------------------
# Servicios: mark sent / retry
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_mark_outbox_event_sent():
    company, _ = _mk_org()
    ev = publish_outbox_event(source_module="POS", event_type="X", payload={}, company=company)
    out = mark_outbox_event_sent(event=ev)
    assert out.status == OutboxEvent.Status.SENT
    assert out.published_at is not None
    assert out.attempt_count == 1
    assert out.last_error == ""


@pytest.mark.django_db
def test_mark_outbox_event_retry_sets_backoff():
    company, _ = _mk_org()
    ev = publish_outbox_event(source_module="POS", event_type="X", payload={}, company=company)
    out = mark_outbox_event_retry(event=ev, error="boom", max_attempts=5)
    assert out.status == OutboxEvent.Status.PENDING
    assert out.attempt_count == 1
    assert out.next_attempt_at is not None
    assert out.last_error == "boom"


@pytest.mark.django_db
def test_mark_outbox_event_retry_reaches_failed():
    company, _ = _mk_org()
    ev = publish_outbox_event(source_module="POS", event_type="X", payload={}, company=company)
    out = mark_outbox_event_retry(event=ev, error="x", max_attempts=1)
    assert out.status == OutboxEvent.Status.FAILED
    assert out.next_attempt_at is None
    assert out.attempt_count == 1


# ---------------------------------------------------------------------------
# Servicios: salud y dispatch
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_collect_outbox_health_counts():
    company, _ = _mk_org()
    publish_outbox_event(source_module="POS", event_type="A", payload={}, company=company)  # pending fresco
    retry_ev = publish_outbox_event(source_module="POS", event_type="A", payload={}, company=company)
    mark_outbox_event_retry(event=retry_ev, error="x", max_attempts=5)  # pending con next_attempt futuro
    failed_ev = publish_outbox_event(source_module="POS", event_type="B", payload={}, company=company)
    mark_outbox_event_retry(event=failed_ev, error="x", max_attempts=1)  # failed

    d = collect_outbox_health(source_module="POS").as_dict()
    assert d["pending_count"] == 2
    assert d["failed_count"] == 1
    assert d["retry_count"] == 1
    # Solo el pending fresco (sin next_attempt) es despachable ahora.
    assert d["dispatchable_pending_count"] == 1
    assert isinstance(d["by_source_module_event_type"], list)
    assert len(d["by_source_module_event_type"]) >= 1


@pytest.mark.django_db
def test_dispatch_sends_with_sender():
    company, _ = _mk_org()
    ev = publish_outbox_event(source_module="POS", event_type="X", payload={}, company=company)
    calls = []
    summary = dispatch_outbox_events(sender=lambda e: calls.append(e.id))
    assert summary.attempted == 1
    assert summary.sent == 1
    ev.refresh_from_db()
    assert ev.status == OutboxEvent.Status.SENT
    assert calls == [ev.id]


@pytest.mark.django_db
def test_dispatch_retry_on_sender_error():
    company, _ = _mk_org()
    ev = publish_outbox_event(source_module="POS", event_type="X", payload={}, company=company)

    def _boom(_e):
        raise RuntimeError("nope")

    summary = dispatch_outbox_events(sender=_boom, max_attempts=5)
    assert summary.attempted == 1
    assert summary.retried == 1
    ev.refresh_from_db()
    assert ev.status == OutboxEvent.Status.PENDING
    assert ev.attempt_count == 1
    assert "nope" in ev.last_error


@pytest.mark.django_db
def test_dispatch_noop_sender_skips_operational_contract_unless_allowed():
    company, _ = _mk_org()
    ev = publish_outbox_event(source_module="BILLING", event_type="DocumentIssued", payload={}, company=company)
    # sender por defecto (noop) excluye eventos de contrato contable.
    summary = dispatch_outbox_events()
    assert summary.attempted == 0
    ev.refresh_from_db()
    assert ev.status == OutboxEvent.Status.PENDING
    # con el flag explícito sí se procesan.
    summary2 = dispatch_outbox_events(allow_noop_for_operational_events=True)
    assert summary2.attempted == 1
    assert summary2.sent == 1
    ev.refresh_from_db()
    assert ev.status == OutboxEvent.Status.SENT


@pytest.mark.django_db
def test_dispatch_skips_future_next_attempt():
    company, _ = _mk_org()
    ev = publish_outbox_event(source_module="POS", event_type="X", payload={}, company=company)
    mark_outbox_event_retry(event=ev, error="x", max_attempts=5)  # next_attempt en el futuro
    summary = dispatch_outbox_events(sender=lambda e: None)
    assert summary.attempted == 0
    ev.refresh_from_db()
    assert ev.status == OutboxEvent.Status.PENDING


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

def _client_with_perms(*, company, branch, perm_codes):
    user = _mk_user("api")
    UserMembership.objects.create(user=user, org_unit=company, is_active=True)
    UserMembership.objects.create(user=user, org_unit=branch, is_active=True)
    role = Role.objects.create(name=f"role_{uuid.uuid4().hex[:8]}", is_active=True)
    for code in perm_codes:
        perm, _ = Permission.objects.get_or_create(code=code, defaults={"description": code, "is_active": True})
        RolePermission.objects.get_or_create(role=role, permission=perm)
    RoleAssignment.objects.create(user=user, role=role, org_unit=company, is_active=True)
    RoleAssignment.objects.create(user=user, role=role, org_unit=branch, is_active=True)

    client = APIClient()
    login = client.post("/api/auth/login/", {"username": user.username, "password": "pass12345"}, format="json")
    assert login.status_code == 200, login.data
    access = login.data.get("access")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    client.defaults["HTTP_X_COMPANY_ID"] = str(company.id)
    client.defaults["HTTP_X_BRANCH_ID"] = str(branch.id)
    return client


@pytest.mark.django_db
def test_health_endpoint_is_public():
    resp = APIClient().get("/api/integration/health/")
    assert resp.status_code == 200
    assert resp.data == {"ok": True, "module": "integration"}


@pytest.mark.django_db
def test_outbox_list_forbidden_without_permission():
    company, branch = _mk_org()
    client = _client_with_perms(company=company, branch=branch, perm_codes=[])
    resp = client.get("/api/integration/outbox/")
    assert resp.status_code == 403


@pytest.mark.django_db
def test_outbox_list_ok_with_permission():
    company, branch = _mk_org()
    client = _client_with_perms(company=company, branch=branch, perm_codes=["integration.outbox.read"])
    publish_outbox_event(source_module="POS", event_type="X", payload={}, company=company, branch=branch)
    resp = client.get("/api/integration/outbox/")
    assert resp.status_code == 200
    assert resp.data["count"] == 1
    assert resp.data["results"][0]["source_module"] == "POS"


@pytest.mark.django_db
def test_outbox_mark_sent_via_api():
    company, branch = _mk_org()
    client = _client_with_perms(company=company, branch=branch, perm_codes=["integration.outbox.publish"])
    ev = publish_outbox_event(source_module="POS", event_type="X", payload={}, company=company, branch=branch)
    resp = client.post(f"/api/integration/outbox/{ev.event_id}/sent/", {}, format="json")
    assert resp.status_code == 200
    assert resp.data["status"] == OutboxEvent.Status.SENT
    ev.refresh_from_db()
    assert ev.status == OutboxEvent.Status.SENT


@pytest.mark.django_db
def test_inbox_ack_via_api():
    company, branch = _mk_org()
    client = _client_with_perms(company=company, branch=branch, perm_codes=["integration.inbox.process"])
    ev = publish_outbox_event(source_module="POS", event_type="X", payload={}, company=company, branch=branch)
    inbox, _created = create_or_get_inbox_event(event=ev, consumer="accounting")
    resp = client.post(
        f"/api/integration/inbox/{inbox.id}/ack/",
        {"status": InboxEvent.Status.PROCESSED},
        format="json",
    )
    assert resp.status_code == 200
    assert resp.data["status"] == InboxEvent.Status.PROCESSED
    inbox.refresh_from_db()
    assert inbox.status == InboxEvent.Status.PROCESSED
    assert inbox.processed_at is not None
