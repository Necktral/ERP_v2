"""Helper estándar de auditoría de servicio (Fase 0 — fundación transversal).

Consolida el patrón de "request sintético" (hoy duplicado en parties/hr/iam/rbac)
para emitir `AuditEvent` desde la capa de servicio sin un request HTTP, y ofrece
`emit_service_event` como punto único para cablear auditoría detallada (actor,
tiempo, motivo, causalidad) en los kernels que hoy no emiten.
"""
from __future__ import annotations

from typing import Any

from .writer import write_event


class ServiceAuditRequest:
    """Request sintético para encadenar auditoría por company desde servicios."""

    def __init__(self, *, company, branch=None, request_id: str = "", path: str = "", method: str = "") -> None:
        self.company = company
        self.branch = branch
        self.META: dict[str, Any] = {}
        self.path = path
        self.method = method
        self.request_id = request_id


def build_audit_request(*, company, branch=None, base_request=None, request_id: str = "", path: str = "", method: str = ""):
    """Devuelve el request real si se provee; si no, uno sintético con el scope."""
    if base_request is not None:
        return base_request
    return ServiceAuditRequest(company=company, branch=branch, request_id=request_id, path=path, method=method)


def emit_service_event(
    *,
    company,
    module: str,
    event_type: str,
    branch=None,
    request=None,
    reason_code: str = "",
    actor_user=None,
    subject_type: str = "",
    subject_id: str = "",
    before_snapshot: dict | None = None,
    after_snapshot: dict | None = None,
    metadata: dict | None = None,
):
    """Emite un AuditEvent detallado desde un servicio (con o sin request HTTP)."""
    meta = dict(metadata or {})
    meta.setdefault("company_id", str(getattr(company, "id", "")))
    if branch is not None:
        meta.setdefault("branch_id", str(getattr(branch, "id", "")))
    return write_event(
        request=build_audit_request(company=company, branch=branch, base_request=request),
        module=module,
        event_type=event_type,
        reason_code=reason_code,
        actor_user=actor_user,
        subject_type=subject_type,
        subject_id=subject_id,
        before_snapshot=before_snapshot,
        after_snapshot=after_snapshot,
        metadata=meta,
    )
