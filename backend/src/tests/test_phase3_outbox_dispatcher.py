from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta
from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import IntegrityError
from django.test import override_settings
from django.utils import timezone

from apps.kernels.accounting.models import EconomicEvent, JournalDraft, JournalEntry
from apps.kernels.accounting.services import dispatch_accounting_outbox_events
from apps.modulos.iam.models import OrgUnit
from apps.modulos.integration.models import InboxEvent, OutboxEvent
from apps.modulos.integration.services import collect_outbox_health, dispatch_outbox_events, publish_outbox_event

User = get_user_model()


def _mk_scope():
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


def _publish_billing_invoice(*, company, branch, user=None) -> OutboxEvent:
    return publish_outbox_event(
        source_module="BILLING",
        event_type="DocumentIssued",
        payload={
            "doc_id": 9001,
            "doc_type": "INVOICE",
            "series": "T",
            "number": 1,
            "currency": "NIO",
            "subtotal": "100.00",
            "tax_total": "15.00",
            "total": "115.00",
            "is_fiscal": True,
            "fiscal_adapter_mode": "B",
        },
        company=company,
        branch=branch,
        actor_user=user,
    )


@pytest.mark.django_db
def test_outbox_dispatcher_marks_sent_on_success():
    ev = OutboxEvent.objects.create(
        source_module="CEC",
        event_type="CloseRunPackaged",
        payload={"ok": True},
    )
    fixed_now = timezone.make_aware(datetime(2026, 3, 8, 8, 0, 0))
    summary = dispatch_outbox_events(sender=lambda _: None, limit=10, now=fixed_now)
    ev.refresh_from_db()

    assert summary.attempted == 1
    assert summary.sent == 1
    assert summary.retried == 0
    assert summary.failed == 0
    assert ev.status == OutboxEvent.Status.SENT
    assert ev.attempt_count == 1
    assert ev.published_at == fixed_now


@pytest.mark.django_db
def test_outbox_dispatcher_retries_with_exponential_backoff():
    ev = OutboxEvent.objects.create(
        source_module="CEC",
        event_type="CloseRunExecuted",
        payload={"ok": True},
    )
    fixed_now = timezone.make_aware(datetime(2026, 3, 8, 9, 0, 0))

    def _fail(_):
        raise RuntimeError("temporary broker error")

    summary = dispatch_outbox_events(sender=_fail, limit=10, now=fixed_now)
    ev.refresh_from_db()

    assert summary.attempted == 1
    assert summary.sent == 0
    assert summary.retried == 1
    assert summary.failed == 0
    assert ev.status == OutboxEvent.Status.PENDING
    assert ev.attempt_count == 1
    assert ev.next_attempt_at == fixed_now + timedelta(minutes=2)
    assert "temporary broker error" in ev.last_error


@pytest.mark.django_db
def test_outbox_dispatcher_moves_to_failed_after_max_attempts():
    ev = OutboxEvent.objects.create(
        source_module="CEC",
        event_type="CloseRunExecuted",
        payload={"ok": True},
        attempt_count=1,
    )
    fixed_now = timezone.make_aware(datetime(2026, 3, 8, 10, 0, 0))

    def _fail(_):
        raise RuntimeError("still failing")

    summary = dispatch_outbox_events(sender=_fail, limit=10, now=fixed_now, max_attempts=2)
    ev.refresh_from_db()

    assert summary.attempted == 1
    assert summary.sent == 0
    assert summary.retried == 0
    assert summary.failed == 1
    assert ev.status == OutboxEvent.Status.FAILED
    assert ev.attempt_count == 2
    assert ev.next_attempt_at is None


@pytest.mark.django_db
def test_inbox_idempotency_unique_per_event_consumer():
    event_id = uuid.uuid4()
    InboxEvent.objects.create(
        event_id=event_id,
        consumer="accounting.projector",
        source_module="CEC",
        event_type="CloseRunPackaged",
        payload={"x": 1},
    )
    with pytest.raises(IntegrityError):
        InboxEvent.objects.create(
            event_id=event_id,
            consumer="accounting.projector",
            source_module="CEC",
            event_type="CloseRunPackaged",
            payload={"x": 1},
        )


