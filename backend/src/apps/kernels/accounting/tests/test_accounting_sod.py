"""Tests de SoD híbrido en accounting (Unidad #4, sub-incremento B).

Segregación approve≠generate sobre el state machine de JournalDraft: el actor que
generó un draft (humano) no puede aprobarlo (invariante #6, anti-patrón #10). Los
drafts de proyección automática (`generated_by=None`) no aplican la restricción.
La segregación post≠approve ya existía en `post_journal_drafts`.
"""
from __future__ import annotations

import uuid

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.kernels.accounting.models import JournalDraft
from apps.kernels.accounting.services import (
    approve_journal_drafts,
    link_operational_event_to_accounting,
    seed_posting_rules_v1_for_company,
)
from apps.modulos.iam.models import OrgUnit
from apps.modulos.integration.models import OutboxEvent

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


def _link(*, company, branch, actor_user=None):
    seed_posting_rules_v1_for_company(company=company)
    event = OutboxEvent.objects.create(
        source_module="BILLING",
        event_type="DocumentIssued",
        company=company,
        branch=branch,
        payload={"data": {"doc_type": "INVOICE", "total": "115.00", "subtotal": "100.00", "tax_total": "15.00"}},
        occurred_at=timezone.now(),
    )
    return link_operational_event_to_accounting(outbox_event=event, actor_user=actor_user)


@pytest.mark.django_db
def test_generated_by_is_stamped_from_actor():
    company, branch = _mk_scope()
    gen = _actor()
    link = _link(company=company, branch=branch, actor_user=gen)
    draft = JournalDraft.objects.get(id=link.journal_draft_id)
    assert draft.generated_by_id == gen.id


@pytest.mark.django_db
def test_approve_blocks_self_generated_draft():
    company, branch = _mk_scope()
    gen = _actor()
    link = _link(company=company, branch=branch, actor_user=gen)

    result = approve_journal_drafts(company_id=company.id, actor_user=gen)

    assert result.failed >= 1
    assert any("SoD" in e["error"] for e in result.errors)
    draft = JournalDraft.objects.get(id=link.journal_draft_id)
    assert draft.state == JournalDraft.State.VALIDATED  # no aprobado


@pytest.mark.django_db
def test_approve_allows_different_actor():
    company, branch = _mk_scope()
    gen, approver = _actor(), _actor()
    link = _link(company=company, branch=branch, actor_user=gen)

    result = approve_journal_drafts(company_id=company.id, actor_user=approver)

    assert result.approved >= 1
    assert result.failed == 0
    draft = JournalDraft.objects.get(id=link.journal_draft_id)
    assert draft.state == JournalDraft.State.APPROVED_FOR_POSTING


@pytest.mark.django_db
def test_approve_allows_system_generated_draft():
    # Proyección automática (sin actor): generated_by=None -> sin restricción de SoD.
    company, branch = _mk_scope()
    approver = _actor()
    link = _link(company=company, branch=branch, actor_user=None)
    draft = JournalDraft.objects.get(id=link.journal_draft_id)
    assert draft.generated_by_id is None

    result = approve_journal_drafts(company_id=company.id, actor_user=approver)
    assert result.approved >= 1
    draft.refresh_from_db()
    assert draft.state == JournalDraft.State.APPROVED_FOR_POSTING


@pytest.mark.django_db
def test_approve_self_generated_with_override():
    company, branch = _mk_scope()
    gen = _actor()
    link = _link(company=company, branch=branch, actor_user=gen)

    result = approve_journal_drafts(company_id=company.id, actor_user=gen, allow_same_generator=True)
    assert result.approved >= 1
    draft = JournalDraft.objects.get(id=link.journal_draft_id)
    assert draft.state == JournalDraft.State.APPROVED_FOR_POSTING
