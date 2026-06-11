"""
Tests del paquete contador del CEC (explainer + síntesis asesora opcional).

Centinelas: cada gate y cada código de excepción que services.py puede emitir DEBE
tener explicación de catálogo (si alguien agrega un control nuevo sin explicarlo,
estos tests fallan). Paquete: cierre limpio, cierre bloqueado, run sin ejecutar,
código desconocido (fallback), invariante de solo-lectura. Síntesis: apagada por
kill switch, degradación ante fallo del LLM, respuesta con mock. API: endpoint
explain con RBAC.
"""
from __future__ import annotations

import inspect
import re
import uuid
from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from apps.modulos.cec import ai_explainer as ai_explainer_mod
from apps.modulos.cec import services as cec_services
from apps.modulos.cec.explainer import (
    _EXCEPTION_EXPLANATIONS,
    _GATE_EXPLANATIONS,
    _STATUS_EXPLANATIONS,
    build_accountant_package,
)
from apps.modulos.cec.models import CECException, CloseRun
from apps.modulos.cec.services import execute_close_run
from apps.modulos.iam.models import OrgUnit, UserMembership
from apps.modulos.integration.models import OutboxEvent
from apps.modulos.rbac.models import Permission, Role, RoleAssignment, RolePermission

User = get_user_model()
UT = OrgUnit.UnitType
S = CloseRun.Status


def _mk_org():
    s = uuid.uuid4().hex[:6]
    holding = OrgUnit.objects.create(unit_type=UT.HOLDING, name=f"H_{s}")
    company = OrgUnit.objects.create(unit_type=UT.COMPANY, name=f"C_{s}", parent=holding)
    branch = OrgUnit.objects.create(unit_type=UT.BRANCH, name=f"B_{s}", parent=company)
    return company, branch


def _window():
    end = timezone.now()
    return end - timedelta(days=1), end


def _executed_run(company, branch):
    run = CloseRun.objects.create(company=company, branch=branch, run_type=CloseRun.RunType.DAILY)
    ws, we = _window()
    execute_close_run(run=run, request=None, actor=None, window_start=ws, window_end=we, strict=True)
    run.refresh_from_db()
    return run


# ---------------------------------------------------------------------------
# Centinelas de cobertura del catálogo
# ---------------------------------------------------------------------------

def test_catalogo_cubre_todos_los_codigos_de_excepcion_de_services():
    src = inspect.getsource(cec_services)
    emitted = set(re.findall(r'"code": "([A-Z][A-Z_0-9]+)"', src))
    assert emitted, "el centinela no encontró códigos en services.py (cambió el formato?)"
    missing = emitted - set(_EXCEPTION_EXPLANATIONS)
    assert not missing, f"códigos de excepción sin explicación de catálogo: {sorted(missing)}"


def test_catalogo_cubre_todos_los_gates_de_services():
    src = inspect.getsource(cec_services)
    emitted = set(re.findall(r'"name": "([a-z][a-z_0-9]+)"', src))
    assert emitted, "el centinela no encontró gates en services.py (cambió el formato?)"
    missing = emitted - set(_GATE_EXPLANATIONS)
    assert not missing, f"gates sin explicación de catálogo: {sorted(missing)}"


def test_todos_los_estados_del_run_tienen_explicacion():
    assert set(_STATUS_EXPLANATIONS) == set(CloseRun.Status.values)


# ---------------------------------------------------------------------------
# Paquete determinista
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_paquete_de_cierre_limpio_listo_para_entrega():
    company, branch = _mk_org()
    run = _executed_run(company, branch)
    assert run.status == S.PACKAGED

    pkg = build_accountant_package(run)
    assert pkg["verdict"]["code"] == "LISTO_PARA_ENTREGA"
    assert pkg["consistency_score"] == 100
    assert pkg["gates"] and all(g["title"] for g in pkg["gates"])
    assert pkg["gates_failed_count"] == 0
    assert pkg["open_exceptions_count"] == 0
    assert pkg["output_manifest_hash"] == run.output_manifest_hash
    assert "100" in pkg["narrative"]
    assert run.output_manifest_hash in pkg["narrative"]
    # Los gates de compras/fiscal B no aplican en una empresa sin actividad.
    na = [g for g in pkg["gates"] if not g["applies"]]
    assert na and all("No aplica" in g["result_text"] for g in na)


