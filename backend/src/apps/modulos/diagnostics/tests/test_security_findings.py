"""Tests del ledger SecurityFinding (B-2): ingesta, excepciones con vencimiento,
reconciliación, preservación de triage humano y API. Detectan bugs, no pintan verde.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from apps.modulos.diagnostics.findings import (
    ingest_findings,
    load_exceptions,
    parse_npm_findings,
    parse_pip_findings,
)
from apps.modulos.diagnostics.models import SecurityFinding
from apps.modulos.diagnostics.tests._helpers import mk_client, mk_scope

PIP = {
    "dependencies": [
        {
            "name": "somepkg",
            "version": "1.0.0",
            "vulns": [
                {
                    "id": "CVE-2024-0001",
                    "severity": [{"score": 9.1}],
                    "fix_versions": ["1.0.1"],
                }
            ],
        }
    ]
}
NPM = {
    "vulnerabilities": {
        "leftpad": {
            "severity": "high",
            "fixAvailable": {"version": "2.0.0"},
            "via": [{"source": 1234}],
        }
    }
}


def _exc(expires_on: str) -> dict:
    return {
        "version": 1,
        "exceptions": [
            {
                "source": "pip",
                "package": "somepkg",
                "vuln_id": "CVE-2024-0001",
                "expires_on": expires_on,
                "reason": "mitigado en runtime",
            }
        ],
    }


@pytest.mark.django_db
def test_ingest_creates_findings_with_risk_class():
    raw = parse_pip_findings(PIP) + parse_npm_findings(NPM)
    res = ingest_findings(raw_findings=raw, exceptions=[], sources=["pip", "npm"])
    assert res.created == 2
    f = SecurityFinding.objects.get(source_tool="pip", vuln_id="CVE-2024-0001")
    assert f.risk_class == "C2"  # dep high/critical, reachability desconocida → C2 (no C1)
    assert f.status == "open"
    assert f.cve_id == "CVE-2024-0001"
    assert f.fixed_version == "1.0.1"
    n = SecurityFinding.objects.get(source_tool="npm", package="leftpad")
    assert n.severity_raw == "high" and n.risk_class == "C2"


@pytest.mark.django_db
def test_exception_not_expired_marks_accepted_risk():
    future = (date.today() + timedelta(days=30)).isoformat()
    ingest_findings(
        raw_findings=parse_pip_findings(PIP),
        exceptions=load_exceptions(_exc(future)),
        sources=["pip"],
    )
    f = SecurityFinding.objects.get(vuln_id="CVE-2024-0001")
    assert f.status == "accepted_risk"
    assert f.expires_at == date.today() + timedelta(days=30)
    assert f.accepted_risk_reason == "mitigado en runtime"


@pytest.mark.django_db
def test_expired_exception_reopens():
    past = (date.today() - timedelta(days=1)).isoformat()
    ingest_findings(
        raw_findings=parse_pip_findings(PIP),
        exceptions=load_exceptions(_exc(past)),
        sources=["pip"],
    )
    f = SecurityFinding.objects.get(vuln_id="CVE-2024-0001")
    assert f.status == "open"  # excepción vencida vuelve a bloquear


@pytest.mark.django_db
def test_reconciliation_marks_missing_as_fixed():
    ingest_findings(raw_findings=parse_pip_findings(PIP), exceptions=[], sources=["pip"])
    res = ingest_findings(raw_findings=[], exceptions=[], sources=["pip"])
    assert res.resolved == 1
    assert SecurityFinding.objects.get(vuln_id="CVE-2024-0001").status == "fixed"


@pytest.mark.django_db
def test_human_triage_is_preserved_on_reingest():
    ingest_findings(raw_findings=parse_pip_findings(PIP), exceptions=[], sources=["pip"])
    f = SecurityFinding.objects.get(vuln_id="CVE-2024-0001")
    f.status = "false_positive"
    f.save()
    ingest_findings(raw_findings=parse_pip_findings(PIP), exceptions=[], sources=["pip"])
    f.refresh_from_db()
    assert f.status == "false_positive"  # la ingesta NO pisa el triage humano


@pytest.mark.django_db
def test_dedupe_by_natural_key():
    raw = parse_pip_findings(PIP)
    ingest_findings(raw_findings=raw, exceptions=[], sources=["pip"])
    ingest_findings(raw_findings=raw, exceptions=[], sources=["pip"])
    assert SecurityFinding.objects.filter(vuln_id="CVE-2024-0001").count() == 1


@pytest.mark.django_db
def test_findings_api_requires_permission():
    from rest_framework.test import APIClient

    resp = APIClient().get("/api/diagnostics/findings/")
    assert resp.status_code in (401, 403)


@pytest.mark.django_db
def test_findings_api_lists_with_permission():
    ingest_findings(raw_findings=parse_pip_findings(PIP), exceptions=[], sources=["pip"])
    company, branch = mk_scope()
    client = mk_client(company=company, branch=branch, perm_codes=["diagnostics.finding.read"])
    r = client.get("/api/diagnostics/findings/")
    assert r.status_code == 200, r.data
    assert len(r.data["results"]) == 1
    assert r.data["results"][0]["vuln_id"] == "CVE-2024-0001"


@pytest.mark.django_db
def test_seed_grants_finding_read_to_company_admin():
    from apps.modulos.rbac.models import Role, RolePermission
    from apps.modulos.rbac.seed_v01 import seed_rbac_v01

    seed_rbac_v01()
    role = Role.objects.get(name="company_admin")
    codes = set(
        RolePermission.objects.filter(role=role).values_list("permission__code", flat=True)
    )
    assert "diagnostics.finding.read" in codes
