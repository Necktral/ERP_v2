"""Shim de auditoría compartido del kernel accounting.

Extraído de `services.py` para que tanto `services` como `phase7` puedan emitir
`AuditEvent` `ACCOUNTING_*` sin crear un ciclo de imports (services importa phase7).
Cierra el hueco `audit=0` (invariante #4: actor/tiempo/razón/causación).
"""
from __future__ import annotations

from typing import Any

from apps.modulos.audit.writer import write_event


class _AccountingAuditRequest:
    """Request sintético para encadenar auditoría por company sin HTTP.

    El kernel accounting opera con `actor_user` (no recibe `request`); este shim
    aporta el scope que `audit.writer.write_event` usa para particionar la cadena.
    """

    def __init__(self, *, company, branch=None) -> None:
        self.company = company
        self.branch = branch
        self.META: dict[str, Any] = {}
        self.path = ""
        self.method = ""
        self.request_id = ""


def write_accounting_audit_event(
    *,
    actor_user,
    company,
    branch,
    event_type: str,
    subject_type: str,
    subject_id: str,
    before_snapshot: dict[str, Any] | None = None,
    after_snapshot: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    reason_code: str = "ACCOUNTING_OK",
) -> None:
    """Auditoría de servicio del kernel accounting (cierra el hueco `audit=0`, invariante #4)."""
    meta: dict[str, Any] = {"company_id": str(getattr(company, "id", "") or "")}
    if branch is not None:
        meta["branch_id"] = str(getattr(branch, "id", "") or "")
    if metadata:
        meta.update(metadata)
    write_event(
        request=_AccountingAuditRequest(company=company, branch=branch),
        module="ACCOUNTING",
        event_type=event_type,
        reason_code=reason_code,
        actor_user=actor_user,
        subject_type=subject_type,
        subject_id=str(subject_id),
        before_snapshot=before_snapshot,
        after_snapshot=after_snapshot,
        metadata=meta,
    )
