from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.utils import timezone

from apps.modulos.iam.models import OrgUnit
from apps.modulos.retail_pos.models import PosSession, PosTicket, PosTicketStatus
from apps.modulos.retail_pos.services import (
    close_pos_session,
    checkout_ticket,
    open_ticket,
    retry_ticket_compensation,
    void_ticket,
)
from apps.kernels.payments.services import capture_payment_intent, create_payment_intent

from .errors import SyncRejectError
from .registry import HandlerResult, register


CANONICAL_COMMANDS: dict[str, str] = {
    "POS_TICKET": "POS_TICKET",
    "POS.TICKET": "POS_TICKET",
    "POS_PAYMENT_INTENT": "POS_PAYMENT_INTENT",
    "POS.PAYMENT_INTENT": "POS_PAYMENT_INTENT",
    "POS_VOID": "POS_VOID",
    "POS.VOID": "POS_VOID",
    "POS_CASH_COUNT": "POS_CASH_COUNT",
    "POS.CASH_COUNT": "POS_CASH_COUNT",
    "POS_COMPENSATION_RETRY": "POS_COMPENSATION_RETRY",
    "POS.COMPENSATION_RETRY": "POS_COMPENSATION_RETRY",
}


def _require_int(payload: dict[str, Any], key: str) -> int:
    v = payload.get(key, None)
    if v is None:
        raise SyncRejectError("POS_SCHEMA_INVALID", {key: "required"})
    try:
        return int(v)
    except Exception:
        raise SyncRejectError("POS_SCHEMA_INVALID", {key: "invalid"})


def _require_decimal(payload: dict[str, Any], key: str) -> Decimal:
    v = payload.get(key, None)
    if v is None:
        raise SyncRejectError("POS_SCHEMA_INVALID", {key: "required"})
    try:
        return Decimal(str(v))
    except Exception:
        raise SyncRejectError("POS_SCHEMA_INVALID", {key: "invalid"})


def _optional_str(payload: dict[str, Any], key: str, default: str = "") -> str:
    v = payload.get(key, None)
    if v is None:
        return default
    return str(v)


def _attach_scope_to_request(*, request, company_id: int, branch_id: int | None) -> None:
    company = OrgUnit.objects.filter(id=company_id, unit_type=OrgUnit.UnitType.COMPANY, is_active=True).first()
    if not company:
        raise SyncRejectError("POS_INVALID_SCOPE", {"company_id": "unknown"})

    request.company = company

    if branch_id is None:
        request.branch = None
        return

    branch = OrgUnit.objects.filter(
        id=branch_id,
        unit_type=OrgUnit.UnitType.BRANCH,
        parent_id=company_id,
        is_active=True,
    ).first()
    if not branch:
        raise SyncRejectError("POS_INVALID_SCOPE", {"branch_id": "unknown"})

    request.branch = branch


def _resolve_actor(ctx: dict[str, Any]):
    actor = ctx.get("actor_user")
    if actor is not None and getattr(actor, "is_authenticated", False):
        return actor
    device = ctx.get("device")
    enrolled = getattr(device, "enrolled_by_user", None)
    if enrolled is None or not getattr(enrolled, "is_authenticated", False):
        raise SyncRejectError("POS_ACTOR_REQUIRED", {})
    return enrolled


