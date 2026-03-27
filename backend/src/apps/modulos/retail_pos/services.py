from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import hmac
from typing import Any
from uuid import uuid4

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.modulos.audit.writer import write_event
from apps.modulos.integration.services import publish_outbox_event
from apps.modulos.estacion_servicios.models import FuelPaymentMethod, FuelSaleStatus, FuelShift
from apps.modulos.estacion_servicios.services import cancel_sale, create_sale, record_dispense
from apps.kernels.payments.models import CashMovement
from apps.kernels.payments.services import (
    capture_payment_intent,
    close_cash_session,
    create_payment_intent,
    open_cash_session,
    post_cash_movement,
)
from config.metrics import record_pos_checkout

from .models import (
    PeripheralCapability,
    PeripheralKind,
    PosPeripheralStatus,
    PosEdgeChallenge,
    PosEdgeChallengeStatus,
    PosEdgeSession,
    PosEdgeSessionStatus,
    PosSession,
    PosSessionStatus,
    PosTicket,
    PosTicketLine,
    PosTicketStatus,
)


MONEY_Q = Decimal("0.01")


@dataclass(frozen=True)
class OpenPosSessionResult:
    session: PosSession
    duplicate: bool


@dataclass(frozen=True)
class OpenPosTicketResult:
    ticket: PosTicket
    duplicate: bool


@dataclass(frozen=True)
class IssueEdgeChallengeResult:
    challenge: PosEdgeChallenge


@dataclass(frozen=True)
class EdgeHandshakeResult:
    session: PosEdgeSession
    devices_synced: int


@dataclass(frozen=True)
class PosCompensationCycleResult:
    attempted: int
    succeeded: int
    failed: int
    still_pending: int
    errors: list[dict[str, str]]


def _money(v: Decimal) -> Decimal:
    return Decimal(v).quantize(MONEY_Q, rounding=ROUND_HALF_UP)


def _require_branch(request):
    branch = getattr(request, "branch", None)
    if branch is None:
        raise ValueError("X-Branch-Id requerido")
    return branch


def _require_actor(actor_user):
    if actor_user is None or not getattr(actor_user, "is_authenticated", False):
        raise ValueError("Actor requerido para operación POS")
    return actor_user


def _new_correlation(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:20]}"


def _utc_now():
    return timezone.now()


def _ttl_seconds(name: str, default: int) -> int:
    try:
        raw = int(getattr(settings, name, default))
        if raw <= 0:
            return default
        return raw
    except Exception:  # noqa: BLE001
        return default


def _int_setting(name: str, default: int, minimum: int = 1, maximum: int | None = None) -> int:
    try:
        raw = int(getattr(settings, name, default))
    except Exception:  # noqa: BLE001
        raw = default
    value = max(minimum, raw)
    if maximum is not None:
        value = min(value, maximum)
    return value


def _compensation_max_attempts() -> int:
    return _int_setting("POS_COMPENSATION_MAX_ATTEMPTS", 8, minimum=1, maximum=20)


def _compensation_backoff_cap_minutes() -> int:
    return _int_setting("POS_COMPENSATION_BACKOFF_CAP_MIN", 60, minimum=1, maximum=1440)


def _next_compensation_retry_at(*, now, attempt: int):
    cap = _compensation_backoff_cap_minutes()
    delay_minutes = min(2 ** max(1, int(attempt)), cap)
    return now + timedelta(minutes=int(delay_minutes))


def _edge_shared_secret_b64() -> str:
    return str(getattr(settings, "POS_EDGE_CONNECTOR_SHARED_SECRET", "") or "").strip()


def _edge_handshake_message(*, challenge: PosEdgeChallenge, connector_id: str) -> bytes:
    return (
        f"{challenge.challenge_id}.{challenge.nonce}.{challenge.company_id}.{challenge.branch_id}.{connector_id}".encode(
            "utf-8"
        )
    )


def _verify_edge_hmac_signature(*, secret_b64: str, message: bytes, signature_b64: str) -> bool:
    if not secret_b64 or not signature_b64:
        return False
    try:
        secret = base64.b64decode(secret_b64.encode("utf-8"), validate=True)
        expected = hmac.new(secret, message, hashlib.sha256).digest()
        actual = base64.b64decode(signature_b64.encode("utf-8"), validate=True)
    except Exception:  # noqa: BLE001
        return False
    return hmac.compare_digest(expected, actual)


