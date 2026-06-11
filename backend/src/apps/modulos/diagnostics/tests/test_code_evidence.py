"""Tests de la 'línea de falla' (CodeUnitEvidence): ¿la línea que falló está testeada?

Sin IA: parsea coverage.xml, ata la línea del fallo a su cobertura, y lo integra al *por qué*.
"""
from __future__ import annotations

import uuid
from typing import Any

import pytest

from apps.modulos.diagnostics.code_evidence import ingest_code_evidence
from apps.modulos.diagnostics.coverage import coverage_state_for_line, parse_coverage_xml
from apps.modulos.diagnostics.diagnose import build_evidence_bundle, summarize
from apps.modulos.diagnostics.models import CodeUnitEvidence, ErrorEvent
from apps.modulos.diagnostics.tests._helpers import mk_client, mk_scope

_PATH = "apps/kernels/payments/services.py"

COV_XML = """<?xml version="1.0"?>
<coverage><packages><package><classes>
<class filename="src/apps/kernels/payments/services.py">
<lines><line number="100" hits="0"/><line number="101" hits="3"/></lines>
</class>
</classes></package></packages></coverage>"""


def _err(**kw: Any) -> ErrorEvent:
    defaults: dict[str, Any] = {
        "exception_type": "ValueError",
        "stack_hash": uuid.uuid4().hex,
        "file_path": _PATH,
        "line_number": 100,
        "domain": "payments",
        "risk_class": "C1",
    }
    defaults.update(kw)
    return ErrorEvent.objects.create(**defaults)


def test_parse_and_coverage_state_normalizes_paths():
    cov = parse_coverage_xml(COV_XML)
    # distintos prefijos, mismo archivo → match
    assert coverage_state_for_line(cov, "backend/src/apps/kernels/payments/services.py", 100) == "uncovered"
    assert coverage_state_for_line(cov, "/app/backend/src/apps/kernels/payments/services.py", 101) == "covered"
    assert coverage_state_for_line(cov, _PATH, 999) == "unknown"  # línea no medida
    assert coverage_state_for_line(cov, "apps/otro/x.py", 1) == "unknown"  # archivo no medido


def test_parse_empty_or_garbage_is_safe():
    assert parse_coverage_xml("") == {}
    assert parse_coverage_xml("no es xml <<<") == {}


@pytest.mark.django_db
def test_ingest_links_failing_line_to_coverage():
    e = _err(line_number=100)
    res = ingest_code_evidence(cov_map=parse_coverage_xml(COV_XML))
    assert res["created"] == 1
    cue = CodeUnitEvidence.objects.get(path=_PATH, line_start=100)
    assert cue.coverage_state == "uncovered"
    assert str(e.error_id) in cue.error_refs
    assert cue.domain == "payments"


@pytest.mark.django_db
def test_diagnose_bundle_surfaces_uncovered_line():
    e = _err(line_number=100)
    CodeUnitEvidence.objects.create(
        path=_PATH, line_start=100, coverage_state="uncovered", domain="payments"
    )
    bundle = build_evidence_bundle(e)
    assert bundle["coverage"]["state"] == "uncovered"
    assert "linea_sin_test" in bundle["signals"]
    assert "NO está cubierta" in summarize(e, bundle)


@pytest.mark.django_db
def test_diagnose_bundle_no_coverage_when_unknown():
    e = _err()
    bundle = build_evidence_bundle(e)  # sin CodeUnitEvidence ingerido
    assert bundle["coverage"] is None
    assert "linea_sin_test" not in bundle["signals"]


@pytest.mark.django_db
def test_code_evidence_api_lists_with_permission():
    CodeUnitEvidence.objects.create(path=_PATH, line_start=100, coverage_state="uncovered")
    company, branch = mk_scope()
    client = mk_client(company=company, branch=branch, perm_codes=["diagnostics.error.read"])
    r = client.get("/api/diagnostics/code-evidence/?coverage_state=uncovered")
    assert r.status_code == 200, r.data
    assert len(r.data["results"]) == 1
    assert r.data["results"][0]["coverage_state"] == "uncovered"


@pytest.mark.django_db
def test_code_evidence_api_requires_permission():
    from rest_framework.test import APIClient

    assert APIClient().get("/api/diagnostics/code-evidence/").status_code in (401, 403)
