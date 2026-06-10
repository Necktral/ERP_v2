"""Tests del motor de causa raíz determinista (el *por qué* de un fallo, sin IA).

Verifican que la supervisión del fallo arma evidencia (contexto + timeline + relacionados
+ blast radius + señales) y NUNCA inventa la hipótesis con IA (queda para humano/advisory).
"""
from __future__ import annotations

import uuid
from typing import Any

import pytest

from apps.modulos.diagnostics.diagnose import build_evidence_bundle, create_diagnostic_run
from apps.modulos.diagnostics.models import DiagnosticRun, ErrorEvent, SecurityFinding
from apps.modulos.diagnostics.tests._helpers import mk_client, mk_scope

_PAYMENTS_PATH = "backend/src/apps/kernels/payments/services.py"


def _err(**kw: Any) -> ErrorEvent:
    defaults: dict[str, Any] = {
        "exception_type": "ValueError",
        "stack_hash": uuid.uuid4().hex,
        "file_path": _PAYMENTS_PATH,
        "line_number": 100,
        "function_name": "capture",
        "domain": "payments",
        "risk_class": "C1",
        "endpoint": "/api/payments/x/",
        "method": "POST",
        "occurrence_count": 1,
    }
    defaults.update(kw)
    return ErrorEvent.objects.create(**defaults)


@pytest.mark.django_db
def test_evidence_bundle_has_context_timeline_and_signals():
    e = _err(occurrence_count=7)
    b = build_evidence_bundle(e)
    assert b["error"]["domain"] == "payments"
    assert b["error"]["risk_class"] == "C1"
    assert b["timeline"]["occurrence_count"] == 7
    assert "alta_frecuencia" in b["signals"]
    assert "dominio_C1" in b["signals"]


@pytest.mark.django_db
def test_related_errors_same_domain_excludes_self_and_others():
    e = _err(file_path="a/payments/x.py")
    other = _err(file_path="a/payments/y.py")
    unrelated = _err(domain="reporting", file_path="a/reporting/z.py", risk_class="C2")
    b = build_evidence_bundle(e)
    ids = {r["error_id"] for r in b["related_errors"]}
    assert str(other.error_id) in ids
    assert str(e.error_id) not in ids
    assert str(unrelated.error_id) not in ids


@pytest.mark.django_db
def test_related_findings_on_same_file():
    e = _err(file_path=_PAYMENTS_PATH)
    SecurityFinding.objects.create(
        source_tool="bandit", vuln_id="B101", file_path=_PAYMENTS_PATH, risk_class="C1"
    )
    b = build_evidence_bundle(e)
    assert len(b["related_findings"]) == 1
    assert b["related_findings"][0]["source_tool"] == "bandit"


@pytest.mark.django_db
def test_create_run_is_deterministic_without_ai():
    e = _err()
    run = create_diagnostic_run(error=e, trigger_type="manual")
    assert run.ai_assisted is False
    assert run.generated_by == "deterministic"
    assert run.subject_id == str(e.error_id)
    assert run.risk_class == "C1"
    assert run.root_cause_hypothesis == ""  # la IA NO rellena la hipótesis
    assert "PENDIENTE" in run.summary
    assert run.blast_radius["domain"] == "payments"


@pytest.mark.django_db
def test_diagnose_api_creates_run():
    e = _err()
    company, branch = mk_scope()
    client = mk_client(company=company, branch=branch, perm_codes=["diagnostics.diagnose.run"])
    r = client.post(f"/api/diagnostics/errors/{e.error_id}/diagnose/")
    assert r.status_code == 201, r.data
    assert r.data["ai_assisted"] is False
    assert DiagnosticRun.objects.filter(subject_id=str(e.error_id)).count() == 1


@pytest.mark.django_db
def test_diagnose_api_requires_permission():
    from rest_framework.test import APIClient

    e = _err()
    r = APIClient().post(f"/api/diagnostics/errors/{e.error_id}/diagnose/")
    assert r.status_code in (401, 403)


@pytest.mark.django_db
def test_diagnoses_list_with_permission():
    create_diagnostic_run(error=_err())
    company, branch = mk_scope()
    client = mk_client(company=company, branch=branch, perm_codes=["diagnostics.diagnose.read"])
    r = client.get("/api/diagnostics/diagnoses/")
    assert r.status_code == 200, r.data
    assert len(r.data["results"]) == 1


@pytest.mark.django_db
def test_seed_grants_diagnose_perms_to_company_admin():
    from apps.modulos.rbac.models import Role, RolePermission
    from apps.modulos.rbac.seed_v01 import seed_rbac_v01

    seed_rbac_v01()
    role = Role.objects.get(name="company_admin")
    codes = set(
        RolePermission.objects.filter(role=role).values_list("permission__code", flat=True)
    )
    assert {"diagnostics.diagnose.read", "diagnostics.diagnose.run"} <= codes
