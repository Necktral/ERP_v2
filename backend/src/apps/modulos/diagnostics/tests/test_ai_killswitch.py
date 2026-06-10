"""Tests del botón de apagado de la IA (kill switch) + interruptor de observabilidad.

Verifican: la IA está APAGADA por defecto; el flag de entorno es un hard-switch que
manda sobre el botón runtime; el botón runtime apaga la IA en caliente; el subsistema de
diagnóstico se puede apagar (la captura deja de registrar); y la API del botón está gateada.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from django.core.signals import got_request_exception
from django.test import override_settings

from apps.modulos.diagnostics.flags import ai_features_enabled, diagnostics_enabled
from apps.modulos.diagnostics.models import AIControl, ErrorEvent
from apps.modulos.diagnostics.tests._helpers import mk_client, mk_scope


@override_settings(AI_FEATURES_ENABLED=False)
def test_ai_is_off_by_default_via_env_without_db():
    # Hard-off por entorno: ni siquiera toca la DB.
    assert ai_features_enabled() is False


@pytest.mark.django_db
@override_settings(AI_FEATURES_ENABLED=True)
def test_ai_on_requires_env_and_runtime_button():
    assert ai_features_enabled() is True  # AIControl arranca encendido
    ctrl = AIControl.current()
    ctrl.ai_enabled = False
    ctrl.save()
    assert ai_features_enabled() is False  # el botón runtime lo apaga


@pytest.mark.django_db
@override_settings(AI_FEATURES_ENABLED=False)
def test_env_hard_off_overrides_runtime_on():
    ctrl = AIControl.current()
    ctrl.ai_enabled = True
    ctrl.save()
    assert ai_features_enabled() is False  # el entorno manda


@override_settings(DIAGNOSTICS_ENABLED=False)
def test_diagnostics_subsystem_can_be_disabled():
    assert diagnostics_enabled() is False


@pytest.mark.django_db
@override_settings(DIAGNOSTICS_ENABLED=False)
def test_capture_noops_when_diagnostics_disabled():
    req = SimpleNamespace(
        request_id="off12345678", path="/x/", method="GET", company=None, branch=None
    )
    try:
        raise ValueError("boom")
    except ValueError:
        got_request_exception.send(sender=None, request=req)
    assert ErrorEvent.objects.count() == 0  # captura apagada → nada se registra


@pytest.mark.django_db
def test_aicontrol_singleton_is_stable():
    a = AIControl.current()
    a.ai_enabled = False
    a.save()
    b = AIControl.current()
    assert a.pk == b.pk == AIControl.SINGLETON_ID
    assert AIControl.objects.count() == 1
    assert b.ai_enabled is False


@pytest.mark.django_db
def test_ai_control_api_get_and_toggle():
    company, branch = mk_scope()
    client = mk_client(
        company=company,
        branch=branch,
        perm_codes=["diagnostics.ai_control.read", "diagnostics.ai_control.manage"],
    )
    r = client.get("/api/diagnostics/ai-control/")
    assert r.status_code == 200, r.data
    assert r.data["ai_enabled"] is True

    r = client.post(
        "/api/diagnostics/ai-control/", {"enabled": False, "reason": "pánico"}, format="json"
    )
    assert r.status_code == 200, r.data
    assert r.data["ai_enabled"] is False
    assert AIControl.current().ai_enabled is False


@pytest.mark.django_db
def test_ai_control_toggle_requires_manage_permission():
    company, branch = mk_scope()
    client = mk_client(
        company=company, branch=branch, perm_codes=["diagnostics.ai_control.read"]
    )  # solo lectura
    r = client.post("/api/diagnostics/ai-control/", {"enabled": False}, format="json")
    assert r.status_code in (401, 403)
