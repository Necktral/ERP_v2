"""Tests de B-4: regression-sentinel (fixed→regressed) + gate de release (C1 abierto bloquea).

'La IA diagnostica; los gates bloquean; el humano decide excepciones' — todo sin IA.
"""
from __future__ import annotations

import sys
import uuid
from typing import Any

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.modulos.diagnostics.gates import evaluate_release_gates
from apps.modulos.diagnostics.models import ErrorEvent, SecurityFinding
from apps.modulos.diagnostics.services import record_error_event
from apps.modulos.diagnostics.tests._helpers import mk_client, mk_scope


def _raise_capture() -> ErrorEvent:
    try:
        raise ValueError("boom")
    except ValueError:
        exc_type, exc_value, tb = sys.exc_info()
        assert exc_type is not None
        return record_error_event(exc_type=exc_type, exc_value=exc_value, tb=tb, request=None)


def _err(**kw: Any) -> ErrorEvent:
    defaults: dict[str, Any] = {
        "exception_type": "E",
        "stack_hash": uuid.uuid4().hex,
        "domain": "payments",
        "risk_class": "C1",
        "status": "open",
    }
    defaults.update(kw)
    return ErrorEvent.objects.create(**defaults)


# --- Regression-sentinel --------------------------------------------------------

@pytest.mark.django_db
def test_regression_sentinel_reopens_fixed_error():
    first = _raise_capture()
    ErrorEvent.objects.filter(pk=first.pk).update(status="fixed")
    second = _raise_capture()  # mismo stack_hash → misma fila
    assert second.pk == first.pk
    second.refresh_from_db()
    assert second.status == "regressed"
    assert second.occurrence_count == 2


@pytest.mark.django_db
def test_open_error_reappearing_stays_open():
    first = _raise_capture()
    second = _raise_capture()
    assert second.pk == first.pk  # misma fila (mismo stack_hash)
    second.refresh_from_db()
    assert second.status == "open"  # no estaba 'fixed' → no es regresión


# --- Gate de release ------------------------------------------------------------

@pytest.mark.django_db
def test_gate_blocks_on_open_c1_error():
    _err(risk_class="C1", status="open")
    res = evaluate_release_gates()
    assert res["blocked"] is True
    assert res["counts"]["c1_errors_open"] == 1


@pytest.mark.django_db
def test_gate_passes_without_c1():
    _err(risk_class="C2", domain="reporting", status="open")
    assert evaluate_release_gates()["blocked"] is False


@pytest.mark.django_db
def test_gate_blocks_on_open_c1_finding():
    SecurityFinding.objects.create(
        source_tool="bandit", vuln_id="B101", risk_class="C1", status="open"
    )
    res = evaluate_release_gates()
    assert res["blocked"] is True
    assert res["counts"]["c1_findings_open"] == 1


@pytest.mark.django_db
def test_fixed_c1_error_does_not_block():
    _err(risk_class="C1", status="fixed")
    assert evaluate_release_gates()["blocked"] is False


# --- API + command --------------------------------------------------------------

@pytest.mark.django_db
def test_release_readiness_api_reports_block():
    _err(risk_class="C1", status="open")
    company, branch = mk_scope()
    client = mk_client(company=company, branch=branch, perm_codes=["diagnostics.error.read"])
    r = client.get("/api/diagnostics/release-readiness/")
    assert r.status_code == 200, r.data
    assert r.data["blocked"] is True


@pytest.mark.django_db
def test_release_readiness_requires_permission():
    from rest_framework.test import APIClient

    assert APIClient().get("/api/diagnostics/release-readiness/").status_code in (401, 403)


@pytest.mark.django_db
def test_command_fails_when_c1_open():
    _err(risk_class="C1", status="open")
    with pytest.raises(CommandError):
        call_command("check_release_gates")


@pytest.mark.django_db
def test_command_ok_when_clean():
    call_command("check_release_gates")  # no debe lanzar
