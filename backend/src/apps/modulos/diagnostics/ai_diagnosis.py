"""Motor IA advisory de causa raíz (B-5) — SIEMPRE detrás del kill switch.

Rellena la hipótesis de causa de un `DiagnosticRun` usando un `RootCauseProvider`
(por defecto, heurístico determinista). **No corre si la IA está apagada**
(`flags.ai_features_enabled()` = entorno `AI_FEATURES_ENABLED` Y botón `AIControl`).
Es advisory: marca `ai_assisted=True` y deja `human_review` al humano; nunca decide.
Toda corrida deja un `AIAgentRun` (auditoría). Degradable: es un endpoint manual, jamás
en la ruta crítica.
"""
from __future__ import annotations

import time
from typing import Any

from .flags import ai_features_enabled
from .models import AIAgentRun, DiagnosticRun
from .providers import HeuristicRootCauseProvider, RootCauseProvider


class AIDisabledError(RuntimeError):
    """La IA está apagada (kill switch); no se puede correr el diagnóstico advisory."""


def run_ai_diagnosis(
    *, run: DiagnosticRun, provider: RootCauseProvider | None = None, actor: Any = None
) -> DiagnosticRun:
    if not ai_features_enabled():
        raise AIDisabledError("IA apagada (kill switch): encendela en /api/diagnostics/ai-control/")

    prov: RootCauseProvider = provider or HeuristicRootCauseProvider()
    started = time.monotonic()
    proposal = prov.propose(run.evidence)
    latency_ms = int((time.monotonic() - started) * 1000)

    run.root_cause_hypothesis = proposal.hypothesis
    run.recommended_fix = proposal.recommended_fix
    run.recommended_tests = proposal.recommended_tests
    run.confidence = proposal.confidence
    run.ai_assisted = True
    run.generated_by = f"ai:{prov.name}"
    run.save(
        update_fields=[
            "root_cause_hypothesis",
            "recommended_fix",
            "recommended_tests",
            "confidence",
            "ai_assisted",
            "generated_by",
            "updated_at",
        ]
    )

    AIAgentRun.objects.create(
        agent_name="root_cause_advisor",
        model_id=prov.model_id,
        subject_run=run,
        status="completed",
        confidence=proposal.confidence,
        latency_ms=latency_ms,
        created_by=actor if (actor and getattr(actor, "is_authenticated", False)) else None,
    )
    return run
