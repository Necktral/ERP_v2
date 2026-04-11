from __future__ import annotations

import json
from io import StringIO
from types import SimpleNamespace

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.modulos.iam.models import OrgUnit


def _mk_company(name: str = "Company Test") -> OrgUnit:
    holding = OrgUnit.objects.create(
        unit_type=OrgUnit.UnitType.HOLDING,
        name=f"Holding {name}",
    )
    return OrgUnit.objects.create(
        unit_type=OrgUnit.UnitType.COMPANY,
        name=name,
        parent=holding,
    )


def _dispatch_stats(*, attempted: int = 0, sent: int = 0, retried: int = 0, failed: int = 0) -> SimpleNamespace:
    return SimpleNamespace(
        attempted=attempted,
        sent=sent,
        retried=retried,
        failed=failed,
    )


def _phase7b_evidence(payload: dict, secret: str) -> dict:
    del secret
    return {
        **payload,
        "evidence_hash": "hash",
        "signature_type": "sha256",
    }


@pytest.mark.django_db
def test_run_fx_revaluation_command_success_normalizes_account_codes(monkeypatch: pytest.MonkeyPatch):
    import apps.kernels.accounting.management.commands.run_fx_revaluation as cmd_mod

    captured: dict[str, object] = {}

    def _fake_run_fx_revaluation(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            run_id="fx-1",
            status="COMPLETED",
            idempotent=False,
            entries_created=2,
            issues_count=0,
            summary_json={"ok": True},
        )

    monkeypatch.setattr(cmd_mod, "run_fx_revaluation", _fake_run_fx_revaluation)

    out = StringIO()
    call_command(
        "run_fx_revaluation",
        company_id=7,
        year=2026,
        month=3,
        account_codes=["  1101 ", "ab-2"],
        stdout=out,
    )

    payload = json.loads(out.getvalue().strip())
    assert captured["scope_account_codes"] == ["1101", "AB-2"]
    assert payload["run_id"] == "fx-1"
    assert payload["status"] == "COMPLETED"


@pytest.mark.django_db
def test_run_fx_revaluation_command_blocked_strict_raises(monkeypatch: pytest.MonkeyPatch):
    import apps.kernels.accounting.management.commands.run_fx_revaluation as cmd_mod

    monkeypatch.setattr(
        cmd_mod,
        "run_fx_revaluation",
        lambda **kwargs: SimpleNamespace(
            run_id="fx-2",
            status="BLOCKED",
            idempotent=True,
            entries_created=0,
            issues_count=1,
            summary_json={},
        ),
    )

    with pytest.raises(CommandError, match="FX revaluation blocked"):
        call_command(
            "run_fx_revaluation",
            company_id=8,
            year=2026,
            month=3,
        )


@pytest.mark.django_db
def test_run_intercompany_cycle_command_exports_report(tmp_path, monkeypatch: pytest.MonkeyPatch):
    import apps.kernels.accounting.management.commands.run_intercompany_cycle as cmd_mod

    monkeypatch.setattr(
        cmd_mod,
        "run_intercompany_cycle",
        lambda **kwargs: SimpleNamespace(report={"issues_count": 0, "processed": 4, "confirmed": 4}),
    )
    monkeypatch.setattr(cmd_mod, "dispatch_outbox_events", lambda **kwargs: _dispatch_stats(attempted=2, sent=2))
    monkeypatch.setattr(cmd_mod, "build_phase7b_evidence", _phase7b_evidence)

    out_path = tmp_path / "intercompany_cycle.json"
    call_command(
        "run_intercompany_cycle",
        company_id=3,
        limit=200,
        dispatch_limit=50,
        output=str(out_path),
    )

    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["company_id"] == 3
    assert payload["cycle_passed"] is True
    assert payload["cycle"]["processed"] == 4


@pytest.mark.django_db
def test_run_intercompany_cycle_command_strict_gate_fails(monkeypatch: pytest.MonkeyPatch):
    import apps.kernels.accounting.management.commands.run_intercompany_cycle as cmd_mod

    monkeypatch.setattr(
        cmd_mod,
        "run_intercompany_cycle",
        lambda **kwargs: SimpleNamespace(report={"issues_count": 2}),
    )
    monkeypatch.setattr(cmd_mod, "dispatch_outbox_events", lambda **kwargs: _dispatch_stats())
    monkeypatch.setattr(cmd_mod, "build_phase7b_evidence", _phase7b_evidence)

    with pytest.raises(CommandError, match="intercompany cycle gate failed"):
        call_command(
            "run_intercompany_cycle",
            company_id=3,
        )


