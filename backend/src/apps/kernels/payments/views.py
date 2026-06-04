from __future__ import annotations

import logging

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.modulos.common.domain_errors import DomainError
from apps.modulos.common.pagination import get_limit_offset, paginate_queryset
from apps.modulos.common.permissions import rbac_permission
from apps.modulos.iam.models import ApprovalRequest

from .models import CashSession, PaymentIntent
from .serializers import (
    CashMovementCreateIn,
    CashSessionCloseIn,
    CashSessionOpenIn,
    PaymentIntentCreateIn,
    PaymentIntentReverseCaptureIn,
)
from .services import (
    PaymentsConflictError,
    PaymentsDomainError,
    PaymentsInvalidStateError,
    PaymentsNotFoundError,
    PaymentsValidationError,
    close_cash_session,
    create_payment_intent,
    open_cash_session,
    post_cash_movement_with_status,
    reverse_captured_payment_intent,
)


logger = logging.getLogger(__name__)


def _status_for_payments_error(exc: PaymentsDomainError, *, request, view_name: str) -> int:
    if isinstance(exc, PaymentsNotFoundError):
        return status.HTTP_404_NOT_FOUND
    if isinstance(exc, (PaymentsConflictError, PaymentsInvalidStateError)):
        return status.HTTP_409_CONFLICT
    if isinstance(exc, PaymentsValidationError):
        return status.HTTP_400_BAD_REQUEST
    logger.warning(
        "payments domain error no clasificado mapeado a 400",
        extra={
            "payments_error_unclassified": True,
            "error_class": exc.__class__.__name__,
            "view_name": str(view_name),
            "path": str(getattr(request, "path", "") or ""),
            "company_id": getattr(getattr(request, "company", None), "id", None),
            "branch_id": getattr(getattr(request, "branch", None), "id", None),
        },
    )
    return status.HTTP_400_BAD_REQUEST


def _status_for_approval_error(exc: DomainError) -> int:
    """Mapea errores de la primitiva SoD (iam.approvals) a HTTP."""
    from apps.modulos.iam.approvals import (
        ApprovalStateError,
        ApproverNotAuthorizedError,
        SelfApprovalError,
    )
    if isinstance(exc, (SelfApprovalError, ApproverNotAuthorizedError)):
        return status.HTTP_403_FORBIDDEN
    if isinstance(exc, ApprovalStateError):
        return status.HTTP_409_CONFLICT
    return status.HTTP_400_BAD_REQUEST


class HealthView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        return Response({"ok": True, "module": "payments"}, status=status.HTTP_200_OK)


