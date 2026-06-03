"""Emisión de Notas de Crédito (Unidad #1 — facturacion).

Capacidad avanzada que faltaba: el `DocType.CREDIT_NOTE` y el método del adaptador
`issue_credit_note` existían pero sin un servicio que los orqueste. Aquí se emite
una nota de crédito (total o parcial) enlazada a una factura emitida, reutilizando
los building blocks existentes:

- `create_draft` para líneas/totales/idempotencia.
- la interfaz fiscal A/B (`adapter.issue_credit_note` + `produce_fiscal_evidence`).
- la máquina de estados fiscal (`_set_fiscal_status`) y la numeración (`_allocate_document_number`).

Controla el saldo acreditable del original, audita (`BILLING_CREDIT_NOTE_ISSUED`) y
publica el evento canónico `CreditNoteIssued` (§6.3). La contabilización (reversa)
queda a cargo del consumidor del evento (consistencia eventual, §6.1).
"""
from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.modulos.audit.writer import write_event
from apps.modulos.integration.services import publish_outbox_event

from .models import BillingDocument, DocStatus, DocType, FiscalMode, FiscalStatus
from .services import (
    BillingError,
    BillingNotFoundError,
    _allocate_document_number,
    _fiscal_payload,
    _resolve_config,
    _set_fiscal_issue_fields,
    _set_fiscal_status,
    create_draft,
    get_fiscal_adapter,
)

_CENT = Decimal("0.01")


def _remaining_creditable(original: BillingDocument) -> Decimal:
    return Decimal(original.total) - Decimal(original.credited_total or 0)


def _mirror_lines(original: BillingDocument) -> list[dict]:
    return [
        {
            "description": ln.description,
            "quantity": str(ln.quantity),
            "unit_price": str(ln.unit_price),
            "tax_rate": str(ln.tax_rate),
            "discount_pct": str(ln.discount_pct),
        }
        for ln in original.lines.all()
    ]


@transaction.atomic
def issue_credit_note(
    *,
    request,
    actor,
    original_doc_id: int,
    reason: str,
    lines: list[dict] | None = None,
    idempotency_key: str = "",
    correlation_id: str = "",
    causation_id: str = "",
) -> BillingDocument:
    company = request.company
    branch = request.branch

    key = str(idempotency_key or "").strip()
    if key:
        existing = (
            BillingDocument.objects.filter(
                company=company, doc_type=DocType.CREDIT_NOTE, idempotency_key=key
            )
            .select_for_update()
            .first()
        )
        if existing is not None and existing.status == DocStatus.ISSUED:
            return existing

    try:
        original = BillingDocument.objects.select_for_update().get(
            id=original_doc_id, company=company, branch=branch
        )
    except BillingDocument.DoesNotExist as exc:
        raise BillingNotFoundError("documento original no encontrado") from exc

    if original.doc_type != DocType.INVOICE:
        raise BillingError("solo se puede acreditar una factura (INVOICE)")
    if original.status != DocStatus.ISSUED:
        raise BillingError("solo se puede acreditar un documento emitido (ISSUED)")

    cn_lines = lines if lines is not None else _mirror_lines(original)
    if not cn_lines:
        raise BillingError("la nota de crédito requiere al menos una línea")

    # 1) Draft de la nota de crédito (reusa líneas/totales/idempotencia).
    draft = create_draft(
        request=request,
        actor=actor,
        doc_type=DocType.CREDIT_NOTE,
        series=original.series,
        currency=original.currency,
        customer_name=original.customer_name,
        customer_ref=original.customer_ref,
        customer_party_id=original.customer_party_id,
        is_fiscal=original.is_fiscal,
        lines=cn_lines,
        idempotency_key=key,
        payment_method=original.payment_method,
        source_module="BILLING",
        source_type="CREDIT_NOTE_OF",
        source_id=str(original.id),
    )
    cn = BillingDocument.objects.select_for_update().get(id=draft.doc_id)

    # 2) Control de saldo acreditable (tolerancia de 1 centavo por redondeo).
    if Decimal(cn.total) > _remaining_creditable(original) + _CENT:
        raise BillingError(
            "el monto a acreditar excede el saldo acreditable del documento original"
        )

    # 3) Emisión fiscal (interfaz A/B + máquina de estados).
    cn.related_doc = original
    _allocate_document_number(doc=cn)
    cn.status = DocStatus.ISSUED
    cn.issued_at = timezone.now()

    runtime_cfg = _resolve_config(company=company, branch=branch)
    adapter = get_fiscal_adapter(company=company, branch=branch)

    if runtime_cfg.mode == FiscalMode.B:
        reserved_ref = adapter.attach_or_reserve_reference(doc=cn)
        _set_fiscal_status(cn, target=FiscalStatus.NUMBER_RESERVED)
        _set_fiscal_issue_fields(
            doc=cn, mode=runtime_cfg.mode, reference=reserved_ref, evidence_id="",
            metadata={"adapter_code": adapter.adapter_code},
        )

    fiscal_res = adapter.issue_credit_note(request=request, original_doc=original, credit_note_doc=cn)
    evidence = adapter.produce_fiscal_evidence(request=request, doc=cn)

    if runtime_cfg.mode == FiscalMode.B:
        _set_fiscal_status(cn, target=FiscalStatus.ISSUED)
    elif not cn.fiscal_status:
        cn.fiscal_status = FiscalStatus.ISSUED

    _set_fiscal_issue_fields(
        doc=cn, mode=runtime_cfg.mode, reference=fiscal_res.reference,
        evidence_id=evidence.evidence_id, metadata=(fiscal_res.metadata or {}),
    )
    cn.save(
        update_fields=[
            "related_doc", "number", "status", "issued_at",
            "fiscal_mode_resolved", "fiscal_status", "fiscal_reference",
            "fiscal_evidence_id", "fiscal_metadata_json",
        ]
    )

    # 4) Actualiza el saldo acreditado del original.
    original.credited_total = Decimal(original.credited_total or 0) + Decimal(cn.total)
    original.save(update_fields=["credited_total"])

    # 5) Auditoría detallada + evento canónico.
    write_event(
        request=request,
        module="BILLING",
        event_type="BILLING_CREDIT_NOTE_ISSUED",
        reason_code="BILLING_OK",
        actor_user=actor,
        subject_type="BILLING_DOC",
        subject_id=str(cn.id),
        after_snapshot={
            "credit_note_id": cn.id,
            "original_doc_id": original.id,
            "number": cn.number,
            "total": str(cn.total),
            "fiscal_status": cn.fiscal_status,
            "fiscal_reference": cn.fiscal_reference,
        },
        metadata={
            "reason": reason or "",
            "original_doc_id": str(original.id),
            "original_credited_total": str(original.credited_total),
        },
    )
    publish_outbox_event(
        request=request,
        source_module="BILLING",
        event_type="CreditNoteIssued",
        payload={
            "credit_note_id": cn.id,
            "original_doc_id": original.id,
            "doc_type": cn.doc_type,
            "series": cn.series,
            "number": cn.number,
            "currency": cn.currency,
            "subtotal": str(cn.subtotal),
            "tax_total": str(cn.tax_total),
            "total": str(cn.total),
            "is_fiscal": bool(cn.is_fiscal),
            "fiscal_status": cn.fiscal_status,
            "fiscal_reference": cn.fiscal_reference,
            **_fiscal_payload(doc=cn),
        },
        actor_user=actor,
        company=company,
        branch=branch,
        correlation_id=correlation_id or "",
        causation_id=causation_id or "",
    )
    return cn