@pytest.mark.django_db
def test_run_consolidated_close_command_exports_report(tmp_path, monkeypatch: pytest.MonkeyPatch):
    import apps.kernels.accounting.management.commands.run_consolidated_close as cmd_mod

    monkeypatch.setattr(
        cmd_mod,
        "run_consolidation",
        lambda **kwargs: SimpleNamespace(
            run_id="cons-1",
            status="COMPLETED",
            idempotent=True,
            manifest_hash="manifest",
            issues_count=0,
            summary_json={"lines": 1},
        ),
    )
    monkeypatch.setattr(cmd_mod, "dispatch_outbox_events", lambda **kwargs: _dispatch_stats(attempted=1, sent=1))
    monkeypatch.setattr(cmd_mod, "build_phase7b_evidence", _phase7b_evidence)

    out_path = tmp_path / "consolidated_close.json"
    call_command(
        "run_consolidated_close",
        parent_company_id=10,
        year=2026,
        month=3,
        company_ids=[10, 11],
        output=str(out_path),
    )

    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["run_id"] == "cons-1"
    assert payload["close_passed"] is True


@pytest.mark.django_db
def test_run_consolidated_close_command_strict_gate_fails(monkeypatch: pytest.MonkeyPatch):
    import apps.kernels.accounting.management.commands.run_consolidated_close as cmd_mod

    monkeypatch.setattr(
        cmd_mod,
        "run_consolidation",
        lambda **kwargs: SimpleNamespace(
            run_id="cons-2",
            status="BLOCKED",
            idempotent=False,
            manifest_hash="manifest-2",
            issues_count=1,
            summary_json={"lines": 0},
        ),
    )
    monkeypatch.setattr(cmd_mod, "dispatch_outbox_events", lambda **kwargs: _dispatch_stats())
    monkeypatch.setattr(cmd_mod, "build_phase7b_evidence", _phase7b_evidence)

    with pytest.raises(CommandError, match="consolidated close gate failed"):
        call_command(
            "run_consolidated_close",
            parent_company_id=10,
            year=2026,
            month=3,
            company_ids=[10, 11],
        )


@pytest.mark.django_db
def test_run_phase7_gl_cycle_command_exports_report(tmp_path, monkeypatch: pytest.MonkeyPatch):
    import apps.kernels.accounting.management.commands.run_phase7_gl_cycle as cmd_mod

    dispatch_results = [
        _dispatch_stats(attempted=1, sent=1),
        _dispatch_stats(attempted=2, sent=2),
    ]

    monkeypatch.setattr(cmd_mod, "dispatch_outbox_events", lambda **kwargs: dispatch_results.pop(0))
    monkeypatch.setattr(
        cmd_mod,
        "post_journal_drafts",
        lambda **kwargs: SimpleNamespace(
            attempted=1,
            approved=0,
            posted=1,
            skipped=0,
            failed=0,
            errors=[],
        ),
    )
    monkeypatch.setattr(
        cmd_mod,
        "run_fx_revaluation",
        lambda **kwargs: SimpleNamespace(
            run_id="fx-ok",
            status="COMPLETED",
            idempotent=True,
            entries_created=1,
            issues_count=0,
        ),
    )
    monkeypatch.setattr(
        cmd_mod,
        "collect_phase7_operational_health",
        lambda **kwargs: {
            "inbox_failed_count": 0,
            "outbox_failed_count": 0,
            "unbalanced_entries_count": 0,
            "missing_lines_count": 0,
            "stale_revaluation_count": 0,
        },
    )
    monkeypatch.setattr(
        cmd_mod,
        "build_phase7_evidence",
        lambda payload, secret: {
            **payload,
            "evidence_hash": "phase7-hash",
            "signature_type": "sha256",
        },
    )

    out_path = tmp_path / "phase7_cycle.json"
    call_command(
        "run_phase7_gl_cycle",
        company_id=77,
        run_id="phase7-run",
        output=str(out_path),
    )

    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["cycle_passed"] is True
    assert payload["revaluation"]["status"] == "COMPLETED"
    assert payload["posting"]["failed"] == 0


