"""Servicios del comisariato: cuentas de crédito + venta a crédito.

La venta reusa `facturacion` (factura a crédito de inventario): `create_draft` →
marcar crédito → `issue_doc(apply_inventory=True)`, que emite ingreso (GL), baja de
inventario (COGS) y crea la CxC en portfolio (`link_billing_document_to_receivable`,
idempotente por reference_type="BILLING_DOC"/doc_id). Aquí sólo orquestamos y validamos
el límite de crédito del cliente; cero contabilidad reinventada.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional

from django.db import transaction

from apps.kernels.facturacion.models import BillingDocument, CreditStatus, DocStatus, DocType
from apps.kernels.facturacion.services import create_draft, issue_doc
from apps.kernels.portfolio.models import ObligationStatus, Receivable
from apps.modulos.audit.writer import write_event
from apps.modulos.iam.models import OrgUnit
from apps.modulos.parties.models import Party

from .models import CustomerCreditAccount, CustomerSegment

# CxC que cuentan contra el límite (saldo vivo). Las terminales no consumen crédito.
TERMINAL_STATUSES = {
    ObligationStatus.PAID,
    ObligationStatus.WRITTEN_OFF,
    ObligationStatus.CANCELLED,
}


class ComisariatoError(ValueError):
    """Error de dominio del comisariato (reason_code en .args[0])."""


def _q2(value) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"))


# ---------------------------------------------------------------------------
# Cuentas de crédito
# ---------------------------------------------------------------------------

def get_or_create_account(
    *,
    request,
    actor,
    company: OrgUnit,
    party: Party,
    segment: str,
    credit_limit=Decimal("0.00"),
    collecting_company: Optional[OrgUnit] = None,
    is_active: bool = True,
    notes: str = "",
) -> CustomerCreditAccount:
    """Crea o actualiza la cuenta de crédito (límite + segmento) de un cliente."""
    if segment not in CustomerSegment.values:
        raise ComisariatoError("COMISARIATO_INVALID_SEGMENT")
    # C-01: None = sin tope (ilimitado, explícito); un valor numérico se normaliza a 2 dec.
    credit_limit = None if credit_limit is None else _q2(credit_limit)

    with transaction.atomic():
        account, created = CustomerCreditAccount.objects.select_for_update().get_or_create(
            company=company, party=party,
            defaults={
                "segment": segment, "credit_limit": credit_limit,
                "collecting_company": collecting_company, "is_active": is_active, "notes": notes,
            },
        )
        if not created:
            account.segment = segment
            account.credit_limit = credit_limit
            account.collecting_company = collecting_company
            account.is_active = is_active
            account.notes = notes
        account.full_clean()
        account.save()

        write_event(
            request=request, module="COMISARIATO", event_type="COMISARIATO_ACCOUNT_UPSERTED",
            reason_code="COMISARIATO_OK", actor_user=actor,
            subject_type="COMISARIATO_ACCOUNT", subject_id=str(account.id),
            metadata={
                "company_id": company.id, "party_id": party.id, "segment": segment,
                "credit_limit": str(credit_limit), "created": created,
            },
        )
    return account


def outstanding_balance(*, company: OrgUnit, party: Party, currency: str = "NIO") -> Decimal:
    """Σ saldo vivo de las CxC del cliente en la empresa, en UNA moneda.

    C-02: filtra por `currency` para no mezclar NIO+USD (antes sumaba todas las
    monedas y el saldo contra el límite quedaba mal si había CxC en distinta moneda).
    """
    rows = (
        Receivable.objects.filter(company=company, party=party, currency=currency)
        .exclude(status__in=TERMINAL_STATUSES)
    )
    return _q2(sum((r.outstanding_amount for r in rows), Decimal("0.00")))


def available_credit(account: CustomerCreditAccount, *, currency: str = "NIO") -> Optional[Decimal]:
    """Crédito disponible = límite − saldo vivo (misma moneda).

    C-01: ``None`` solo si la cuenta NO tiene tope (``credit_limit`` NULL). Con
    ``credit_limit == 0`` el disponible es ``−saldo`` (≤ 0) → sin crédito.
    """
    if account.credit_limit is None:
        return None
    bal = outstanding_balance(company=account.company, party=account.party, currency=currency)
    return _q2(account.credit_limit - bal)


# ---------------------------------------------------------------------------
# Venta a crédito (sobre facturacion)
# ---------------------------------------------------------------------------

def _receivable_for_doc(*, company: OrgUnit, doc_id: int) -> Optional[Receivable]:
    return Receivable.objects.filter(
        company=company, reference_type="BILLING_DOC", reference_id=doc_id
    ).first()


def _bundle(*, account: CustomerCreditAccount, doc: BillingDocument, duplicate: bool) -> dict[str, Any]:
    rec = _receivable_for_doc(company=doc.company, doc_id=doc.id)
    avail = available_credit(account, currency=doc.currency)
    return {
        "doc_id": doc.id,
        "number": doc.number,
        "status": doc.status,
        "receivable_id": str(rec.obligation_id) if rec else None,
        "total": str(doc.total),
        "available_after": str(avail) if avail is not None else None,
        "duplicate": duplicate,
    }


def sell_on_credit(
    *,
    request,
    actor,
    account: CustomerCreditAccount,
    warehouse_id: int,
    lines: list[dict],
    reference_code: str,
    currency: str = "NIO",
    is_fiscal: bool = True,
) -> dict[str, Any]:
    """Vende mercadería a crédito al cliente del comisariato.

    Baja inventario (COGS), reconoce ingreso (GL), emite factura y crea la CxC del
    cliente. Idempotente por `reference_code`. Valida el límite ANTES de emitir; si se
    excede, hace rollback total (sin documento, sin inventario, sin CxC).
    """
    if not reference_code:
        raise ComisariatoError("COMISARIATO_REFERENCE_REQUIRED")
    company: OrgUnit = request.company
    if account.company_id != company.id:
        raise ComisariatoError("COMISARIATO_ACCOUNT_COMPANY_MISMATCH")
    if not account.is_active:
        raise ComisariatoError("COMISARIATO_ACCOUNT_INACTIVE")
    if not lines:
        raise ComisariatoError("COMISARIATO_LINES_REQUIRED")

    # Cada línea debe apuntar a un ítem de inventario + bodega (para el despacho).
    norm_lines: list[dict] = []
    for ln in lines:
        if not ln.get("inventory_item_id"):
            raise ComisariatoError("COMISARIATO_LINE_ITEM_REQUIRED")
        norm_lines.append({**ln, "warehouse_id": ln.get("warehouse_id") or warehouse_id})

    idem = f"comis-sale:{company.id}:{reference_code}"

    with transaction.atomic():
        res = create_draft(
            request=request, actor=actor, doc_type=DocType.INVOICE, series="A",
            currency=currency, customer_name=account.party.display_name, customer_ref="",
            is_fiscal=is_fiscal, customer_party_id=account.party_id, lines=norm_lines,
            idempotency_key=idem, source_module="COMISARIATO", source_type="CREDIT_SALE",
            source_id=reference_code,
        )
        doc = BillingDocument.objects.select_for_update().get(id=res.doc_id)

        if doc.status == DocStatus.ISSUED:
            # Reentrada idempotente: ya emitida; no re-cobra ni re-despacha.
            return _bundle(account=account, doc=doc, duplicate=True)

        total = _q2(doc.total)
        avail = available_credit(account, currency=currency)
        if avail is not None and total > avail:
            # Rollback total: el documento borrador recién creado se descarta.
            raise ComisariatoError("COMISARIATO_CREDIT_LIMIT_EXCEEDED")

        doc.credit_status = CreditStatus.APPROVED
        doc.save(update_fields=["credit_status"])

        issue_doc(
            request=request, actor=actor, doc_id=doc.id, apply_inventory=True,
            idempotency_key=f"comis-issue:{doc.id}",
        )
        doc.refresh_from_db()
        rec = _receivable_for_doc(company=company, doc_id=doc.id)

        write_event(
            request=request, module="COMISARIATO", event_type="COMISARIATO_CREDIT_SALE",
            reason_code="COMISARIATO_OK", actor_user=actor,
            subject_type="COMISARIATO_SALE", subject_id=str(doc.id),
            metadata={
                "account_id": account.id, "party_id": account.party_id, "segment": account.segment,
                "reference_code": reference_code, "total": str(doc.total),
                "receivable_id": str(rec.obligation_id) if rec else None,
            },
        )
        return _bundle(account=account, doc=doc, duplicate=False)