def _expire_stale_edge_state(*, company, branch) -> None:
    now = _utc_now()
    PosEdgeChallenge.objects.filter(
        company=company,
        branch=branch,
        status=PosEdgeChallengeStatus.PENDING,
        expires_at__lt=now,
    ).update(
        status=PosEdgeChallengeStatus.EXPIRED,
    )
    PosEdgeSession.objects.filter(
        company=company,
        branch=branch,
        status=PosEdgeSessionStatus.ACTIVE,
        expires_at__lt=now,
    ).update(
        status=PosEdgeSessionStatus.EXPIRED,
    )


_CAPABILITY_PRIORITY = {
    PeripheralCapability.SUPPORTED: 3,
    PeripheralCapability.EXPERIMENTAL: 2,
    PeripheralCapability.UNSUPPORTED: 1,
}


def _normalize_capability(value: str | None) -> str:
    raw = str(value or "").strip().lower()
    if raw == PeripheralCapability.SUPPORTED:
        return PeripheralCapability.SUPPORTED
    if raw == PeripheralCapability.UNSUPPORTED:
        return PeripheralCapability.UNSUPPORTED
    return PeripheralCapability.EXPERIMENTAL


def _merge_capability_registry(
    *,
    registry_payload: dict[str, Any] | None,
    devices_payload: list[dict[str, Any]] | None,
) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in (registry_payload or {}).items():
        if not key:
            continue
        out[str(key).upper()] = _normalize_capability(str(value))

    for row in devices_payload or []:
        kind = str(row.get("device_kind") or "").upper()
        if kind not in PeripheralKind.values:
            continue
        candidate = _normalize_capability(str(row.get("capability_level") or PeripheralCapability.EXPERIMENTAL))
        current = out.get(kind)
        if current is None or _CAPABILITY_PRIORITY[candidate] >= _CAPABILITY_PRIORITY[_normalize_capability(current)]:
            out[kind] = candidate
    return dict(sorted(out.items(), key=lambda item: item[0]))


def get_current_pos_session(*, company, branch) -> PosSession | None:
    return (
        PosSession.objects.filter(company=company, branch=branch, status=PosSessionStatus.OPEN)
        .order_by("-opened_at", "-id")
        .first()
    )


@transaction.atomic
def open_pos_session(*, request, actor_user, opening_amount: Decimal = Decimal("0.00"), note: str = "") -> OpenPosSessionResult:
    actor = _require_actor(actor_user)
    branch = _require_branch(request)
    company = request.company

    existing = (
        PosSession.objects.select_for_update()
        .filter(company=company, branch=branch, status=PosSessionStatus.OPEN)
        .order_by("-opened_at", "-id")
        .first()
    )
    if existing is not None:
        return OpenPosSessionResult(session=existing, duplicate=True)

    cash_session = open_cash_session(
        request=request,
        actor=actor,
        opening_amount=_money(opening_amount),
        notes=note or "",
    )

    session = PosSession.objects.create(
        company=company,
        branch=branch,
        status=PosSessionStatus.OPEN,
        opened_by=actor,
        opening_amount=_money(opening_amount),
        note=note or "",
        cash_session=cash_session,
    )

    publish_outbox_event(
        request=request,
        source_module="POS",
        event_type="POSSessionOpened",
        payload={
            "session_id": int(session.id),
            "status": session.status,
            "cash_session_id": session.cash_session_id,
            "opening_amount": str(session.opening_amount),
        },
        actor_user=actor,
        company=company,
        branch=branch,
    )

    write_event(
        request=request,
        module="POS",
        event_type="POS_SESSION_OPENED",
        reason_code="SYNC_OK",
        subject_type="POS_SESSION",
        subject_id=str(session.id),
        actor_user=actor,
        metadata={
            "company_id": str(company.id),
            "branch_id": str(branch.id),
            "cash_session_id": str(session.cash_session_id or ""),
        },
    )

    return OpenPosSessionResult(session=session, duplicate=False)


