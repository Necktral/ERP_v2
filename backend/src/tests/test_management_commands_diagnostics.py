from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from io import StringIO
from types import SimpleNamespace
from typing import Any

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.kernels.accounting.models import OperationalPostingConfig
from apps.kernels.reporting.models import ReportDatasetDefinition
from apps.kernels.reporting.registry import list_dataset_specs
from apps.modulos.iam.models import OrgUnit

User = get_user_model()


def _mk_scope() -> tuple[OrgUnit, OrgUnit]:
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="H")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="C", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name="B", parent=company)
    return company, branch


def _load_json_stdout(out: StringIO) -> dict:
    return json.loads(out.getvalue().strip())


@pytest.mark.django_db
def test_seed_auth_users_creates_updates_and_controls_secret_output() -> None:
    hidden = StringIO()
    call_command(
        "seed_auth_users",
        admin_username="diag_admin",
        admin_email="admin@test.local",
        admin_password="Admin!12345",
        admin_totp_secret="JBSWY3DPEHPK3PXP",
        admin_enable_2fa=True,
        admin_superuser=True,
        user_username="diag_user",
        user_email="user@test.local",
        user_password="User!12345",
        stdout=hidden,
    )
    admin = User.objects.get(username="diag_admin")
    user = User.objects.get(username="diag_user")
    assert admin.is_staff is True
    assert admin.is_superuser is True
    assert admin.totp_enabled is True
    assert admin.totp_secret == "JBSWY3DPEHPK3PXP"
    assert user.is_staff is False
    assert "ADMIN_TOTP_SECRET" not in hidden.getvalue()

    shown = StringIO()
    call_command(
        "seed_auth_users",
        admin_username="diag_admin",
        admin_email="admin2@test.local",
        admin_password="Admin!67890",
        admin_totp_secret="JBSWY3DPEHPK3PXP",
        admin_enable_2fa=True,
        show_secrets=True,
        user_username="diag_user",
        user_email="user2@test.local",
        user_password="User!67890",
        stdout=shown,
    )
    admin.refresh_from_db()
    assert admin.email == "admin2@test.local"
    assert "ADMIN_TOTP_SECRET: JBSWY3DPEHPK3PXP" in shown.getvalue()


@pytest.mark.django_db
def test_reporting_catalog_commands_seed_verify_and_expose_placeholders() -> None:
    out_seed = StringIO()
    call_command("seed_reporting_catalog", stdout=out_seed)
    assert ReportDatasetDefinition.objects.count() == len(list_dataset_specs())
    assert "created=" in out_seed.getvalue()

    # Segunda corrida valida idempotencia/update path sin duplicar definiciones.
    out_seed_again = StringIO()
    call_command("seed_reporting_catalog", stdout=out_seed_again)
    assert ReportDatasetDefinition.objects.count() == len(list_dataset_specs())
    assert "updated=" in out_seed_again.getvalue()

    out_verify = StringIO()
    call_command("verify_reporting_kernel", stdout=out_verify)
    assert f"registry={len(list_dataset_specs())} datasets" in out_verify.getvalue()
    assert f"persisted={len(list_dataset_specs())}" in out_verify.getvalue()

    out_export = StringIO()
    call_command("export_dataset", stdout=out_export)
    assert "R3 pendiente" in out_export.getvalue()

    out_warm = StringIO()
    call_command("warm_reporting_snapshots", stdout=out_warm)
    assert "R4 pendiente" in out_warm.getvalue()


