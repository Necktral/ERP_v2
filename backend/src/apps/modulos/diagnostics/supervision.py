"""Supervisión DETERMINISTA de fallos (Mundo B) — la cola priorizada del *qué falla y por qué*.

El ledger ya guarda **qué** falló (`ErrorEvent`), **por qué** (`DiagnosticRun`) y si la línea
que falló **está testeada** (`CodeUnitEvidence`); los gates dan un veredicto **binario** de
release. Falta lo que el operador necesita a diario: una **cola priorizada** que responda
*qué está fallando AHORA, qué tan grave y por qué*, sin pescar entre cientos de filas.

Todo acá es DETERMINISTA y auditable — esto es **supervisión, no opinión**: el `priority_score`
se arma de factores explícitos (riesgo Necktral + estado + frecuencia + recencia + cobertura de
la línea) y se devuelve su **desglose**. Nada de IA: mismas filas → mismo orden. Es la capa que
materializa el principio rector "*saber por qué falla es lo fundamental*": cruza el fallo con su
causa raíz determinista y con si la línea está cubierta, y lo empuja arriba si es accionable.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from django.utils import timezone

from .gates import evaluate_release_gates
from .models import (
    CodeUnitEvidence,
    CoverageState,
    DiagnosticRun,
    ErrorEvent,
    ErrorStatus,
    RiskClass,
)

# Estados que cuentan como "fallo activo" (necesita atención del operador).
ACTIVE_ERROR_STATES: tuple[str, ...] = (
    ErrorStatus.OPEN,
    ErrorStatus.TRIAGED,
    ErrorStatus.CONFIRMED,
    ErrorStatus.REGRESSED,
)

# Pesos del score — EXPLÍCITOS y versionados: cambiarlos es una decisión de diseño, no un
# parámetro mágico. El riesgo Necktral domina (C1 >> C2 >> C3); el resto matiza el orden.
_RISK_WEIGHT: dict[str, int] = {
    RiskClass.C1.value: 1000,
    RiskClass.C2.value: 100,
    RiskClass.C3.value: 10,
}
_STATUS_BONUS: dict[str, int] = {
    ErrorStatus.REGRESSED.value: 500,  # lo peor: algo "corregido" volvió a romperse
    ErrorStatus.CONFIRMED.value: 60,
    ErrorStatus.TRIAGED.value: 30,
    ErrorStatus.OPEN.value: 20,
}
_FREQ_CAP = 200  # un error ruidoso no debe dominar: el aporte por frecuencia se topa
_RECENT_WINDOW_HOURS = 24
_RECENT_BONUS = 40  # visto en las últimas 24h => sube (supervisión es del AHORA)
_UNCOVERED_BONUS = 80  # la línea que falló NO está testeada => más accionable/riesgoso
_SPIKE_THRESHOLD = 20  # occurrence_count a partir del cual es "alta frecuencia"


def _coverage_index() -> dict[tuple[str, int], str]:
    """Mapa (path, line) -> coverage_state, para anotar la línea exacta que falló."""
    idx: dict[tuple[str, int], str] = {}
    for cu in CodeUnitEvidence.objects.all().only("path", "line_start", "coverage_state"):
        idx[(cu.path, cu.line_start)] = cu.coverage_state
    return idx


def _latest_run_index() -> dict[str, DiagnosticRun]:
    """Último `DiagnosticRun` por error. El qs viene ordenado `-created_at` (Meta), así que
    el primero que veo de cada `subject_id` es el más reciente."""
    latest: dict[str, DiagnosticRun] = {}
    for run in DiagnosticRun.objects.filter(subject_type="error_event"):
        if run.subject_id not in latest:
            latest[run.subject_id] = run
    return latest


def score_error(
    error: ErrorEvent, *, coverage_state: str | None = None, now: datetime | None = None
) -> tuple[int, dict[str, int]]:
    """Score de prioridad DETERMINISTA + su desglose (transparente, suma exacta)."""
    now = now or timezone.now()
    risk = _RISK_WEIGHT.get(error.risk_class, _RISK_WEIGHT[RiskClass.C3.value])
    status_bonus = _STATUS_BONUS.get(error.status, 0)
    frequency = min(int(error.occurrence_count), _FREQ_CAP)
    recency = 0
    if error.last_seen_at and error.last_seen_at >= now - timedelta(hours=_RECENT_WINDOW_HOURS):
        recency = _RECENT_BONUS
    uncovered = _UNCOVERED_BONUS if coverage_state == CoverageState.UNCOVERED else 0
    factors = {
        "risk": risk,
        "status": status_bonus,
        "frequency": frequency,
        "recency": recency,
        "uncovered_line": uncovered,
    }
    return sum(factors.values()), factors


def _alerts_for(error: ErrorEvent, coverage_state: str | None) -> list[dict[str, str]]:
    """Reglas de alerta DETERMINISTAS sobre un fallo activo."""
    out: list[dict[str, str]] = []
    if error.risk_class == RiskClass.C1:
        out.append({"level": "critical", "code": "c1_activo", "message": "Fallo C1 activo"})
    if error.status == ErrorStatus.REGRESSED:
        out.append(
            {"level": "critical", "code": "regresion", "message": "Regresión: un fallo corregido reapareció"}
        )
    if int(error.occurrence_count) >= _SPIKE_THRESHOLD:
        out.append(
            {
                "level": "warning",
                "code": "alta_frecuencia",
                "message": f"Alta frecuencia: {error.occurrence_count} ocurrencias",
            }
        )
    if coverage_state == CoverageState.UNCOVERED and error.risk_class in (
        RiskClass.C1,
        RiskClass.C2,
    ):
        out.append(
            {
                "level": "warning",
                "code": "linea_sin_test",
                "message": "La línea que falló no está cubierta por tests",
            }
        )
    return out


# Orden de severidad de alertas para un volcado determinista.
_ALERT_LEVEL_ORDER = {"critical": 0, "warning": 1, "info": 2}


def build_supervision_summary(*, limit: int = 20, now: datetime | None = None) -> dict[str, Any]:
    """Supervisión determinista: salud global + alertas + cola priorizada con el *por qué*.

    `health`:
      - `blocked`  si el gate de release bloquea (hay C1 abierto, error o hallazgo);
      - `at_risk`  si hay fallos activos C1/C2 o alguna alerta, pero el gate no bloquea;
      - `healthy`  si no hay fallos activos relevantes.
    """
    now = now or timezone.now()
    coverage = _coverage_index()
    runs = _latest_run_index()

    active = list(ErrorEvent.objects.filter(status__in=list(ACTIVE_ERROR_STATES)))

    counts_by_risk: dict[str, int] = {
        RiskClass.C1.value: 0,
        RiskClass.C2.value: 0,
        RiskClass.C3.value: 0,
    }
    counts_by_status: dict[str, int] = {}
    uncovered_active = 0
    alerts: list[dict[str, str]] = []
    scored: list[tuple[int, dict[str, int], ErrorEvent, str | None, DiagnosticRun | None]] = []

    for error in active:
        cstate = coverage.get((error.file_path, error.line_number))
        score, factors = score_error(error, coverage_state=cstate, now=now)
        run = runs.get(str(error.error_id))

        counts_by_risk[error.risk_class] = counts_by_risk.get(error.risk_class, 0) + 1
        counts_by_status[error.status] = counts_by_status.get(error.status, 0) + 1
        if cstate == CoverageState.UNCOVERED:
            uncovered_active += 1
        for alert in _alerts_for(error, cstate):
            alerts.append({**alert, "error_id": str(error.error_id)})

        scored.append((score, factors, error, cstate, run))

    # Orden determinista: score desc, luego más reciente, luego id (desempate estable).
    scored.sort(key=lambda t: (-t[0], -t[2].last_seen_at.timestamp(), str(t[2].error_id)))
    alerts.sort(key=lambda a: (_ALERT_LEVEL_ORDER.get(a["level"], 9), a["code"], a["error_id"]))

    queue: list[dict[str, Any]] = []
    for score, factors, error, cstate, run in scored[:limit]:
        queue.append(
            {
                "error_id": str(error.error_id),
                "exception_type": error.exception_type,
                "domain": error.domain,
                "risk_class": error.risk_class,
                "status": error.status,
                "occurrence_count": error.occurrence_count,
                "last_seen_at": error.last_seen_at.isoformat(),
                "endpoint": error.endpoint,
                "location": f"{error.file_path}:{error.line_number}" if error.file_path else "",
                "coverage_state": cstate or CoverageState.UNKNOWN.value,
                "priority_score": score,
                "score_factors": factors,
                # El *por qué*: causa raíz determinista ya calculada, si existe.
                "has_diagnosis": run is not None,
                "latest_run_id": str(run.run_id) if run else None,
                "why_summary": run.summary if run else "",
            }
        )

    gate = evaluate_release_gates()
    total_active = len(active)
    if gate["blocked"]:
        health = "blocked"
    elif counts_by_risk[RiskClass.C1.value] or counts_by_risk[RiskClass.C2.value] or alerts:
        health = "at_risk"
    else:
        health = "healthy"

    return {
        "generated_at": now.isoformat(),
        "health": health,
        "counts": {
            "total_active": total_active,
            "by_risk": counts_by_risk,
            "by_status": counts_by_status,
            "uncovered_active": uncovered_active,
            "regressions": counts_by_status.get(ErrorStatus.REGRESSED.value, 0),
        },
        "release_gate": gate,
        "alerts": alerts,
        "queue": queue,
    }
