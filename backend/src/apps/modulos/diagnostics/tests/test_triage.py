"""Tests del triage humano (API + dominio): "el humano decide excepciones", con reglas.

Fijan: las transiciones legales (estados de máquina NO fijables), el rastro de quién
decidió (`owner`), que `accepted_risk` de findings va por el contrato de excepciones
(no por API), que las decisiones humanas son sticky ante la re-ingesta, y que el
centinela de regresión le gana a un `fixed` humano si el fallo reaparece.
"""
from __future__ import annotations

import sys
import uuid

import pytest
from rest_framework.test import APIClient

from apps.modulos.diagnostics.findings import RawFinding, ingest_findings
from apps.modulos.diagnostics.gates import evaluate_release_gates
from apps.modulos.diagnostics.models import ErrorEvent, SecurityFinding
from apps.modulos.diagnostics.services import record_error_event
from apps.modulos.diagnostics.triage import TriageError, triage_error, triage_finding

from ._helpers import mk_client, mk_scope


def _capture(msg: str) -> ErrorEvent:
    try:
        raise RuntimeError(msg)
    except RuntimeError:
        exc_type, exc_value, tb = sys.exc_info()
        assert exc_type is not None
        return record_error_event(exc_type=exc_type, exc_value=exc_value, tb=tb, request=None)


def _mk_error(*, risk: str = "C1", status: str = "open") -> ErrorEvent:
    return ErrorEvent.objects.create(
        exception_type="Boom",
        stack_hash=uuid.uuid4().hex,
        domain="payments",
        risk_class=risk,
        status=status,
    )


def _mk_finding(*, risk: str = "C1", status: str = "open") -> SecurityFinding:
    return SecurityFinding.objects.create(
        source_tool="pip",
        vuln_id=f"CVE-2026-{uuid.uuid4().hex[:6]}",
        package="paquete-x",
        risk_class=risk,
        status=status,
    )


# --- Dominio (sin HTTP) -----------------------------------------------------------

@pytest.mark.django_db
def test_estados_de_maquina_no_son_fijables():
    err = _mk_error()
    with pytest.raises(TriageError):
        triage_error(error=err, status="open", owner="ana")
    with pytest.raises(TriageError):
        triage_error(error=err, status="regressed", owner="ana")
    f = _mk_finding()
    with pytest.raises(TriageError):
        triage_finding(finding=f, status="open", owner="ana")


@pytest.mark.django_db
def test_accepted_risk_de_finding_no_pasa_por_triage():
    # Esa decisión vive en el contrato de excepciones CON VENCIMIENTO.
    f = _mk_finding()
    with pytest.raises(TriageError):
        triage_finding(finding=f, status="accepted_risk", owner="ana")


@pytest.mark.django_db
def test_triage_deja_rastro_de_quien_decidio():
    err = triage_error(error=_mk_error(), status="confirmed", owner="ana.perez")
    assert (err.status, err.owner) == ("confirmed", "ana.perez")


# --- Interacción con la automática (lo importante) --------------------------------

@pytest.mark.django_db
def test_accepted_risk_humano_desbloquea_el_gate():
    _mk_error(risk="C1")
    assert evaluate_release_gates()["blocked"] is True
    err = ErrorEvent.objects.get()
    triage_error(error=err, status="accepted_risk", owner="gerente")
    assert evaluate_release_gates()["blocked"] is False


@pytest.mark.django_db
def test_fixed_humano_pierde_contra_el_centinela_de_regresion():
    # Al ledger no se le puede mentir: 'fixed' que reaparece vuelve a 'regressed'.
    ev = _capture("misma-huella")
    triage_error(error=ev, status="fixed", owner="dev")
    ev2 = _capture("misma-huella")
    assert ev2.error_id == ev.error_id
    assert ev2.status == "regressed"


@pytest.mark.django_db
def test_false_positive_es_sticky_ante_reingesta():
    raw = [
        RawFinding(
            source_tool="pip",
            vuln_id="CVE-2026-0001",
            package="paquete-x",
            severity_raw="high_or_critical",
        )
    ]
    ingest_findings(raw_findings=raw, exceptions=[], sources=["pip"])
    f = SecurityFinding.objects.get()
    triage_finding(finding=f, status="false_positive", owner="ana")
    ingest_findings(raw_findings=raw, exceptions=[], sources=["pip"])
    f.refresh_from_db()
    assert f.status == "false_positive"  # la re-ingesta NO pisa la decisión humana


# --- API -------------------------------------------------------------------------

@pytest.mark.django_db
def test_api_triage_error_confirma_y_firma():
    company, branch = mk_scope()
    client = mk_client(
        company=company, branch=branch, perm_codes=["diagnostics.error.triage"]
    )
    err = _mk_error()
    r = client.post(
        f"/api/diagnostics/errors/{err.error_id}/triage/",
        {"status": "confirmed"},
        format="json",
    )
    assert r.status_code == 200, r.data
    assert r.data["status"] == "confirmed"
    assert r.data["owner"]  # quién decidió queda registrado


@pytest.mark.django_db
def test_api_triage_estado_ilegal_es_400():
    company, branch = mk_scope()
    client = mk_client(
        company=company, branch=branch, perm_codes=["diagnostics.error.triage"]
    )
    err = _mk_error()
    r = client.post(
        f"/api/diagnostics/errors/{err.error_id}/triage/",
        {"status": "regressed"},
        format="json",
    )
    assert r.status_code == 400


@pytest.mark.django_db
def test_api_triage_finding_requiere_permiso():
    company, branch = mk_scope()
    sin_permiso = mk_client(
        company=company, branch=branch, perm_codes=["diagnostics.finding.read"]
    )
    f = _mk_finding()
    r = sin_permiso.post(
        f"/api/diagnostics/findings/{f.finding_id}/triage/",
        {"status": "false_positive"},
        format="json",
    )
    assert r.status_code == 403
    assert APIClient().post(
        f"/api/diagnostics/findings/{f.finding_id}/triage/", {"status": "confirmed"}
    ).status_code in (401, 403)


@pytest.mark.django_db
def test_api_triage_finding_false_positive():
    company, branch = mk_scope()
    client = mk_client(
        company=company, branch=branch, perm_codes=["diagnostics.finding.triage"]
    )
    f = _mk_finding()
    r = client.post(
        f"/api/diagnostics/findings/{f.finding_id}/triage/",
        {"status": "false_positive"},
        format="json",
    )
    assert r.status_code == 200, r.data
    assert r.data["status"] == "false_positive"
