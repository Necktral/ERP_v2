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
from apps.modulos.estacion_servicios.models import (
    FuelDispense,
    FuelPaymentMethod,
    FuelPriceUOM,
    FuelProduct,
    FuelSale,
    FuelSaleStatus,
    FuelSaleType,
    FuelShift,
    FuelVolumeUOM,
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


def _seed_fuel_entries(*, company: OrgUnit, branch: OrgUnit):
    actor = _mk_user("fuel")
    UserMembership.objects.create(user=actor, org_unit=company, is_active=True)
    UserMembership.objects.create(user=actor, org_unit=branch, is_active=True)
    shift = FuelShift.objects.create(
        company=company,
        branch=branch,
        status="OPEN",
        opened_by=actor,
    )
    now = timezone.now()
    disp_1 = FuelDispense.objects.create(
        company=company,
        branch=branch,
        shift=shift,
        occurred_at=now - timedelta(hours=2),
        recorded_by=actor,
        product=FuelProduct.DIESEL,
        liters=Decimal("10.0000"),
        volume_entered=Decimal("10.0000"),
        volume_uom=FuelVolumeUOM.LITER,
        unit_price=Decimal("2.5000"),
        unit_price_entered=Decimal("2.5000"),
        unit_price_uom=FuelPriceUOM.PER_LITER,
        amount=Decimal("25.00"),
        amount_canonical=Decimal("25.00"),
        amount_delta=Decimal("0.00"),
        pump_code="P1",
        nozzle_code="N1",
    )
    disp_2 = FuelDispense.objects.create(
        company=company,
        branch=branch,
        shift=shift,
        occurred_at=now - timedelta(hours=1),
        recorded_by=actor,
        product=FuelProduct.GASOLINE,
        liters=Decimal("5.0000"),
        volume_entered=Decimal("5.0000"),
        volume_uom=FuelVolumeUOM.LITER,
        unit_price=Decimal("3.0000"),
        unit_price_entered=Decimal("3.0000"),
        unit_price_uom=FuelPriceUOM.PER_LITER,
        amount=Decimal("15.00"),
        amount_canonical=Decimal("15.00"),
        amount_delta=Decimal("0.00"),
        pump_code="P2",
        nozzle_code="N2",
    )
    disp_3 = FuelDispense.objects.create(
        company=company,
        branch=branch,
        shift=shift,
        occurred_at=now - timedelta(minutes=30),
        recorded_by=actor,
        product=FuelProduct.DIESEL,
        liters=Decimal("8.0000"),
        volume_entered=Decimal("8.0000"),
        volume_uom=FuelVolumeUOM.LITER,
        unit_price=Decimal("2.5000"),
        unit_price_entered=Decimal("2.5000"),
        unit_price_uom=FuelPriceUOM.PER_LITER,
        amount=Decimal("20.00"),
        amount_canonical=Decimal("20.00"),
        amount_delta=Decimal("0.00"),
        pump_code="P1",
        nozzle_code="N1",
    )
    FuelSale.objects.create(
        company=company,
        branch=branch,
        shift=shift,
        dispense=disp_1,
        sale_type=FuelSaleType.PUBLIC,
        payment_method=FuelPaymentMethod.CASH,
        total_amount=Decimal("25.00"),
        status=FuelSaleStatus.ACTIVE,
        created_by=actor,
    )
    FuelSale.objects.create(
        company=company,
        branch=branch,
        shift=shift,
        dispense=disp_2,
        sale_type=FuelSaleType.PUBLIC,
        payment_method=FuelPaymentMethod.CASH,
        total_amount=Decimal("15.00"),
        status=FuelSaleStatus.CANCELLED,
        created_by=actor,
    )
    FuelSale.objects.create(
        company=company,
        branch=branch,
        shift=shift,
        dispense=disp_3,
        sale_type=FuelSaleType.PUBLIC,
        payment_method=FuelPaymentMethod.CASH,
        total_amount=Decimal("20.00"),
        status=FuelSaleStatus.ACTIVE,
        created_by=actor,
    )


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
    assert run.data["quality_status"] in {"PASS", "WARN", "FAIL"}
    assert isinstance(run.data["quality_checks"], list)

    runs = client.get("/api/reporting/runs/")
    assert runs.status_code == 200
    assert runs.data["count"] >= 1

    detail = client.get(f"/api/reporting/runs/{run.data['run_id']}/")
    assert detail.status_code == 200
    assert detail.data["dataset_key"] == "accounting.trial_balance.period"
    assert detail.data["status"] == "SUCCEEDED"
    assert detail.data["quality_status"] in {"PASS", "WARN", "FAIL"}
    assert isinstance(detail.data["quality_checks"], list)


@pytest.mark.django_db
def test_reporting_run_emits_audit_event():
    # PR-7: cierra audit=0 en reporting — ejecutar un dataset emite REPORTING_DATASET_EXECUTED.
    from apps.modulos.audit.models import AuditEvent

    company, branch = _mk_org()
    _seed_accounting_posted_entries(company=company, branch=branch)
    call_command("seed_reporting_catalog")

    client = _client_with_perms(
        company=company, branch=branch,
        perm_codes=["report.dataset.read", "report.run.read", "accounting.report.read"],
    )
    run = client.post(
        "/api/reporting/datasets/accounting.trial_balance.period/run/",
        {"filters": {"year": 2026, "month": 3}}, format="json",
    )
    assert run.status_code == 200, run.data
    run_id = run.data["run_id"]

    ev = AuditEvent.objects.filter(event_type="REPORTING_DATASET_EXECUTED", subject_id=str(run_id)).first()
    assert ev is not None
    assert ev.subject_type == "REPORT_RUN"
    assert ev.metadata.get("dataset_key") == "accounting.trial_balance.period"


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


@pytest.mark.django_db
@pytest.mark.parametrize("export_format", ["json", "csv", "xlsx"])
def test_reporting_export_from_run_id(export_format: str):
    company, branch = _mk_org()
    _seed_accounting_posted_entries(company=company, branch=branch)
    call_command("seed_reporting_catalog")
    client = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=[
            "report.dataset.read",
            "report.dataset.export",
            "report.run.read",
            "accounting.report.read",
        ],
    )
    run = client.post(
        "/api/reporting/datasets/accounting.trial_balance.period/run/",
        {"filters": {"year": 2026, "month": 3}},
        format="json",
    )
    assert run.status_code == 200
    run_id = run.data["run_id"]

    exported = client.post(
        f"/api/reporting/runs/{run_id}/export/",
        {"format": export_format},
        format="json",
    )
    assert exported.status_code == 200
    assert exported.data["run_id"] == run_id
    assert exported.data["status"] == "SUCCEEDED"
    assert exported.data["format"] == export_format
    assert int(exported.data["file_size"]) > 0
    assert exported.data["output_hash"]

    detail = client.get(f"/api/reporting/exports/{exported.data['export_id']}/")
    assert detail.status_code == 200
    assert detail.data["export_id"] == exported.data["export_id"]
    assert detail.data["output_hash"] == exported.data["output_hash"]


