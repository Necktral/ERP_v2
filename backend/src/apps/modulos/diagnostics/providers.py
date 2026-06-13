"""Proveedores de hipótesis de causa raíz para el motor IA advisory (B-5).

La abstracción `RootCauseProvider` es el **seam** donde se enchufa un modelo real. El
default `HeuristicRootCauseProvider` es **determinista, sin LLM, sin red ni costo**: un
placeholder honesto (no finge ser un modelo) que produce una hipótesis basada en reglas
sobre la evidencia. `OpenAICompatibleProvider` es el **proveedor LLM real** (API
OpenAI-compat, p.ej. un `llama-server` local/offline): el modelo vive FUERA del repo, el
backend solo habla HTTP a `DIAGNOSTICS_LLM_BASE_URL`, es **degradable** (cualquier fallo
cae al heurístico) y sigue **detrás del kill switch**. `get_root_cause_provider()` elige
uno u otro según el setting, sin tocar el resto del pipeline.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Protocol

import requests
from django.conf import settings


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


_PROMPT_SYSTEM = (
    "Sos un analista de causa raíz de software. Respondé SOLO en español, conciso. "
    "Devolvé exactamente tres líneas etiquetadas, sin texto extra, sin markdown ni "
    "negritas:\n"
    "HIPOTESIS: <causa probable>\nFIX: <arreglo sugerido>\nTEST: <test recomendado>"
)


def _build_prompt(evidence: dict[str, Any]) -> str:
    err = evidence.get("error", {}) if isinstance(evidence, dict) else {}
    signals = evidence.get("signals", []) if isinstance(evidence, dict) else []
    timeline = evidence.get("timeline", {}) if isinstance(evidence, dict) else {}
    loc = f"{err.get('file_path')}:{err.get('line_number')}"
    return (
        f"Fallo: {err.get('exception_type')} en {loc}, función {err.get('function_name')}().\n"
        f"Dominio: {err.get('domain')} (riesgo {err.get('risk_class')}).\n"
        f"Endpoint: {err.get('method')} {err.get('endpoint')}.\n"
        f"Ocurrencias: {timeline.get('occurrence_count')}.\n"
        f"Señales: {', '.join(signals) if signals else 'ninguna'}."
    )


def _strip_reasoning(content: str) -> str:
    """Los modelos de razonamiento (p.ej. OpenThinker) emiten `<think>...</think>`; nos
    quedamos con lo que viene DESPUÉS del cierre. Un `<think>` SIN cerrar significa que el
    modelo agotó los tokens razonando: no hay respuesta utilizable (el llamador degrada),
    jamás persistimos chain-of-thought crudo como reporte."""
    marker = "</think>"
    idx = content.rfind(marker)
    if idx != -1:
        return content[idx + len(marker):].strip()
    if "<think>" in content:
        return ""
    return content.strip()


# Etiqueta al inicio de línea, tolerante a markdown (negritas/encabezados/viñetas) y tilde.
_LABEL_RE = re.compile(
    r"^[\s>*#-]*(HIP[ÓO]TESIS|FIX|TEST)[\s*]*:[\s*]*", re.IGNORECASE | re.MULTILINE
)


def _parse_llm_answer(content: str) -> RootCauseProposal | None:
    """Parsea la respuesta etiquetada (HIPOTESIS/FIX/TEST). Si no hay nada usable → None
    (el llamador degrada al heurístico). Tolera markdown (`**HIPOTESIS:**`) y secciones
    multilínea: un 7B local no siempre respeta el formato a la letra."""
    text = _strip_reasoning(content)
    if not text:
        return None
    fields: dict[str, str] = {}
    matches = list(_LABEL_RE.finditer(text))
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        key = m.group(1)[0].lower()  # h|f|t
        value = text[m.end():end].strip().strip("*").strip()
        if key not in fields and value:
            fields[key] = value
    hypothesis = fields.get("h") or text  # sin estructura: el texto completo como hipótesis
    hypothesis = hypothesis.strip()
    if not hypothesis:
        return None
    return RootCauseProposal(
        hypothesis=hypothesis[:2000],
        recommended_fix=fields.get("f", "")[:2000],
        recommended_tests=fields.get("t", "")[:2000],
        confidence="medium",
    )


class OpenAICompatibleProvider:
    """Proveedor LLM real vía API OpenAI-compat (p.ej. `llama-server` local/offline).

    **Degradable:** cualquier fallo (red, timeout, HTTP, JSON, respuesta vacía) cae al
    proveedor heurístico — **nunca rompe** el endpoint. El modelo vive FUERA del repo; el
    backend solo habla HTTP a `base_url`. El kill switch lo chequea `run_ai_diagnosis`
    antes de usar cualquier proveedor.
    """

    name = "llm"

    def __init__(
        self,
        *,
        base_url: str,
        model_id: str = "local",
        timeout: float = 30.0,
        max_tokens: int = 4096,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model_id = model_id
        self.timeout = timeout
        # Presupuesto generoso: un modelo razonador gasta cientos de tokens en <think>
        # ANTES de la respuesta; si se trunca ahí, no hay reporte y se degrada.
        self.max_tokens = max_tokens
        self._fallback = HeuristicRootCauseProvider()

    def propose(self, evidence: dict[str, Any]) -> RootCauseProposal:
        try:
            content = self._chat(evidence)
            parsed = _parse_llm_answer(content)
        except (requests.RequestException, KeyError, ValueError, IndexError, TypeError):
            parsed = None  # degradable: jamás propaga el fallo del modelo
        return parsed if parsed is not None else self._fallback.propose(evidence)

    def _chat(self, evidence: dict[str, Any]) -> str:
        resp = requests.post(
            f"{self.base_url}/v1/chat/completions",
            json={
                "model": self.model_id,
                "messages": [
                    {"role": "system", "content": _PROMPT_SYSTEM},
                    {"role": "user", "content": _build_prompt(evidence)},
                ],
                "temperature": 0.2,
                "max_tokens": self.max_tokens,
                "stream": False,
            },
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        return str(data["choices"][0]["message"]["content"])


def get_root_cause_provider() -> RootCauseProvider:
    """Selector: LLM si hay `DIAGNOSTICS_LLM_BASE_URL`; si no, el heurístico determinista."""
    base_url = str(getattr(settings, "DIAGNOSTICS_LLM_BASE_URL", "") or "").strip()
    if not base_url:
        return HeuristicRootCauseProvider()
    return OpenAICompatibleProvider(
        base_url=base_url,
        model_id=str(getattr(settings, "DIAGNOSTICS_LLM_MODEL", "local") or "local"),
        timeout=float(getattr(settings, "DIAGNOSTICS_LLM_TIMEOUT", 30.0)),
        max_tokens=int(getattr(settings, "DIAGNOSTICS_LLM_MAX_TOKENS", 4096)),
    )
