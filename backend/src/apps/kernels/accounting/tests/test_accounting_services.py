"""
Tests del kernel accounting — contratos críticos usados por otros kernels:
  - seed_posting_rules_v1_for_company
  - link_operational_event_to_accounting
  - apply_accounting_link_to_outbox_event
  - dispatch_accounting_outbox_events
  - approve_journal_drafts
  - post_journal_drafts
  - close_fiscal_period
"""
from __future__ import annotations

import uuid
from datetime import timezone as dt_timezone
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.kernels.accounting.models import (
    EconomicEvent,
    FiscalPeriod,
    JournalDraft,
    JournalEntry,
    OperationalPostingConfig,
    PostingRuleSet,
)
from apps.kernels.accounting.services import (
    AccountingConflictError,
    apply_accounting_link_to_outbox_event,
    approve_journal_drafts,
    close_fiscal_period,
    dispatch_accounting_outbox_events,
    link_operational_event_to_accounting,
    post_journal_drafts,
    seed_posting_rules_v1_for_company,
)
from apps.modulos.iam.models import OrgUnit
from apps.modulos.integration.models import OutboxEvent


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _mk_scope(suffix=""):
    s = suffix or uuid.uuid4().hex[:6]
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name=f"H_{s}")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name=f"C_{s}", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name=f"B_{s}", parent=company)
    return company, branch


def _billing_outbox(*, company, branch, event_type="DocumentIssued", doc_type="INVOICE",
                    total="115.00", subtotal="100.00", tax_total="15.00"):
    return OutboxEvent.objects.create(
        source_module="BILLING",
        event_type=event_type,
        company=company,
        branch=branch,
        payload={
            "data": {
                "doc_type": doc_type,
                "total": total,
                "subtotal": subtotal,
                "tax_total": tax_total,
            }
        },
        occurred_at=timezone.now(),
    )


def _inventory_outbox(*, company, branch, event_type="InventoryMovementPosted",
                      movement_type="RECEIVE", total_cost="500.00", qty="10", unit_cost="50.00"):
    return OutboxEvent.objects.create(
        source_module="INVENTORY",
        event_type=event_type,
        company=company,
        branch=branch,
        payload={
            "data": {
                "movement_type": movement_type,
                "total_cost": total_cost,
                "qty": qty,
                "unit_cost": unit_cost,
                "qty_delta": qty,
                "avg_cost": unit_cost,
            }
        },
        occurred_at=timezone.now(),
    )


# ---------------------------------------------------------------------------
# seed_posting_rules_v1_for_company
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_seed_creates_active_ruleset():
    company, _ = _mk_scope()
    rule_set, created = seed_posting_rules_v1_for_company(company=company)

    assert created is True
    assert rule_set.status == PostingRuleSet.Status.ACTIVE
    assert rule_set.code == "shadow_ledger_v1"
    assert rule_set.scope_company == company
    assert isinstance(rule_set.rules_json, dict)
    assert "rules" in rule_set.rules_json


@pytest.mark.django_db
def test_seed_idempotent_returns_existing():
    company, _ = _mk_scope()
    rs1, created1 = seed_posting_rules_v1_for_company(company=company)
    rs2, created2 = seed_posting_rules_v1_for_company(company=company)

    assert created1 is True
    assert created2 is False
    assert rs1.id == rs2.id


@pytest.mark.django_db
def test_seed_two_companies_independent():
    company1, _ = _mk_scope("a")
    company2, _ = _mk_scope("b")

    rs1, _ = seed_posting_rules_v1_for_company(company=company1)
    rs2, _ = seed_posting_rules_v1_for_company(company=company2)

    assert rs1.id != rs2.id
    assert rs1.scope_company == company1
    assert rs2.scope_company == company2


# ---------------------------------------------------------------------------
# link_operational_event_to_accounting — casos base
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_link_unsupported_module_returns_unsupported():
    company, branch = _mk_scope()
    event = OutboxEvent.objects.create(
        source_module="UNKNOWN_MODULE",
        event_type="SomeEvent",
        company=company,
        branch=branch,
        payload={},
        occurred_at=timezone.now(),
    )
    result = link_operational_event_to_accounting(outbox_event=event)
    assert result.status == "UNSUPPORTED"
    assert result.economic_event_id is None


@pytest.mark.django_db
def test_link_unsupported_event_type_returns_unsupported():
    company, branch = _mk_scope()
    event = OutboxEvent.objects.create(
        source_module="BILLING",
        event_type="UnknownEvent",
        company=company,
        branch=branch,
        payload={},
        occurred_at=timezone.now(),
    )
    result = link_operational_event_to_accounting(outbox_event=event)
    assert result.status == "UNSUPPORTED"