@pytest.mark.django_db
def test_reporting_export_requires_permission():
    company, branch = _mk_org()
    _seed_accounting_posted_entries(company=company, branch=branch)
    call_command("seed_reporting_catalog")
    client = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=[
            "report.dataset.read",
            "report.run.read",
            "accounting.report.read",
        ],
    )
    run = client.post(
        "/api/reporting/datasets/accounting.trial_balance.period/run/",
        {"filters": {"year": 2026, "month": 3}},
        format="json",
    )
    assert run.status_code == 200
    denied = client.post(
        f"/api/reporting/runs/{run.data['run_id']}/export/",
        {"format": "json"},
        format="json",
    )
    assert denied.status_code == 403


@pytest.mark.django_db
def test_reporting_export_scope_isolated_by_company():
    company_a, branch_a = _mk_org()
    company_b, branch_b = _mk_org()
    _seed_accounting_posted_entries(company=company_a, branch=branch_a)
    call_command("seed_reporting_catalog")

    producer = _client_with_perms(
        company=company_a,
        branch=branch_a,
        perm_codes=[
            "report.dataset.read",
            "report.dataset.export",
            "report.run.read",
            "accounting.report.read",
        ],
    )
    run = producer.post(
        "/api/reporting/datasets/accounting.trial_balance.period/run/",
        {"filters": {"year": 2026, "month": 3}},
        format="json",
    )
    assert run.status_code == 200

    other_scope = _client_with_perms(
        company=company_b,
        branch=branch_b,
        perm_codes=["report.dataset.export"],
    )
    hidden = other_scope.post(
        f"/api/reporting/runs/{run.data['run_id']}/export/",
        {"format": "json"},
        format="json",
    )
    assert hidden.status_code == 404


