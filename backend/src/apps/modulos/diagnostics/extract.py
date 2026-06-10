"""Funciones puras de extracción/redacción para el ledger de diagnóstico.

Sin dependencias de Django ORM ni de señales: facilita el testeo unitario y evita el
ciclo de importación entre `capture` (señal) y `services` (persistencia). Cumple **J2**
(cero secretos/PII): el stack se arma con SOLO los frames (archivo/línea/código del
repo) — el mensaje de la excepción nunca se guarda crudo (va hasheado aparte) — y encima
se pasa un scrub de `clave=valor` sensibles como defensa en profundidad.
"""
from __future__ import annotations

import hashlib
import re
import traceback
from types import TracebackType

_SRC_MARKER = "backend/src/"
_APP_FRAME_RE = re.compile(r"apps/(?:kernels|modulos)/")
# Redacta de la clave sensible hasta fin de línea (cubre valores multi-token tipo
# "Authorization: Bearer <jwt>"). Sobre-redactar una traza es seguro; subredactar no.
_SECRET_KV_RE = re.compile(
    r"(?i)\b(password|passwd|secret|token|api[_-]?key|authorization|cookie|hmac|private[_-]?key)\b"
    r"(\s*[=:]\s*).*"
)
_MAX_STACK_CHARS = 8000


def normalize_path(path: str) -> str:
    """Recorta hasta `backend/src/` para que el hash sea estable entre entornos."""
    p = (path or "").replace("\\", "/")
    idx = p.find(_SRC_MARKER)
    return p[idx + len(_SRC_MARKER) :] if idx >= 0 else p


def scrub_secrets(text: str) -> str:
    """Redacta patrones `clave=valor`/`clave: valor` sensibles en texto libre."""
    return _SECRET_KV_RE.sub(r"\1\2***REDACTED***", text)


def pick_app_frame(tb: TracebackType | None) -> tuple[str, int, str]:
    """Frame más profundo del repo: (file_path, line_number, function_name)."""
    chosen: tuple[str, int, str] = ("", 0, "")
    cur = tb
    while cur is not None:
        code = cur.tb_frame.f_code
        if _APP_FRAME_RE.search(code.co_filename.replace("\\", "/")):
            chosen = (normalize_path(code.co_filename), cur.tb_lineno, code.co_name)
        cur = cur.tb_next
    return chosen


def stack_hash(exc_type: type, tb: TracebackType | None) -> str:
    """Huella estable del stack (tipo + frames normalizados) para deduplicar."""
    parts = [getattr(exc_type, "__name__", "Error")]
    cur = tb
    while cur is not None:
        code = cur.tb_frame.f_code
        parts.append(f"{normalize_path(code.co_filename)}:{code.co_name}:{cur.tb_lineno}")
        cur = cur.tb_next
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def redacted_stack(tb: TracebackType | None) -> str:
    """Traza solo-frames (sin el mensaje de la excepción), scrubbeada y truncada."""
    text = "".join(traceback.format_tb(tb))
    return scrub_secrets(text)[:_MAX_STACK_CHARS]


def message_hash(exc_value: BaseException | None) -> str:
    """Hash del mensaje (nunca se guarda el mensaje crudo)."""
    msg = str(exc_value) if exc_value is not None else ""
    return hashlib.sha256(msg.encode("utf-8")).hexdigest()
