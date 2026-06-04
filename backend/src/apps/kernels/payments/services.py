from __future__ import annotations

from decimal import Decimal
from typing import Any, Protocol, cast
from uuid import UUID, uuid4

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.http import HttpRequest
from django.utils import timezone

from apps.modulos.audit.writer import write_event
from apps.modulos.common.tender import TENDER_PAYMENT_METHOD_VALUES, TenderPaymentMethod
from apps.modulos.iam.models import OrgUnit
from apps.modulos.integration.models import OutboxEvent
from apps.modulos.integration.services import publish_outbox_event

from .models import CashDenomination, CashMovement, CashSession, PaymentIntent, PaymentRefund


class PaymentsDomainError(ValueError):
    """Error de dominio base para el módulo de pagos."""


class PaymentsNotFoundError(PaymentsDomainError):
    """Entidad no encontrada dentro del scope de pagos."""


class PaymentsInvalidStateError(PaymentsDomainError):
    """Transición inválida de estado."""


class PaymentsConflictError(PaymentsDomainError):
    """Conflicto de concurrencia o unicidad de negocio."""


class PaymentsValidationError(PaymentsDomainError):
    """Error de validación de entrada de dominio."""


class ActorPrincipal(Protocol):
    id: Any


def _normalize_payment_method(payment_method: str) -> str:
    normalized = str(payment_method or "").strip().upper()
    if normalized and normalized not in TENDER_PAYMENT_METHOD_VALUES:
        raise PaymentsValidationError("payment_method inválido.")
    return normalized


def _coerce_actor_for_fk(*, actor: ActorPrincipal, field_name: str) -> Any:
    actor_id = getattr(actor, "id", None)
    if actor_id is None:
        raise PaymentsValidationError(f"{field_name} requiere actor con id no nulo.")
    return cast(Any, actor)


def _branch_from_request(request: HttpRequest) -> OrgUnit:
    branch = getattr(request, "branch", None)
    if branch is None:
        raise PaymentsValidationError("X-Branch-Id requerido")
    if not isinstance(branch, OrgUnit):
        raise PaymentsValidationError("X-Branch-Id inválido")
    return branch


def _scope_from_request(request: HttpRequest) -> tuple[OrgUnit, OrgUnit]:
    company = getattr(request, "company", None)
    if company is None:
        raise PaymentsValidationError("X-Company-Id requerido")
    if not isinstance(company, OrgUnit):
        raise PaymentsValidationError("X-Company-Id inválido")
    branch = _branch_from_request(request)
    return company, branch


def _dt_iso(value) -> str:
    return value.isoformat() if value else ""


def _capture_reversal_metadata(intent: PaymentIntent) -> dict[str, Any]:
    metadata = intent.metadata if isinstance(intent.metadata, dict) else {}
    reversal = metadata.get("capture_reversal")
    return reversal if isinstance(reversal, dict) else {}


def _find_payment_captured_event(*, intent: PaymentIntent, company: OrgUnit, branch: OrgUnit) -> OutboxEvent | None:
    return (
        OutboxEvent.objects.filter(
            source_module="PAYMENTS",
            event_type="PaymentCaptured",
            company=company,
            branch=branch,
            payload__data__payment_id=str(intent.payment_id),
        )
        .order_by("-occurred_at", "-id")
        .first()
    )


def _write_intent_audit_event(
    *,
    request: HttpRequest | None,
    actor: ActorPrincipal,
    intent: PaymentIntent,
    event_type: str,
    company: OrgUnit,
    branch: OrgUnit,
    before_snapshot: dict[str, Any] | None = None,
    after_snapshot: dict[str, Any] | None = None,
    extra_metadata: dict[str, Any] | None = None,
) -> None:
    """Audita una operación de PaymentIntent (espejo de `_write_cash_movement_audit_event`).

    Los event types `PAYMENTS_INTENT_*` y el subject `PAYMENT_INTENT` ya están en el catálogo
    (`audit/contracts.py`). Se llama tras el `publish_outbox_event` de cada `*_for_scope`.
    """
    metadata: dict[str, Any] = {"company_id": str(company.id), "branch_id": str(branch.id)}
    if extra_metadata:
        metadata.update(extra_metadata)
    write_event(
        request=request,
        module="PAYMENTS",
        event_type=event_type,
        reason_code="OK",
        actor_user=actor,
        subject_type="PAYMENT_INTENT",
        subject_id=str(intent.payment_id),
        before_snapshot=before_snapshot,
        after_snapshot=after_snapshot,
        metadata=metadata,
    )


