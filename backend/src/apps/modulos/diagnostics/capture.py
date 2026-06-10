"""Captura best-effort de errores de runtime → `ErrorEvent`.

Receiver de la señal Django `got_request_exception` (500s no manejados del ciclo
request/response). **Nunca propaga ni altera la respuesta**: todo va envuelto en
try/except, mismo patrón best-effort que el tag de Sentry en
`config/middleware/request_id.py`. Un fallo de diagnóstico jamás debe romper un request.
"""
from __future__ import annotations

import sys
from typing import Any

from django.core.signals import got_request_exception
from django.db import connection
from django.dispatch import receiver


@receiver(got_request_exception)
def capture_request_exception(sender: Any, request: Any = None, **kwargs: Any) -> None:
    try:
        exc_type, exc_value, tb = sys.exc_info()
        if exc_type is None:
            return
        # Si la transacción actual está abortada (p. ej. bajo ATOMIC_REQUESTS), un INSERT
        # fallaría igual: no lo intentamos. Mantiene la captura best-effort y evita tocar
        # una conexión en mal estado.
        if getattr(connection, "needs_rollback", False):
            return
        from .services import record_error_event

        record_error_event(exc_type=exc_type, exc_value=exc_value, tb=tb, request=request)
    except Exception:
        # best-effort: un fallo de la captura de diagnóstico nunca rompe el request.
        pass
