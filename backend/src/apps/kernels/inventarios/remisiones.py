"""Remisiones: despacho (punto A) + recepción/cotejo con evidencia (punto B).

Flujo:
1. `create_remision`: el punto A genera la remisión (líneas tomadas de la factura
   de compra/venta cuyos artículos van a inventario) en estado DRAFT.
2. `dispatch_remision`: el punto A confirma el despacho (DRAFT -> DISPATCHED).
3. `attach_remision_photo`: el gerente de compras adjunta evidencia fotográfica.
4. `receive_remision`: el bodeguero del punto B coteja el físico (qty_received por
   línea) y al recibir los artículos ENTRAN a inventario (post_receive en la bodega
   destino). Las diferencias quedan marcadas (`has_discrepancy`). (DISPATCHED -> RECEIVED)

Todo es transaccional, idempotente, auditado (`REMISION_*`) y publica outbox.
"""
from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.modulos.audit.writer import write_event
from apps.modulos.integration.services import publish_outbox_event

from .models import InventoryItem, Remision, RemisionLine, RemisionPhoto, RemisionStatus, Warehouse
from .services import InventoryConflictError, _require_branch, post_receive


class RemisionError(InventoryConflictError):
    """Operación de remisión no permitida o inválida."""


def _audit(*, request, actor, remision: Remision, event_type: str, before=None, after=None, meta=None) -> None:
    write_event(
        request=request,
        module="INVENTORY",
        event_type=event_type,
        reason_code="INVENTORY_OK",
        actor_user=actor,
        subject_type="REMISION",
        subject_id=str(remision.remision_id),
        before_snapshot=before,
        after_snapshot=after,
        metadata={**(meta or {}), "company_id": str(remision.company_id), "branch_id": str(remision.branch_id)},
    )


def _require_transition(remision: Remision, target: str) -> None:
    if not remision.can_transition_to(target):
        raise RemisionError(f"transición de remisión no permitida: {remision.status} -> {target}")


@transaction.atomic
def create_remision(
    *,
    request,
    actor,
    origin_type: str,
    dest_warehouse_id: int,
    lines: list[dict],
    origin_warehouse_id: int | None = None,
    source_module: str = "",
    source_type: str = "",
    source_id: str = "",
    note: str = "",
    idempotency_key: str = "",
) -> Remision:
    company = request.company
    branch = _require_branch(request)

    key = str(idempotency_key or "").strip()
    if key:
        existing = Remision.objects.filter(company=company, idempotency_key=key).first()
        if existing is not None:
            return existing

    if not lines:
        raise RemisionError("la remisión requiere al menos una línea")

    dest_wh = Warehouse.objects.get(id=dest_warehouse_id, company=company)
    origin_wh = (
        Warehouse.objects.get(id=origin_warehouse_id, company=company) if origin_warehouse_id else None
    )

    remision = Remision.objects.create(
        company=company,
        branch=branch,
        origin_type=origin_type,
        source_module=source_module or "",
        source_type=source_type or "",
        source_id=str(source_id or ""),
        origin_warehouse=origin_wh,
        dest_warehouse=dest_wh,
        status=RemisionStatus.DRAFT,
        note=note or "",
        idempotency_key=key,
        created_by=actor,
    )
    for ln in lines:
        item = InventoryItem.objects.get(id=int(ln["item_id"]), company=company)
        RemisionLine.objects.create(
            remision=remision,
            item=item,
            description=str(ln.get("description") or item.name)[:200],
            qty_dispatched=Decimal(str(ln["qty_dispatched"])),
            unit_cost=Decimal(str(ln.get("unit_cost", "0") or "0")),
        )

    _audit(
        request=request, actor=actor, remision=remision, event_type="REMISION_CREATED",
        after={"status": remision.status, "origin_type": origin_type, "lines": len(lines)},
    )
    return remision


