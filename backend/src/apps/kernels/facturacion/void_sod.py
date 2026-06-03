"""SoD (maker-checker) para anulación de documentos fiscales (Unidad #1).

La anulación de un documento emitido es una operación sensible (invariante #6).
Aquí se ofrece el flujo de doble control reutilizando la primitiva
`apps.modulos.iam.approvals`:

- `request_void`: el solicitante (maker) abre una ApprovalRequest.
- `approve_and_void`: un segundo usuario (checker) distinto, con el permiso
  `billing.doc.void.approve`, aprueba y se ejecuta el `void_doc` existente.

El `void_doc` directo se conserva para uso de sistema (p.ej. compensación de Fuel).
"""
from __future__ import annotations

from apps.modulos.iam.approvals import approve as _approve_request
from apps.modulos.iam.approvals import mark_executed, request_approval

from .models import BillingDocument, DocStatus
from .services import BillingError, BillingNotFoundError, void_doc

VOID_ACTION_TYPE = "BILLING_DOC_VOID"
VOID_APPROVE_PERMISSION = "billing.doc.void.approve"


def request_void(*, request, actor, doc_id: int, reason: str, idempotency_key: str = ""):
    company = request.company
    branch = getattr(request, "branch", None)
    try:
        doc = BillingDocument.objects.get(id=doc_id, company=company, branch=branch)
    except BillingDocument.DoesNotExist as exc:
        raise BillingNotFoundError("documento no encontrado") from exc

    if doc.status == DocStatus.DRAFT:
        raise BillingError("cannot void a draft document")
    if doc.status == DocStatus.VOIDED:
        raise BillingError("document already voided")

    return request_approval(
        company=company,
        branch=branch,
        requested_by=actor,
        action_type=VOID_ACTION_TYPE,
        required_permission=VOID_APPROVE_PERMISSION,
        subject_type="BILLING_DOC",
        subject_id=str(doc.id),
        reason=reason or "VOID",
        payload={"doc_id": int(doc.id), "reason": reason or "VOID"},
        idempotency_key=idempotency_key,
        request=request,
    )


def approve_and_void(*, request, approver, approval) -> dict:
    # Valida SoD (approver != maker) y permiso del aprobador en el scope.
    approval = _approve_request(approval=approval, approver=approver, request=request)
    payload = approval.payload or {}
    result = void_doc(
        request=request,
        actor=approver,
        doc_id=int(payload["doc_id"]),
        reason=str(payload.get("reason") or "VOID"),
    )
    mark_executed(approval=approval, actor=approver, request=request)
    return result
