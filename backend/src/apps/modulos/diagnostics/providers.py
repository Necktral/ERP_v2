"""Proveedores de hipótesis de causa raíz para el motor IA advisory (B-5).

La abstracción `RootCauseProvider` es el **seam** donde se enchufa un modelo real. El
default `HeuristicRootCauseProvider` es **determinista, sin LLM, sin red ni costo**: un
placeholder honesto (no finge ser un modelo) que produce una hipótesis basada en reglas
sobre la evidencia. Un proveedor LLM real (que requerirá key + el gateway de Mundo A y
sigue detrás del kill switch) lo reemplaza más adelante sin tocar el resto del pipeline.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class RootCauseProposal:
    hypothesis: str
    recommended_fix: str
    recommended_tests: str
    confidence: str  # low|medium|high


class RootCauseProvider(Protocol):
    name: str
    model_id: str

    def propose(self, evidence: dict[str, Any]) -> RootCauseProposal: ...


class HeuristicRootCauseProvider:
    """Default: reglas deterministas sobre la evidencia. NO es un LLM (confianza baja)."""

    name = "stub"
    model_id = "heuristic-v1"

    def propose(self, evidence: dict[str, Any]) -> RootCauseProposal:
        err = evidence.get("error", {}) if isinstance(evidence, dict) else {}
        signals = evidence.get("signals", []) if isinstance(evidence, dict) else []
        timeline = evidence.get("timeline", {}) if isinstance(evidence, dict) else {}

        parts: list[str] = []
        if "regresion" in signals:
            parts.append(
                "regresión: un fallo ya corregido reapareció; revisar el fix y agregar "
                "test de no-regresión"
            )
        if "alta_frecuencia" in signals:
            parts.append(f"fallo recurrente ({timeline.get('occurrence_count')} veces); priorizar")
        if "dominio_C1" in signals:
            parts.append(
                f"dominio crítico ({err.get('domain')}): revisar idempotencia y validación de estado"
            )
        if "aislado" in signals or not parts:
            parts.append("fallo aislado; revisar el stack y el contexto del request")

        loc = f"{err.get('file_path')}:{err.get('line_number')}"
        hypothesis = f"{err.get('exception_type')} en {loc}. " + "; ".join(parts) + "."
        tests = (
            f"Agregar test que reproduzca {err.get('exception_type')} en "
            f"{err.get('function_name')}() y cubra el caso límite."
        )
        fix = "Revisar la validación/guard de la función afectada y el manejo de estado del flujo."
        return RootCauseProposal(
            hypothesis=hypothesis,
            recommended_fix=fix,
            recommended_tests=tests,
            confidence="low",
        )