@pytest.mark.django_db
def test_link_disabled_runtime_returns_disabled():
    company, branch = _mk_scope()
    OperationalPostingConfig.objects.create(
        company=company,
        posting_mode=OperationalPostingConfig.PostingMode.DISABLED,
        enable_billing=True,
        is_active=True,
    )
    event = _billing_outbox(company=company, branch=branch)
    result = link_operational_event_to_accounting(outbox_event=event)
    assert result.status == "DISABLED"


@pytest.mark.django_db
def test_link_billing_module_disabled_via_config():
    company, branch = _mk_scope()
    OperationalPostingConfig.objects.create(
        company=company,
        posting_mode=OperationalPostingConfig.PostingMode.HYBRID,
        enable_billing=False,
        enable_inventory=True,
        is_active=True,
    )
    event = _billing_outbox(company=company, branch=branch)
    result = link_operational_event_to_accounting(outbox_event=event)
    assert result.status == "DISABLED"


# ---------------------------------------------------------------------------
# link_operational_event_to_accounting — happy path
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_link_billing_invoice_creates_economic_event_and_draft():
    company, branch = _mk_scope()
    seed_posting_rules_v1_for_company(company=company)
    event = _billing_outbox(company=company, branch=branch)

    result = link_operational_event_to_accounting(outbox_event=event)

    assert result.status == "DRAFT_VALIDATED"
    assert result.economic_event_id is not None
    assert result.journal_draft_id is not None
    assert result.error == ""

    eco = EconomicEvent.objects.get(id=result.economic_event_id)
    assert eco.source_module == "BILLING"
    assert eco.event_type == "DocumentIssued"
    assert eco.company == company

    draft = JournalDraft.objects.get(id=result.journal_draft_id)
    assert draft.state == JournalDraft.State.VALIDATED
    assert draft.total_debit == draft.total_credit
    assert draft.total_debit > Decimal("0")


@pytest.mark.django_db
def test_link_billing_credit_note_creates_validated_draft():
    company, branch = _mk_scope()
    seed_posting_rules_v1_for_company(company=company)
    event = _billing_outbox(
        company=company, branch=branch,
        doc_type="CREDIT_NOTE", total="115.00", subtotal="100.00", tax_total="15.00",
    )
    result = link_operational_event_to_accounting(outbox_event=event)
    assert result.status == "DRAFT_VALIDATED"
    assert result.journal_draft_id is not None


@pytest.mark.django_db
def test_link_billing_voided_creates_validated_draft():
    company, branch = _mk_scope()
    seed_posting_rules_v1_for_company(company=company)
    event = _billing_outbox(
        company=company, branch=branch, event_type="DocumentVoided", doc_type="INVOICE",
    )
    result = link_operational_event_to_accounting(outbox_event=event)
    assert result.status == "DRAFT_VALIDATED"


@pytest.mark.django_db
def test_link_inventory_movement_creates_validated_draft():
    company, branch = _mk_scope()
    seed_posting_rules_v1_for_company(company=company)
    event = _inventory_outbox(company=company, branch=branch)

    result = link_operational_event_to_accounting(outbox_event=event)
    assert result.status == "DRAFT_VALIDATED"
    assert result.economic_event_id is not None

    draft = JournalDraft.objects.get(id=result.journal_draft_id)
    assert draft.state == JournalDraft.State.VALIDATED


@pytest.mark.django_db
def test_link_auto_seeds_ruleset_if_none_exists():
    company, branch = _mk_scope()
    # No seed previo — debe crearlo automáticamente
    assert not PostingRuleSet.objects.filter(scope_company=company).exists()
    event = _billing_outbox(company=company, branch=branch)

    result = link_operational_event_to_accounting(outbox_event=event)

    assert result.status == "DRAFT_VALIDATED"
    assert PostingRuleSet.objects.filter(scope_company=company, status=PostingRuleSet.Status.ACTIVE).exists()


@pytest.mark.django_db
def test_link_idempotent_same_outbox_event():
    company, branch = _mk_scope()
    seed_posting_rules_v1_for_company(company=company)
    event = _billing_outbox(company=company, branch=branch)

    r1 = link_operational_event_to_accounting(outbox_event=event)
    r2 = link_operational_event_to_accounting(outbox_event=event)

    assert r1.economic_event_id == r2.economic_event_id
    assert r1.journal_draft_id == r2.journal_draft_id
    assert EconomicEvent.objects.filter(source_outbox_event_id=event.event_id).count() == 1
    assert JournalDraft.objects.filter(economic_event_id=r1.economic_event_id).count() == 1


