"""Interruptores del subsistema de diagnóstico e IA — el "botón de apagado".

- `diagnostics_enabled()`: observabilidad determinista (captura de errores, ingesta).
  Por defecto **ON**; se apaga con `DIAGNOSTICS_ENABLED=false`.
- `ai_features_enabled()`: **KILL SWITCH de TODA la IA**. Apagado por defecto (opt-in):
  requiere `AI_FEATURES_ENABLED=true` (entorno — hard switch que sobrevive a todo) **Y**
  el interruptor runtime `AIControl.ai_enabled` (el "botón" que un admin apaga sin
  redeploy). **Toda** funcionalidad de IA (gateway, motor de diagnóstico, agentes) DEBE
  consultar esta función antes de actuar.
"""
from __future__ import annotations

from django.conf import settings


def diagnostics_enabled() -> bool:
    return bool(getattr(settings, "DIAGNOSTICS_ENABLED", True))


def ai_features_enabled() -> bool:
    # Hard kill por entorno: si el entorno no habilita IA, nunca corre (sin tocar la DB).
    if not bool(getattr(settings, "AI_FEATURES_ENABLED", False)):
        return False
    from .models import AIControl

    return bool(AIControl.current().ai_enabled)
