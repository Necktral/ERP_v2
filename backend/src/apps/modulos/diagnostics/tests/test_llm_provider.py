"""Tests del proveedor LLM real para B-5 (`OpenAICompatibleProvider`) — todo con HTTP mockeado.

Fijan: el selector por setting (URL vacía → heurístico), el parseo de la respuesta (incluido
el bloque `<think>` de los modelos de razonamiento), la **degradación** (cualquier fallo del
modelo cae al heurístico, nunca rompe) y que el **kill switch** sigue mandando (IA apagada =>
ni siquiera se llama al modelo). No se levanta ningún modelo: `requests.post` está mockeado.
"""
from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import requests
from django.test import override_settings

from apps.modulos.diagnostics.ai_diagnosis import AIDisabledError, run_ai_diagnosis
from apps.modulos.diagnostics.diagnose import create_diagnostic_run
from apps.modulos.diagnostics.models import AIAgentRun, ErrorEvent
from apps.modulos.diagnostics.providers import (
    HeuristicRootCauseProvider,
    OpenAICompatibleProvider,
    _parse_llm_answer,
    _strip_reasoning,
    get_root_cause_provider,
)

_POST = "apps.modulos.diagnostics.providers.requests.post"

_EVIDENCE: dict[str, Any] = {
    "error": {
        "exception_type": "ValueError",
        "file_path": "backend/src/apps/kernels/payments/services.py",
        "line_number": 184,
        "function_name": "capture_payment",
        "domain": "payments",
        "risk_class": "C1",
        "method": "POST",
        "endpoint": "/api/payments/capture/",
    },
    "signals": ["dominio_C1", "alta_frecuencia"],
    "timeline": {"occurrence_count": 17},
}

# Respuesta típica de un modelo de razonamiento: bloque <think> + respuesta etiquetada.
_LLM_CONTENT = (
    "<think>Es un ValueError en payments, alta frecuencia, dominio C1...</think>\n"
    "HIPOTESIS: validación de monto ausente en la sucursal X\n"
    "FIX: agregar guard de monto > 0 antes de capturar\n"
    "TEST: capturar con monto None y esperar 400"
)


def _fake_response(content: str) -> MagicMock:
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = {"choices": [{"message": {"content": content}}]}
    return resp


def _err(**kw: Any) -> ErrorEvent:
    defaults: dict[str, Any] = {
        "exception_type": "ValueError",
        "stack_hash": uuid.uuid4().hex,
        "file_path": "backend/src/apps/kernels/payments/services.py",
        "line_number": 184,
        "function_name": "capture_payment",
        "domain": "payments",
        "risk_class": "C1",
        "occurrence_count": 17,
    }
    defaults.update(kw)
    return ErrorEvent.objects.create(**defaults)


# --- Selector por setting -------------------------------------------------------

@override_settings(DIAGNOSTICS_LLM_BASE_URL="")
def test_factory_returns_heuristic_when_no_url():
    assert isinstance(get_root_cause_provider(), HeuristicRootCauseProvider)


@override_settings(DIAGNOSTICS_LLM_BASE_URL="http://llm.local:8080", DIAGNOSTICS_LLM_MODEL="openthinker")
def test_factory_returns_llm_when_url_set():
    prov = get_root_cause_provider()
    assert isinstance(prov, OpenAICompatibleProvider)
    assert prov.base_url == "http://llm.local:8080"
    assert prov.model_id == "openthinker"


@override_settings(DIAGNOSTICS_LLM_BASE_URL="http://llm.local:8080", DIAGNOSTICS_LLM_MAX_TOKENS=2048)
def test_factory_pasa_max_tokens_y_el_payload_lo_usa():
    prov = get_root_cause_provider()
    assert prov.max_tokens == 2048
    with patch(_POST, return_value=_fake_response(_LLM_CONTENT)) as post:
        prov.propose(_EVIDENCE)
    assert post.call_args.kwargs["json"]["max_tokens"] == 2048


# --- Parseo ---------------------------------------------------------------------

def test_strip_reasoning_removes_think_block():
    assert _strip_reasoning("<think>razonando</think>\nRESPUESTA").strip() == "RESPUESTA"
    assert _strip_reasoning("sin think").strip() == "sin think"


def test_parse_structured_answer():
    proposal = _parse_llm_answer(_LLM_CONTENT)
    assert proposal is not None
    assert "monto" in proposal.hypothesis
    assert proposal.recommended_fix.startswith("agregar guard")
    assert "monto None" in proposal.recommended_tests
    assert proposal.confidence == "medium"