@pytest.mark.django_db
def test_link_no_matching_rule_returns_pending_rule():
    company, branch = _mk_scope()
    # Seedear ruleset real pero con doc_type sin regla → no hay match
    seed_posting_rules_v1_for_company(company=company)
    # doc_type "INTERNAL_ADJUSTMENT" no existe en build_rules_json_v1
    event = OutboxEvent.objects.create(
        source_module="BILLING",
        event_type="DocumentIssued",
        company=company,
        branch=branch,
        payload={"data": {"doc_type": "INTERNAL_ADJUSTMENT", "total": "100.00", "subtotal": "87.00", "tax_total": "13.00"}},
        occurred_at=timezone.now(),
    )

    result = link_operational_event_to_accounting(outbox_event=event)
    assert result.status == "PENDING_RULE"
    assert result.economic_event_id is not None


# ---------------------------------------------------------------------------
# apply_accounting_link_to_outbox_event
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_apply_link_enriches_outbox_payload():
    company, branch = _mk_scope()
    seed_posting_rules_v1_for_company(company=company)
    event = _billing_outbox(company=company, branch=branch)

    link = link_operational_event_to_accounting(outbox_event=event)
    apply_accounting_link_to_outbox_event(outbox_event=event, link=link)

    event.refresh_from_db()
    data = event.payload["data"]
    assert data["accounting_status"] == "DRAFT_VALIDATED"
    assert data["economic_event_id"] == link.economic_event_id
    assert data["journal_draft_id"] == link.journal_draft_id


@pytest.mark.django_db
def test_apply_link_unsupported_enriches_without_ids():
    company, branch = _mk_scope()
    event = OutboxEvent.objects.create(
        source_module="UNKNOWN",
        event_type="X",
        company=company,
        branch=branch,
        payload={"data": {}},
        occurred_at=timezone.now(),
    )
    from apps.kernels.accounting.services import OperationalAccountingLinkResult
    link = OperationalAccountingLinkResult(status="UNSUPPORTED")
    apply_accounting_link_to_outbox_event(outbox_event=event, link=link)

    event.refresh_from_db()
    assert event.payload["data"]["accounting_status"] == "UNSUPPORTED"
    assert event.payload["data"]["economic_event_id"] is None


# ---------------------------------------------------------------------------
# dispatch_accounting_outbox_events
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_dispatch_processes_pending_billing_events():
    company, branch = _mk_scope()
    seed_posting_rules_v1_for_company(company=company)

    e1 = _billing_outbox(company=company, branch=branch)
    e2 = _billing_outbox(company=company, branch=branch)

    summary = dispatch_accounting_outbox_events(limit=50)

    assert summary.attempted >= 2
    assert summary.sent >= 2

    e1.refresh_from_db()
    e2.refresh_from_db()
    assert e1.payload["data"]["accounting_status"] == "DRAFT_VALIDATED"
    assert e2.payload["data"]["accounting_status"] == "DRAFT_VALIDATED"


# ---------------------------------------------------------------------------
# approve_journal_drafts
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_approve_validated_drafts():
    company, branch = _mk_scope()
    seed_posting_rules_v1_for_company(company=company)

    event = _billing_outbox(company=company, branch=branch)
    link = link_operational_event_to_accounting(outbox_event=event)
    assert link.status == "DRAFT_VALIDATED"

    result = approve_journal_drafts(company_id=company.id)

    assert result.attempted >= 1
    assert result.approved >= 1
    assert result.failed == 0

    draft = JournalDraft.objects.get(id=link.journal_draft_id)
    assert draft.state == JournalDraft.State.APPROVED_FOR_POSTING


@pytest.mark.django_db
def test_approve_skips_already_approved():
    company, branch = _mk_scope()
    seed_posting_rules_v1_for_company(company=company)

    event = _billing_outbox(company=company, branch=branch)
    link_operational_event_to_accounting(outbox_event=event)

    approve_journal_drafts(company_id=company.id)
    # Segunda pasada: draft ya en APPROVED — no hay VALIDATED que procesar
    result2 = approve_journal_drafts(company_id=company.id)
    assert result2.attempted == 0


# ---------------------------------------------------------------------------
# post_journal_drafts
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_post_drafts_auto_approve():
    company, branch = _mk_scope()
    seed_posting_rules_v1_for_company(company=company)

    event = _billing_outbox(company=company, branch=branch)
    link = link_operational_event_to_accounting(outbox_event=event)
    assert link.status == "DRAFT_VALIDATED"

    result = post_journal_drafts(company_id=company.id, auto_approve=True, allow_same_approver=True)

    assert result.attempted >= 1
    assert result.posted >= 1
    assert result.failed == 0

    draft = JournalDraft.objects.get(id=link.journal_draft_id)
    assert draft.state == JournalDraft.State.POSTED
    assert JournalEntry.objects.filter(draft=draft).exists()