@pytest.mark.django_db
def test_run_phase7_gl_cycle_command_strict_gate_fails(monkeypatch: pytest.MonkeyPatch):
    import apps.kernels.accounting.management.commands.run_phase7_gl_cycle as cmd_mod

    dispatch_results = [
        _dispatch_stats(),
        _dispatch_stats(),
    ]
    monkeypatch.setattr(cmd_mod, "dispatch_outbox_events", lambda **kwargs: dispatch_results.pop(0))
    monkeypatch.setattr(
        cmd_mod,
        "post_journal_drafts",
        lambda **kwargs: SimpleNamespace(
            attempted=1,
            approved=0,
            posted=0,
            skipped=1,
            failed=1,
            errors=["failed posting"],
        ),
    )
    monkeypatch.setattr(
        cmd_mod,
        "run_fx_revaluation",
        lambda **kwargs: SimpleNamespace(
            run_id="fx-fail",
            status="COMPLETED",
            idempotent=True,
            entries_created=0,
            issues_count=0,
        ),
    )
    monkeypatch.setattr(
        cmd_mod,
        "collect_phase7_operational_health",
        lambda **kwargs: {
            "inbox_failed_count": 0,
            "outbox_failed_count": 0,
            "unbalanced_entries_count": 0,
            "missing_lines_count": 0,
            "stale_revaluation_count": 0,
        },
    )
    monkeypatch.setattr(cmd_mod, "build_phase7_evidence", lambda payload, secret: payload)

    with pytest.raises(CommandError, match="phase7 cycle gate failed"):
        call_command(
            "run_phase7_gl_cycle",
            company_id=77,
        )


@pytest.mark.django_db
def test_export_gl_report_trial_balance_csv(tmp_path, monkeypatch: pytest.MonkeyPatch):
    import apps.kernels.accounting.management.commands.export_gl_report as cmd_mod

    company = _mk_company("GL CSV")
    monkeypatch.setattr(cmd_mod, "resolve_period_range", lambda year=None, month=None: None)
    monkeypatch.setattr(
        cmd_mod,
        "trial_balance_queryset",
        lambda **kwargs: [
            {
                "account__code": "1101",
                "account__name": "Caja",
                "account__account_type": "ASSET",
                "debit_total": "100.00",
                "credit_total": "0.00",
            }
        ],
    )

    out_path = tmp_path / "trial_balance.csv"
    call_command(
        "export_gl_report",
        company_id=company.id,
        report="trial_balance",
        format="csv",
        output=str(out_path),
    )

    csv_raw = out_path.read_text(encoding="utf-8")
    assert "account_code,account_name,account_type,debit_total,credit_total" in csv_raw
    assert "1101,Caja,ASSET,100.00,0.00" in csv_raw


@pytest.mark.django_db
def test_export_gl_report_general_ledger_requires_account_code():
    company = _mk_company("GL Missing Account")
    with pytest.raises(CommandError, match="--account-code es requerido para general_ledger"):
        call_command(
            "export_gl_report",
            company_id=company.id,
            report="general_ledger",
            format="json",
        )


@pytest.mark.django_db
def test_export_reporting_observability_snapshot_output_file(tmp_path, monkeypatch: pytest.MonkeyPatch):
    import apps.kernels.reporting.management.commands.export_reporting_observability_snapshot as cmd_mod

    monkeypatch.setattr(cmd_mod, "build_reporting_observability", lambda **kwargs: {"p95_ms": 100})
    monkeypatch.setattr(cmd_mod, "build_dashboard_observability", lambda **kwargs: {"errors": 0})

    out_path = tmp_path / "snapshot.json"
    call_command(
        "export_reporting_observability_snapshot",
        window_hours=0,
        output=str(out_path),
    )

    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["window_hours"] == 1
    assert payload["reporting"]["p95_ms"] == 100
    assert payload["dashboard"]["errors"] == 0


@pytest.mark.django_db
def test_export_reporting_observability_snapshot_stdout(monkeypatch: pytest.MonkeyPatch):
    import apps.kernels.reporting.management.commands.export_reporting_observability_snapshot as cmd_mod

    monkeypatch.setattr(cmd_mod, "build_reporting_observability", lambda **kwargs: {"window": kwargs["window_hours"]})
    monkeypatch.setattr(cmd_mod, "build_dashboard_observability", lambda **kwargs: {"window": kwargs["window_hours"]})

    out = StringIO()
    call_command(
        "export_reporting_observability_snapshot",
        window_hours=5,
        stdout=out,
    )
    payload = json.loads(out.getvalue().strip())
    assert payload["window_hours"] == 5
    assert payload["reporting"]["window"] == 5