@pytest.mark.django_db
def test_reporting_snapshot_hit_and_generate_flow():
    company, branch = _mk_org()
    _seed_accounting_posted_entries(company=company, branch=branch)
    call_command("seed_reporting_catalog")
    client = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=[
            "report.dataset.read",
            "report.run.read",
            "report.snapshot.generate",
            "accounting.report.read",
        ],
    )

    first = client.post(
        "/api/reporting/datasets/accounting.trial_balance.period/run/",
        {"filters": {"year": 2026, "month": 3}},
        format="json",
    )
    assert first.status_code == 200
    first_detail = client.get(f"/api/reporting/runs/{first.data['run_id']}/")
    assert first_detail.status_code == 200
    assert first_detail.data["source_summary"].get("snapshot_id")

    second = client.post(
        "/api/reporting/datasets/accounting.trial_balance.period/run/",
        {"filters": {"year": 2026, "month": 3}},
        format="json",
    )
    assert second.status_code == 200
    second_detail = client.get(f"/api/reporting/runs/{second.data['run_id']}/")
    assert second_detail.status_code == 200
    assert second_detail.data["source_summary"].get("materialization") == "SNAPSHOT_HIT"

    snaps = client.get("/api/reporting/snapshots/?dataset_key=accounting.trial_balance.period")
    assert snaps.status_code == 200
    assert int(snaps.data["count"]) >= 1

    generated = client.post(
        "/api/reporting/snapshots/generate/",
        {"dataset_key": "accounting.trial_balance.period", "filters": {"year": 2026, "month": 3}, "force_refresh": True},
        format="json",
    )
    assert generated.status_code == 200
    assert generated.data["snapshot_id"]
    assert generated.data["materialization_strategy"] in {"SNAPSHOT_REBUILD", "CACHE_REFRESH"}


@pytest.mark.django_db
def test_reporting_snapshot_generate_requires_permission():
    company, branch = _mk_org()
    _seed_accounting_posted_entries(company=company, branch=branch)
    call_command("seed_reporting_catalog")
    client = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=["report.dataset.read", "report.run.read", "accounting.report.read"],
    )
    denied = client.post(
        "/api/reporting/snapshots/generate/",
        {"dataset_key": "accounting.trial_balance.period", "filters": {"year": 2026, "month": 3}},
        format="json",
    )
    assert denied.status_code == 403