@transaction.atomic
def close_pos_session(*, request, actor_user, session: PosSession, counted_amount: Decimal, note: str = "") -> PosSession:
    actor = _require_actor(actor_user)
    if session.status == PosSessionStatus.CLOSED:
        return session
    if session.status != PosSessionStatus.OPEN:
        raise ValueError("Sesión POS no válida para cierre")

    if session.cash_session_id:
        close_cash_session(
            request=request,
            actor=actor,
            session_id=int(session.cash_session_id),
            counted_amount=_money(counted_amount),
            notes=note or "",
        )

    session.status = PosSessionStatus.CLOSED
    session.closed_by = actor
    session.closed_at = timezone.now()
    session.counted_amount = _money(counted_amount)
    session.difference_amount = _money(Decimal(session.counted_amount) - Decimal(session.opening_amount))
    if note:
        session.note = note
    session.save(
        update_fields=[
            "status",
            "closed_by",
            "closed_at",
            "counted_amount",
            "difference_amount",
            "note",
        ]
    )

    publish_outbox_event(
        request=request,
        source_module="POS",
        event_type="POSSessionClosed",
        payload={
            "session_id": int(session.id),
            "status": session.status,
            "counted_amount": str(session.counted_amount),
            "difference_amount": str(session.difference_amount),
        },
        actor_user=actor,
        company=session.company,
        branch=session.branch,
    )

    write_event(
        request=request,
        module="POS",
        event_type="POS_SESSION_CLOSED",
        reason_code="SYNC_OK",
        subject_type="POS_SESSION",
        subject_id=str(session.id),
        actor_user=actor,
    )

    return session


@transaction.atomic
def open_ticket(
    *,
    request,
    actor_user,
    session: PosSession,
    shift_id: int,
    idempotency_key: str = "",
    external_ref: str = "",
    customer_name: str = "",
    customer_ref: str = "",
    sale_type: str,
    payment_method: str,
) -> OpenPosTicketResult:
    actor = _require_actor(actor_user)
    branch = _require_branch(request)
    company = request.company

    if session.status != PosSessionStatus.OPEN:
        raise ValueError("Sesión POS cerrada")

    if idempotency_key:
        existing = PosTicket.objects.filter(company=company, idempotency_key=idempotency_key).first()
        if existing is not None:
            return OpenPosTicketResult(ticket=existing, duplicate=True)

    shift = FuelShift.objects.filter(
        id=int(shift_id),
        company=company,
        branch=branch,
    ).first()
    if shift is None:
        raise ValueError("Shift inválido para POS")

    ticket = PosTicket.objects.create(
        company=company,
        branch=branch,
        session=session,
        shift=shift,
        status=PosTicketStatus.CART_OPEN,
        idempotency_key=idempotency_key or "",
        correlation_id="",
        causation_id="",
        external_ref=external_ref or "",
        customer_name=customer_name or "",
        customer_ref=customer_ref or "",
        sale_type=sale_type,
        payment_method=payment_method,
        created_by=actor,
    )
    corr = _new_correlation(f"pos-ticket-{ticket.id}")
    ticket.correlation_id = corr
    ticket.causation_id = f"{corr}:open"
    ticket.save(update_fields=["correlation_id", "causation_id"])

    publish_outbox_event(
        request=request,
        source_module="POS",
        event_type="POSTicketOpened",
        payload={
            "ticket_id": int(ticket.id),
            "session_id": int(ticket.session_id),
            "shift_id": int(ticket.shift_id),
            "status": ticket.status,
            "payment_method": ticket.payment_method,
            "sale_type": ticket.sale_type,
        },
        actor_user=actor,
        company=company,
        branch=branch,
        correlation_id=ticket.correlation_id,
        causation_id=ticket.causation_id,
    )

    return OpenPosTicketResult(ticket=ticket, duplicate=False)


@transaction.atomic
def create_ticket_line(*, ticket: PosTicket, line_payload: dict[str, Any]) -> PosTicketLine:
    if ticket.status in (PosTicketStatus.VOIDED, PosTicketStatus.CLOSED):
        raise ValueError("Ticket no editable")

    max_line = ticket.lines.order_by("-line_no").values_list("line_no", flat=True).first() or 0
    line_no = int(max_line) + 1

    volume = Decimal(str(line_payload["volume"]))
    unit_price = Decimal(str(line_payload["unit_price_entered"]))
    amount_estimated = _money(volume * unit_price)

    return PosTicketLine.objects.create(
        ticket=ticket,
        line_no=line_no,
        product=str(line_payload["product"]),
        volume=volume,
        volume_uom=str(line_payload.get("volume_uom") or "LITER"),
        unit_price_entered=unit_price,
        unit_price_uom=str(line_payload.get("unit_price_uom") or "PER_LITER"),
        amount_estimated=amount_estimated,
        metadata=dict(line_payload.get("metadata") or {}),
    )


def _ensure_first_line(*, ticket: PosTicket, line_payload: dict[str, Any] | None) -> PosTicketLine:
    current = ticket.lines.order_by("line_no", "id").first()
    if current is not None:
        return current
    if line_payload is None:
        raise ValueError("Ticket requiere al menos una línea para checkout")
    return create_ticket_line(ticket=ticket, line_payload=line_payload)