def create_payment_intent_for_scope(
    *,
    company: OrgUnit,
    branch: OrgUnit,
    actor: ActorPrincipal,
    request: HttpRequest | None = None,
    amount: Decimal,
    currency: str = "NIO",
    idempotency_key: str = "",
    external_ref: str = "",
    provider: str = "",
    payment_method: str = "",
) -> tuple[PaymentIntent, bool]:
    normalized_payment_method = _normalize_payment_method(payment_method)
    with transaction.atomic():
        if idempotency_key:
            existing = PaymentIntent.objects.filter(company=company, idempotency_key=idempotency_key).first()
            if existing is not None:
                return existing, True

        intent = PaymentIntent.objects.create(
            company=company,
            branch=branch,
            amount=amount,
            currency=currency or "NIO",
            idempotency_key=idempotency_key or "",
            external_ref=external_ref or "",
            provider=provider or "",
            payment_method=normalized_payment_method,
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
                "payment_method": intent.payment_method,
            },
            actor_user=actor,
            company=company,
            branch=branch,
        )
        return intent, False


def create_payment_intent(
    *,
    request: HttpRequest,
    actor: ActorPrincipal,
    amount: Decimal,
    currency: str = "NIO",
    idempotency_key: str = "",
    external_ref: str = "",
    provider: str = "",
    payment_method: str = "",
) -> tuple[PaymentIntent, bool]:
    company, branch = _scope_from_request(request)
    return create_payment_intent_for_scope(
        company=company,
        branch=branch,
        actor=actor,
        request=request,
        amount=amount,
        currency=currency,
        idempotency_key=idempotency_key,
        external_ref=external_ref,
        provider=provider,
        payment_method=payment_method,
    )


def capture_payment_intent_for_scope(
    *,
    company: OrgUnit,
    branch: OrgUnit,
    actor: ActorPrincipal,
    payment_id: str | UUID,
    request: HttpRequest | None = None,
    provider_txn_id: str = "",
    metadata: dict[str, Any] | None = None,
) -> PaymentIntent:
    with transaction.atomic():
        intent = (
            PaymentIntent.objects.select_for_update()
            .filter(
                payment_id=payment_id,
                company=company,
                branch=branch,
            )
            .first()
        )
        if intent is None:
            raise PaymentsNotFoundError("Payment intent no encontrado.")
        if intent.status == PaymentIntent.Status.CAPTURED:
            return intent
        if intent.status in (PaymentIntent.Status.FAILED, PaymentIntent.Status.REFUNDED):
            raise PaymentsInvalidStateError("Payment intent no se puede capturar en su estado actual.")

        previous_status = intent.status
        intent.status = PaymentIntent.Status.CAPTURED
        intent.captured_at = timezone.now()
        intent.updated_at = timezone.now()
        if provider_txn_id:
            intent.provider_txn_id = provider_txn_id
        if metadata:
            merged = dict(intent.metadata or {})
            merged.update(dict(metadata))
            intent.metadata = merged
        intent.save(update_fields=["status", "captured_at", "provider_txn_id", "metadata", "updated_at"])

        publish_outbox_event(
            request=request,
            source_module="PAYMENTS",
            event_type="PaymentCaptured",
            payload={
                "payment_id": str(intent.payment_id),
                "amount": str(intent.amount),
                "currency": intent.currency,
                "status": intent.status,
                "provider_txn_id": intent.provider_txn_id,
                "payment_method": intent.payment_method,
            },
            actor_user=actor,
            company=company,
            branch=branch,
        )
        _write_intent_audit_event(
            request=request,
            actor=actor,
            intent=intent,
            event_type="PAYMENTS_INTENT_CAPTURED",
            company=company,
            branch=branch,
            before_snapshot={"status": previous_status},
            after_snapshot={
                "status": intent.status,
                "captured_at": _dt_iso(intent.captured_at),
                "provider_txn_id": intent.provider_txn_id,
                "amount": str(intent.amount),
            },
        )
        return intent


def capture_payment_intent(
    *,
    request: HttpRequest,
    actor: ActorPrincipal,
    payment_id: str | UUID,
    provider_txn_id: str = "",
    metadata: dict[str, Any] | None = None,
) -> PaymentIntent:
    company, branch = _scope_from_request(request)
    return capture_payment_intent_for_scope(
        company=company,
        branch=branch,
        actor=actor,
        request=request,
        payment_id=payment_id,
        provider_txn_id=provider_txn_id,
        metadata=metadata,
    )


