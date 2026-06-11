"""Síntesis LLM OPCIONAL del paquete contador — asesora, detrás del kill switch.

El LLM (OpenAI-compat: el llama-server local de diagnostics o una API externa) redacta
una lectura en lenguaje natural del paquete determinista de `explainer.py`. Reglas duras:
- Si el kill switch está apagado, no hay URL configurada o CUALQUIER cosa falla →
  devuelve None y el endpoint responde solo con el paquete determinista (que es la
  verdad contable por sí mismo). La síntesis jamás rompe el explain ni lanza.
- `CEC_LLM_BASE_URL` vacío hereda `DIAGNOSTICS_LLM_BASE_URL` (un solo servidor local
  sirve a todos los consumidores de IA).
- El texto es ASESOR: se marca `advisory` y nunca alimenta decisiones automáticas.
"""
from __future__ import annotations

import json
from typing import Any

import requests
from django.conf import settings

from apps.modulos.diagnostics.flags import ai_features_enabled

_PROMPT_SYSTEM = (
    "Sos el asistente contable de Necktral (ERP). Te paso el paquete determinista de un "
    "cierre económico (CEC). Redactá en español, breve y claro para el contador: qué pasó "
    "en el cierre, qué bloquea la entrega (si algo la bloquea) y qué conviene revisar "
    "primero. Usá SOLO los datos del paquete; no inventés cifras, fechas ni causas. Si un "
    "dato no está en el paquete, decí que no está. Tu texto es una opinión asesora: la "
    "verdad contable es el paquete."
)

_MAX_EXCEPTIONS_FOR_LLM = 15


def _llm_config() -> tuple[str, str, float]:
    base = str(getattr(settings, "CEC_LLM_BASE_URL", "") or "").strip()
    if not base:
        base = str(getattr(settings, "DIAGNOSTICS_LLM_BASE_URL", "") or "").strip()
    model = str(getattr(settings, "CEC_LLM_MODEL", "") or "").strip()
    if not model:
        model = str(getattr(settings, "DIAGNOSTICS_LLM_MODEL", "local") or "local")
    timeout = float(getattr(settings, "CEC_LLM_TIMEOUT", 30.0))
    return base.rstrip("/"), model, timeout


def _strip_reasoning(content: str) -> str:
    # Modelos razonadores locales (OpenThinker) envuelven su razonamiento en <think>.
    if "</think>" in content:
        content = content.split("</think>", 1)[1]
    return content.strip()


def _compact_package(package: dict[str, Any]) -> dict[str, Any]:
    """Reduce el paquete a lo que el modelo necesita (los locales 7B tienen contexto corto)."""
    failed_gates = [
        {"title": g["title"], "result": g["result_text"], "metric": g["metric"]}
        for g in package.get("gates", [])
        if g.get("applies") and not g.get("passed")
    ]
    open_exceptions = [
        {
            "title": ex["title"],
            "severity": ex["severity_label"],
            "is_blocking": ex["is_blocking"],
            "what_to_check": ex["what_to_check"],
            "details": ex["details"],
        }
        for ex in package.get("exceptions", [])
        if ex.get("status") in ("OPEN", "IN_PROGRESS")
    ][:_MAX_EXCEPTIONS_FOR_LLM]
    return {
        "status": package.get("status"),
        "status_explained": package.get("status_explained"),
        "verdict": package.get("verdict"),
        "consistency_score": package.get("consistency_score"),
        "window_start": package.get("window_start"),
        "window_end": package.get("window_end"),
        "failed_gates": failed_gates,
        "open_exceptions": open_exceptions,
    }


def synthesize_explanation(package: dict[str, Any]) -> dict[str, Any] | None:
    """Lectura asesora del paquete, o None (sin IA / sin config / fallo)."""
    if not ai_features_enabled():
        return None
    base_url, model, timeout = _llm_config()
    if not base_url:
        return None

    compact = json.dumps(_compact_package(package), ensure_ascii=False, sort_keys=True)
    try:
        resp = requests.post(
            f"{base_url}/v1/chat/completions",
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": _PROMPT_SYSTEM},
                    {"role": "user", "content": f"Paquete del cierre:\n{compact}"},
                ],
                "temperature": 0.2,
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        text = _strip_reasoning(str(data["choices"][0]["message"]["content"]))
    except (requests.RequestException, KeyError, ValueError, IndexError, TypeError):
        return None  # degradación: el paquete determinista queda en pie
    if not text:
        return None
    return {"text": text, "advisory": True}
