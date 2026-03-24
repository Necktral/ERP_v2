from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APIClient

from apps.kernels.accounting.models import (
    ChartOfAccount,
    EconomicEvent,
    FiscalPeriod,
    JournalDraft,
    JournalEntry,
    JournalEntryLine,
    PostingRuleSet,
)
from apps.modulos.iam.models import OrgUnit, UserMembership
from apps.modulos.rbac.models import Permission, Role, RoleAssignment, RolePermission

User = get_user_model()


def _mk_org():
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="Holding")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="Company", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name="Branch", parent=company)
    return company, branch


def _mk_user(prefix: str = "report"):
    username = f"{prefix}_{uuid.uuid4().hex[:8]}"
    return User.objects.create_user(username=username, email=f"{username}@test.local", password="pass12345")


def _client_with_perms(*, company: OrgUnit, branch: OrgUnit, perm_codes: list[str]) -> APIClient:
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
    r = client.post("/api/auth/login/", {"username": user.username, "password": "pass12345"}, format="json")
    assert r.status_code == 200
    access = r.data.get("access") if isinstance(r.data, dict) else None
    if isinstance(access, str) and access:
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    client.defaults["HTTP_X_COMPANY_ID"] = str(company.id)
    client.defaults["HTTP_X_BRANCH_ID"] = str(branch.id)
    return client


def _seed_accounting_posted_entries(*, company: OrgUnit, branch: OrgUnit):
    period = FiscalPeriod.objects.create(company=company, year=2026, month=3, status=FiscalPeriod.Status.OPEN)
    rule_set = PostingRuleSet.objects.create(
        code=f"RS-{uuid.uuid4().hex[:8]}",
        version=1,
        status=PostingRuleSet.Status.ACTIVE,
        fiscal_mode=PostingRuleSet.FiscalMode.BOTH,
        scope_company=company,
        rules_json={},
    )

    coa_cash = ChartOfAccount.objects.create(
        company=company, code="1101", name="Caja", account_type=ChartOfAccount.AccountType.ASSET, is_postable=True
    )
    coa_rev = ChartOfAccount.objects.create(
        company=company,
        code="4101",
        name="Ingresos",
        account_type=ChartOfAccount.AccountType.REVENUE,
        is_postable=True,
    )
    coa_exp = ChartOfAccount.objects.create(
        company=company,
        code="5101",
        name="Gastos",
        account_type=ChartOfAccount.AccountType.EXPENSE,
        is_postable=True,
    )

    def _entry(*, event_type: str, debit_account: ChartOfAccount, credit_account: ChartOfAccount, amount: Decimal):
        event = EconomicEvent.objects.create(
            source_module="BILLING",
            event_type=event_type,
            company=company,
            branch=branch,
            payload={"data": {"total": str(amount)}},
            occurred_at=timezone.now() - timedelta(days=1),
        )
        draft = JournalDraft.objects.create(
            economic_event=event,
            rule_set=rule_set,
            state=JournalDraft.State.POSTED,
            lines_json=[],
            total_debit=amount,
            total_credit=amount,
        )
        entry = JournalEntry.objects.create(
            draft=draft,
            period=period,
            company=company,
            branch=branch,
            entry_date=timezone.localdate() - timedelta(days=1),
            description=f"{event_type} {amount}",
            debit_total=amount,
            credit_total=amount,
            is_posted=True,
        )
        JournalEntryLine.objects.create(
            journal_entry=entry,
            line_no=1,
            account=debit_account,
            account_code_snapshot=debit_account.code,
            amount_tx=amount,
            debit_base=amount,
            credit_base=Decimal("0.00"),
        )
        JournalEntryLine.objects.create(
            journal_entry=entry,
            line_no=2,
            account=credit_account,
            account_code_snapshot=credit_account.code,
            amount_tx=amount,
            debit_base=Decimal("0.00"),
            credit_base=amount,
        )

    _entry(event_type="DocumentIssued", debit_account=coa_cash, credit_account=coa_rev, amount=Decimal("100.00"))
    _entry(event_type="ExpenseBooked", debit_account=coa_exp, credit_account=coa_cash, amount=Decimal("20.00"))