@transaction.atomic
def checkout_ticket(*, request, actor_user, ticket: PosTicket, line_payload: dict[str, Any] | None = None) -> PosTicket:
    started_at = timezone.now()
    actor = _require_actor(actor_user)

    if ticket.status == PosTicketStatus.VOIDED:
        raise ValueError("Ticket anulado")
    if ticket.status == PosTicketStatus.CLOSED:
        return ticket

    if ticket.session.status != PosSessionStatus.OPEN:
        raise ValueError("La sesión POS está cerrada")

    ticket.status = PosTicketStatus.CHECKOUT_PENDING
    ticket.checkout_started_at = started_at
    ticket.last_error = ""
    ticket.save(update_fields=["status", "checkout_started_at", "last_error", "updated_at"])

    sale = None
    try:
        line = _ensure_first_line(ticket=ticket, line_payload=line_payload)
        shift = ticket.shift

        dispense = record_dispense(
            request=request,
            company=ticket.company,
            branch=ticket.branch,
            shift=shift,
            actor_user=actor,
            product=line.product,
            volume_entered=line.volume,
            volume_uom=line.volume_uom,
            unit_price_entered=line.unit_price_entered,
            unit_price_uom=line.unit_price_uom,
            external_ref=ticket.external_ref,
            note=f"POS ticket {ticket.id}",
        )

        sale = create_sale(
            request=request,
            company=ticket.company,
            branch=ticket.branch,
            shift=shift,
            dispense=dispense,
            actor_user=actor,
            sale_type=ticket.sale_type,
            payment_method=ticket.payment_method,
            customer_name=ticket.customer_name,
            customer_ref=ticket.customer_ref,
            is_fiscal=False,
        )

        intent, _ = create_payment_intent(
            request=request,
            actor=actor,
            amount=Decimal(sale.total_amount),
            currency="NIO",
            idempotency_key=f"pos-ticket:{ticket.id}:payment",
            external_ref=f"pos-ticket:{ticket.id}",
            provider="POS",
        )
        intent = capture_payment_intent(
            request=request,
            actor=actor,
            payment_id=intent.payment_id,
            provider_txn_id=f"pos:{ticket.id}:{timezone.now().strftime('%Y%m%d%H%M%S')}",
            metadata={"ticket_id": int(ticket.id), "channel": "retail_pos"},
        )

        cash_movement = None
        if ticket.payment_method == FuelPaymentMethod.CASH and ticket.session.cash_session_id:
            cash_movement = post_cash_movement(
                request=request,
                actor=actor,
                session_id=int(ticket.session.cash_session_id),
                movement_type=CashMovement.MovementType.INCOME,
                amount=Decimal(sale.total_amount),
                reference=f"pos-ticket:{ticket.id}",
                reason="POS_CHECKOUT",
            )

        now = timezone.now()
        ticket.sale = sale
        ticket.payment_intent = intent
        ticket.cash_movement = cash_movement
        ticket.total_amount = _money(Decimal(sale.total_amount))
        ticket.status = PosTicketStatus.PAID
        ticket.paid_at = now
        ticket.status = PosTicketStatus.CLOSED
        ticket.closed_at = now
        ticket.last_error = ""
        ticket.compensation_pending = False
        ticket.compensation_last_error = ""
        ticket.compensation_next_retry_at = None
        ticket.last_compensation_at = now
        ticket.save(
            update_fields=[
                "sale",
                "payment_intent",
                "cash_movement",
                "total_amount",
                "status",
                "paid_at",
                "closed_at",
                "last_error",
                "compensation_pending",
                "compensation_last_error",
                "compensation_next_retry_at",
                "last_compensation_at",
                "updated_at",
            ]
        )

        publish_outbox_event(
            request=request,
            source_module="POS",
            event_type="POSPaymentCaptured",
            payload={
                "ticket_id": int(ticket.id),
                "payment_id": str(intent.payment_id),
                "amount": str(ticket.total_amount),
                "cash_movement_id": int(cash_movement.id) if cash_movement else None,
            },
            actor_user=actor,
            company=ticket.company,
            branch=ticket.branch,
            correlation_id=ticket.correlation_id,
            causation_id=f"{ticket.correlation_id}:payment-captured",
        )

        publish_outbox_event(
            request=request,
            source_module="POS",
            event_type="POSTicketClosed",
            payload={
                "ticket_id": int(ticket.id),
                "status": ticket.status,
                "sale_id": int(sale.id),
                "payment_id": str(intent.payment_id),
                "total_amount": str(ticket.total_amount),
            },
            actor_user=actor,
            company=ticket.company,
            branch=ticket.branch,
            correlation_id=ticket.correlation_id,
            causation_id=f"{ticket.correlation_id}:ticket-closed",
        )

        write_event(
            request=request,
            module="POS",
            event_type="POS_TICKET_CLOSED",
            reason_code="SYNC_OK",
            subject_type="POS_TICKET",
            subject_id=str(ticket.id),
            actor_user=actor,
            metadata={
                "sale_id": str(sale.id),
                "payment_id": str(intent.payment_id),
                "total_amount": str(ticket.total_amount),
            },
        )
        record_pos_checkout(ok=True, reason="", started_at=started_at)
        return ticket

    except Exception as exc:  # noqa: BLE001
        now = timezone.now()
        attempt = int(ticket.compensation_attempts) + 1
        retryable = attempt < _compensation_max_attempts()
        ticket.last_error = str(exc)[:255]
        ticket.status = PosTicketStatus.CHECKOUT_PENDING
        ticket.compensation_pending = bool(retryable)
        ticket.compensation_attempts = int(attempt)
        ticket.compensation_last_error = ticket.last_error
        ticket.compensation_next_retry_at = _next_compensation_retry_at(now=now, attempt=attempt) if retryable else None
        ticket.last_compensation_at = now
        ticket.save(
            update_fields=[
                "status",
                "last_error",
                "compensation_pending",
                "compensation_attempts",
                "compensation_last_error",
                "compensation_next_retry_at",
                "last_compensation_at",
                "updated_at",
            ]
        )

        if sale is not None and sale.status == FuelSaleStatus.ACTIVE:
            try:
                cancel_sale(request=request, sale=sale, actor_user=actor, reason="POS_COMPENSATION_AUTO")
            except Exception:  # noqa: BLE001
                pass

        publish_outbox_event(
            request=request,
            source_module="POS",
            event_type="POSCompensationRaised",
            payload={
                "ticket_id": int(ticket.id),
                "status": ticket.status,
                "error": ticket.last_error,
                "attempt": int(ticket.compensation_attempts),
                "retryable": bool(ticket.compensation_pending),
                "next_retry_at": (
                    ticket.compensation_next_retry_at.isoformat() if ticket.compensation_next_retry_at else None
                ),
            },
            actor_user=actor,
            company=ticket.company,
            branch=ticket.branch,
            correlation_id=ticket.correlation_id,
            causation_id=f"{ticket.correlation_id}:compensation-raised",
        )
        record_pos_checkout(ok=False, reason="CHECKOUT_FAILED", started_at=started_at)
        return ticket