@transaction.atomic
def dispatch_remision(*, request, actor, remision: Remision) -> Remision:
    remision = Remision.objects.select_for_update().get(pk=remision.pk)
    _require_transition(remision, RemisionStatus.DISPATCHED)
    before = {"status": remision.status}
    remision.status = RemisionStatus.DISPATCHED
    remision.dispatched_by = actor
    remision.dispatched_at = timezone.now()
    remision.save(update_fields=["status", "dispatched_by", "dispatched_at", "updated_at"])

    _audit(request=request, actor=actor, remision=remision, event_type="REMISION_DISPATCHED",
           before=before, after={"status": remision.status})
    publish_outbox_event(
        request=request, source_module="INVENTORY", event_type="RemisionDispatched",
        payload={"remision_id": str(remision.remision_id), "dest_warehouse_id": remision.dest_warehouse_id},
        actor_user=actor, company=remision.company, branch=remision.branch,
    )
    return remision


@transaction.atomic
def attach_remision_photo(
    *, request, actor, remision: Remision, storage_ref: str, sha256: str = "", mime_type: str = "image/jpeg", caption: str = ""
) -> RemisionPhoto:
    photo = RemisionPhoto.objects.create(
        remision=remision, storage_ref=storage_ref, sha256=sha256 or "",
        mime_type=mime_type or "image/jpeg", caption=caption or "", uploaded_by=actor,
    )
    _audit(request=request, actor=actor, remision=remision, event_type="REMISION_PHOTO_ATTACHED",
           after={"photo_id": photo.id, "storage_ref": storage_ref})
    return photo


@transaction.atomic
def receive_remision(*, request, actor, remision: Remision, received_lines: list[dict]) -> Remision:
    remision = Remision.objects.select_for_update().get(pk=remision.pk)
    _require_transition(remision, RemisionStatus.RECEIVED)

    qty_by_line = {int(r["line_id"]): Decimal(str(r["qty_received"])) for r in received_lines}
    has_discrepancy = False

    for line in remision.lines.select_related("item").all():
        qty_recv = qty_by_line.get(line.id, Decimal("0"))
        line.qty_received = qty_recv
        if qty_recv != Decimal(line.qty_dispatched):
            has_discrepancy = True
        if qty_recv > 0:
            res = post_receive(
                request=request,
                actor=actor,
                warehouse_id=remision.dest_warehouse_id,
                item_id=line.item_id,
                qty=qty_recv,
                unit_cost=Decimal(line.unit_cost),
                idempotency_key=f"remision:{remision.id}:line:{line.id}",
                note=f"Recepción remisión {remision.remision_id}"[:255],
                source_module="INVENTORY",
                source_type="REMISION",
                source_id=str(remision.id),
            )
            line.received_movement_id = res.movement_id
        line.save(update_fields=["qty_received", "received_movement"])

    before = {"status": remision.status}
    remision.status = RemisionStatus.RECEIVED
    remision.received_by = actor
    remision.received_at = timezone.now()
    remision.has_discrepancy = has_discrepancy
    remision.save(update_fields=["status", "received_by", "received_at", "has_discrepancy", "updated_at"])

    _audit(request=request, actor=actor, remision=remision, event_type="REMISION_RECEIVED",
           before=before, after={"status": remision.status, "has_discrepancy": has_discrepancy})
    publish_outbox_event(
        request=request, source_module="INVENTORY", event_type="RemisionReceived",
        payload={
            "remision_id": str(remision.remision_id),
            "dest_warehouse_id": remision.dest_warehouse_id,
            "has_discrepancy": has_discrepancy,
            "lines": remision.lines.count(),
        },
        actor_user=actor, company=remision.company, branch=remision.branch,
    )
    return remision


@transaction.atomic
def cancel_remision(*, request, actor, remision: Remision, reason: str = "") -> Remision:
    remision = Remision.objects.select_for_update().get(pk=remision.pk)
    _require_transition(remision, RemisionStatus.CANCELLED)
    before = {"status": remision.status}
    remision.status = RemisionStatus.CANCELLED
    if reason:
        remision.note = (f"{remision.note} | CANCEL: {reason}").strip(" |")[:255]
    remision.save(update_fields=["status", "note", "updated_at"])
    _audit(request=request, actor=actor, remision=remision, event_type="REMISION_CANCELLED",
           before=before, after={"status": remision.status}, meta={"reason": reason or ""})
    return remision
