"""Persistencia del ledger de `ErrorEvent` (dedupe por `stack_hash`).

`record_error_event` es el único punto de escritura: clasifica dominio + riesgo,
redacta, y hace upsert por `stack_hash` (misma huella → `occurrence_count++`). Cumple
**J1** (correlation_id/domain/risk_class siempre), **J2** (redacción), **J5** (dedupe).
"""
from __future__ import annotations

from types import TracebackType
from typing import Any

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .domain_map import domain_for_path, risk_class_for_domain
from .extract import (
    message_hash,
    pick_app_frame,
    redacted_stack,
    stack_hash,
)
from .models import ErrorEvent, ErrorStatus


def record_error_event(
    *,
    exc_type: type[BaseException],
    exc_value: BaseException | None,
    tb: TracebackType | None,
    request: Any = None,
) -> ErrorEvent:
    file_path, line_number, function_name = pick_app_frame(tb)
    domain = domain_for_path(file_path)
    risk = risk_class_for_domain(domain)
    shash = stack_hash(exc_type, tb)

    endpoint = (getattr(request, "path", "") or "")[:512]
    method = (getattr(request, "method", "") or "")[:16]
    correlation_id = (getattr(request, "request_id", "") or "")[:64]
    company = getattr(request, "company", None)
    company_id = (str(getattr(company, "id", "") or ""))[:64]
    branch = getattr(request, "branch", None)
    branch_id = (str(getattr(branch, "id", "") or ""))[:64]

    now = timezone.now()
    with transaction.atomic():
        obj, created = ErrorEvent.objects.select_for_update().get_or_create(
            stack_hash=shash,
            defaults={
                "exception_type": getattr(exc_type, "__name__", "Error")[:255],
                "message_hash": message_hash(exc_value),
                "stack_trace_redacted": redacted_stack(tb),
                "file_path": file_path[:512],
                "line_number": line_number,
                "function_name": function_name[:255],
                "endpoint": endpoint,
                "method": method,
                "http_status": 500,
                "domain": domain[:64],
                "risk_class": risk,
                "correlation_id": correlation_id,
                "company_id": company_id,
                "branch_id": branch_id,
                "first_seen_at": now,
                "last_seen_at": now,
            },
        )
        if not created:
            updates: dict[str, Any] = {
                "occurrence_count": F("occurrence_count") + 1,
                "last_seen_at": now,
                "correlation_id": correlation_id or obj.correlation_id,
            }
            # Regression-sentinel: si un fallo ya 'corregido' reaparece, vuelve a 'regressed'.
            if obj.status == ErrorStatus.FIXED:
                updates["status"] = ErrorStatus.REGRESSED
            ErrorEvent.objects.filter(pk=obj.pk).update(**updates)
            obj.refresh_from_db()
    return obj