def test_parse_unstructured_uses_full_text_as_hypothesis():
    proposal = _parse_llm_answer("<think>x</think>\nUna explicación libre sin etiquetas")
    assert proposal is not None
    assert proposal.hypothesis == "Una explicación libre sin etiquetas"
    assert proposal.recommended_fix == ""


def test_parse_empty_returns_none():
    assert _parse_llm_answer("<think>solo razonó</think>") is None


def test_think_sin_cerrar_no_es_respuesta():
    # El modelo agotó max_tokens razonando: NUNCA persistir chain-of-thought como reporte.
    assert _strip_reasoning("<think>razonó y razonó pero se truncó") == ""
    assert _parse_llm_answer("<think>razonó y razonó pero se truncó") is None


def test_parse_tolera_markdown_y_multilinea():
    # Un 7B local real (OpenThinker) responde con negritas y secciones multilínea.
    content = (
        "<think>pensando</think>\n"
        "**HIPOTESIS:**  \nLa división usa dias_laborados sin guard.\n"
        "Pasa en cierres con asistencia vacía.\n"
        "**FIX:**  \n1. Validar dias_laborados > 0.\n2. Retornar 0 si no hay días.\n"
        "**TEST:**  \nCerrar período sin asistencia y esperar séptimo día = 0."
    )
    proposal = _parse_llm_answer(content)
    assert proposal is not None
    assert proposal.hypothesis.startswith("La división usa dias_laborados")
    assert "asistencia vacía" in proposal.hypothesis  # multilínea completa
    assert "Validar dias_laborados > 0" in proposal.recommended_fix
    assert proposal.recommended_tests.startswith("Cerrar período")
    assert proposal.confidence == "medium"


# --- Proveedor LLM (mockeado) ---------------------------------------------------

def test_llm_provider_parses_mocked_response():
    prov = OpenAICompatibleProvider(base_url="http://llm.local:8080", model_id="m")
    with patch(_POST, return_value=_fake_response(_LLM_CONTENT)) as post:
        proposal = prov.propose(_EVIDENCE)
    assert post.called
    assert "monto" in proposal.hypothesis
    assert proposal.confidence == "medium"


def test_llm_provider_degrades_on_network_error():
    prov = OpenAICompatibleProvider(base_url="http://llm.local:8080")
    with patch(_POST, side_effect=requests.ConnectionError("server caído")):
        proposal = prov.propose(_EVIDENCE)
    # Cae al heurístico: nunca rompe; confianza baja delata la degradación.
    assert proposal.confidence == "low"
    assert proposal.hypothesis != ""


def test_llm_provider_degrades_on_bad_payload():
    prov = OpenAICompatibleProvider(base_url="http://llm.local:8080")
    bad = MagicMock()
    bad.raise_for_status.return_value = None
    bad.json.return_value = {"unexpected": "shape"}  # sin choices -> KeyError
    with patch(_POST, return_value=bad):
        proposal = prov.propose(_EVIDENCE)
    assert proposal.confidence == "low"  # degradó al heurístico


def test_llm_provider_degrades_on_http_error():
    prov = OpenAICompatibleProvider(base_url="http://llm.local:8080")
    resp = MagicMock()
    resp.raise_for_status.side_effect = requests.HTTPError("500")
    with patch(_POST, return_value=resp):
        proposal = prov.propose(_EVIDENCE)
    assert proposal.confidence == "low"


# --- Integración con run_ai_diagnosis + kill switch -----------------------------

@pytest.mark.django_db
@override_settings(AI_FEATURES_ENABLED=True, DIAGNOSTICS_LLM_BASE_URL="http://llm.local:8080",
                   DIAGNOSTICS_LLM_MODEL="openthinker-q4")
def test_run_ai_diagnosis_uses_llm_when_configured():
    run = create_diagnostic_run(error=_err())
    with patch(_POST, return_value=_fake_response(_LLM_CONTENT)) as post:
        run = run_ai_diagnosis(run=run)
    assert post.called
    assert run.ai_assisted is True
    assert run.generated_by == "ai:llm"
    assert run.confidence == "medium"
    assert "monto" in run.root_cause_hypothesis
    agent = AIAgentRun.objects.get(subject_run=run)
    assert agent.model_id == "openthinker-q4"


@pytest.mark.django_db
@override_settings(DIAGNOSTICS_LLM_BASE_URL="http://llm.local:8080")
def test_kill_switch_blocks_llm_and_never_calls_model():
    # IA apagada por defecto (AI_FEATURES_ENABLED no seteado) aunque haya URL de LLM.
    run = create_diagnostic_run(error=_err())
    with patch(_POST) as post:
        with pytest.raises(AIDisabledError):
            run_ai_diagnosis(run=run)
    assert not post.called  # ni siquiera se intenta hablar con el modelo
    assert AIAgentRun.objects.count() == 0