@register("POS_TICKET")
def handle_pos_ticket(ctx: dict[str, Any], payload: dict[str, Any]) -> HandlerResult:
    request = ctx["request"]
    company_id = int(ctx["company_id"])
    branch_id = ctx.get("branch_id")
    if branch_id is None:
        raise SyncRejectError("POS_INVALID_SCOPE", {"branch_id": "required"})

    _attach_scope_to_request(request=request, company_id=company_id, branch_id=int(branch_id))
    actor = _resolve_actor(ctx)

    session_id = _require_int(payload, "session_id")
    shift_id = _require_int(payload, "shift_id")

    session = PosSession.objects.filter(
        id=session_id,
        company_id=company_id,
        branch_id=int(branch_id),
    ).first()
    if session is None:
        raise SyncRejectError("POS_INVALID_SCOPE", {"session_id": "unknown"})

    line_payload = {
        "product": _optional_str(payload, "product"),
        "volume": _require_decimal(payload, "volume"),
        "volume_uom": _optional_str(payload, "volume_uom", "LITER"),
        "unit_price_entered": _require_decimal(payload, "unit_price_entered"),
        "unit_price_uom": _optional_str(payload, "unit_price_uom", "PER_LITER"),
        "metadata": dict(payload.get("metadata") or {}),
    }

    try:
        ticket_result = open_ticket(
            request=request,
            actor_user=actor,
            session=session,
            shift_id=shift_id,
            idempotency_key=_optional_str(payload, "idempotency_key") or str(ctx["command_id"]),
            external_ref=_optional_str(payload, "external_ref"),
            customer_name=_optional_str(payload, "customer_name"),
            customer_ref=_optional_str(payload, "customer_ref"),
            sale_type=_optional_str(payload, "sale_type", "PUBLIC"),
            payment_method=_optional_str(payload, "payment_method", "CASH"),
        )
        ticket = checkout_ticket(
            request=request,
            actor_user=actor,
            ticket=ticket_result.ticket,
            line_payload=line_payload,
        )
    except ValueError as exc:
        raise SyncRejectError("POS_SCHEMA_INVALID", {"detail": str(exc)})
    if ticket.status != PosTicketStatus.CLOSED:
        raise SyncRejectError(
            "POS_COMPENSATION_PENDING",
            {
                "ticket_id": int(ticket.id),
                "status": str(ticket.status),
                "compensation_attempts": int(ticket.compensation_attempts),
                "last_error": str(ticket.compensation_last_error or ticket.last_error or ""),
            },
        )

    return {
        "refs": {
            "ticket_id": int(ticket.id),
            "sale_id": int(ticket.sale_id) if ticket.sale_id else None,
            "payment_id": str(ticket.payment_intent.payment_id) if ticket.payment_intent else "",
            "status": str(ticket.status),
        }
    }


@register("POS_PAYMENT_INTENT")
def handle_pos_payment_intent(ctx: dict[str, Any], payload: dict[str, Any]) -> HandlerResult:
    request = ctx["request"]
    company_id = int(ctx["company_id"])
    branch_id = ctx.get("branch_id")
    if branch_id is None:
        raise SyncRejectError("POS_INVALID_SCOPE", {"branch_id": "required"})

    _attach_scope_to_request(request=request, company_id=company_id, branch_id=int(branch_id))
    actor = _resolve_actor(ctx)

    ticket_id = _require_int(payload, "ticket_id")
    ticket = PosTicket.objects.filter(id=ticket_id, company_id=company_id, branch_id=int(branch_id)).first()
    if ticket is None:
        raise SyncRejectError("POS_INVALID_SCOPE", {"ticket_id": "unknown"})

    if ticket.payment_intent_id:
        intent = ticket.payment_intent
        return {
            "refs": {
                "ticket_id": int(ticket.id),
                "payment_id": str(intent.payment_id) if intent else "",
                "status": str(intent.status) if intent else "",
            }
        }

    amount = _require_decimal(payload, "amount")
    try:
        intent, _ = create_payment_intent(
            request=request,
            actor=actor,
            amount=amount,
            currency=_optional_str(payload, "currency", "NIO"),
            idempotency_key=_optional_str(payload, "idempotency_key") or f"pos-ticket:{ticket.id}:sync-intent",
            external_ref=f"pos-ticket:{ticket.id}",
            provider="POS_SYNC",
        )
        intent = capture_payment_intent(
            request=request,
            actor=actor,
            payment_id=intent.payment_id,
            provider_txn_id=_optional_str(payload, "provider_txn_id", f"sync:{ticket.id}:{timezone.now().strftime('%Y%m%d%H%M%S')}")
            or "",
            metadata={"ticket_id": int(ticket.id), "channel": "sync_v2"},
        )
    except ValueError as exc:
        raise SyncRejectError("POS_SCHEMA_INVALID", {"detail": str(exc)})

    ticket.payment_intent = intent
    ticket.save(update_fields=["payment_intent", "updated_at"])

    return {
        "refs": {
            "ticket_id": int(ticket.id),
            "payment_id": str(intent.payment_id),
            "status": str(intent.status),
        }
    }


