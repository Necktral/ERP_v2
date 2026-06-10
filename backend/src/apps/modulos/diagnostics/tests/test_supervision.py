"""Tests de supervisión determinista: la cola priorizada del *qué falla y por qué*.

Fijan el contrato del `priority_score` (riesgo/estado/frecuencia/recencia/cobertura), las
reglas de alerta, el veredicto de salud y el endpoint. Detectan drift si alguien afloja la
priorización o rompe el desglose auditable. Todo determinista, sin IA.
"""
from __future__ import annotations

import uuid
from typing import Any

import pytest
from django.core.management import call_command

from apps.modulos.diagnostics.models import (
    CodeUnitEvidence,
    DiagnosticRun,
    ErrorEvent,
)
from apps.modulos.diagnostics.supervision import (
    _FREQ_CAP,
    _UNCOVERED_BONUS,
    build_supervision_summary,
)
from apps.modulos.diagnostics.tests._helpers import mk_client, mk_scope


def _err(**kw: Any) -> ErrorEvent:
    defaults: dict[str, Any] = {
        "exception_type": "ValueError",
        "stack_hash": uuid.uuid4().hex,
        "domain": "payments",
        "risk_class": "C1",
        "status": "open",
    }
    defaults.update(kw)
    return ErrorEvent.objects.create(**defaults)


def _item(summary: dict[str, Any], error: ErrorEvent) -> dict[str, Any]:
    by_id = {row["error_id"]: row for row in summary["queue"]}
    return by_id[str(error.error_id)]


# --- Priorización ---------------------------------------------------------------

@pytest.mark.django_db
def test_queue_prioritizes_c1_over_c3():
    c3 = _err(risk_class="C3", domain="reporting")
    c1 = _err(risk_class="C1")
    summary = build_supervision_summary()
    ids = [row["error_id"] for row in summary["queue"]]
    assert ids[0] == str(c1.error_id)  # C1 manda
    assert _item(summary, c1)["priority_score"] > _item(summary, c3)["priority_score"]


@pytest.mark.django_db
def test_regressed_outranks_open_same_risk():
    open_e = _err(risk_class="C2", domain="reporting", status="open")
    regressed = _err(risk_class="C2", domain="reporting", status="regressed")
    summary = build_supervision_summary()
    assert summary["queue"][0]["error_id"] == str(regressed.error_id)
    assert (
        _item(summary, regressed)["priority_score"]
        > _item(summary, open_e)["priority_score"]
    )


@pytest.mark.django_db
def test_uncovered_failing_line_scores_higher():
    covered = _err(file_path="a/covered.py", line_number=20)
    uncovered = _err(file_path="a/uncovered.py", line_number=10)
    CodeUnitEvidence.objects.create(
        path="a/uncovered.py", line_start=10, coverage_state="uncovered", domain="payments"
    )
    summary = build_supervision_summary()
    delta = (
        _item(summary, uncovered)["priority_score"]
        - _item(summary, covered)["priority_score"]
    )
    assert delta == _UNCOVERED_BONUS  # único factor que difiere
    assert _item(summary, uncovered)["score_factors"]["uncovered_line"] == _UNCOVERED_BONUS
    assert _item(summary, covered)["score_factors"]["uncovered_line"] == 0


@pytest.mark.django_db
def test_frequency_contribution_is_capped():
    e = _err(occurrence_count=5000)
    summary = build_supervision_summary()
    assert _item(summary, e)["score_factors"]["frequency"] == _FREQ_CAP


@pytest.mark.django_db
def test_score_factors_sum_equals_score():
    e = _err()
    item = _item(build_supervision_summary(), e)
    assert sum(item["score_factors"].values()) == item["priority_score"]


# --- Alertas --------------------------------------------------------------------

@pytest.mark.django_db
def test_alerts_flag_c1_regression_and_spike():
    _err(risk_class="C1", status="regressed", occurrence_count=50)
    codes = {a["code"] for a in build_supervision_summary()["alerts"]}
    assert {"c1_activo", "regresion", "alta_frecuencia"} <= codes


@pytest.mark.django_db
def test_alert_linea_sin_test_only_for_reachable_risk():
    e = _err(risk_class="C1", file_path="a/x.py", line_number=7)
    CodeUnitEvidence.objects.create(path="a/x.py", line_start=7, coverage_state="uncovered")
    alerts = build_supervision_summary()["alerts"]
    assert any(
        a["code"] == "linea_sin_test" and a["error_id"] == str(e.error_id) for a in alerts
    )


# --- Salud ----------------------------------------------------------------------

@pytest.mark.django_db
def test_health_blocked_when_c1_open():
    _err(risk_class="C1", status="open")
    assert build_supervision_summary()["health"] == "blocked"


@pytest.mark.django_db
def test_health_at_risk_with_c2_but_no_c1():
    _err(risk_class="C2", domain="reporting", status="open")
    summary = build_supervision_summary()
    assert summary["release_gate"]["blocked"] is False
    assert summary["health"] == "at_risk"


@pytest.mark.django_db
def test_health_healthy_without_active_failures():
    _err(risk_class="C1", status="fixed")  # corregido => no activo
    summary = build_supervision_summary()
    assert summary["health"] == "healthy"
    assert summary["queue"] == []
    assert summary["counts"]["total_active"] == 0


# --- El "por qué": enlace a la causa raíz determinista --------------------------

@pytest.mark.django_db
def test_queue_links_latest_diagnostic_run():
    e = _err(risk_class="C1")
    DiagnosticRun.objects.create(
        subject_type="error_event",
        subject_id=str(e.error_id),
        risk_class="C1",
        summary="payments: validación de monto ausente en sucursal X",
    )
    item = _item(build_supervision_summary(), e)
    assert item["has_diagnosis"] is True
    assert item["latest_run_id"] is not None
    assert "sucursal X" in item["why_summary"]


@pytest.mark.django_db
def test_queue_marks_missing_diagnosis():
    e = _err(risk_class="C1")
    item = _item(build_supervision_summary(), e)
    assert item["has_diagnosis"] is False
    assert item["why_summary"] == ""


# --- Endpoint + command ---------------------------------------------------------

@pytest.mark.django_db
def test_supervision_endpoint_returns_summary():
    _err(risk_class="C1", status="open")
    company, branch = mk_scope()
    client = mk_client(company=company, branch=branch, perm_codes=["diagnostics.error.read"])
    r = client.get("/api/diagnostics/supervision/")
    assert r.status_code == 200, r.data
    assert r.data["health"] == "blocked"
    assert len(r.data["queue"]) == 1


@pytest.mark.django_db
def test_supervision_endpoint_requires_permission():
    from rest_framework.test import APIClient

    assert APIClient().get("/api/diagnostics/supervision/").status_code in (401, 403)


@pytest.mark.django_db
def test_supervision_endpoint_rejects_bad_limit():
    company, branch = mk_scope()
    client = mk_client(company=company, branch=branch, perm_codes=["diagnostics.error.read"])
    assert client.get("/api/diagnostics/supervision/?limit=abc").status_code == 400
    assert client.get("/api/diagnostics/supervision/?limit=0").status_code == 400


@pytest.mark.django_db
def test_supervision_command_runs():
    _err(risk_class="C1", status="open")
    call_command("supervision_report")  # legible, no debe lanzar
    call_command("supervision_report", "--json")  # máquina, no debe lanzar
