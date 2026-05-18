from __future__ import annotations

import logging

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.modulos.common.pagination import get_limit_offset, paginate_queryset
from apps.modulos.common.permissions import rbac_permission

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
    permission_classes = [rbac_permission("payments.cash_movement.create")]

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