@pytest.mark.django_db
def test_export_gl_report_command_formats_json_csv_and_validation(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    import apps.kernels.accounting.management.commands.export_gl_report as cmd_mod

    company, _ = _mk_scope()

    monkeypatch.setattr(
        cmd_mod,
        "trial_balance_queryset",
        lambda **kwargs: [
            {
                "account__code": "1101",
                "account__name": "Caja",
                "account__account_type": "ASSET",
                "debit_total": Decimal("10.00"),
                "credit_total": Decimal("0.00"),
            }
        ],
    )
    monkeypatch.setattr(
        cmd_mod,
        "general_ledger_queryset",
        lambda **kwargs: [
            SimpleNamespace(
                journal_entry_id=7,
                journal_entry=SimpleNamespace(entry_date=date(2026, 3, 1), description="entry"),
                line_no=1,
                currency="NIO",
                fx_rate=Decimal("1.00000000"),
                amount_tx=Decimal("10.00"),
                debit_base=Decimal("10.00"),
                credit_base=Decimal("0.00"),
            )
        ],
    )
    monkeypatch.setattr(
        cmd_mod,
        "pnl_report",
        lambda **kwargs: {
            "rows": [
                {
                    "account_code": "4101",
                    "account_name": "Ventas",
                    "account_type": "REVENUE",
                    "debit_total": "0.00",
                    "credit_total": "50.00",
                    "balance": "50.00",
                }
            ],
            "totals": {"revenue": "50.00", "expense": "0.00", "net_income": "50.00"},
        },
    )
    monkeypatch.setattr(
        cmd_mod,
        "balance_sheet_report",
        lambda **kwargs: {
            "assets": {"rows": [], "total": "0.00"},
            "liabilities": {"rows": [], "total": "0.00"},
            "equity": {"rows": [], "total": "0.00"},
        },
    )

    json_out = StringIO()
    call_command("export_gl_report", company_id=company.id, report="trial_balance", format="json", stdout=json_out)
    assert _load_json_stdout(json_out)["rows"][0]["account_code"] == "1101"

    csv_path = tmp_path / "gl.csv"
    call_command(
        "export_gl_report",
        company_id=company.id,
        report="general_ledger",
        account_code=" 1101 ",
        format="csv",
        output=str(csv_path),
    )
    csv_raw = csv_path.read_text(encoding="utf-8")
    assert "journal_entry_id,entry_date,description" in csv_raw
    assert "7,2026-03-01,entry" in csv_raw

    pnl_out = StringIO()
    call_command("export_gl_report", company_id=company.id, report="pnl", format="csv", stdout=pnl_out)
    assert "net_income,50.00" in pnl_out.getvalue()

    bs_out = StringIO()
    call_command("export_gl_report", company_id=company.id, report="balance_sheet", format="csv", stdout=bs_out)
    assert "assets_total" in bs_out.getvalue()

    with pytest.raises(CommandError, match="account-code"):
        call_command("export_gl_report", company_id=company.id, report="general_ledger")
    with pytest.raises(CommandError, match="month debe"):
        call_command("export_gl_report", company_id=company.id, report="trial_balance", year=2026, month=13)


@pytest.mark.django_db
def test_operational_snapshot_and_pilot_commands_cover_rollout_and_errors(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    import apps.kernels.accounting.management.commands.export_operational_load_snapshot as snapshot_cmd
    import apps.kernels.accounting.management.commands.manage_operational_posting_pilot as pilot_cmd
    import apps.modulos.estacion_servicios.services as fuel_services

    company, branch = _mk_scope()
    snapshot_payload = {
        "generated_at": datetime(2026, 3, 1, 10, 0, 0),
        "company_id": company.id,
        "branch_id": branch.id,
        "amount": Decimal("12.34"),
    }
    monkeypatch.setattr(snapshot_cmd, "build_operational_monitor_snapshot", lambda **kwargs: snapshot_payload)
    monkeypatch.setattr(pilot_cmd, "build_operational_monitor_snapshot", lambda **kwargs: snapshot_payload)
    monkeypatch.setattr(
        pilot_cmd,
        "dispatch_outbox_events",
        lambda **kwargs: SimpleNamespace(attempted=1, sent=1, retried=0, failed=0),
    )
    monkeypatch.setattr(
        fuel_services,
        "run_fuel_compensation_cycle",
        lambda **kwargs: SimpleNamespace(attempted=2, succeeded=2, failed=0, still_pending=0, errors=[]),
    )
    monkeypatch.setattr(
        pilot_cmd,
        "close_fiscal_period",
        lambda **kwargs: SimpleNamespace(
            status="CLOSED",
            period_id=5,
            pending_drafts=0,
            was_already_closed=False,
            force_applied=bool(kwargs.get("force")),
            gate_summary={"blocked": False},
        ),
    )

    snap_out = StringIO()
    call_command(
        "export_operational_load_snapshot",
        company_id=company.id,
        branch_id=branch.id,
        date_from="2026-03-01",
        date_to="2026-03-31",
        stdout=snap_out,
    )
    assert _load_json_stdout(snap_out)["amount"] == "12.34"

    out_path = tmp_path / "pilot.json"
    call_command(
        "manage_operational_posting_pilot",
        company_id=company.id,
        branch_id=branch.id,
        action="rollback",
        attempt_close=True,
        force=True,
        year=2026,
        month=3,
        cycles=2,
        dispatch_limit=5,
        fuel_limit=7,
        output=str(out_path),
    )
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["action"] == "rollback"
    assert payload["config_after"]["posting_mode"] == OperationalPostingConfig.PostingMode.DISABLED
    assert payload["rollback_cycle"]["cycles"] == 2
    assert payload["close_attempt"]["ok"] is True

    status_out = StringIO()
    call_command(
        "manage_operational_posting_pilot",
        company_id=company.id,
        branch_id=branch.id,
        action="status",
        stdout=status_out,
    )
    assert _load_json_stdout(status_out)["action"] == "status"

    with pytest.raises(CommandError, match="ambos --date-from"):
        call_command("manage_operational_posting_pilot", company_id=company.id, branch_id=branch.id, action="status", date_from="2026-03-01")
    with pytest.raises(CommandError, match="date-from no puede"):
        call_command(
            "export_operational_load_snapshot",
            company_id=company.id,
            branch_id=branch.id,
            date_from="2026-04-01",
            date_to="2026-03-01",
        )


@pytest.mark.django_db
def test_reverse_journal_entry_command_delegates_and_validates_actor(monkeypatch: pytest.MonkeyPatch) -> None:
    import apps.kernels.accounting.management.commands.reverse_journal_entry as cmd_mod

    captured: dict[str, Any] = {}

    def fake_reverse(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            original_entry_id=10,
            reversal_entry_id=11,
            period_id=12,
            period_year=2026,
            period_month=3,
            idempotent=False,
        )

    monkeypatch.setattr(cmd_mod, "reverse_journal_entry", fake_reverse)
    actor = User.objects.create_user(username="reverse_actor", password="x")

    out = StringIO()
    call_command(
        "reverse_journal_entry",
        company_id=1,
        entry_id=10,
        reason="Ajuste",
        reversal_date="2026-03-31",
        allow_same_poster=True,
        actor_user_id=actor.id,
        stdout=out,
    )
    payload = _load_json_stdout(out)
    assert payload["reversal_entry_id"] == 11
    assert captured["reversal_date"].isoformat() == "2026-03-31"
    assert captured["actor_user"].id == actor.id
    assert captured["allow_same_poster"] is True

    with pytest.raises(CommandError, match="actor-user-id inválido"):
        call_command("reverse_journal_entry", company_id=1, entry_id=10, reason="Ajuste", actor_user_id=999999)
    with pytest.raises(CommandError, match="YYYY-MM-DD"):
        call_command("reverse_journal_entry", company_id=1, entry_id=10, reason="Ajuste", reversal_date="31/03/2026")