@pytest.mark.django_db
def test_dispatch_outbox_command_dispatches_pending_events():
    ev = OutboxEvent.objects.create(
        source_module="CEC",
        event_type="CloseRunExecuted",
        payload={"ok": True},
    )
    stdout = StringIO()
    call_command("dispatch_outbox", limit=10, stdout=stdout)
    ev.refresh_from_db()

    assert ev.status == OutboxEvent.Status.SENT
    output = stdout.getvalue()
    assert "attempted=1" in output


@pytest.mark.django_db
def test_dispatch_outbox_leaves_operational_event_pending_without_explicit_sender():
    company, branch = _mk_scope()
    event = _publish_billing_invoice(company=company, branch=branch)

    summary = dispatch_outbox_events(limit=10, source_module="BILLING")

    event.refresh_from_db()
    assert summary.attempted == 0
    assert summary.sent == 0
    assert event.status == OutboxEvent.Status.PENDING
    assert event.attempt_count == 0
    assert event.published_at is None
    assert EconomicEvent.objects.filter(company=company, source_outbox_event_id=event.event_id).count() == 0


@pytest.mark.django_db
def test_outbox_health_reports_pending_retry_failed_and_oldest_age():
    fixed_now = timezone.make_aware(datetime(2026, 3, 8, 12, 0, 0))
    OutboxEvent.objects.create(
        source_module="BILLING",
        event_type="DocumentIssued",
        payload={"ok": True},
        occurred_at=fixed_now - timedelta(minutes=10),
    )
    OutboxEvent.objects.create(
        source_module="BILLING",
        event_type="DocumentIssued",
        payload={"ok": True},
        attempt_count=2,
        next_attempt_at=fixed_now - timedelta(minutes=1),
        occurred_at=fixed_now - timedelta(minutes=3),
    )
    OutboxEvent.objects.create(
        source_module="INVENTORY",
        event_type="InventoryMovementPosted",
        payload={"ok": True},
        status=OutboxEvent.Status.FAILED,
        attempt_count=5,
        occurred_at=fixed_now - timedelta(minutes=7),
    )

    health = collect_outbox_health(now=fixed_now)

    assert health.pending_count == 2
    assert health.dispatchable_pending_count == 2
    assert health.retry_count == 1
    assert health.failed_count == 1
    assert health.oldest_pending_age_seconds == 600
    rows = {
        (row["source_module"], row["event_type"], row["status"]): row
        for row in health.by_source_module_event_type
    }
    assert rows[("BILLING", "DocumentIssued", OutboxEvent.Status.PENDING)]["count"] == 2
    assert rows[("BILLING", "DocumentIssued", OutboxEvent.Status.PENDING)]["retry_count"] == 1
    assert rows[("INVENTORY", "InventoryMovementPosted", OutboxEvent.Status.FAILED)]["count"] == 1


@pytest.mark.django_db
def test_dispatch_outbox_health_only_is_read_only_and_json_parseable():
    fixed_now = timezone.make_aware(datetime(2026, 3, 8, 12, 30, 0))
    ev = OutboxEvent.objects.create(
        source_module="CEC",
        event_type="CloseRunExecuted",
        payload={"ok": True},
        attempt_count=1,
        last_error="previous",
        next_attempt_at=fixed_now - timedelta(minutes=1),
        occurred_at=fixed_now - timedelta(minutes=5),
    )
    before = {
        "status": ev.status,
        "attempt_count": ev.attempt_count,
        "last_error": ev.last_error,
        "next_attempt_at": ev.next_attempt_at,
        "published_at": ev.published_at,
    }

    stdout = StringIO()
    call_command("dispatch_outbox", health_only=True, json=True, stdout=stdout)
    ev.refresh_from_db()
    payload = json.loads(stdout.getvalue())

    assert payload["pending_count"] == 1
    assert payload["dispatchable_pending_count"] == 1
    assert payload["retry_count"] == 1
    assert payload["failed_count"] == 0
    assert {
        "status": ev.status,
        "attempt_count": ev.attempt_count,
        "last_error": ev.last_error,
        "next_attempt_at": ev.next_attempt_at,
        "published_at": ev.published_at,
    } == before