@transaction.atomic
def void_ticket(*, request, actor_user, ticket: PosTicket, reason: str = "VOID") -> PosTicket:
    actor = _require_actor(actor_user)

    if ticket.status == PosTicketStatus.VOIDED:
        return ticket

    publish_outbox_event(
        request=request,
        source_module="POS",
        event_type="POSVoidRequested",
        payload={
            "ticket_id": int(ticket.id),
            "reason": reason,
            "status": ticket.status,
        },
        actor_user=actor,
        company=ticket.company,
        branch=ticket.branch,
        correlation_id=ticket.correlation_id,
        causation_id=f"{ticket.correlation_id}:void-requested",
    )

    if ticket.sale_id and ticket.sale and ticket.sale.status != FuelSaleStatus.CANCELLED:
        cancel_sale(request=request, sale=ticket.sale, actor_user=actor, reason=reason)

    if ticket.cash_movement_id and ticket.session.cash_session_id and ticket.total_amount > 0:
        post_cash_movement(
            request=request,
            actor=actor,
            session_id=int(ticket.session.cash_session_id),
            movement_type=CashMovement.MovementType.REFUND,
            amount=Decimal(ticket.total_amount),
            reference=f"pos-ticket:{ticket.id}",
            reason=f"VOID:{reason}",
        )

    ticket.status = PosTicketStatus.VOIDED
    ticket.voided_at = timezone.now()
    ticket.void_reason = reason or "VOID"
    ticket.compensation_pending = False
    ticket.compensation_next_retry_at = None
    ticket.save(
        update_fields=[
            "status",
            "voided_at",
            "void_reason",
            "compensation_pending",
            "compensation_next_retry_at",
            "updated_at",
        ]
    )

    write_event(
        request=request,
        module="POS",
        event_type="POS_TICKET_VOIDED",
        reason_code="SYNC_OK",
        subject_type="POS_TICKET",
        subject_id=str(ticket.id),
        actor_user=actor,
        metadata={"reason": ticket.void_reason},
    )
    return ticket


