"""Handlers del sync engine para facturación offline.

El dispositivo móvil crea documentos y pagos sin conexión.
Cuando se sincroniza, estos handlers los aplican al servidor.

Comandos soportados:
  BILLING.DRAFT.CREATE  — crear borrador
  BILLING.DOC.ISSUE     — emitir documento
  BILLING.PAYMENT.ADD   — registrar pago
  BILLING.ORDER.CREATE  — crear orden por encargo
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from apps.modulos.iam.models import OrgUnit

from apps.kernels.facturacion.services import (
    BillingError,
    create_draft,
    create_order,
    create_payment,
    issue_doc,
)
from apps.kernels.facturacion.models import CustomerType, DocType

from .errors import SyncRejectError
from .registry import HandlerResult, register


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _attach_billing_scope(*, request, company_id: int, branch_id: int | None) -> None:
    company = OrgUnit.objects.filter(id=company_id, unit_type=OrgUnit.UnitType.COMPANY, is_active=True).first()
    if not company:
        raise SyncRejectError("BILLING_INVALID_SCOPE", {"company_id": "unknown"})
    request.company = company

    if branch_id is None:
        raise SyncRejectError("BILLING_INVALID_SCOPE", {"branch_id": "required"})

    branch = OrgUnit.objects.filter(
        id=branch_id, unit_type=OrgUnit.UnitType.BRANCH,
        parent_id=company_id, is_active=True,
    ).first()
    if not branch:
        raise SyncRejectError("BILLING_INVALID_SCOPE", {"branch_id": "unknown"})
    request.branch = branch


def _require(payload: dict, key: str) -> Any:
    v = payload.get(key)
    if v is None:
        raise SyncRejectError("BILLING_SCHEMA_INVALID", {key: "required"})
    return v


def _opt_str(payload: dict, key: str, default: str = "") -> str:
    return str(payload.get(key) or default)


def _opt_bool(payload: dict, key: str, default: bool = False) -> bool:
    v = payload.get(key)
    return bool(v) if v is not None else default


def _opt_int(payload: dict, key: str) -> int | None:
    v = payload.get(key)
    if v is None:
        return None
    try:
        return int(v)
    except Exception:
        raise SyncRejectError("BILLING_SCHEMA_INVALID", {key: "invalid int"})


def _map_billing_error(err: BillingError) -> SyncRejectError:
    msg = str(err).lower()
    if "not found" in msg or "no encontrado" in msg:
        return SyncRejectError("BILLING_NOT_FOUND", {"detail": str(err)})
    if "stock" in msg or "bodega" in msg:
        return SyncRejectError("BILLING_INVENTORY_ERROR", {"detail": str(err)})
    return SyncRejectError("BILLING_SCHEMA_INVALID", {"detail": str(err)})


# ---------------------------------------------------------------------------
# Handler: BILLING.DRAFT.CREATE
# ---------------------------------------------------------------------------

@register("BILLING.DRAFT.CREATE")
def handle_billing_draft_create(ctx: dict[str, Any], payload: dict[str, Any]) -> HandlerResult:
    request = ctx["request"]
    company_id = int(ctx["company_id"])
    branch_id = ctx.get("branch_id")
    _attach_billing_scope(request=request, company_id=company_id, branch_id=int(branch_id) if branch_id else None)

    doc_type = _opt_str(payload, "doc_type", DocType.INVOICE)
    lines_raw = payload.get("lines", [])
    if not lines_raw:
        raise SyncRejectError("BILLING_SCHEMA_INVALID", {"lines": "required"})

    idempotency_key = _opt_str(payload, "idempotency_key")
    if idempotency_key:
        scoped_key = f"BILLING.DRAFT.CREATE:{company_id}:{branch_id}:{idempotency_key}"
    else:
        scoped_key = str(ctx["command_id"])

    try:
        result = create_draft(
            request=request,
            actor=None,
            doc_type=doc_type,
            series=_opt_str(payload, "series", "A"),
            currency=_opt_str(payload, "currency", "NIO"),
            customer_name=_opt_str(payload, "customer_name"),
            customer_ref=_opt_str(payload, "customer_ref"),
            customer_type=_opt_str(payload, "customer_type", CustomerType.EXTERNAL),
            customer_party_id=_opt_int(payload, "customer_party_id"),
            is_fiscal=_opt_bool(payload, "is_fiscal"),
            lines=lines_raw,
            idempotency_key=scoped_key,
            payment_method=_opt_str(payload, "payment_method"),
            source_module="SYNC",
            source_type="OFFLINE_DRAFT",
            source_id=str(ctx["command_id"]),
        )
    except BillingError as e:
        raise _map_billing_error(e)

    return {"refs": {"doc_id": result.doc_id}}


# ---------------------------------------------------------------------------
# Handler: BILLING.DOC.ISSUE
# ---------------------------------------------------------------------------

@register("BILLING.DOC.ISSUE")
def handle_billing_doc_issue(ctx: dict[str, Any], payload: dict[str, Any]) -> HandlerResult:
    request = ctx["request"]
    company_id = int(ctx["company_id"])
    branch_id = ctx.get("branch_id")
    _attach_billing_scope(request=request, company_id=company_id, branch_id=int(branch_id) if branch_id else None)

    doc_id = _opt_int(payload, "doc_id")
    if doc_id is None:
        raise SyncRejectError("BILLING_SCHEMA_INVALID", {"doc_id": "required"})

    apply_inventory = _opt_bool(payload, "apply_inventory", False)
    print_after_issue = _opt_bool(payload, "print_after_issue", False)

    idempotency_key = _opt_str(payload, "idempotency_key") or str(ctx["command_id"])

    try:
        result = issue_doc(
            request=request,
            actor=None,
            doc_id=doc_id,
            apply_inventory=apply_inventory,
            print_after_issue=print_after_issue,
            idempotency_key=idempotency_key,
        )
    except BillingError as e:
        raise _map_billing_error(e)

    return {
        "refs": {
            "doc_id": result.get("doc_id"),
            "number": result.get("number"),
            "fiscal_status": result.get("fiscal_status", ""),
            "accounting_status": result.get("accounting_status", ""),
        }
    }


# ---------------------------------------------------------------------------
# Handler: BILLING.PAYMENT.ADD
# ---------------------------------------------------------------------------

@register("BILLING.PAYMENT.ADD")
def handle_billing_payment_add(ctx: dict[str, Any], payload: dict[str, Any]) -> HandlerResult:
    request = ctx["request"]
    company_id = int(ctx["company_id"])
    branch_id = ctx.get("branch_id")
    _attach_billing_scope(request=request, company_id=company_id, branch_id=int(branch_id) if branch_id else None)

    doc_id = _opt_int(payload, "doc_id")
    if doc_id is None:
        raise SyncRejectError("BILLING_SCHEMA_INVALID", {"doc_id": "required"})

    payment_method = _opt_str(payload, "payment_method")
    if not payment_method:
        raise SyncRejectError("BILLING_SCHEMA_INVALID", {"payment_method": "required"})

    amount_raw = payload.get("amount")
    if amount_raw is None:
        raise SyncRejectError("BILLING_SCHEMA_INVALID", {"amount": "required"})
    try:
        amount = Decimal(str(amount_raw))
    except Exception:
        raise SyncRejectError("BILLING_SCHEMA_INVALID", {"amount": "invalid"})

    try:
        result = create_payment(
            request=request,
            actor=None,
            doc_id=doc_id,
            payment_method=payment_method,
            amount=amount,
            currency=_opt_str(payload, "currency", "NIO"),
            reference=_opt_str(payload, "reference"),
            notes=_opt_str(payload, "notes"),
            payroll_period_ref=_opt_str(payload, "payroll_period_ref"),
            coffee_lot_ref=_opt_str(payload, "coffee_lot_ref"),
            auto_confirm=_opt_bool(payload, "auto_confirm", True),
        )
    except BillingError as e:
        raise _map_billing_error(e)

    return {
        "refs": {
            "payment_id": result.payment_id,
            "doc_id": result.doc_id,
            "amount_paid": str(result.amount_paid),
            "payment_status": result.payment_status,
        }
    }


# ---------------------------------------------------------------------------
# Handler: BILLING.ORDER.CREATE — por encargo
# ---------------------------------------------------------------------------

@register("BILLING.ORDER.CREATE")
def handle_billing_order_create(ctx: dict[str, Any], payload: dict[str, Any]) -> HandlerResult:
    request = ctx["request"]
    company_id = int(ctx["company_id"])
    branch_id = ctx.get("branch_id")
    _attach_billing_scope(request=request, company_id=company_id, branch_id=int(branch_id) if branch_id else None)

    lines_raw = payload.get("lines", [])
    if not lines_raw:
        raise SyncRejectError("BILLING_SCHEMA_INVALID", {"lines": "required"})

    try:
        result = create_order(
            request=request,
            actor=None,
            customer_name=_opt_str(payload, "customer_name"),
            customer_ref=_opt_str(payload, "customer_ref"),
            customer_type=_opt_str(payload, "customer_type", CustomerType.EXTERNAL),
            customer_party_id=_opt_int(payload, "customer_party_id"),
            currency=_opt_str(payload, "currency", "NIO"),
            lines=lines_raw,
            notes=_opt_str(payload, "notes"),
        )
    except BillingError as e:
        raise _map_billing_error(e)

    return {"refs": {"order_id": result.order_id, "status": result.status}}