@register("POS_VOID")
def handle_pos_void(ctx: dict[str, Any], payload: dict[str, Any]) -> HandlerResult:
    request = ctx["request"]
    company_id = int(ctx["company_id"])
    branch_id = ctx.get("branch_id")
    if branch_id is None:
        raise SyncRejectError("POS_INVALID_SCOPE", {"branch_id": "required"})

    _attach_scope_to_request(request=request, company_id=company_id, branch_id=int(branch_id))
    actor = _resolve_actor(ctx)

    ticket_id = _require_int(payload, "ticket_id")
    ticket = PosTicket.objects.filter(id=ticket_id, company_id=company_id, branch_id=int(branch_id)).first()
    if ticket is None:
        raise SyncRejectError("POS_INVALID_SCOPE", {"ticket_id": "unknown"})

    try:
        ticket = void_ticket(
            request=request,
            actor_user=actor,
            ticket=ticket,
            reason=_optional_str(payload, "reason", "VOID"),
        )
    except ValueError as exc:
        raise SyncRejectError("POS_SCHEMA_INVALID", {"detail": str(exc)})

    return {
        "refs": {
            "ticket_id": int(ticket.id),
            "status": str(ticket.status),
            "voided_at": ticket.voided_at.isoformat() if ticket.voided_at else "",
        }
    }


@register("POS_CASH_COUNT")
def handle_pos_cash_count(ctx: dict[str, Any], payload: dict[str, Any]) -> HandlerResult:
    request = ctx["request"]
    company_id = int(ctx["company_id"])
    branch_id = ctx.get("branch_id")
    if branch_id is None:
        raise SyncRejectError("POS_INVALID_SCOPE", {"branch_id": "required"})

    _attach_scope_to_request(request=request, company_id=company_id, branch_id=int(branch_id))
    actor = _resolve_actor(ctx)

    session_id = _require_int(payload, "session_id")
    counted_amount = _require_decimal(payload, "counted_amount")

    session = PosSession.objects.filter(id=session_id, company_id=company_id, branch_id=int(branch_id)).first()
    if session is None:
        raise SyncRejectError("POS_INVALID_SCOPE", {"session_id": "unknown"})

    try:
        session = close_pos_session(
            request=request,
            actor_user=actor,
            session=session,
            counted_amount=counted_amount,
            note=_optional_str(payload, "note"),
        )
    except ValueError as exc:
        raise SyncRejectError("POS_SCHEMA_INVALID", {"detail": str(exc)})

    return {
        "refs": {
            "session_id": int(session.id),
            "status": str(session.status),
            "difference_amount": str(session.difference_amount),
        }
    }


@register("POS_COMPENSATION_RETRY")
def handle_pos_compensation_retry(ctx: dict[str, Any], payload: dict[str, Any]) -> HandlerResult:
    request = ctx["request"]
    company_id = int(ctx["company_id"])
    branch_id = ctx.get("branch_id")
    if branch_id is None:
        raise SyncRejectError("POS_INVALID_SCOPE", {"branch_id": "required"})

    _attach_scope_to_request(request=request, company_id=company_id, branch_id=int(branch_id))
    actor = _resolve_actor(ctx)

    ticket_id = _require_int(payload, "ticket_id")
    ticket = PosTicket.objects.filter(id=ticket_id, company_id=company_id, branch_id=int(branch_id)).first()
    if ticket is None:
        raise SyncRejectError("POS_INVALID_SCOPE", {"ticket_id": "unknown"})

    try:
        updated = retry_ticket_compensation(
            request=request,
            actor_user=actor,
            ticket=ticket,
            reason=_optional_str(payload, "reason", "SYNC_RETRY"),
        )
    except ValueError as exc:
        raise SyncRejectError("POS_SCHEMA_INVALID", {"detail": str(exc)})
    if updated.status != PosTicketStatus.CLOSED:
        raise SyncRejectError(
            "POS_COMPENSATION_PENDING",
            {
                "ticket_id": int(updated.id),
                "status": str(updated.status),
                "compensation_attempts": int(updated.compensation_attempts),
                "last_error": str(updated.compensation_last_error or updated.last_error or ""),
            },
        )

    return {
        "refs": {
            "ticket_id": int(updated.id),
            "status": str(updated.status),
            "compensation_pending": bool(updated.compensation_pending),
            "compensation_attempts": int(updated.compensation_attempts),
        }
    }