@transaction.atomic
def retry_ticket_compensation(*, request, actor_user, ticket: PosTicket, reason: str = "") -> PosTicket:
    actor = _require_actor(actor_user)

    if ticket.status == PosTicketStatus.CLOSED:
        return ticket
    if ticket.status == PosTicketStatus.VOIDED:
        raise ValueError("Ticket anulado; no aplica retry de compensación")
    if ticket.status != PosTicketStatus.CHECKOUT_PENDING:
        raise ValueError("Ticket no está en estado reintentable")

    publish_outbox_event(
        request=request,
        source_module="POS",
        event_type="POSCompensationRetried",
        payload={
            "ticket_id": int(ticket.id),
            "reason": reason or "",
            "attempt": int(ticket.compensation_attempts) + 1,
        },
        actor_user=actor,
        company=ticket.company,
        branch=ticket.branch,
        correlation_id=ticket.correlation_id,
        causation_id=f"{ticket.correlation_id}:compensation-retried",
    )

    return checkout_ticket(
        request=request,
        actor_user=actor,
        ticket=ticket,
        line_payload=None,
    )


def run_pos_compensation_cycle(
    *,
    company=None,
    branch=None,
    limit: int = 100,
    actor_user=None,
    now=None,
) -> PosCompensationCycleResult:
    clock = now or timezone.now()
    limit_n = max(1, int(limit))

    due_filter = Q(status=PosTicketStatus.CHECKOUT_PENDING) & Q(compensation_pending=True) & (
        Q(compensation_next_retry_at__isnull=True) | Q(compensation_next_retry_at__lte=clock)
    )

    qs = PosTicket.objects.filter(due_filter)
    if company is not None:
        qs = qs.filter(company=company)
    if branch is not None:
        qs = qs.filter(branch=branch)

    ticket_ids = list(qs.order_by("compensation_next_retry_at", "id").values_list("id", flat=True)[:limit_n])

    attempted = succeeded = failed = still_pending = 0
    errors: list[dict[str, str]] = []
    for ticket_id in ticket_ids:
        attempted += 1
        try:
            with transaction.atomic():
                ticket = (
                    PosTicket.objects.select_for_update()
                    .select_related("company", "branch", "session", "created_by")
                    .get(id=int(ticket_id))
                )
                if ticket.status != PosTicketStatus.CHECKOUT_PENDING:
                    continue
                if not ticket.compensation_pending:
                    continue
                if ticket.compensation_next_retry_at is not None and ticket.compensation_next_retry_at > clock:
                    still_pending += 1
                    continue
                actor = actor_user or ticket.created_by
                updated = retry_ticket_compensation(
                    request=request_shim_for_ticket(ticket=ticket),
                    actor_user=actor,
                    ticket=ticket,
                    reason="AUTO_RETRY_CYCLE",
                )
                if updated.status == PosTicketStatus.CLOSED:
                    succeeded += 1
                elif updated.compensation_pending:
                    still_pending += 1
                else:
                    failed += 1
        except Exception as exc:  # noqa: BLE001
            failed += 1
            errors.append({"ticket_id": str(ticket_id), "error": str(exc)})

    return PosCompensationCycleResult(
        attempted=int(attempted),
        succeeded=int(succeeded),
        failed=int(failed),
        still_pending=int(still_pending),
        errors=errors,
    )


def request_shim_for_ticket(*, ticket: PosTicket):
    class _RequestShim:
        company: object
        branch: object
        data: dict[str, object]

        def __init__(self, *, company, branch) -> None:
            self.company = company
            self.branch = branch
            self.data = {}

    return _RequestShim(company=ticket.company, branch=ticket.branch)


@transaction.atomic
def upsert_peripheral_status(*, request, actor_user, payload: dict[str, Any]) -> PosPeripheralStatus:
    actor = _require_actor(actor_user)
    branch = _require_branch(request)
    company = request.company

    defaults = {
        "connector_id": str(payload["connector_id"]),
        "connector_version": str(payload.get("connector_version") or ""),
        "device_kind": str(payload["device_kind"]),
        "capability_level": str(payload.get("capability_level") or "experimental"),
        "status": str(payload.get("status") or "ONLINE"),
        "metadata": dict(payload.get("metadata") or {}),
        "last_seen_at": timezone.now(),
        "updated_by": actor,
    }
    if payload.get("edge_session") is not None:
        defaults["edge_session"] = payload.get("edge_session")

    row, _ = PosPeripheralStatus.objects.update_or_create(
        company=company,
        branch=branch,
        device_key=str(payload["device_key"]),
        defaults=defaults,
    )
    return row