@pytest.mark.django_db
def test_paquete_con_excepcion_bloqueante_queda_bloqueado():
    company, branch = _mk_org()
    run = CloseRun.objects.create(
        company=company, branch=branch, run_type=CloseRun.RunType.DAILY, status=S.REOPENED_EXCEPTION
    )
    CECException.objects.create(
        source_module="CEC",
        code="CASH_DIFFERENCE_NONZERO",
        severity=CECException.Severity.HIGH,
        status=CECException.Status.OPEN,
        company=company,
        branch=branch,
        related_object_type="CASH_SESSION",
        related_object_id="7",
        details_json={"difference_amount": "-150.00"},
        is_blocking=True,
        close_run=run,
    )

    pkg = build_accountant_package(run)
    assert pkg["verdict"]["code"] == "BLOQUEADO"
    assert pkg["blocking_open_count"] == 1
    ex = pkg["exceptions"][0]
    assert ex["title"] == "Caja cerró con diferencia"
    assert ex["meaning"] and ex["what_to_check"]
    assert ex["severity_label"] == "Alta"
    assert "Bloquean la entrega" in pkg["narrative"]
    assert "Caja cerró con diferencia" in pkg["narrative"]


@pytest.mark.django_db
def test_paquete_de_run_sin_ejecutar():
    company, branch = _mk_org()
    run = CloseRun.objects.create(company=company, branch=branch, run_type=CloseRun.RunType.DAILY)
    pkg = build_accountant_package(run)
    assert pkg["verdict"]["code"] == "SIN_EJECUTAR"
    assert pkg["gates"] == []
    assert "sin ventana ejecutada" in pkg["narrative"]


@pytest.mark.django_db
def test_codigo_desconocido_usa_fallback_generico():
    company, branch = _mk_org()
    run = CloseRun.objects.create(company=company, branch=branch, run_type=CloseRun.RunType.DAILY)
    CECException.objects.create(
        source_module="MANUAL",
        code="CODIGO_INVENTADO_X1",
        severity=CECException.Severity.LOW,
        company=company,
        branch=branch,
        close_run=run,
    )
    pkg = build_accountant_package(run)
    ex = pkg["exceptions"][0]
    assert ex["title"] == "Excepción CODIGO_INVENTADO_X1"
    assert "MANUAL" in ex["meaning"]


@pytest.mark.django_db
def test_el_paquete_es_solo_lectura():
    company, branch = _mk_org()
    run = _executed_run(company, branch)
    status_before = run.status
    updated_before = run.updated_at
    outbox_before = OutboxEvent.objects.count()
    exceptions_before = CECException.objects.count()

    build_accountant_package(run)

    run.refresh_from_db()
    assert run.status == status_before
    assert run.updated_at == updated_before
    assert OutboxEvent.objects.count() == outbox_before
    assert CECException.objects.count() == exceptions_before


# ---------------------------------------------------------------------------
# Síntesis LLM asesora (opcional, degradable)
# ---------------------------------------------------------------------------

_PKG_MINIMO = {
    "status": "REOPENED_EXCEPTION",
    "status_explained": "Reabierto por excepción",
    "verdict": {"code": "BLOQUEADO", "text": "bloqueado"},
    "consistency_score": 80,
    "window_start": "",
    "window_end": "",
    "gates": [],
    "exceptions": [],
}


def test_sintesis_apagada_por_kill_switch(monkeypatch):
    monkeypatch.setattr(ai_explainer_mod, "ai_features_enabled", lambda: False)
    assert ai_explainer_mod.synthesize_explanation(_PKG_MINIMO) is None