@pytest.mark.django_db
def test_dispatch_outbox_command_json_emits_dispatch_and_health_summary():
    OutboxEvent.objects.create(
        source_module="CEC",
        event_type="CloseRunExecuted",
        payload={"ok": True},
    )

    stdout = StringIO()
    call_command("dispatch_outbox", limit=10, json=True, stdout=stdout)
    payload = json.loads(stdout.getvalue())

    assert payload["dispatch"]["attempted"] == 1
    assert payload["dispatch"]["sent"] == 1
    assert payload["health_before"]["pending_count"] == 1
    assert payload["health_after"]["pending_count"] == 0


@pytest.mark.django_db
@override_settings(
    ACCOUNTING_POSTING_MODE="HYBRID",
    ACCOUNTING_POSTING_ENABLE_BILLING=True,
    ACCOUNTING_POSTING_ENABLE_INVENTORY=True,
    ACCOUNTING_POSTING_AUTO_POST_ON_WRITE=False,
)
def test_accounting_dispatch_links_operational_accounting_without_duplicates_or_auto_post():
    company, branch = _mk_scope()
    user = User.objects.create_user(username=f"outbox_{uuid.uuid4().hex[:8]}", password="x")
    call_command("seed_posting_rules_v1", company_id=company.id)
    event = _publish_billing_invoice(company=company, branch=branch, user=user)
    InboxEvent.objects.create(
        event_id=event.event_id,
        consumer="accounting.projector",
        source_module=event.source_module,
        event_type=event.event_type,
        payload=event.payload,
    )

    dispatch_accounting_outbox_events(limit=10, source_module="BILLING")
    event.refresh_from_db()

    assert event.status == OutboxEvent.Status.SENT
    data = event.payload["data"]
    assert data["accounting_status"] == "DRAFT_VALIDATED"
    assert EconomicEvent.objects.filter(company=company, source_outbox_event_id=event.event_id).count() == 1
    economic_event = EconomicEvent.objects.get(company=company, source_outbox_event_id=event.event_id)
    assert JournalDraft.objects.filter(economic_event=economic_event).count() == 1
    assert JournalDraft.objects.get(economic_event=economic_event).state == JournalDraft.State.VALIDATED
    assert JournalEntry.objects.filter(draft__economic_event=economic_event).count() == 0
    assert InboxEvent.objects.filter(event_id=event.event_id, consumer="accounting.projector").count() == 1

    event.status = OutboxEvent.Status.PENDING
    event.published_at = None
    event.next_attempt_at = None
    event.save(update_fields=["status", "published_at", "next_attempt_at"])
    dispatch_accounting_outbox_events(limit=10, source_module="BILLING")

    assert EconomicEvent.objects.filter(company=company, source_outbox_event_id=event.event_id).count() == 1
    assert JournalDraft.objects.filter(economic_event=economic_event).count() == 1
    assert JournalEntry.objects.filter(draft__economic_event=economic_event).count() == 0
    assert InboxEvent.objects.filter(event_id=event.event_id, consumer="accounting.projector").count() == 1


@pytest.mark.django_db
def test_dispatch_outbox_no_local_consumers_preserves_explicit_external_mode():
    company, branch = _mk_scope()
    user = User.objects.create_user(username=f"outbox_no_local_{uuid.uuid4().hex[:8]}", password="x")
    call_command("seed_posting_rules_v1", company_id=company.id)
    event = _publish_billing_invoice(company=company, branch=branch, user=user)

    call_command("dispatch_outbox", limit=10, source_module="BILLING", no_local_consumers=True, stdout=StringIO())
    event.refresh_from_db()

    assert event.status == OutboxEvent.Status.SENT
    assert EconomicEvent.objects.filter(company=company, source_outbox_event_id=event.event_id).count() == 0
    assert JournalDraft.objects.count() == 0
    assert JournalEntry.objects.count() == 0
