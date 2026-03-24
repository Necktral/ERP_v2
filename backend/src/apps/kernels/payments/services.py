from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone

from apps.modulos.integration.services import publish_outbox_event

from .models import CashMovement, CashSession, PaymentIntent


def _branch_from_request(request):
    branch = getattr(request, "branch", None)
    if branch is None:
        raise ValueError("X-Branch-Id requerido")
    return branch


def create_payment_intent(
    *,
    request,
    actor,
    amount: Decimal,
    currency: str = "NIO",
    idempotency_key: str = "",
    external_ref: str = "",
    provider: str = "",
) -> tuple[PaymentIntent, bool]:
    company = request.company
    branch = _branch_from_request(request)
    with transaction.atomic():
        if idempotency_key:
            existing = PaymentIntent.objects.filter(company=company, idempotency_key=idempotency_key).first()
            if existing:
                return existing, True

        intent = PaymentIntent.objects.create(
            company=company,
            branch=branch,
            amount=amount,
            currency=currency or "NIO",
            idempotency_key=idempotency_key or "",
            external_ref=external_ref or "",
            provider=provider or "",
        )
        publish_outbox_event(
            request=request,
            source_module="PAYMENTS",
            event_type="PaymentIntentCreated",
            payload={
                "payment_id": str(intent.payment_id),
                "amount": str(intent.amount),
                "currency": intent.currency,
                "status": intent.status,
                "idempotency_key": intent.idempotency_key,
            },
            actor_user=actor,
            company=company,
            branch=branch,
        )
        return intent, False


def open_cash_session(*, request, actor, opening_amount: Decimal = Decimal("0.00"), notes: str = "") -> CashSession:
    company = request.company
    branch = _branch_from_request(request)
    with transaction.atomic():
        existing = CashSession.objects.select_for_update().filter(
            company=company,
            branch=branch,
            status=CashSession.Status.OPEN,
        )
        if existing.exists():
            raise ValueError("Ya existe una cash session OPEN para esta sucursal.")

        session = CashSession.objects.create(
            company=company,
            branch=branch,
            opened_by=actor,
            status=CashSession.Status.OPEN,
            opening_amount=opening_amount,
            expected_amount=opening_amount,
            counted_amount=Decimal("0.00"),
            difference_amount=Decimal("0.00"),
            notes=notes or "",
        )
        publish_outbox_event(
            request=request,
            source_module="PAYMENTS",
            event_type="CashSessionOpened",
            payload={"session_id": session.id, "opening_amount": str(session.opening_amount)},
            actor_user=actor,
            company=company,
            branch=branch,
        )
        return session


def post_cash_movement(
    *,
    request,
    actor,
    session_id: int,
    movement_type: str,
    amount: Decimal,
    reference: str = "",
    reason: str = "",
) -> CashMovement:
    company = request.company
    branch = _branch_from_request(request)

    with transaction.atomic():
        session = get_object_or_404(CashSession.objects.select_for_update(), id=session_id, company=company, branch=branch)
        if session.status not in (CashSession.Status.OPEN, CashSession.Status.COUNT_PENDING):
            raise ValueError("Cash session no permite movimientos en su estado actual.")

        mov = CashMovement.objects.create(
            session=session,
            movement_type=movement_type,
            amount=amount,
            reference=reference or "",
            reason=reason or "",
            created_by=actor,
        )

        sign = Decimal("1")
        if movement_type in (CashMovement.MovementType.EXPENSE, CashMovement.MovementType.REFUND):
            sign = Decimal("-1")
        session.expected_amount = Decimal(session.expected_amount) + (Decimal(amount) * sign)
        session.save(update_fields=["expected_amount"])

        publish_outbox_event(
            request=request,
            source_module="PAYMENTS",
            event_type="CashMovementPosted",
            payload={
                "session_id": session.id,
                "movement_id": mov.id,
                "movement_type": mov.movement_type,
                "amount": str(mov.amount),
                "reference": mov.reference,
            },
            actor_user=actor,
            company=company,
            branch=branch,
        )
        return mov


def close_cash_session(*, request, actor, session_id: int, counted_amount: Decimal, notes: str = "") -> CashSession:
    company = request.company
    branch = _branch_from_request(request)

    with transaction.atomic():
        session = get_object_or_404(CashSession.objects.select_for_update(), id=session_id, company=company, branch=branch)
        if session.status == CashSession.Status.CLOSED:
            return session
        if session.status not in (
            CashSession.Status.OPEN,
            CashSession.Status.COUNT_PENDING,
            CashSession.Status.REVIEW_PENDING,
        ):
            raise ValueError("Estado de cash session inválido para cierre.")

        session.status = CashSession.Status.CLOSED
        session.closed_by = actor
        session.closed_at = timezone.now()
        session.counted_amount = counted_amount
        session.difference_amount = Decimal(counted_amount) - Decimal(session.expected_amount)
        if notes:
            session.notes = notes
        try:
            session.clean()
        except ValidationError as exc:
            raise ValueError(str(exc)) from exc
        session.save(
            update_fields=[
                "status",
                "closed_by",
                "closed_at",
                "counted_amount",
                "difference_amount",
                "notes",
            ]
        )

        publish_outbox_event(
            request=request,
            source_module="PAYMENTS",
            event_type="CashSessionClosed",
            payload={
                "session_id": session.id,
                "expected_amount": str(session.expected_amount),
                "counted_amount": str(session.counted_amount),
                "difference_amount": str(session.difference_amount),
            },
            actor_user=actor,
            company=company,
            branch=branch,
        )
        return session
