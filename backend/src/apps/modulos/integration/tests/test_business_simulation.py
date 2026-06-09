"""La simulación del spine corre end-to-end y todas las etapas quedan OK."""
from __future__ import annotations

import json

import pytest
from django.core.management import call_command


@pytest.mark.django_db
def test_business_simulation_spine_runs_green(tmp_path):
    report_path = tmp_path / "sim.json"
    call_command("run_business_simulation", "--tag", "test1", "--workers", "2", "--report", str(report_path))

    report = json.loads(report_path.read_text(encoding="utf-8"))
    failed = [s for s in report["stages"] if s["status"] != "OK"]
    assert not failed, f"etapas fallidas: {[(s['stage'], s.get('error')) for s in failed]}"
    assert report["ok"] is True
    stage_names = [s["stage"] for s in report["stages"]]
    assert stage_names == ["org_rbac", "parties_hr", "inventory", "billing", "portfolio", "payroll", "accounting"]


@pytest.mark.django_db
def test_business_simulation_is_idempotent(tmp_path):
    """Re-ejecutar con el mismo tag no rompe (códigos/idempotency keys estables)."""
    call_command("run_business_simulation", "--tag", "idem", "--workers", "1", "--report", str(tmp_path / "a.json"))
    call_command("run_business_simulation", "--tag", "idem", "--workers", "1", "--report", str(tmp_path / "b.json"))
    report = json.loads((tmp_path / "b.json").read_text(encoding="utf-8"))
    assert report["ok"] is True