class PaymentIntentListCreateView(APIView):
    def get_permissions(self):
        if self.request.method == "GET":
            return [rbac_permission("payments.intent.read")()]
        return [rbac_permission("payments.intent.create")()]

    def get(self, request):
        company = request.company
        branch = getattr(request, "branch", None)
        qs = PaymentIntent.objects.filter(company=company).order_by("-created_at", "-id")
        if branch is not None:
            qs = qs.filter(branch=branch)

        limit, offset = get_limit_offset(request)
        total, rows = paginate_queryset(qs, limit=limit, offset=offset)
        results = [
            {
                "payment_id": str(r.payment_id),
                "amount": str(r.amount),
                "currency": r.currency,
                "status": r.status,
                "external_ref": r.external_ref,
                "provider": r.provider,
                "provider_txn_id": r.provider_txn_id,
                "payment_method": r.payment_method,
                "created_at": r.created_at,
            }
            for r in rows
        ]
        return Response(
            {"count": total, "limit": limit, "offset": offset, "results": results},
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        s = PaymentIntentCreateIn(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        try:
            intent, idempotent = create_payment_intent(
                request=request,
                actor=request.user,
                amount=v["amount"],
                currency=v.get("currency") or "NIO",
                idempotency_key=v.get("idempotency_key", "") or "",
                external_ref=v.get("external_ref", "") or "",
                provider=v.get("provider", "") or "",
                payment_method=v.get("payment_method", "") or "",
            )
        except PaymentsDomainError as exc:
            return Response(
                {"detail": str(exc)},
                status=_status_for_payments_error(exc, request=request, view_name="PaymentIntentListCreateView.post"),
            )

        return Response(
            {
                "payment_id": str(intent.payment_id),
                "status": intent.status,
                "amount": str(intent.amount),
                "currency": intent.currency,
                "payment_method": intent.payment_method,
                "idempotent": bool(idempotent),
            },
            status=status.HTTP_200_OK if idempotent else status.HTTP_201_CREATED,
        )


class PaymentIntentReverseCaptureView(APIView):
    permission_classes = [rbac_permission("payments.intent.create")]

    def post(self, request, payment_id):
        s = PaymentIntentReverseCaptureIn(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        try:
            intent, idempotent = reverse_captured_payment_intent(
                request=request,
                actor=request.user,
                payment_id=payment_id,
                idempotency_key=v["idempotency_key"],
                reason=v.get("reason", "") or "",
            )
        except PaymentsDomainError as exc:
            return Response(
                {"detail": str(exc)},
                status=_status_for_payments_error(
                    exc,
                    request=request,
                    view_name="PaymentIntentReverseCaptureView.post",
                ),
            )

        return Response(
            {
                "payment_id": str(intent.payment_id),
                "status": intent.status,
                "amount": str(intent.amount),
                "currency": intent.currency,
                "payment_method": intent.payment_method,
                "idempotent": bool(idempotent),
            },
            status=status.HTTP_200_OK if idempotent else status.HTTP_201_CREATED,
        )


class CashSessionListView(APIView):
    permission_classes = [rbac_permission("payments.cash_session.read")]

    def get(self, request):
        company = request.company
        branch = getattr(request, "branch", None)
        qs = CashSession.objects.filter(company=company).order_by("-opened_at", "-id")
        if branch is not None:
            qs = qs.filter(branch=branch)

        limit, offset = get_limit_offset(request)
        total, rows = paginate_queryset(qs, limit=limit, offset=offset)
        results = [
            {
                "id": r.id,
                "status": r.status,
                "opening_amount": str(r.opening_amount),
                "expected_amount": str(r.expected_amount),
                "counted_amount": str(r.counted_amount),
                "difference_amount": str(r.difference_amount),
                "opened_at": r.opened_at,
                "closed_at": r.closed_at,
            }
            for r in rows
        ]
        return Response(
            {"count": total, "limit": limit, "offset": offset, "results": results},
            status=status.HTTP_200_OK,
        )


class CashSessionOpenView(APIView):
    permission_classes = [rbac_permission("payments.cash_session.open")]

    def post(self, request):
        s = CashSessionOpenIn(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        try:
            session = open_cash_session(
                request=request,
                actor=request.user,
                opening_amount=v.get("opening_amount") or 0,
                notes=v.get("notes", "") or "",
            )
        except PaymentsDomainError as exc:
            return Response(
                {"detail": str(exc)},
                status=_status_for_payments_error(exc, request=request, view_name="CashSessionOpenView.post"),
            )

        return Response({"id": session.id, "status": session.status}, status=status.HTTP_201_CREATED)


class CashSessionCloseView(APIView):
    permission_classes = [rbac_permission("payments.cash_session.close")]

    def post(self, request, session_id: int):
        s = CashSessionCloseIn(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        try:
            session = close_cash_session(
                request=request,
                actor=request.user,
                session_id=session_id,
                counted_amount=v["counted_amount"],
                notes=v.get("notes", "") or "",
            )
        except PaymentsDomainError as exc:
            return Response(
                {"detail": str(exc)},
                status=_status_for_payments_error(exc, request=request, view_name="CashSessionCloseView.post"),
            )

        return Response(
            {
                "id": session.id,
                "status": session.status,
                "expected_amount": str(session.expected_amount),
                "counted_amount": str(session.counted_amount),
                "difference_amount": str(session.difference_amount),
            },
            status=status.HTTP_200_OK,
        )


class CashMovementCreateView(APIView):
    """GET → list   POST → create (backward compat — mismo endpoint)"""

    def get_permissions(self):
        if self.request.method == "POST":
            return [rbac_permission("payments.cash_movement.create")()]
        return [rbac_permission("payments.cash_session.read")()]

    def get(self, request, session_id: int):
        company = request.company
        branch = getattr(request, "branch", None)
        session = CashSession.objects.filter(company=company, id=session_id).first()
        if branch and session and session.branch_id and session.branch_id != branch.id:
            session = None
        if not session:
            return Response({"detail": "No encontrada."}, status=status.HTTP_404_NOT_FOUND)
        from apps.modulos.common.pagination import get_limit_offset, paginate_queryset
        qs = session.movements.order_by("-created_at")
        if request.query_params.get("movement_type"):
            qs = qs.filter(movement_type=request.query_params["movement_type"])
        limit, offset = get_limit_offset(request)
        total, rows = paginate_queryset(qs, limit=limit, offset=offset)
        return Response({"count": total, "limit": limit, "offset": offset,
                         "results": [{"id": m.id, "movement_type": m.movement_type,
                                      "amount": str(m.amount), "reference": m.reference,
                                      "created_at": m.created_at} for m in rows]})

    def post(self, request, session_id: int):
        s = CashMovementCreateIn(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        try:
            mov, idempotent = post_cash_movement_with_status(
                request=request,
                actor=request.user,
                session_id=session_id,
                movement_type=v["movement_type"],
                amount=v["amount"],
                reference=v.get("reference", "") or "",
                reason=v.get("reason", "") or "",
                idempotency_key=v.get("idempotency_key", "") or "",
            )
        except PaymentsDomainError as exc:
            return Response(
                {"detail": str(exc)},
                status=_status_for_payments_error(exc, request=request, view_name="CashMovementCreateView.post"),
            )

        return Response(
            {
                "id": mov.id,
                "session_id": mov.session_id,
                "movement_type": mov.movement_type,
                "amount": str(mov.amount),
                "idempotent": bool(idempotent),
            },
            status=status.HTTP_200_OK if idempotent else status.HTTP_201_CREATED,
        )


class PaymentIntentDetailView(APIView):
    permission_classes = [rbac_permission("payments.intent.read")]

    def get(self, request, payment_id):
        company = request.company
        branch = getattr(request, "branch", None)
        qs = PaymentIntent.objects.filter(company=company, payment_id=payment_id)
        if branch:
            qs = qs.filter(branch=branch)
        intent = qs.first()
        if not intent:
            return Response({"detail": "No encontrado."}, status=status.HTTP_404_NOT_FOUND)
        return Response({
            "payment_id": str(intent.payment_id),
            "status": intent.status,
            "amount": str(intent.amount),
            "amount_authorized": str(intent.amount_authorized) if intent.amount_authorized else None,
            "amount_captured": str(intent.amount_captured) if intent.amount_captured else None,
            "amount_refunded": str(intent.amount_refunded),
            "outstanding_amount": str(intent.outstanding_amount),
            "refundable_amount": str(intent.refundable_amount),
            "currency": intent.currency,
            "payment_method": intent.payment_method,
            "external_ref": intent.external_ref,
            "provider": intent.provider,
            "provider_txn_id": intent.provider_txn_id,
            "authorized_at": intent.authorized_at,
            "captured_at": intent.captured_at,
            "refunded_at": intent.refunded_at,
            "failed_at": intent.failed_at,
            "failure_reason": intent.failure_reason,
            "cancellation_reason": intent.cancellation_reason,
            "created_at": intent.created_at,
        })


class PaymentIntentAuthorizeView(APIView):
    permission_classes = [rbac_permission("payments.intent.create")]

    def post(self, request, payment_id):
        from .services import authorize_payment_intent
        from .serializers import PaymentIntentAuthorizeIn
        s = PaymentIntentAuthorizeIn(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        try:
            intent = authorize_payment_intent(
                request=request, actor=request.user,
                payment_id=payment_id,
                amount_authorized=v.get("amount_authorized"),
                provider_txn_id=v.get("provider_txn_id", "") or "",
            )
        except PaymentsDomainError as exc:
            return Response({"detail": str(exc)},
                            status=_status_for_payments_error(exc, request=request, view_name="authorize"))
        return Response({"payment_id": str(intent.payment_id), "status": intent.status})


class PaymentIntentCaptureView(APIView):
    permission_classes = [rbac_permission("payments.intent.create")]

    def post(self, request, payment_id):
        from apps.kernels.payments.services import capture_payment_intent
        from .serializers import PaymentIntentCaptureIn
        s = PaymentIntentCaptureIn(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        try:
            intent = capture_payment_intent(
                request=request, actor=request.user,
                payment_id=payment_id,
                provider_txn_id=v.get("provider_txn_id", "") or "",
            )
        except PaymentsDomainError as exc:
            return Response({"detail": str(exc)},
                            status=_status_for_payments_error(exc, request=request, view_name="capture"))
        return Response({"payment_id": str(intent.payment_id), "status": intent.status,
                         "amount_captured": str(intent.amount_captured or intent.amount)})


class PaymentIntentRefundView(APIView):
    """SoD (maker): POST crea una ApprovalRequest de reembolso; NO reembolsa directo.

    El reembolso se ejecuta cuando un segundo usuario (checker, distinto, con
    `payments.refund.approve`) aprueba en PaymentRefundApproveView.
    """
    permission_classes = [rbac_permission("payments.refund.request")]

    def post(self, request, payment_id):
        from .serializers import PaymentIntentRefundIn
        from .sod import request_refund
        s = PaymentIntentRefundIn(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        try:
            approval = request_refund(
                request=request, actor=request.user,
                payment_id=payment_id,
                amount=v["amount"],
                reason=v.get("reason", "") or "",
                idempotency_key=v.get("idempotency_key", "") or "",
            )
        except PaymentsDomainError as exc:
            return Response({"detail": str(exc)},
                            status=_status_for_payments_error(exc, request=request, view_name="refund_request"))
        return Response(
            {
                "approval_request_id": str(approval.request_id),
                "status": approval.status,
                "action_type": approval.action_type,
            },
            status=status.HTTP_202_ACCEPTED,
        )


class PaymentRefundApproveView(APIView):
    """SoD (checker): aprueba y ejecuta el reembolso (usuario != maker)."""
    permission_classes = [rbac_permission("payments.refund.approve")]

    def post(self, request, request_id):
        from .sod import approve_and_refund
        approval = ApprovalRequest.objects.filter(
            request_id=request_id, company=request.company, action_type="PAYMENTS_REFUND"
        ).first()
        if approval is None:
            return Response({"detail": "Solicitud de aprobación no encontrada."},
                            status=status.HTTP_404_NOT_FOUND)
        try:
            refund = approve_and_refund(request=request, approver=request.user, approval=approval)
        except PaymentsDomainError as exc:
            return Response({"detail": str(exc)},
                            status=_status_for_payments_error(exc, request=request, view_name="refund_approve"))
        except DomainError as exc:
            return Response({"detail": str(exc)}, status=_status_for_approval_error(exc))
        return Response(
            {"refund_id": str(refund.refund_id), "amount": str(refund.amount),
             "intent_status": refund.intent.status},
            status=status.HTTP_201_CREATED,
        )


class PaymentIntentCancelView(APIView):
    permission_classes = [rbac_permission("payments.intent.create")]

    def post(self, request, payment_id):
        from .services import cancel_payment_intent
        try:
            intent = cancel_payment_intent(
                request=request, actor=request.user,
                payment_id=payment_id,
                reason=request.data.get("reason", "") or "",
            )
        except PaymentsDomainError as exc:
            return Response({"detail": str(exc)},
                            status=_status_for_payments_error(exc, request=request, view_name="cancel"))
        return Response({"payment_id": str(intent.payment_id), "status": intent.status})


class CashSessionDetailView(APIView):
    permission_classes = [rbac_permission("payments.cash_session.read")]

    def get(self, request, session_id: int):
        company = request.company
        branch = getattr(request, "branch", None)
        qs = CashSession.objects.filter(company=company, id=session_id)
        if branch:
            qs = qs.filter(branch=branch)
        session = qs.first()
        if not session:
            return Response({"detail": "No encontrada."}, status=status.HTTP_404_NOT_FOUND)

        movements_qs = session.movements.order_by("-created_at")[:50]
        return Response({
            "id": session.id,
            "register_id": session.register_id,
            "status": session.status,
            "opening_amount": str(session.opening_amount),
            "expected_amount": str(session.expected_amount),
            "counted_amount": str(session.counted_amount),
            "difference_amount": str(session.difference_amount),
            "opened_at": session.opened_at,
            "closed_at": session.closed_at,
            "notes": session.notes,
            "movements": [
                {
                    "id": m.id,
                    "movement_type": m.movement_type,
                    "amount": str(m.amount),
                    "payment_method": m.payment_method,
                    "reference": m.reference,
                    "reason": m.reason,
                    "created_at": m.created_at,
                }
                for m in movements_qs
            ],
        })


class CashSessionMovementListView(APIView):
    permission_classes = [rbac_permission("payments.cash_session.read")]

    def get(self, request, session_id: int):
        company = request.company
        branch = getattr(request, "branch", None)
        qs_s = CashSession.objects.filter(company=company, id=session_id)
        if branch:
            qs_s = qs_s.filter(branch=branch)
        session = qs_s.first()
        if not session:
            return Response({"detail": "No encontrada."}, status=status.HTTP_404_NOT_FOUND)

        from apps.modulos.common.pagination import get_limit_offset, paginate_queryset
        qs = session.movements.order_by("-created_at")
        mov_type = request.query_params.get("movement_type")
        if mov_type:
            qs = qs.filter(movement_type=mov_type)
        limit, offset = get_limit_offset(request)
        total, rows = paginate_queryset(qs, limit=limit, offset=offset)
        return Response({
            "count": total, "limit": limit, "offset": offset,
            "results": [
                {
                    "id": m.id,
                    "movement_type": m.movement_type,
                    "amount": str(m.amount),
                    "payment_method": m.payment_method,
                    "reference": m.reference,
                    "reason": m.reason,
                    "payment_intent_id": str(m.payment_intent.payment_id) if m.payment_intent_id else None,
                    "created_at": m.created_at,
                }
                for m in rows
            ],
        })


class CashSessionDenominationView(APIView):
    """POST → registra arqueo de caja por denominación."""
    permission_classes = [rbac_permission("payments.cash_session.close")]

    def post(self, request, session_id: int):
        from .services import submit_denomination_count
        denominations = request.data.get("denominations", [])
        if not denominations:
            return Response({"detail": "denominations requerido."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            session, denoms, total = submit_denomination_count(
                request=request, actor=request.user,
                session_id=session_id, denominations=denominations,
            )
        except PaymentsDomainError as exc:
            return Response({"detail": str(exc)},
                            status=_status_for_payments_error(exc, request=request, view_name="denomination"))
        return Response({
            "session_id": session.id,
            "total_counted": str(total),
            "expected_amount": str(session.expected_amount),
            "difference": str(total - session.expected_amount),
            "denominations": [
                {"denomination_value": str(d.denomination_value),
                 "denomination_type": d.denomination_type,
                 "quantity": d.quantity,
                 "subtotal": str(d.subtotal)}
                for d in denoms
            ],
        })


class CashSessionReopenView(APIView):
    """SoD (maker): POST crea una ApprovalRequest de reapertura; NO reabre directo.

    La reapertura se ejecuta cuando un segundo usuario (checker, distinto, con
    `payments.cash.reopen.approve`) aprueba en CashReopenApproveView.
    """
    permission_classes = [rbac_permission("payments.cash.reopen.request")]

    def post(self, request, session_id: int):
        from .sod import request_reopen
        reason = request.data.get("reason", "") or ""
        try:
            approval = request_reopen(
                request=request, actor=request.user,
                session_id=session_id, reason=reason,
            )
        except PaymentsDomainError as exc:
            return Response({"detail": str(exc)},
                            status=_status_for_payments_error(exc, request=request, view_name="reopen_request"))
        return Response(
            {
                "approval_request_id": str(approval.request_id),
                "status": approval.status,
                "action_type": approval.action_type,
            },
            status=status.HTTP_202_ACCEPTED,
        )


class CashReopenApproveView(APIView):
    """SoD (checker): aprueba y ejecuta la reapertura (usuario != maker)."""
    permission_classes = [rbac_permission("payments.cash.reopen.approve")]

    def post(self, request, request_id):
        from .sod import approve_and_reopen
        approval = ApprovalRequest.objects.filter(
            request_id=request_id, company=request.company, action_type="PAYMENTS_CASH_REOPEN"
        ).first()
        if approval is None:
            return Response({"detail": "Solicitud de aprobación no encontrada."},
                            status=status.HTTP_404_NOT_FOUND)
        try:
            session = approve_and_reopen(request=request, approver=request.user, approval=approval)
        except PaymentsDomainError as exc:
            return Response({"detail": str(exc)},
                            status=_status_for_payments_error(exc, request=request, view_name="reopen_approve"))
        except DomainError as exc:
            return Response({"detail": str(exc)}, status=_status_for_approval_error(exc))
        return Response({"id": session.id, "status": session.status})