def reverse_captured_payment_intent_for_scope(
    *,
    company: OrgUnit,
    branch: OrgUnit,
    actor: ActorPrincipal,
    payment_id: str | UUID,
    request: HttpRequest | None = None,
    idempotency_key: str,
    reason: str = "",
) -> tuple[PaymentIntent, bool]:
    idempotency_key = str(idempotency_key or "").strip()
    reason = str(reason or "").strip()
    if not idempotency_key:
        raise PaymentsValidationError("idempotency_key requerido.")
    if len(reason) > 255:
        raise PaymentsValidationError("reason demasiado largo.")

    with transaction.atomic():
        intent = (
            PaymentIntent.objects.select_for_update()
            .filter(
                payment_id=payment_id,
                company=company,
                branch=branch,
            )
            .first()
        )
        if intent is None:
            raise PaymentsNotFoundError("Payment intent no encontrado.")

        if intent.status == PaymentIntent.Status.REFUNDED:
            reversal = _capture_reversal_metadata(intent)
            if str(reversal.get("idempotency_key") or "") == idempotency_key:
                if str(reversal.get("reason") or "") != reason:
                    raise PaymentsConflictError("Idempotency key reutilizada con payload distinto.")
                return intent, True
            if reversal:
                raise PaymentsConflictError("Payment intent ya fue reversado con otra idempotency_key.")
            raise PaymentsInvalidStateError("Payment intent no se puede reversar en su estado actual.")

        if intent.status != PaymentIntent.Status.CAPTURED:
            raise PaymentsInvalidStateError("Payment intent no se puede reversar en su estado actual.")

        # Métodos que permiten reversal electrónico
        REVERSIBLE_METHODS = {
            TenderPaymentMethod.TRANSFER,
            TenderPaymentMethod.CARD,
            TenderPaymentMethod.CREDIT,
        }
        if intent.payment_method and intent.payment_method not in REVERSIBLE_METHODS:
            raise PaymentsInvalidStateError(
                f"Reversal electrónico no soportado para '{intent.payment_method}'. "
                "Use refund_payment_intent para otros métodos."
            )

        captured_event = _find_payment_captured_event(intent=intent, company=company, branch=branch)
        if captured_event is None:
            raise PaymentsConflictError("PaymentCaptured original requerido para reversa.")

        now = timezone.now()
        previous_status = intent.status
        reversal_id = str(uuid4())
        metadata = dict(intent.metadata) if isinstance(intent.metadata, dict) else {}
        metadata["capture_reversal"] = {
            "idempotency_key": idempotency_key,
            "reason": reason,
            "reversal_id": reversal_id,
            "reverses_event_type": "PaymentCaptured",
            "reverses_outbox_event_id": str(captured_event.event_id),
            "reversed_at": now.isoformat(),
        }

        intent.status = PaymentIntent.Status.REFUNDED
        intent.refunded_at = now
        intent.updated_at = now
        intent.metadata = metadata
        intent.save(update_fields=["status", "refunded_at", "metadata", "updated_at"])

        publish_outbox_event(
            request=request,
            source_module="PAYMENTS",
            event_type="PaymentCaptureReversed",
            payload={
                "payment_id": str(intent.payment_id),
                "amount": str(intent.amount),
                "currency": intent.currency,
                "payment_method": intent.payment_method,
                "provider_txn_id": intent.provider_txn_id,
                "previous_status": previous_status,
                "status": intent.status,
                "captured_at": _dt_iso(intent.captured_at),
                "refunded_at": _dt_iso(intent.refunded_at),
                "idempotency_key": idempotency_key,
                "reason": reason,
                "reversal_id": reversal_id,
                "reverses_event_type": "PaymentCaptured",
                "reverses_outbox_event_id": str(captured_event.event_id),
            },
            actor_user=actor,
            company=company,
            branch=branch,
            correlation_id=str(captured_event.correlation_id or ""),
            causation_id=str(captured_event.event_id),
        )
        _write_intent_audit_event(
            request=request,
            actor=actor,
            intent=intent,
            event_type="PAYMENTS_INTENT_REVERSED",
            company=company,
            branch=branch,
            before_snapshot={"status": previous_status},
            after_snapshot={
                "status": intent.status,
                "refunded_at": _dt_iso(intent.refunded_at),
            },
            extra_metadata={
                "idempotency_key": idempotency_key,
                "reason": reason,
                "reversal_id": reversal_id,
            },
        )
        return intent, False


def reverse_captured_payment_intent(
    *,
    request: HttpRequest,
    actor: ActorPrincipal,
    payment_id: str | UUID,
    idempotency_key: str,
    reason: str = "",
) -> tuple[PaymentIntent, bool]:
    company, branch = _scope_from_request(request)
    return reverse_captured_payment_intent_for_scope(
        company=company,
        branch=branch,
        actor=actor,
        request=request,
        payment_id=payment_id,
        idempotency_key=idempotency_key,
        reason=reason,
    )