@pytest.mark.django_db
def test_post_drafts_requires_approved_when_flag_set():
    company, branch = _mk_scope()
    seed_posting_rules_v1_for_company(company=company)

    event = _billing_outbox(company=company, branch=branch)
    link = link_operational_event_to_accounting(outbox_event=event)

    # require_approved=True sin auto_approve → draft VALIDATED se saltea
    result = post_journal_drafts(
        company_id=company.id, require_approved=True, auto_approve=False,
    )
    assert result.skipped >= 1
    assert result.posted == 0

    draft = JournalDraft.objects.get(id=link.journal_draft_id)
    assert draft.state == JournalDraft.State.VALIDATED


@pytest.mark.django_db
def test_post_drafts_sod_block_same_approver():
    from django.contrib.auth import get_user_model
    User = get_user_model()
    actor = User.objects.create_user(username=f"u_{uuid.uuid4().hex[:8]}", password="x")

    company, branch = _mk_scope()
    seed_posting_rules_v1_for_company(company=company)

    event = _billing_outbox(company=company, branch=branch)
    link_operational_event_to_accounting(outbox_event=event)

    # Aprobar con actor
    approve_journal_drafts(company_id=company.id, actor_user=actor)

    # Postear con el mismo actor sin allow_same_approver → debe fallar por SoD
    result = post_journal_drafts(
        company_id=company.id,
        require_approved=True,
        actor_user=actor,
        allow_same_approver=False,
    )
    assert result.failed >= 1
    assert any("SoD" in e["error"] for e in result.errors)


# ---------------------------------------------------------------------------
# close_fiscal_period
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_close_fiscal_period_open_no_pending_drafts():
    company, _ = _mk_scope()
    FiscalPeriod.objects.create(company=company, year=2026, month=1, status=FiscalPeriod.Status.OPEN)

    result = close_fiscal_period(company_id=company.id, year=2026, month=1)

    assert result.status == FiscalPeriod.Status.CLOSED
    assert result.was_already_closed is False
    assert result.pending_drafts == 0

    period = FiscalPeriod.objects.get(company=company, year=2026, month=1)
    assert period.status == FiscalPeriod.Status.CLOSED


@pytest.mark.django_db
def test_close_fiscal_period_idempotent():
    company, _ = _mk_scope()
    FiscalPeriod.objects.create(company=company, year=2026, month=2, status=FiscalPeriod.Status.CLOSED)

    result = close_fiscal_period(company_id=company.id, year=2026, month=2)

    assert result.was_already_closed is True
    assert result.status == FiscalPeriod.Status.CLOSED


@pytest.mark.django_db
def test_close_fiscal_period_creates_period_if_missing():
    company, _ = _mk_scope()
    assert not FiscalPeriod.objects.filter(company=company, year=2026, month=5).exists()

    result = close_fiscal_period(company_id=company.id, year=2026, month=5)

    assert result.status == FiscalPeriod.Status.CLOSED
    assert FiscalPeriod.objects.filter(company=company, year=2026, month=5).exists()


@pytest.mark.django_db
def test_close_fiscal_period_blocked_by_pending_drafts():
    company, branch = _mk_scope()
    seed_posting_rules_v1_for_company(company=company)

    # Crear draft VALIDATED en el periodo 2026-03 — bloquea el cierre
    from datetime import datetime as dt
    event = _billing_outbox(company=company, branch=branch)
    event.occurred_at = dt(2026, 3, 15, tzinfo=dt_timezone.utc)
    event.save(update_fields=["occurred_at"])
    link = link_operational_event_to_accounting(outbox_event=event)
    assert link.status == "DRAFT_VALIDATED"

    # Con drafts pendientes, close_fiscal_period lanza AccountingConflictError
    with pytest.raises(AccountingConflictError, match="drafts"):
        close_fiscal_period(company_id=company.id, year=2026, month=3, force=False)

    # Periodo sigue OPEN
    period = FiscalPeriod.objects.filter(company=company, year=2026, month=3).first()
    if period:
        assert period.status == FiscalPeriod.Status.OPEN


@pytest.mark.django_db
def test_close_fiscal_period_invalid_company_raises():
    with pytest.raises(ValueError, match="company"):
        close_fiscal_period(company_id=999999, year=2026, month=1)


@pytest.mark.django_db
def test_close_fiscal_period_invalid_month_raises():
    company, _ = _mk_scope()
    with pytest.raises(ValueError, match="month"):
        close_fiscal_period(company_id=company.id, year=2026, month=13)