@transaction.atomic
def issue_edge_challenge(
    *,
    request,
    actor_user,
    connector_id: str,
    connector_version: str = "",
    metadata: dict[str, Any] | None = None,
) -> IssueEdgeChallengeResult:
    actor = _require_actor(actor_user)
    branch = _require_branch(request)
    company = request.company
    _expire_stale_edge_state(company=company, branch=branch)

    now = _utc_now()
    challenge_ttl = _ttl_seconds("POS_EDGE_CHALLENGE_TTL_SEC", 120)
    challenge = PosEdgeChallenge.objects.create(
        company=company,
        branch=branch,
        nonce=uuid4().hex,
        status=PosEdgeChallengeStatus.PENDING,
        connector_id=str(connector_id or "").strip(),
        connector_version=str(connector_version or "").strip(),
        metadata=dict(metadata or {}),
        created_by=actor,
        issued_at=now,
        expires_at=now + timedelta(seconds=challenge_ttl),
    )
    return IssueEdgeChallengeResult(challenge=challenge)


@transaction.atomic
def handshake_edge_connector(
    *,
    request,
    actor_user,
    payload: dict[str, Any],
) -> EdgeHandshakeResult:
    actor = _require_actor(actor_user)
    branch = _require_branch(request)
    company = request.company
    _expire_stale_edge_state(company=company, branch=branch)

    challenge_id = str(payload["challenge_id"])
    connector_id = str(payload["connector_id"]).strip()
    connector_version = str(payload.get("connector_version") or "").strip()
    signature = str(payload["signature"]).strip()

    challenge = (
        PosEdgeChallenge.objects.select_for_update()
        .filter(challenge_id=challenge_id, company=company, branch=branch)
        .first()
    )
    if challenge is None:
        raise ValueError("CHALLENGE_NOT_FOUND")
    if challenge.status == PosEdgeChallengeStatus.CONSUMED:
        raise ValueError("REPLAY_DETECTED")
    if challenge.status == PosEdgeChallengeStatus.EXPIRED or challenge.expires_at < _utc_now():
        if challenge.status != PosEdgeChallengeStatus.EXPIRED:
            challenge.status = PosEdgeChallengeStatus.EXPIRED
            challenge.save(update_fields=["status"])
        raise ValueError("CHALLENGE_EXPIRED")
    if challenge.connector_id and challenge.connector_id != connector_id:
        raise ValueError("CHALLENGE_CONNECTOR_MISMATCH")

    secret = _edge_shared_secret_b64()
    if not secret:
        raise ValueError("EDGE_SHARED_SECRET_NOT_CONFIGURED")
    msg = _edge_handshake_message(challenge=challenge, connector_id=connector_id)
    if not _verify_edge_hmac_signature(secret_b64=secret, message=msg, signature_b64=signature):
        raise ValueError("BAD_SIGNATURE")

    PosEdgeSession.objects.filter(
        company=company,
        branch=branch,
        connector_id=connector_id,
        status=PosEdgeSessionStatus.ACTIVE,
    ).update(
        status=PosEdgeSessionStatus.CLOSED,
    )

    session_ttl = _ttl_seconds("POS_EDGE_SESSION_TTL_SEC", 3600)
    now = _utc_now()
    devices_payload = [dict(row) for row in list(payload.get("devices") or [])]
    capability_registry = _merge_capability_registry(
        registry_payload=dict(payload.get("capability_registry") or {}),
        devices_payload=devices_payload,
    )

    session = PosEdgeSession.objects.create(
        company=company,
        branch=branch,
        status=PosEdgeSessionStatus.ACTIVE,
        connector_id=connector_id,
        connector_version=connector_version,
        challenge=challenge,
        capability_registry=capability_registry,
        metadata=dict(payload.get("metadata") or {}),
        created_by=actor,
        issued_at=now,
        expires_at=now + timedelta(seconds=session_ttl),
        last_seen_at=now,
    )

    devices_synced = 0
    for device in devices_payload:
        upsert_peripheral_status(
            request=request,
            actor_user=actor,
            payload={
                "connector_id": connector_id,
                "connector_version": connector_version,
                "device_key": str(device["device_key"]),
                "device_kind": str(device["device_kind"]),
                "capability_level": _normalize_capability(str(device.get("capability_level") or "")),
                "status": str(device.get("status") or "ONLINE"),
                "metadata": dict(device.get("metadata") or {}),
                "edge_session": session,
            },
        )
        devices_synced += 1

    challenge.status = PosEdgeChallengeStatus.CONSUMED
    challenge.consumed_by = actor
    challenge.consumed_at = now
    if connector_version and not challenge.connector_version:
        challenge.connector_version = connector_version
    challenge.save(update_fields=["status", "consumed_by", "consumed_at", "connector_version"])

    return EdgeHandshakeResult(session=session, devices_synced=devices_synced)