def open_cash_session_for_scope(
    *,
    company: OrgUnit,
    branch: OrgUnit,
    actor: ActorPrincipal,
    request: HttpRequest | None = None,
    opening_amount: Decimal = Decimal("0.00"),
    register_id: str = "",
    notes: str = "",
) -> CashSession:
    with transaction.atomic():
        actor_fk = _coerce_actor_for_fk(actor=actor, field_name="opened_by")
        reg_id = (register_id or "").strip()

        # Verificar sesión abierta para el mismo register
        existing = CashSession.objects.select_for_update().filter(
            company=company,
            branch=branch,
            register_id=reg_id,
            status=CashSession.Status.OPEN,
        )
        if existing.exists():
            raise PaymentsConflictError(
                f"Ya existe una cash session OPEN para register_id='{reg_id}' en esta sucursal."
            )

        session = CashSession.objects.create(
            company=company,
            branch=branch,
            register_id=reg_id,
            opened_by=actor_fk,
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
        write_event(
            request=request,
            module="PAYMENTS",
            event_type="PAYMENTS_CASH_SESSION_OPENED",
            reason_code="OK",
            actor_user=actor,
            subject_type="CASH_SESSION",
            subject_id=str(session.id),
            after_snapshot={
                "status": session.status,
                "opening_amount": str(session.opening_amount),
                "register_id": session.register_id,
            },
            metadata={"company_id": str(company.id), "branch_id": str(branch.id)},
        )
        return session


def open_cash_session(
    *,
    request: HttpRequest,
    actor: ActorPrincipal,
    opening_amount: Decimal = Decimal("0.00"),
    register_id: str = "",
    notes: str = "",
) -> CashSession:
    company, branch = _scope_from_request(request)
    return open_cash_session_for_scope(
        company=company,
        branch=branch,
        actor=actor,
        request=request,
        opening_amount=opening_amount,
        register_id=register_id,
        notes=notes,
    )


def _cash_movement_payload_matches(
    *,
    movement: CashMovement,
    movement_type: str,
    amount: Decimal,
    reference: str,
    reason: str,
) -> bool:
    return (
        movement.movement_type == movement_type
        and Decimal(movement.amount) == Decimal(amount)
        and (movement.reference or "") == (reference or "")
        and (movement.reason or "") == (reason or "")
    )


def _idempotent_cash_movement_or_conflict(
    *,
    movement: CashMovement,
    movement_type: str,
    amount: Decimal,
    reference: str,
    reason: str,
) -> CashMovement:
    if not _cash_movement_payload_matches(
        movement=movement,
        movement_type=movement_type,
        amount=amount,
        reference=reference,
        reason=reason,
    ):
        raise PaymentsConflictError("Idempotency key reutilizada con payload distinto.")
    return movement


def _write_cash_movement_audit_event(
    *,
    request: HttpRequest | None,
    actor: ActorPrincipal,
    mov: CashMovement,
    idempotency_key: str,
) -> None:
    write_event(
        request=request,
        module="PAYMENTS",
        event_type="PAYMENTS_CASH_MOVEMENT_POSTED",
        reason_code="OK",
        actor_user=actor,
        subject_type="CASH_MOVEMENT",
        subject_id=str(mov.id),
        metadata={
            "session_id": str(mov.session_id),
            "movement_id": str(mov.id),
            "movement_type": mov.movement_type,
            "amount": str(mov.amount),
            "reference": mov.reference,
            "reason": mov.reason,
            "idempotency_key": idempotency_key,
        },
    )


def post_cash_movement_for_scope(
    *,
    company: OrgUnit,
    branch: OrgUnit,
    actor: ActorPrincipal,
    session_id: int,
    movement_type: str,
    amount: Decimal,
    request: HttpRequest | None = None,
    reference: str = "",
    reason: str = "",
    idempotency_key: str = "",
) -> tuple[CashMovement, bool]:
    reference = reference or ""
    reason = reason or ""
    idempotency_key = (idempotency_key or "").strip()
    with transaction.atomic():
        actor_fk = _coerce_actor_for_fk(actor=actor, field_name="created_by")
        session = (
            CashSession.objects.select_for_update()
            .filter(id=session_id, company=company, branch=branch)
            .first()
        )
        if session is None:
            raise PaymentsNotFoundError("Cash session no encontrada.")
        if session.status not in (CashSession.Status.OPEN, CashSession.Status.COUNT_PENDING):
            raise PaymentsInvalidStateError("Cash session no permite movimientos en su estado actual.")

        if idempotency_key:
            existing = (
                CashMovement.objects.select_for_update()
                .filter(session=session, idempotency_key=idempotency_key)
                .first()
            )
            if existing is not None:
                return (
                    _idempotent_cash_movement_or_conflict(
                        movement=existing,
                        movement_type=movement_type,
                        amount=amount,
                        reference=reference,
                        reason=reason,
                    ),
                    True,
                )

        try:
            with transaction.atomic():
                mov = CashMovement.objects.create(
                    session=session,
                    movement_type=movement_type,
                    amount=amount,
                    reference=reference,
                    reason=reason,
                    idempotency_key=idempotency_key,
                    created_by=actor_fk,
                )
        except IntegrityError:
            if not idempotency_key:
                raise
            existing = (
                CashMovement.objects.select_for_update()
                .filter(session=session, idempotency_key=idempotency_key)
                .first()
            )
            if existing is None:
                raise
            return (
                _idempotent_cash_movement_or_conflict(
                    movement=existing,
                    movement_type=movement_type,
                    amount=amount,
                    reference=reference,
                    reason=reason,
                ),
                True,
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
        _write_cash_movement_audit_event(
            request=request,
            actor=actor,
            mov=mov,
            idempotency_key=idempotency_key,
        )
        return mov, False


def post_cash_movement(
    *,
    request: HttpRequest,
    actor: ActorPrincipal,
    session_id: int,
    movement_type: str,
    amount: Decimal,
    reference: str = "",
    reason: str = "",
    idempotency_key: str = "",
) -> CashMovement:
    company, branch = _scope_from_request(request)
    mov, _idempotent = post_cash_movement_for_scope(
        company=company,
        branch=branch,
        actor=actor,
        session_id=session_id,
        movement_type=movement_type,
        amount=amount,
        request=request,
        reference=reference,
        reason=reason,
        idempotency_key=idempotency_key,
    )
    return mov


def post_cash_movement_with_status(
    *,
    request: HttpRequest,
    actor: ActorPrincipal,
    session_id: int,
    movement_type: str,
    amount: Decimal,
    reference: str = "",
    reason: str = "",
    idempotency_key: str = "",
) -> tuple[CashMovement, bool]:
    company, branch = _scope_from_request(request)
    return post_cash_movement_for_scope(
        company=company,
        branch=branch,
        actor=actor,
        session_id=session_id,
        movement_type=movement_type,
        amount=amount,
        request=request,
        reference=reference,
        reason=reason,
        idempotency_key=idempotency_key,
    )


def close_cash_session_for_scope(
    *,
    company: OrgUnit,
    branch: OrgUnit,
    actor: ActorPrincipal,
    session_id: int,
    counted_amount: Decimal,
    request: HttpRequest | None = None,
    notes: str = "",
) -> CashSession:
    with transaction.atomic():
        actor_fk = _coerce_actor_for_fk(actor=actor, field_name="closed_by")
        session = (
            CashSession.objects.select_for_update()
            .filter(id=session_id, company=company, branch=branch)
            .first()
        )
        if session is None:
            raise PaymentsNotFoundError("Cash session no encontrada.")
        if session.status == CashSession.Status.CLOSED:
            return session
        if session.status not in (
            CashSession.Status.OPEN,
            CashSession.Status.COUNT_PENDING,
            CashSession.Status.REVIEW_PENDING,
        ):
            raise PaymentsInvalidStateError("Estado de cash session inválido para cierre.")

        prev_status = session.status
        session.status = CashSession.Status.CLOSED
        session.closed_by = actor_fk
        session.closed_at = timezone.now()
        session.counted_amount = counted_amount
        session.difference_amount = Decimal(counted_amount) - Decimal(session.expected_amount)
        if notes:
            session.notes = notes
        try:
            session.clean()
        except ValidationError as exc:
            raise PaymentsValidationError(str(exc)) from exc
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
        write_event(
            request=request,
            module="PAYMENTS",
            event_type="PAYMENTS_CASH_SESSION_CLOSED",
            reason_code="OK",
            actor_user=actor,
            subject_type="CASH_SESSION",
            subject_id=str(session.id),
            before_snapshot={"status": prev_status},
            after_snapshot={
                "status": session.status,
                "expected_amount": str(session.expected_amount),
                "counted_amount": str(session.counted_amount),
                "difference_amount": str(session.difference_amount),
            },
            metadata={"company_id": str(company.id), "branch_id": str(branch.id)},
        )
        # Detección formal de diferencia de caja (sobrante/faltante).
        if session.difference_amount != Decimal("0.00"):
            kind = "OVER" if session.difference_amount > 0 else "SHORT"
            publish_outbox_event(
                request=request,
                source_module="PAYMENTS",
                event_type="CashDifferenceDetected",
                payload={
                    "session_id": session.id,
                    "expected_amount": str(session.expected_amount),
                    "counted_amount": str(session.counted_amount),
                    "difference_amount": str(session.difference_amount),
                    "kind": kind,
                },
                actor_user=actor,
                company=company,
                branch=branch,
            )
            write_event(
                request=request,
                module="PAYMENTS",
                event_type="PAYMENTS_CASH_DIFFERENCE_DETECTED",
                reason_code="OK",
                actor_user=actor,
                subject_type="CASH_SESSION",
                subject_id=str(session.id),
                after_snapshot={"difference_amount": str(session.difference_amount), "kind": kind},
                metadata={"company_id": str(company.id), "branch_id": str(branch.id)},
            )
        return session


def close_cash_session(
    *,
    request: HttpRequest,
    actor: ActorPrincipal,
    session_id: int,
    counted_amount: Decimal,
    notes: str = "",
) -> CashSession:
    company, branch = _scope_from_request(request)
    return close_cash_session_for_scope(
        company=company,
        branch=branch,
        actor=actor,
        session_id=session_id,
        counted_amount=counted_amount,
        request=request,
        notes=notes,
    )


# ---------------------------------------------------------------------------
# authorize_payment_intent — INTENDED → AUTHORIZED
# ---------------------------------------------------------------------------

def authorize_payment_intent_for_scope(
    *,
    company: OrgUnit,
    branch: OrgUnit,
    actor: ActorPrincipal,
    payment_id: str | UUID,
    request: HttpRequest | None = None,
    amount_authorized: Decimal | None = None,
    provider_txn_id: str = "",
    metadata: dict[str, Any] | None = None,
) -> PaymentIntent:
    with transaction.atomic():
        intent = (
            PaymentIntent.objects.select_for_update()
            .filter(payment_id=payment_id, company=company, branch=branch)
            .first()
        )
        if intent is None:
            raise PaymentsNotFoundError("Payment intent no encontrado.")
        if intent.status == PaymentIntent.Status.AUTHORIZED:
            return intent
        if intent.status != PaymentIntent.Status.INTENDED:
            raise PaymentsInvalidStateError(
                f"Solo se puede autorizar desde INTENDED. Estado actual: {intent.status}"
            )

        previous_status = intent.status
        intent.status = PaymentIntent.Status.AUTHORIZED
        intent.authorized_at = timezone.now()
        intent.amount_authorized = amount_authorized or intent.amount
        if provider_txn_id:
            intent.provider_txn_id = provider_txn_id
        if metadata:
            merged = dict(intent.metadata or {})
            merged.update(metadata)
            intent.metadata = merged
        intent.save(update_fields=["status", "authorized_at", "amount_authorized", "provider_txn_id", "metadata", "updated_at"])

        publish_outbox_event(
            request=request,
            source_module="PAYMENTS",
            event_type="PaymentAuthorized",
            payload={
                "payment_id": str(intent.payment_id),
                "amount": str(intent.amount),
                "amount_authorized": str(intent.amount_authorized),
                "currency": intent.currency,
                "status": intent.status,
                "payment_method": intent.payment_method,
            },
            actor_user=actor,
            company=company,
            branch=branch,
        )
        _write_intent_audit_event(
            request=request,
            actor=actor,
            intent=intent,
            event_type="PAYMENTS_INTENT_AUTHORIZED",
            company=company,
            branch=branch,
            before_snapshot={"status": previous_status},
            after_snapshot={
                "status": intent.status,
                "amount_authorized": str(intent.amount_authorized),
                "authorized_at": _dt_iso(intent.authorized_at),
                "provider_txn_id": intent.provider_txn_id,
            },
        )
        return intent


def authorize_payment_intent(
    *,
    request: HttpRequest,
    actor: ActorPrincipal,
    payment_id: str | UUID,
    amount_authorized: Decimal | None = None,
    provider_txn_id: str = "",
    metadata: dict[str, Any] | None = None,
) -> PaymentIntent:
    company, branch = _scope_from_request(request)
    return authorize_payment_intent_for_scope(
        company=company, branch=branch, actor=actor,
        request=request, payment_id=payment_id,
        amount_authorized=amount_authorized,
        provider_txn_id=provider_txn_id, metadata=metadata,
    )


# ---------------------------------------------------------------------------
# cancel_payment_intent — INTENDED/AUTHORIZED → CANCELLED
# ---------------------------------------------------------------------------

def cancel_payment_intent_for_scope(
    *,
    company: OrgUnit,
    branch: OrgUnit,
    actor: ActorPrincipal,
    payment_id: str | UUID,
    request: HttpRequest | None = None,
    reason: str = "",
) -> PaymentIntent:
    with transaction.atomic():
        intent = (
            PaymentIntent.objects.select_for_update()
            .filter(payment_id=payment_id, company=company, branch=branch)
            .first()
        )
        if intent is None:
            raise PaymentsNotFoundError("Payment intent no encontrado.")
        if intent.status == PaymentIntent.Status.CANCELLED:
            return intent
        if intent.status in (PaymentIntent.Status.CAPTURED, PaymentIntent.Status.PARTIALLY_CAPTURED):
            raise PaymentsInvalidStateError("No se puede cancelar un pago ya capturado. Use refund.")
        if intent.status in (PaymentIntent.Status.REFUNDED, PaymentIntent.Status.FAILED):
            raise PaymentsInvalidStateError(f"No se puede cancelar desde estado {intent.status}.")

        previous_status = intent.status
        intent.status = PaymentIntent.Status.CANCELLED
        intent.cancellation_reason = (reason or "")[:255]
        intent.save(update_fields=["status", "cancellation_reason", "updated_at"])

        publish_outbox_event(
            request=request,
            source_module="PAYMENTS",
            event_type="PaymentCancelled",
            payload={
                "payment_id": str(intent.payment_id),
                "amount": str(intent.amount),
                "currency": intent.currency,
                "status": intent.status,
                "reason": intent.cancellation_reason,
            },
            actor_user=actor,
            company=company,
            branch=branch,
        )
        _write_intent_audit_event(
            request=request,
            actor=actor,
            intent=intent,
            event_type="PAYMENTS_INTENT_CANCELLED",
            company=company,
            branch=branch,
            before_snapshot={"status": previous_status},
            after_snapshot={
                "status": intent.status,
                "cancellation_reason": intent.cancellation_reason,
            },
        )
        return intent


def cancel_payment_intent(
    *,
    request: HttpRequest,
    actor: ActorPrincipal,
    payment_id: str | UUID,
    reason: str = "",
) -> PaymentIntent:
    company, branch = _scope_from_request(request)
    return cancel_payment_intent_for_scope(
        company=company, branch=branch, actor=actor,
        request=request, payment_id=payment_id, reason=reason,
    )


# ---------------------------------------------------------------------------
# refund_payment_intent — reembolso parcial o total post-capture
# ---------------------------------------------------------------------------

def refund_payment_intent_for_scope(
    *,
    company: OrgUnit,
    branch: OrgUnit,
    actor: ActorPrincipal,
    payment_id: str | UUID,
    amount: Decimal,
    request: HttpRequest | None = None,
    idempotency_key: str = "",
    reason: str = "",
    provider_refund_id: str = "",
) -> PaymentRefund:
    idempotency_key = (idempotency_key or "").strip()
    if amount <= 0:
        raise PaymentsValidationError("El monto del reembolso debe ser > 0.")

    with transaction.atomic():
        intent = (
            PaymentIntent.objects.select_for_update()
            .filter(payment_id=payment_id, company=company, branch=branch)
            .first()
        )
        if intent is None:
            raise PaymentsNotFoundError("Payment intent no encontrado.")

        if intent.status not in (
            PaymentIntent.Status.CAPTURED,
            PaymentIntent.Status.PARTIALLY_CAPTURED,
            PaymentIntent.Status.PARTIALLY_REFUNDED,
        ):
            raise PaymentsInvalidStateError(
                f"Solo se puede reembolsar un pago capturado. Estado: {intent.status}"
            )

        # Idempotencia
        if idempotency_key:
            existing = PaymentRefund.objects.filter(
                intent=intent, idempotency_key=idempotency_key
            ).first()
            if existing:
                return existing

        refundable = intent.refundable_amount
        if amount > refundable:
            raise PaymentsValidationError(
                f"Monto a reembolsar ({amount}) excede el monto refundable ({refundable})."
            )

        refund = PaymentRefund.objects.create(
            intent=intent,
            company=company,
            amount=amount,
            currency=intent.currency,
            reason=(reason or "")[:255],
            idempotency_key=idempotency_key,
            provider_refund_id=provider_refund_id or "",
            created_by=actor if getattr(actor, "id", None) else None,
        )

        previous_status = intent.status
        intent.amount_refunded = (intent.amount_refunded or Decimal("0.00")) + amount
        if intent.amount_refunded >= (intent.amount_captured or intent.amount):
            intent.status = PaymentIntent.Status.REFUNDED
        else:
            intent.status = PaymentIntent.Status.PARTIALLY_REFUNDED
        intent.refunded_at = timezone.now()
        intent.save(update_fields=["amount_refunded", "status", "refunded_at", "updated_at"])

        publish_outbox_event(
            request=request,
            source_module="PAYMENTS",
            event_type="PaymentRefunded",
            payload={
                "payment_id": str(intent.payment_id),
                "refund_id": str(refund.refund_id),
                "amount_refunded": str(amount),
                "total_refunded": str(intent.amount_refunded),
                "currency": intent.currency,
                "status": intent.status,
                "reason": reason,
            },
            actor_user=actor,
            company=company,
            branch=branch,
        )
        _write_intent_audit_event(
            request=request,
            actor=actor,
            intent=intent,
            event_type="PAYMENTS_INTENT_REFUNDED",
            company=company,
            branch=branch,
            before_snapshot={"status": previous_status},
            after_snapshot={
                "status": intent.status,
                "amount_refunded": str(intent.amount_refunded),
                "refunded_at": _dt_iso(intent.refunded_at),
            },
            extra_metadata={
                "refund_id": str(refund.refund_id),
                "amount": str(amount),
                "total_refunded": str(intent.amount_refunded),
                "reason": (reason or "")[:255],
            },
        )
        return refund


def refund_payment_intent(
    *,
    request: HttpRequest,
    actor: ActorPrincipal,
    payment_id: str | UUID,
    amount: Decimal,
    idempotency_key: str = "",
    reason: str = "",
    provider_refund_id: str = "",
) -> PaymentRefund:
    company, branch = _scope_from_request(request)
    return refund_payment_intent_for_scope(
        company=company, branch=branch, actor=actor,
        request=request, payment_id=payment_id,
        amount=amount, idempotency_key=idempotency_key,
        reason=reason, provider_refund_id=provider_refund_id,
    )


# ---------------------------------------------------------------------------
# Arqueo de caja — CashDenomination
# ---------------------------------------------------------------------------

NICARAGUA_BILLS = [Decimal("1000"), Decimal("500"), Decimal("200"), Decimal("100"),
                   Decimal("50"), Decimal("20"), Decimal("10")]
NICARAGUA_COINS = [Decimal("25"), Decimal("10"), Decimal("5"), Decimal("1"), Decimal("0.50")]


def submit_denomination_count(
    *,
    request: HttpRequest,
    actor: ActorPrincipal,
    session_id: int,
    denominations: list[dict],
) -> tuple[CashSession, list[CashDenomination], Decimal]:
    """
    Registra el arqueo de caja por denominación.
    denominations: [{"denomination_value": 100.00, "quantity": 5, "denomination_type": "BILL"}, ...]
    Retorna (session, denominations, total_counted).
    """
    company, branch = _scope_from_request(request)
    with transaction.atomic():
        session = (
            CashSession.objects.select_for_update()
            .filter(id=session_id, company=company, branch=branch)
            .first()
        )
        if session is None:
            raise PaymentsNotFoundError("Cash session no encontrada.")
        if session.status not in (CashSession.Status.OPEN, CashSession.Status.COUNT_PENDING):
            raise PaymentsInvalidStateError("Solo se puede hacer arqueo en sesión OPEN o COUNT_PENDING.")

        # Eliminar denominaciones previas del arqueo
        CashDenomination.objects.filter(session=session).delete()

        created = []
        total_counted = Decimal("0.00")
        for d in denominations:
            qty = int(d.get("quantity", 0))
            if qty < 0:
                raise PaymentsValidationError("Cantidad de denominación no puede ser negativa.")
            denom_val = Decimal(str(d["denomination_value"]))
            denom_type = str(d.get("denomination_type", CashDenomination.DenominationType.BILL))
            obj = CashDenomination.objects.create(
                session=session,
                denomination_type=denom_type,
                denomination_value=denom_val,
                quantity=qty,
            )
            created.append(obj)
            total_counted += obj.subtotal

        session.counted_amount = total_counted
        session.status = CashSession.Status.COUNT_PENDING
        session.save(update_fields=["counted_amount", "status"])

    return session, created, total_counted


# ---------------------------------------------------------------------------
# reopen_cash_session — para investigación
# ---------------------------------------------------------------------------

def reopen_cash_session_for_investigation(
    *,
    request: HttpRequest,
    actor: ActorPrincipal,
    session_id: int,
    reason: str,
) -> CashSession:
    company, branch = _scope_from_request(request)
    with transaction.atomic():
        session = (
            CashSession.objects.select_for_update()
            .filter(id=session_id, company=company, branch=branch)
            .first()
        )
        if session is None:
            raise PaymentsNotFoundError("Cash session no encontrada.")
        if session.status != CashSession.Status.CLOSED:
            raise PaymentsInvalidStateError("Solo se puede reabrir una sesión CLOSED.")

        session.status = CashSession.Status.REOPENED_FOR_INVESTIGATION
        session.closed_at = None
        metadata = dict(session.metadata or {})
        metadata["reopen_reason"] = reason
        metadata["reopened_at"] = timezone.now().isoformat()
        session.metadata = metadata
        session.save(update_fields=["status", "closed_at", "metadata"])

        publish_outbox_event(
            request=request,
            source_module="PAYMENTS",
            event_type="CashSessionReopened",
            payload={"session_id": session.id, "reason": reason},
            actor_user=actor,
            company=company,
            branch=branch,
        )
        write_event(
            request=request,
            module="PAYMENTS",
            event_type="PAYMENTS_CASH_SESSION_REOPENED",
            reason_code="OK",
            actor_user=actor,
            subject_type="CASH_SESSION",
            subject_id=str(session.id),
            before_snapshot={"status": CashSession.Status.CLOSED},
            after_snapshot={"status": session.status},
            metadata={"company_id": str(company.id), "branch_id": str(branch.id), "reason": reason},
        )
    return session
