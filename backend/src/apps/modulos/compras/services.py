from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.iam.models import OrgUnit
from apps.integration.services import publish_outbox_event

from .models import PurchaseDocument, PurchaseDocStatus, PurchaseDocType, PurchaseSequence


class ProcurementError(Exception):
    pass


class ProcurementNotFoundError(ProcurementError):
    pass


@dataclass(frozen=True)
class PurchaseCreateResult:
    doc_id: int


def _allocate_number(*, doc: PurchaseDocument) -> None:
    seq, _ = PurchaseSequence.objects.select_for_update().get_or_create(
        company=doc.company,
        branch=doc.branch,
        doc_type=doc.doc_type,
        series=doc.series,
        defaults={"next_number": 1, "updated_at": timezone.now()},
    )
    number = int(seq.next_number)
    seq.next_number = number + 1
    seq.updated_at = timezone.now()
    seq.save(update_fields=["next_number", "updated_at"])
    doc.number = number


def create_purchase_draft(
    *,
    request,
    actor,
    doc_type: str,
    series: str,
    currency: str,
    supplier_name: str,
    supplier_ref: str,
    external_ref: str,
    subtotal: Decimal,
    tax_total: Decimal,
    total: Decimal,
    notes: str = "",
    metadata_json: dict | None = None,
    idempotency_key: str = "",
) -> PurchaseCreateResult:
    company: OrgUnit = request.company
    branch: OrgUnit = request.branch

    if doc_type not in PurchaseDocType.values:
        raise ProcurementError("invalid doc_type")

    with transaction.atomic():
        if idempotency_key:
            existing = PurchaseDocument.objects.filter(company=company, idempotency_key=idempotency_key).first()
            if existing is not None:
                return PurchaseCreateResult(doc_id=int(existing.id))

        doc = PurchaseDocument.objects.create(
            company=company,
            branch=branch,
            doc_type=doc_type,
            status=PurchaseDocStatus.DRAFT,
            series=(series or "P").strip().upper(),
            number=0,
            currency=(currency or "NIO").strip().upper(),
            supplier_name=supplier_name or "",
            supplier_ref=supplier_ref or "",
            external_ref=external_ref or "",
            subtotal=Decimal(str(subtotal)),
            tax_total=Decimal(str(tax_total)),
            total=Decimal(str(total)),
            notes=notes or "",
            metadata_json=dict(metadata_json or {}),
            idempotency_key=idempotency_key or "",
            created_by=actor,
        )

        publish_outbox_event(
            request=request,
            source_module="PROCUREMENT",
            event_type="ProcurementDocumentDrafted",
            payload={
                "doc_id": int(doc.id),
                "doc_type": doc.doc_type,
                "status": doc.status,
                "series": doc.series,
                "currency": doc.currency,
                "subtotal": str(doc.subtotal),
                "tax_total": str(doc.tax_total),
                "total": str(doc.total),
                "supplier_ref": doc.supplier_ref,
                "external_ref": doc.external_ref,
                "idempotency_key": doc.idempotency_key,
            },
            actor_user=actor,
            company=company,
            branch=branch,
        )
        return PurchaseCreateResult(doc_id=int(doc.id))


def post_purchase_document(*, request, actor, doc_id: int) -> dict:
    company: OrgUnit = request.company
    branch: OrgUnit = request.branch

    with transaction.atomic():
        try:
            doc = PurchaseDocument.objects.select_for_update().get(id=int(doc_id), company=company, branch=branch)
        except PurchaseDocument.DoesNotExist as exc:
            raise ProcurementNotFoundError("documento de compra no encontrado") from exc

        if doc.status == PurchaseDocStatus.VOIDED:
            raise ProcurementError("cannot post a voided purchase document")
        if doc.status == PurchaseDocStatus.POSTED:
            return {"ok": True, "already_posted": True, "doc_id": int(doc.id), "number": int(doc.number)}

        _allocate_number(doc=doc)
        doc.status = PurchaseDocStatus.POSTED
        doc.posted_at = timezone.now()
        doc.save(update_fields=["number", "status", "posted_at"])

        publish_outbox_event(
            request=request,
            source_module="PROCUREMENT",
            event_type="ProcurementDocumentPosted",
            payload={
                "doc_id": int(doc.id),
                "doc_type": doc.doc_type,
                "status": doc.status,
                "series": doc.series,
                "number": int(doc.number),
                "currency": doc.currency,
                "subtotal": str(doc.subtotal),
                "tax_total": str(doc.tax_total),
                "total": str(doc.total),
                "supplier_ref": doc.supplier_ref,
                "external_ref": doc.external_ref,
            },
            actor_user=actor,
            company=company,
            branch=branch,
        )

        return {
            "ok": True,
            "doc_id": int(doc.id),
            "status": doc.status,
            "number": int(doc.number),
        }


def void_purchase_document(*, request, actor, doc_id: int, reason: str = "VOID") -> dict:
    company: OrgUnit = request.company
    branch: OrgUnit = request.branch

    with transaction.atomic():
        try:
            doc = PurchaseDocument.objects.select_for_update().get(id=int(doc_id), company=company, branch=branch)
        except PurchaseDocument.DoesNotExist as exc:
            raise ProcurementNotFoundError("documento de compra no encontrado") from exc

        if doc.status == PurchaseDocStatus.VOIDED:
            return {"ok": True, "already_voided": True, "doc_id": int(doc.id)}
        if doc.status == PurchaseDocStatus.DRAFT:
            raise ProcurementError("cannot void a draft purchase document")

        doc.status = PurchaseDocStatus.VOIDED
        doc.voided_at = timezone.now()
        doc.void_reason = (reason or "VOID")[:255]
        doc.save(update_fields=["status", "voided_at", "void_reason"])

        publish_outbox_event(
            request=request,
            source_module="PROCUREMENT",
            event_type="ProcurementDocumentVoided",
            payload={
                "doc_id": int(doc.id),
                "doc_type": doc.doc_type,
                "status": doc.status,
                "series": doc.series,
                "number": int(doc.number),
                "currency": doc.currency,
                "subtotal": str(doc.subtotal),
                "tax_total": str(doc.tax_total),
                "total": str(doc.total),
                "reason": doc.void_reason,
                "supplier_ref": doc.supplier_ref,
                "external_ref": doc.external_ref,
            },
            actor_user=actor,
            company=company,
            branch=branch,
        )

        return {"ok": True, "doc_id": int(doc.id), "status": doc.status}