@pytest.mark.django_db
def test_reporting_catalog_and_run_flow_with_accounting_adapter():
    company, branch = _mk_org()
    _seed_accounting_posted_entries(company=company, branch=branch)
    call_command("seed_reporting_catalog")

    client = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=[
            "report.catalog.read",
            "report.dataset.read",
            "report.run.read",
            "accounting.report.read",
        ],
    )

    catalog = client.get("/api/reporting/catalog/")
    assert catalog.status_code == 200
    assert catalog.data["count"] >= 5

    run = client.post(
        "/api/reporting/datasets/accounting.trial_balance.period/run/",
        {"filters": {"year": 2026, "month": 3}},
        format="json",
    )
    assert run.status_code == 200
    assert run.data["dataset_key"] == "accounting.trial_balance.period"
    assert "run_id" in run.data
    assert "rows" in run.data
    assert "totals" in run.data

    runs = client.get("/api/reporting/runs/")
    assert runs.status_code == 200
    assert runs.data["count"] >= 1

    detail = client.get(f"/api/reporting/runs/{run.data['run_id']}/")
    assert detail.status_code == 200
    assert detail.data["dataset_key"] == "accounting.trial_balance.period"
    assert detail.data["status"] == "SUCCEEDED"


@pytest.mark.django_db
def test_reporting_run_requires_domain_permission():
    company, branch = _mk_org()
    _seed_accounting_posted_entries(company=company, branch=branch)
    call_command("seed_reporting_catalog")

    client = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=["report.dataset.read"],
    )
    run = client.post(
        "/api/reporting/datasets/accounting.pnl.period/run/",
        {"filters": {"year": 2026, "month": 3}},
        format="json",
    )
    assert run.status_code == 403


@pytest.mark.django_db
def test_reporting_parity_trial_balance_and_pnl_against_legacy_accounting():
    company, branch = _mk_org()
    _seed_accounting_posted_entries(company=company, branch=branch)
    call_command("seed_reporting_catalog")

    client = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=[
            "report.dataset.read",
            "report.run.read",
            "report.catalog.read",
            "accounting.report.read",
        ],
    )

    legacy_tb = client.get("/api/accounting/reports/trial-balance/?year=2026&month=3")
    assert legacy_tb.status_code == 200
    rep_tb = client.post(
        "/api/reporting/datasets/accounting.trial_balance.period/run/",
        {"filters": {"year": 2026, "month": 3}},
        format="json",
    )
    assert rep_tb.status_code == 200
    legacy_tb_totals = {
        "debit_total": sum(Decimal(row["debit_total"]) for row in legacy_tb.data["results"]),
        "credit_total": sum(Decimal(row["credit_total"]) for row in legacy_tb.data["results"]),
    }
    rep_tb_totals = {
        "debit_total": Decimal(rep_tb.data["totals"]["debit_total"]),
        "credit_total": Decimal(rep_tb.data["totals"]["credit_total"]),
    }
    assert legacy_tb_totals == rep_tb_totals

    legacy_pnl = client.get("/api/accounting/reports/pnl/?year=2026&month=3")
    assert legacy_pnl.status_code == 200
    rep_pnl = client.post(
        "/api/reporting/datasets/accounting.pnl.period/run/",
        {"filters": {"year": 2026, "month": 3}},
        format="json",
    )
    assert rep_pnl.status_code == 200
    assert legacy_pnl.data["totals"] == rep_pnl.data["totals"]


@pytest.mark.django_db
def test_reporting_run_rejects_invalid_filter_schema():
    company, branch = _mk_org()
    _seed_accounting_posted_entries(company=company, branch=branch)
    call_command("seed_reporting_catalog")
    client = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=["report.dataset.read", "accounting.report.read"],
    )
    run = client.post(
        "/api/reporting/datasets/accounting.trial_balance.period/run/",
        {"filters": {"invalid_field": "x"}},
        format="json",
    )
    assert run.status_code == 400