def test_sintesis_sin_url_configurada(monkeypatch, settings):
    monkeypatch.setattr(ai_explainer_mod, "ai_features_enabled", lambda: True)
    settings.CEC_LLM_BASE_URL = ""
    settings.DIAGNOSTICS_LLM_BASE_URL = ""
    assert ai_explainer_mod.synthesize_explanation(_PKG_MINIMO) is None


def test_sintesis_degrada_si_el_llm_falla(monkeypatch, settings):
    monkeypatch.setattr(ai_explainer_mod, "ai_features_enabled", lambda: True)
    settings.CEC_LLM_BASE_URL = "http://llm.test:8080"

    def _boom(url, json=None, timeout=None):
        raise ai_explainer_mod.requests.ConnectionError("llm caído")

    monkeypatch.setattr(ai_explainer_mod.requests, "post", _boom)
    assert ai_explainer_mod.synthesize_explanation(_PKG_MINIMO) is None  # nunca lanza


def test_sintesis_responde_marcada_como_asesora(monkeypatch, settings):
    monkeypatch.setattr(ai_explainer_mod, "ai_features_enabled", lambda: True)
    settings.CEC_LLM_BASE_URL = "http://llm.test:8080"

    def _fake_post(url, json=None, timeout=None):
        assert url == "http://llm.test:8080/v1/chat/completions"
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {
                "choices": [{"message": {"content": "<think>x</think>El cierre está bloqueado por la caja."}}]
            },
        )

    monkeypatch.setattr(ai_explainer_mod.requests, "post", _fake_post)
    out = ai_explainer_mod.synthesize_explanation(_PKG_MINIMO)
    assert out is not None
    assert out["advisory"] is True
    assert out["text"] == "El cierre está bloqueado por la caja."


# ---------------------------------------------------------------------------
# API + RBAC
# ---------------------------------------------------------------------------

def _client_with_perms(*, company, branch, perm_codes):
    username = f"api_{uuid.uuid4().hex[:8]}"
    user = User.objects.create_user(username=username, email=f"{username}@test.local", password="pass12345")
    UserMembership.objects.create(user=user, org_unit=company, is_active=True)
    UserMembership.objects.create(user=user, org_unit=branch, is_active=True)
    role = Role.objects.create(name=f"role_{uuid.uuid4().hex[:8]}", is_active=True)
    for code in perm_codes:
        perm, _ = Permission.objects.get_or_create(code=code, defaults={"description": code, "is_active": True})
        RolePermission.objects.get_or_create(role=role, permission=perm)
    RoleAssignment.objects.create(user=user, role=role, org_unit=company, is_active=True)
    RoleAssignment.objects.create(user=user, role=role, org_unit=branch, is_active=True)

    client = APIClient()
    login = client.post("/api/auth/login/", {"username": username, "password": "pass12345"}, format="json")
    assert login.status_code == 200, login.data
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data.get('access')}")
    client.defaults["HTTP_X_COMPANY_ID"] = str(company.id)
    client.defaults["HTTP_X_BRANCH_ID"] = str(branch.id)
    return client


@pytest.mark.django_db
def test_explain_endpoint_devuelve_paquete():
    company, branch = _mk_org()
    run = _executed_run(company, branch)
    client = _client_with_perms(company=company, branch=branch, perm_codes=["cec.close_run.read"])

    resp = client.get(f"/api/cec/close-runs/{run.run_id}/explain/")
    assert resp.status_code == 200, resp.data
    assert resp.data["verdict"]["code"] == "LISTO_PARA_ENTREGA"
    assert resp.data["narrative"]
    assert resp.data["ai_synthesis"] is None  # kill switch apagado por defecto


@pytest.mark.django_db
def test_explain_endpoint_exige_permiso():
    company, branch = _mk_org()
    run = _executed_run(company, branch)
    client = _client_with_perms(company=company, branch=branch, perm_codes=["cec.exception.read"])

    resp = client.get(f"/api/cec/close-runs/{run.run_id}/explain/")
    assert resp.status_code == 403
