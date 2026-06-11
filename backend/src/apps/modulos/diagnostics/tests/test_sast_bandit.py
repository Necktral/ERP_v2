"""Tests de la ingesta SAST (bandit) al ledger SecurityFinding — con dominio C1/C2/C3.

Fijan: el parseo del JSON de bandit, el riesgo **dominio-aware** (un hallazgo severo en
`payments` es C1; el mismo en reporting es C2; low es C3), la dedup por (archivo, test, línea),
las excepciones con vencimiento, la reconciliación y que un C1 bloquea el gate de release.
Determinista, sin IA.
"""
from __future__ import annotations

import json
from datetime import date, timedelta

import pytest
from django.core.management import call_command

from apps.modulos.diagnostics.findings import (
    _normalize_sast_path,
    ingest_findings,
    load_exceptions,
    parse_bandit_findings,
    risk_for_sast,
)
from apps.modulos.diagnostics.gates import evaluate_release_gates
from apps.modulos.diagnostics.models import SecurityFinding

_PAYMENTS_FILE = "/app/backend/src/apps/kernels/payments/services.py"


def _bandit(
    *, test_id: str = "B608", line: int = 42, severity: str = "HIGH", filename: str = _PAYMENTS_FILE
) -> dict:
    return {
        "results": [
            {
                "test_id": test_id,
                "test_name": "hardcoded_sql_expressions",
                "filename": filename,
                "line_number": line,
                "issue_severity": severity,
                "issue_confidence": "MEDIUM",
                "issue_cwe": {"id": 89},
            }
        ]
    }


# --- Clasificación dominio-aware + parseo (sin DB) ------------------------------

def test_risk_for_sast_is_domain_aware():
    assert risk_for_sast("HIGH", "payments") == "C1"  # severo en dinero => crítico
    assert risk_for_sast("HIGH", "reporting") == "C2"
    assert risk_for_sast("HIGH", "unknown") == "C3"
    assert risk_for_sast("MEDIUM", "payments") == "C2"  # medium NO escala a C1
    assert risk_for_sast("LOW", "payments") == "C3"  # baja exposición


def test_normalize_path_strips_container_prefix():
    assert _normalize_sast_path("/app/backend/src/x.py") == "backend/src/x.py"
    assert _normalize_sast_path("backend/src/x.py") == "backend/src/x.py"


def test_parse_bandit_maps_fields():
    rfs = parse_bandit_findings(_bandit())
    assert len(rfs) == 1
    rf = rfs[0]
    assert rf.source_tool == "bandit"
    assert rf.vuln_id == "B608:42"  # dedup por test:línea
    assert rf.package == "backend/src/apps/kernels/payments/services.py"
    assert rf.file_path == rf.package
    assert rf.line_start == 42
    assert rf.symbol == "hardcoded_sql_expressions"
    assert rf.domain == "payments"
    assert rf.cwe_id == "CWE-89"
    assert rf.risk_class == "C1"


def test_parse_skips_incomplete_results():
    payload = {"results": [{"test_id": "", "filename": _PAYMENTS_FILE}, {"filename": _PAYMENTS_FILE}]}
    assert parse_bandit_findings(payload) == []


# --- Ingesta / dedup / dominio (DB) ---------------------------------------------

@pytest.mark.django_db
def test_ingest_bandit_sets_structured_fields():
    ingest_findings(raw_findings=parse_bandit_findings(_bandit()), exceptions=[], sources=["bandit"])
    f = SecurityFinding.objects.get(source_tool="bandit")
    assert f.risk_class == "C1"
    assert f.domain == "payments"
    assert f.file_path.endswith("payments/services.py")
    assert f.line_start == 42
    assert f.symbol == "hardcoded_sql_expressions"
    assert f.cwe_id == "CWE-89"
    assert f.status == "open"


@pytest.mark.django_db
def test_distinct_lines_are_distinct_findings():
    payload = {
        "results": [
            {"test_id": "B608", "filename": _PAYMENTS_FILE, "line_number": 42, "issue_severity": "HIGH"},
            {"test_id": "B608", "filename": _PAYMENTS_FILE, "line_number": 99, "issue_severity": "HIGH"},
        ]
    }
    res = ingest_findings(raw_findings=parse_bandit_findings(payload), exceptions=[], sources=["bandit"])
    assert res.created == 2
    assert SecurityFinding.objects.filter(source_tool="bandit").count() == 2


@pytest.mark.django_db
def test_reingest_same_finding_dedupes():
    raw = parse_bandit_findings(_bandit())
    ingest_findings(raw_findings=raw, exceptions=[], sources=["bandit"])
    ingest_findings(raw_findings=raw, exceptions=[], sources=["bandit"])
    assert SecurityFinding.objects.filter(source_tool="bandit", vuln_id="B608:42").count() == 1


# --- Gate de release ------------------------------------------------------------

@pytest.mark.django_db
def test_bandit_c1_blocks_release_gate():
    ingest_findings(raw_findings=parse_bandit_findings(_bandit(severity="HIGH")), exceptions=[], sources=["bandit"])
    res = evaluate_release_gates()
    assert res["blocked"] is True
    assert res["counts"]["c1_findings_open"] >= 1


@pytest.mark.django_db
def test_bandit_low_severity_does_not_block():
    ingest_findings(
        raw_findings=parse_bandit_findings(_bandit(severity="LOW", test_id="B101")),
        exceptions=[],
        sources=["bandit"],
    )
    assert evaluate_release_gates()["blocked"] is False


# --- Excepciones con vencimiento + reconciliación -------------------------------

def _exc(expires_on: str) -> dict:
    return {
        "exceptions": [
            {
                "source": "bandit",
                "package": "backend/src/apps/kernels/payments/services.py",
                "vuln_id": "B608:42",
                "expires_on": expires_on,
                "reason": "revisado, mitigado en runtime",
            }
        ]
    }


@pytest.mark.django_db
def test_bandit_exception_not_expired_accepts_risk():
    future = (date.today() + timedelta(days=30)).isoformat()
    ingest_findings(
        raw_findings=parse_bandit_findings(_bandit()),
        exceptions=load_exceptions(_exc(future)),
        sources=["bandit"],
    )
    f = SecurityFinding.objects.get(source_tool="bandit")
    assert f.status == "accepted_risk"
    assert f.accepted_risk_reason == "revisado, mitigado en runtime"


@pytest.mark.django_db
def test_bandit_expired_exception_reopens():
    past = (date.today() - timedelta(days=1)).isoformat()
    ingest_findings(
        raw_findings=parse_bandit_findings(_bandit()),
        exceptions=load_exceptions(_exc(past)),
        sources=["bandit"],
    )
    assert SecurityFinding.objects.get(source_tool="bandit").status == "open"


@pytest.mark.django_db
def test_bandit_reconciliation_marks_fixed():
    ingest_findings(raw_findings=parse_bandit_findings(_bandit()), exceptions=[], sources=["bandit"])
    res = ingest_findings(raw_findings=[], exceptions=[], sources=["bandit"])
    assert res.resolved == 1
    assert SecurityFinding.objects.get(source_tool="bandit").status == "fixed"


# --- Comando --------------------------------------------------------------------

@pytest.mark.django_db
def test_command_ingests_bandit_report(tmp_path):
    (tmp_path / "bandit.json").write_text(json.dumps(_bandit()), encoding="utf-8")
    call_command(
        "ingest_security_findings",
        "--root", str(tmp_path),
        "--bandit-report", "bandit.json",
    )
    f = SecurityFinding.objects.get(source_tool="bandit")
    assert f.risk_class == "C1" and f.domain == "payments"
