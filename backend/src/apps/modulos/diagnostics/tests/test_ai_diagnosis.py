"""Tests del motor IA advisory (B-5): SIEMPRE detrás del kill switch.

Con la IA apagada (default) no corre y no toca nada (409 / AIDisabledError). Con la IA
encendida, rellena la hipótesis (advisory), marca ai_assisted y deja un AIAgentRun.
"""
from __future__ import annotations

import uuid
from typing import Any

import pytest
from django.test import override_settings

from apps.modulos.diagnostics.ai_diagnosis import AIDisabledError, run_ai_diagnosis
from apps.modulos.diagnostics.diagnose import create_diagnostic_run
from apps.modulos.diagnostics.models import AIAgentRun, AIControl, ErrorEvent
from apps.modulos.diagnostics.tests._helpers import mk_client, mk_scope


def _err(**kw: Any) -> ErrorEvent:
    defaults: dict[str, Any] = {
        "exception_type": "ValueError",
        "stack_hash": uuid.uuid4().hex,
        "file_path": "backend/src/apps/kernels/payments/services.py",
        "line_number": 100,
        "function_name": "capture",
        "domain": "payments",
        "risk_class": "C1",
        "occurrence_count": 7,
    }
    defaults.update(kw)
    return ErrorEvent.objects.create(**defaults)


@pytest.mark.django_db
def test_ai_diagnosis_blocked_when_ai_off_by_default():
    run = create_diagnostic_run(error=_err())
    with pytest.raises(AIDisabledError):
        run_ai_diagnosis(run=run)
    run.refresh_from_db()
    assert run.ai_assisted is False
    assert run.root_cause_hypothesis == ""
    assert AIAgentRun.objects.count() == 0


@pytest.mark.django_db
@override_settings(AI_FEATURES_ENABLED=True)
def test_ai_diagnosis_fills_hypothesis_when_on():
    run = create_diagnostic_run(error=_err(risk_class="C1", occurrence_count=9))
    run = run_ai_diagnosis(run=run)
    assert run.ai_assisted is True
    assert run.generated_by == "ai:stub"
    assert run.confidence == "low"
    assert run.root_cause_hypothesis != ""
    # señales reflejadas por el heurístico
    assert "recurrente" in run.root_cause_hypothesis or "crítico" in run.root_cause_hypothesis
    assert AIAgentRun.objects.filter(subject_run=run).count() == 1


@pytest.mark.django_db
@override_settings(AI_FEATURES_ENABLED=True)
def test_runtime_button_off_blocks_even_with_env_on():
    ctrl = AIControl.current()
    ctrl.ai_enabled = False
    ctrl.save()
    run = create_diagnostic_run(error=_err())
    with pytest.raises(AIDisabledError):
        run_ai_diagnosis(run=run)


@pytest.mark.django_db
def test_ai_analyze_api_returns_409_when_ai_off():
    run = create_diagnostic_run(error=_err())
    company, branch = mk_scope()
    client = mk_client(
        company=company, branch=branch, perm_codes=["diagnostics.ai_diagnose.run"]
    )
    r = client.post(f"/api/diagnostics/diagnoses/{run.run_id}/ai-analyze/")
    assert r.status_code == 409, r.data


@pytest.mark.django_db
@override_settings(AI_FEATURES_ENABLED=True)
def test_ai_analyze_api_runs_when_on():
    run = create_diagnostic_run(error=_err(risk_class="C1"))
    company, branch = mk_scope()
    client = mk_client(
        company=company, branch=branch, perm_codes=["diagnostics.ai_diagnose.run"]
    )
    r = client.post(f"/api/diagnostics/diagnoses/{run.run_id}/ai-analyze/")
    assert r.status_code == 200, r.data
    assert r.data["ai_assisted"] is True
    assert r.data["root_cause_hypothesis"] != ""


@pytest.mark.django_db
def test_ai_analyze_api_requires_permission():
    from rest_framework.test import APIClient

    run = create_diagnostic_run(error=_err())
    r = APIClient().post(f"/api/diagnostics/diagnoses/{run.run_id}/ai-analyze/")
    assert r.status_code in (401, 403)


@pytest.mark.django_db
def test_seed_grants_ai_diagnose_to_company_admin():
    from apps.modulos.rbac.models import Role, RolePermission
    from apps.modulos.rbac.seed_v01 import seed_rbac_v01

    seed_rbac_v01()
    role = Role.objects.get(name="company_admin")
    codes = set(
        RolePermission.objects.filter(role=role).values_list("permission__code", flat=True)
    )
    assert "diagnostics.ai_diagnose.run" in codes