def get_peripheral_capabilities(*, company, branch) -> dict[str, Any]:
    _expire_stale_edge_state(company=company, branch=branch)

    active_session = (
        PosEdgeSession.objects.filter(
            company=company,
            branch=branch,
            status=PosEdgeSessionStatus.ACTIVE,
        )
        .order_by("-issued_at", "-id")
        .first()
    )

    devices_qs = PosPeripheralStatus.objects.filter(company=company, branch=branch).order_by("device_kind", "device_key")
    devices = [
        {
            "id": int(row.id),
            "connector_id": str(row.connector_id),
            "connector_version": str(row.connector_version or ""),
            "device_key": str(row.device_key),
            "device_kind": str(row.device_kind),
            "capability_level": str(row.capability_level),
            "status": str(row.status),
            "last_seen_at": row.last_seen_at,
            "edge_session_id": int(row.edge_session_id) if row.edge_session_id else None,
            "metadata": row.metadata or {},
        }
        for row in devices_qs
    ]

    merged_registry = _merge_capability_registry(
        registry_payload=dict(active_session.capability_registry or {}) if active_session else {},
        devices_payload=devices,
    )

    return {
        "session": {
            "id": int(active_session.id) if active_session else None,
            "connector_id": str(active_session.connector_id) if active_session else "",
            "connector_version": str(active_session.connector_version) if active_session else "",
            "status": str(active_session.status) if active_session else "NONE",
            "issued_at": active_session.issued_at if active_session else None,
            "expires_at": active_session.expires_at if active_session else None,
            "last_seen_at": active_session.last_seen_at if active_session else None,
            "capability_registry": dict(active_session.capability_registry or {}) if active_session else {},
        },
        "registry": merged_registry,
        "devices": devices,
        "count": int(len(devices)),
    }


def get_operational_cockpit(*, company, branch) -> dict[str, Any]:
    now = timezone.now()
    session = get_current_pos_session(company=company, branch=branch)
    tickets_qs = PosTicket.objects.filter(company=company, branch=branch)

    pending = int(tickets_qs.filter(status=PosTicketStatus.CHECKOUT_PENDING).count())
    closed = int(tickets_qs.filter(status=PosTicketStatus.CLOSED).count())
    voided = int(tickets_qs.filter(status=PosTicketStatus.VOIDED).count())

    compensation_qs = tickets_qs.filter(status=PosTicketStatus.CHECKOUT_PENDING, compensation_pending=True)
    compensation_pending = int(compensation_qs.count())
    compensation_overdue = int(
        compensation_qs.filter(
            Q(compensation_next_retry_at__isnull=True) | Q(compensation_next_retry_at__lte=now)
        ).count()
    )
    oldest_started = (
        compensation_qs.exclude(checkout_started_at__isnull=True)
        .order_by("checkout_started_at", "id")
        .values_list("checkout_started_at", flat=True)
        .first()
    )
    max_pending_age_min = 0
    if oldest_started is not None:
        max_pending_age_min = max(0, int((now - oldest_started).total_seconds() // 60))

    peripherals_qs = PosPeripheralStatus.objects.filter(company=company, branch=branch)
    peripherals_total = int(peripherals_qs.count())
    peripherals_online = int(peripherals_qs.filter(status="ONLINE").count())
    peripherals_degraded = int(peripherals_qs.filter(status="DEGRADED").count())
    peripherals_offline = int(peripherals_qs.filter(status="OFFLINE").count())

    return {
        "session": {
            "id": int(session.id) if session else None,
            "status": str(session.status) if session else "NONE",
            "cash_session_id": int(session.cash_session_id) if session and session.cash_session_id else None,
            "opened_at": session.opened_at if session else None,
            "opened_by": int(session.opened_by_id) if session else None,
            "opening_amount": str(session.opening_amount) if session else "0.00",
        },
        "tickets": {
            "pending": pending,
            "closed": closed,
            "voided": voided,
        },
        "compensation": {
            "pending": compensation_pending,
            "overdue": compensation_overdue,
            "max_pending_age_min": int(max_pending_age_min),
        },
        "peripherals": {
            "total": peripherals_total,
            "online": peripherals_online,
            "degraded": peripherals_degraded,
            "offline": peripherals_offline,
        },
    }
