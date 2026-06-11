"""Síntesis LLM OPCIONAL del RAG — detrás del kill switch, degradable, con citas.

El LLM (OpenAI-compat: el llama-server local de diagnostics o una API externa) redacta
una respuesta usando SOLO los fragmentos recuperados, citando [n]. Reglas duras:
- Si el kill switch está apagado, no hay URL configurada o CUALQUIER cosa falla →
  devuelve None y el endpoint responde solo con el retrieval determinista (que es
  útil por sí mismo). La síntesis jamás rompe la búsqueda ni lanza.
- `KNOWLEDGE_LLM_BASE_URL` vacío hereda `DIAGNOSTICS_LLM_BASE_URL` (un solo servidor
  local sirve a ambos mundos).
"""
from __future__ import annotations

from typing import Any

import requests
from django.conf import settings

from apps.modulos.diagnostics.flags import ai_features_enabled

_PROMPT_SYSTEM = (
    "Sos el asistente de documentación interna de Necktral (ERP). Respondé en español, "
    "breve y preciso, USANDO SOLO los fragmentos numerados que te paso. Citá cada "
    "afirmación con [n]. Si los fragmentos no contienen la respuesta, decí exactamente: "
    "'La documentación no cubre esto.' No inventés nada."
)


def _llm_config() -> tuple[str, str, float]:
    base = str(getattr(settings, "KNOWLEDGE_LLM_BASE_URL", "") or "").strip()
    if not base:
        base = str(getattr(settings, "DIAGNOSTICS_LLM_BASE_URL", "") or "").strip()
    model = str(getattr(settings, "KNOWLEDGE_LLM_MODEL", "") or "").strip()
    if not model:
        model = str(getattr(settings, "DIAGNOSTICS_LLM_MODEL", "local") or "local")
    timeout = float(getattr(settings, "KNOWLEDGE_LLM_TIMEOUT", 30.0))
    return base.rstrip("/"), model, timeout


def _strip_reasoning(content: str) -> str:
    # Modelos razonadores locales (OpenThinker) envuelven su razonamiento en <think>.
    if "</think>" in content:
        content = content.split("</think>", 1)[1]
    return content.strip()


def synthesize_answer(query: str, results: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Respuesta sintetizada con citas, o None (sin IA / sin config / fallo)."""
    if not results or not ai_features_enabled():
        return None
    base_url, model, timeout = _llm_config()
    if not base_url:
        return None

    fragments = "\n\n".join(
        f"[{i + 1}] ({r['source_path']} — {r['heading'] or 'sin título'})\n{r['excerpt']}"
        for i, r in enumerate(results)
    )
    try:
        resp = requests.post(
            f"{base_url}/v1/chat/completions",
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": _PROMPT_SYSTEM},
                    {"role": "user", "content": f"Pregunta: {query}\n\nFragmentos:\n{fragments}"},
                ],
                "temperature": 0.2,
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        text = _strip_reasoning(str(data["choices"][0]["message"]["content"]))
    except (requests.RequestException, KeyError, ValueError, IndexError, TypeError):
        return None  # degradación: el retrieval determinista queda en pie
    if not text:
        return None
    return {
        "text": text,
        "sources": [
            {"n": i + 1, "source_path": r["source_path"], "heading": r["heading"]}
            for i, r in enumerate(results)
        ],
    }
