"""Tests de auditoría del kernel accounting (Unidad #4, sub-incremento A).

Cierra el hueco `audit=0`: cada operación sensible (approve/post/close/reverse) debe
emitir su `AuditEvent` `ACCOUNTING_*` con actor y subject (invariante #4).
"""
from __future__ import annotations

import uuid

import pytest
from django.contrib.auth import get_user_model

from apps.kernels.accounting.models import FiscalPeriod, JournalDraft, JournalEntry
from apps.kernels.accounting.services import (
    approve_journal_drafts,
    close_fiscal_period,
    link_operational_event_to_accounting,
    post_journal_drafts,
    reverse_journal_entry,
    seed_posting_rules_v1_for_company,
)
from apps.modulos.audit.models import AuditEvent
from apps.modulos.iam.models import OrgUnit
from apps.modulos.integration.models import OutboxEvent
from django.utils import timezone

User = get_user_model()


def _mk_scope():
    s = uuid.uuid4().hex[:6]
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name=f"H_{s}")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name=f"C_{s}", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name=f"B_{s}", parent=company)
    return company, branch


def _actor():
    name = f"u_{uuid.uuid4().hex[:8]}"
    return User.objects.create_user(username=name, email=f"{name}@test.com", password="x")


def _billing_outbox(*, company, branch):
    return OutboxEvent.objects.create(
        source_module="BILLING",
        event_type="DocumentIssued",
        company=company,
        branch=branch,
        payload={"data": {"doc_type": "INVOICE", "total": "115.00", "subtotal": "100.00", "tax_total": "15.00"}},
        occurred_at=timezone.now(),
    )


def _draft_for(*, company, branch):
    seed_posting_rules_v1_for_company(company=company)
    event = _billing_outbox(company=company, branch=branch)
    link = link_operational_event_to_accounting(outbox_event=event)
    return link


def _audit(event_type, subject_id):
    return AuditEvent.objects.filter(event_type=event_type, subject_id=str(subject_id))


@pytest.mark.django_db
def test_approve_emits_audit():
    company, branch = _mk_scope()
    actor = _actor()
    link = _draft_for(company=company, branch=branch)

    approve_journal_drafts(company_id=company.id, actor_user=actor)

    ev = _audit("ACCOUNTING_JOURNAL_APPROVED", link.journal_draft_id).first()
    assert ev is not None
    assert ev.subject_type == "JOURNAL_DRAFT"
    assert ev.after_snapshot.get("state") == JournalDraft.State.APPROVED_FOR_POSTING


@pytest.mark.django_db
def test_post_emits_audit():
    company, branch = _mk_scope()
    actor = _actor()
    link = _draft_for(company=company, branch=branch)

    post_journal_drafts(company_id=company.id, auto_approve=True, allow_same_approver=True, actor_user=actor)

    entry = JournalEntry.objects.get(draft_id=link.journal_draft_id)
    ev = _audit("ACCOUNTING_JOURNAL_POSTED", entry.id).first()
    assert ev is not None
    assert ev.subject_type == "JOURNAL_ENTRY"
    assert ev.after_snapshot.get("is_posted") is True


@pytest.mark.django_db
def test_close_period_emits_audit():
    company, _ = _mk_scope()
    closer = _actor()
    period = FiscalPeriod.objects.create(company=company, year=2026, month=1, status=FiscalPeriod.Status.OPEN)

    close_fiscal_period(company_id=company.id, year=2026, month=1, actor_user=closer)

    ev = _audit("ACCOUNTING_PERIOD_CLOSED", period.id).first()
    assert ev is not None
    assert ev.subject_type == "FISCAL_PERIOD"
    assert ev.after_snapshot.get("status") == FiscalPeriod.Status.CLOSED


@pytest.mark.django_db
def test_reverse_emits_audit():
    company, branch = _mk_scope()
    poster = _actor()
    reverser = _actor()
    link = _draft_for(company=company, branch=branch)
    post_journal_drafts(company_id=company.id, auto_approve=True, allow_same_approver=True, actor_user=poster)
    entry = JournalEntry.objects.get(draft_id=link.journal_draft_id)

    result = reverse_journal_entry(
        company_id=company.id, journal_entry_id=entry.id, reason="ajuste", actor_user=reverser
    )

    ev = _audit("ACCOUNTING_JOURNAL_REVERSED", result.reversal_entry_id).first()
    assert ev is not None
    assert ev.subject_type == "JOURNAL_ENTRY"
    assert ev.after_snapshot.get("original_journal_entry_id") == entry.id


@pytest.mark.django_db
def test_close_emits_manifest_hash():
    company, _ = _mk_scope()
    closer = _actor()
    period = FiscalPeriod.objects.create(company=company, year=2026, month=2, status=FiscalPeriod.Status.OPEN)

    close_fiscal_period(company_id=company.id, year=2026, month=2, actor_user=closer)

    ev = _audit("ACCOUNTING_PERIOD_CLOSED", period.id).first()
    assert ev is not None
    manifest_hash = ev.metadata.get("close_manifest_hash")
    assert isinstance(manifest_hash, str) and len(manifest_hash) == 64  # sha256 hex


@pytest.mark.django_db
def test_posting_blocked_in_closed_period_audits():
    from django.utils import timezone as djtz

    company, branch = _mk_scope()
    poster = _actor()
    link = _draft_for(company=company, branch=branch)
    draft = JournalDraft.objects.get(id=link.journal_draft_id)

    # Cerrar (force: hay draft pendiente) el periodo del evento.
    local = djtz.localtime(draft.economic_event.occurred_at)
    close_fiscal_period(company_id=company.id, year=local.year, month=local.month, force=True, actor_user=poster)

    # Postear en periodo cerrado -> bloqueado (#10) + AuditEvent.
    result = post_journal_drafts(
        company_id=company.id, auto_approve=True, allow_same_approver=True, actor_user=poster
    )
    assert result.posted == 0
    assert result.failed >= 1
    assert _audit("ACCOUNTING_POSTING_BLOCKED", draft.id).exists()
