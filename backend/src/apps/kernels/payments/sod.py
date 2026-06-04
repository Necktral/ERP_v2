"""SoD (maker-checker) para operaciones sensibles de payments (Unidad #3).

Dos operaciones sensibles (invariante #6) pasan por doble control reutilizando la
primitiva `apps.modulos.iam.approvals`:

- Reembolso de un PaymentIntent: `request_refund` (maker) -> `approve_and_refund` (checker).
- Reapertura de una CashSession para investigación: `request_reopen` (maker) ->
  `approve_and_reopen` (checker).

Las funciones de servicio crudas (`refund_payment_intent_for_scope`,
`reopen_cash_session_for_investigation`) se conservan para orquestación interna/sistema
(igual que `facturacion.void_doc`).
"""
from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from django.http import HttpRequest

from apps.modulos.iam.approvals import approve as _approve_request
from apps.modulos.iam.approvals import mark_executed, request_approval
from apps.modulos.iam.models import ApprovalRequest

from .models import CashSession, PaymentIntent, PaymentRefund
from .services import (
    PaymentsInvalidStateError,
    PaymentsNotFoundError,
    PaymentsValidationError,
    refund_payment_intent_for_scope,
    reopen_cash_session_for_investigation,
)

REFUND_ACTION_TYPE = "PAYMENTS_REFUND"
REFUND_APPROVE_PERMISSION = "payments.refund.approve"
REOPEN_ACTION_TYPE = "PAYMENTS_CASH_REOPEN"
CASH_REOPEN_APPROVE_PERMISSION = "payments.cash.reopen.approve"

_REFUNDABLE_STATES = (
    PaymentIntent.Status.CAPTURED,
    PaymentIntent.Status.PARTIALLY_CAPTURED,
    PaymentIntent.Status.PARTIALLY_REFUNDED,
)


# --------------------------------------------------------------------------- #
# Refund de PaymentIntent
# --------------------------------------------------------------------------- #

def request_refund(
    *,
    request: HttpRequest,
    actor,
    payment_id: str | UUID,
    amount: Decimal,
    reason: str = "",
    idempotency_key: str = "",
) -> ApprovalRequest:
    company = request.company
    branch = getattr(request, "branch", None)
    intent = PaymentIntent.objects.filter(payment_id=payment_id, company=company, branch=branch).first()
    if intent is None:
        raise PaymentsNotFoundError("Payment intent no encontrado.")
    if intent.status not in _REFUNDABLE_STATES:
        raise PaymentsInvalidStateError(
            f"Solo se puede reembolsar un pago capturado. Estado: {intent.status}"
        )
    amount = Decimal(str(amount))
    if amount <= 0:
        raise PaymentsValidationError("El monto del reembolso debe ser > 0.")

    return request_approval(
        company=company,
        branch=branch,
        requested_by=actor,
        action_type=REFUND_ACTION_TYPE,
        required_permission=REFUND_APPROVE_PERMISSION,
        subject_type="PAYMENT_INTENT",
        subject_id=str(intent.payment_id),
        reason=reason or "REFUND",
        payload={
            "payment_id": str(intent.payment_id),
            "amount": str(amount),
            "reason": reason or "",
            "idempotency_key": idempotency_key or "",
        },
        idempotency_key=idempotency_key,
        request=request,
    )


def approve_and_refund(*, request: HttpRequest, approver, approval: ApprovalRequest) -> PaymentRefund:
    # Valida SoD (approver != maker) y permiso del aprobador en el scope.
    approval = _approve_request(approval=approval, approver=approver, request=request)
    payload = approval.payload or {}
    refund = refund_payment_intent_for_scope(
        company=approval.company,
        branch=approval.branch,
        actor=approver,
        request=request,
        payment_id=str(payload["payment_id"]),
        amount=Decimal(str(payload["amount"])),
        idempotency_key=str(payload.get("idempotency_key") or ""),
        reason=str(payload.get("reason") or ""),
    )
    mark_executed(approval=approval, actor=approver, request=request)
    return refund


# --------------------------------------------------------------------------- #
# Reapertura de CashSession para investigación
# --------------------------------------------------------------------------- #

def request_reopen(
    *,
    request: HttpRequest,
    actor,
    session_id: int,
    reason: str,
    idempotency_key: str = "",
) -> ApprovalRequest:
    company = request.company
    branch = getattr(request, "branch", None)
    session = CashSession.objects.filter(id=session_id, company=company, branch=branch).first()
    if session is None:
        raise PaymentsNotFoundError("Cash session no encontrada.")
    if not session.can_transition_to(CashSession.Status.REOPENED_FOR_INVESTIGATION):
        raise PaymentsInvalidStateError("Solo se puede reabrir una sesión CLOSED.")
    if not reason:
        raise PaymentsValidationError("reason requerido.")

    return request_approval(
        company=company,
        branch=branch,
        requested_by=actor,
        action_type=REOPEN_ACTION_TYPE,
        required_permission=CASH_REOPEN_APPROVE_PERMISSION,
        subject_type="CASH_SESSION",
        subject_id=str(session.id),
        reason=reason,
        payload={"session_id": int(session.id), "reason": reason},
        idempotency_key=idempotency_key,
        request=request,
    )


def approve_and_reopen(*, request: HttpRequest, approver, approval: ApprovalRequest) -> CashSession:
    approval = _approve_request(approval=approval, approver=approver, request=request)
    payload = approval.payload or {}
    session = reopen_cash_session_for_investigation(
        request=request,
        actor=approver,
        session_id=int(payload["session_id"]),
        reason=str(payload.get("reason") or "REOPEN"),
    )
    mark_executed(approval=approval, actor=approver, request=request)
    return session