@pytest.mark.django_db
def test_reporting_parity_general_ledger_balance_sheet_operational_reconciliation():
    company, branch = _mk_org()
    _seed_accounting_posted_entries(company=company, branch=branch)
    call_command("seed_reporting_catalog")
    client = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=["report.dataset.read", "report.run.read", "accounting.report.read"],
    )

    legacy_gl = client.get("/api/accounting/reports/general-ledger/?account_code=1101&year=2026&month=3")
    assert legacy_gl.status_code == 200
    rep_gl = client.post(
        "/api/reporting/datasets/accounting.general_ledger.transaction/run/",
        {"filters": {"account_code": "1101", "year": 2026, "month": 3}},
        format="json",
    )
    assert rep_gl.status_code == 200
    assert int(legacy_gl.data["count"]) == len(rep_gl.data["rows"])

    legacy_bs = client.get("/api/accounting/reports/balance-sheet/?year=2026&month=3")
    assert legacy_bs.status_code == 200
    rep_bs = client.post(
        "/api/reporting/datasets/accounting.balance_sheet.as_of/run/",
        {"filters": {"year": 2026, "month": 3}},
        format="json",
    )
    assert rep_bs.status_code == 200
    assert legacy_bs.data["totals"] == rep_bs.data["totals"]

    legacy_or = client.get("/api/accounting/reports/operational-reconciliation/")
    assert legacy_or.status_code == 200
    rep_or = client.post(
        "/api/reporting/datasets/accounting.operational_reconciliation.period/run/",
        {"filters": {}},
        format="json",
    )
    assert rep_or.status_code == 200
    assert legacy_or.data["summary"] == rep_or.data["totals"]


@pytest.mark.django_db
def test_reporting_fuel_datasets_run_and_permission():
    company, branch = _mk_org()
    _seed_fuel_entries(company=company, branch=branch)
    call_command("seed_reporting_catalog")
    today = timezone.localdate().isoformat()

    allowed = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=["report.dataset.read", "fuel.reports.view"],
    )
    for dataset_key in (
        "fuel.sales.by_shift.daily",
        "fuel.sales.by_pump.daily",
        "fuel.dispense_vs_sale.daily",
    ):
        run = allowed.post(
            f"/api/reporting/datasets/{dataset_key}/run/",
            {"filters": {"date_from": today, "date_to": today}},
            format="json",
        )
        assert run.status_code == 200
        assert run.data["dataset_key"] == dataset_key
        assert "rows" in run.data
        assert "totals" in run.data

    denied = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=["report.dataset.read"],
    )
    fail = denied.post(
        "/api/reporting/datasets/fuel.sales.by_shift.daily/run/",
        {"filters": {"date_from": today, "date_to": today}},
        format="json",
    )
    assert fail.status_code == 403


@pytest.mark.django_db
def test_reporting_catalog_and_run_include_dashboard_metadata():
    company, branch = _mk_org()
    _seed_accounting_posted_entries(company=company, branch=branch)
    call_command("seed_reporting_catalog")
    client = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=["report.catalog.read", "report.dataset.read", "accounting.report.read"],
    )

    catalog = client.get("/api/reporting/catalog/")
    assert catalog.status_code == 200
    first = catalog.data["results"][0]
    assert "render_hints" in first
    assert "drill_metadata" in first

    run = client.post(
        "/api/reporting/datasets/accounting.trial_balance.period/run/",
        {"filters": {"year": 2026, "month": 3}},
        format="json",
    )
    assert run.status_code == 200
    assert "render_hints" in run.data
    assert "drill_metadata" in run.data


@pytest.mark.django_db
def test_reporting_saved_views_create_list_and_detail():
    company, branch = _mk_org()
    _seed_accounting_posted_entries(company=company, branch=branch)
    call_command("seed_reporting_catalog")

    owner = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=[
            "report.dashboard.read",
            "report.dashboard.compose",
            "report.dataset.read",
            "accounting.report.read",
        ],
    )
    created = owner.post(
        "/api/reporting/saved-views/",
        {
            "name": "TB marzo",
            "dataset_key": "accounting.trial_balance.period",
            "filters": {"year": 2026, "month": 3},
            "render_state": {"layout": "table"},
            "is_shared": True,
        },
        format="json",
    )
    assert created.status_code == 201
    assert created.data["dataset_key"] == "accounting.trial_balance.period"
    assert created.data["is_shared"] is True
    assert created.data["is_owner"] is True

    listed = owner.get("/api/reporting/saved-views/?dataset_key=accounting.trial_balance.period")
    assert listed.status_code == 200
    assert listed.data["count"] >= 1

    detail = owner.get(f"/api/reporting/saved-views/{created.data['view_id']}/")
    assert detail.status_code == 200
    assert detail.data["view_id"] == created.data["view_id"]


