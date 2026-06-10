"""Captura best-effort de errores de runtime → `ErrorEvent`.

Dos puertas de entrada al ledger:

- HTTP: receiver de la señal Django `got_request_exception` (500s no manejados del
  ciclo request/response). **Nunca propaga ni altera la respuesta**.
- Fuera de HTTP: el context manager `captured(source=...)` para management commands
  y jobs — registra el fallo y lo RE-LANZA (la captura observa, no se traga errores).

Todo va envuelto en try/except, mismo patrón best-effort que el tag de Sentry en
`config/middleware/request_id.py`. Un fallo de diagnóstico jamás debe romper nada.
"""
from __future__ import annotations

import sys
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any, Iterator

from django.core.signals import got_request_exception
from django.db import connection
from django.dispatch import receiver

from .flags import diagnostics_enabled


@receiver(got_request_exception)
def capture_request_exception(sender: Any, request: Any = None, **kwargs: Any) -> None:
    try:
        if not diagnostics_enabled():
            return  # interruptor del subsistema de observabilidad
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


@contextmanager
def captured(*, source: str) -> Iterator[None]:
    """Captura fuera del ciclo HTTP (commands, jobs): registra el fallo y RE-LANZA.

    `source` identifica el origen (p. ej. "command:ingest_security_findings") y queda
    en `endpoint` (method="CLI") para que la supervisión lo distinga de un 500 web.
    La escritura al ledger es best-effort: si la propia captura falla, el error
    ORIGINAL sigue propagándose intacto.
    """
    try:
        yield
    except Exception:
        try:
            if diagnostics_enabled():
                exc_type, exc_value, tb = sys.exc_info()
                if exc_type is not None:
                    from .services import record_error_event

                    shim = SimpleNamespace(
                        path=source, method="CLI", request_id="", company=None, branch=None
                    )
                    record_error_event(
                        exc_type=exc_type, exc_value=exc_value, tb=tb, request=shim
                    )
        except Exception:
            pass  # la captura nunca reemplaza ni oculta el fallo original
        raise