@pytest.mark.django_db
def test_reporting_saved_views_requires_compose_permission():
    company, branch = _mk_org()
    _seed_accounting_posted_entries(company=company, branch=branch)
    call_command("seed_reporting_catalog")

    client = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=["report.dashboard.read", "report.dataset.read", "accounting.report.read"],
    )
    denied = client.post(
        "/api/reporting/saved-views/",
        {
            "name": "TB",
            "dataset_key": "accounting.trial_balance.period",
            "filters": {"year": 2026, "month": 3},
        },
        format="json",
    )
    assert denied.status_code == 403


@pytest.mark.django_db
def test_reporting_saved_views_create_requires_domain_permission_and_valid_filters():
    company, branch = _mk_org()
    _seed_accounting_posted_entries(company=company, branch=branch)
    call_command("seed_reporting_catalog")

    missing_domain = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=["report.dashboard.compose", "report.dataset.read"],
    )
    forbidden = missing_domain.post(
        "/api/reporting/saved-views/",
        {
            "name": "TB sin dominio",
            "dataset_key": "accounting.trial_balance.period",
            "filters": {"year": 2026, "month": 3},
        },
        format="json",
    )
    assert forbidden.status_code == 403

    with_domain = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=["report.dashboard.compose", "report.dataset.read", "accounting.report.read"],
    )
    invalid_filters = with_domain.post(
        "/api/reporting/saved-views/",
        {
            "name": "TB inválido",
            "dataset_key": "accounting.trial_balance.period",
            "filters": {"invalid_field": "x"},
        },
        format="json",
    )
    assert invalid_filters.status_code == 400


@pytest.mark.django_db
def test_reporting_saved_views_visibility_owner_shared_and_scope_isolation():
    company_a, branch_a = _mk_org()
    company_b, branch_b = _mk_org()
    _seed_accounting_posted_entries(company=company_a, branch=branch_a)
    _seed_accounting_posted_entries(company=company_b, branch=branch_b)
    call_command("seed_reporting_catalog")

    owner_a = _client_with_perms(
        company=company_a,
        branch=branch_a,
        perm_codes=[
            "report.dashboard.read",
            "report.dashboard.compose",
            "report.dataset.read",
            "accounting.report.read",
        ],
    )
    private_view = owner_a.post(
        "/api/reporting/saved-views/",
        {
            "name": "Privada A",
            "dataset_key": "accounting.trial_balance.period",
            "filters": {"year": 2026, "month": 3},
            "is_shared": False,
        },
        format="json",
    )
    assert private_view.status_code == 201
    shared_view = owner_a.post(
        "/api/reporting/saved-views/",
        {
            "name": "Compartida A",
            "dataset_key": "accounting.trial_balance.period",
            "filters": {"year": 2026, "month": 3},
            "is_shared": True,
        },
        format="json",
    )
    assert shared_view.status_code == 201

    peer_a = _client_with_perms(
        company=company_a,
        branch=branch_a,
        perm_codes=["report.dashboard.read"],
    )
    peer_list = peer_a.get("/api/reporting/saved-views/")
    assert peer_list.status_code == 200
    visible_ids = {row["view_id"] for row in peer_list.data["results"]}
    assert shared_view.data["view_id"] in visible_ids
    assert private_view.data["view_id"] not in visible_ids

    hidden_detail = peer_a.get(f"/api/reporting/saved-views/{private_view.data['view_id']}/")
    assert hidden_detail.status_code == 404
    visible_detail = peer_a.get(f"/api/reporting/saved-views/{shared_view.data['view_id']}/")
    assert visible_detail.status_code == 200

    other_scope = _client_with_perms(
        company=company_b,
        branch=branch_b,
        perm_codes=["report.dashboard.read"],
    )
    other_list = other_scope.get("/api/reporting/saved-views/")
    assert other_list.status_code == 200
    other_ids = {row["view_id"] for row in other_list.data["results"]}
    assert shared_view.data["view_id"] not in other_ids
