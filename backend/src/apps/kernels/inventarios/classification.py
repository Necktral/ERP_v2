"""Clasificación de inventario por producto: las tres clases (FEFO/FIFO/AVERAGE).

La clase define el **orden de consumo** del stock (no la valuación de costo, que es
la política versionada #8). Hoy se selecciona **manual por producto**; más adelante
podrá asistirse con IA en kernels posteriores reutilizando `set_inventory_class`.

API única que el resto del sistema consume:
- `resolve_inventory_class(item)`: clase efectiva (explícita, o derivada de los flags).
- `lot_consumption_ordering(item)`: orden ORM para seleccionar lotes al despachar.
- `set_inventory_class(...)`: reclasificación manual (o por IA), validada y auditada.
"""
from __future__ import annotations

from django.db import models, transaction

from apps.modulos.audit.writer import write_event

from .models import InventoryClass, InventoryItem


def resolve_inventory_class(item: InventoryItem) -> str:
    """Clase efectiva: la explícita si está; si no, se deriva de la trazabilidad."""
    if item.inventory_class:
        return item.inventory_class
    if item.track_expiry:
        return InventoryClass.FEFO
    if item.track_lots:
        return InventoryClass.FIFO
    return InventoryClass.AVERAGE


def lot_consumption_ordering(item: InventoryItem, *, prefix: str = "") -> tuple:
    """Orden ORM para elegir lotes al despachar, según la clase efectiva.

    - FEFO: primero el de menor vencimiento (los sin vencimiento, al final).
    - FIFO: primero el lote más antiguo (por fecha de producción).
    - AVERAGE: sin orden de lote (fungible).

    `prefix` permite ordenar consultas relacionadas (p.ej. sobre LotBalance con
    `prefix="lot__"`, los campos son del ItemLot relacionado).
    """
    cls = resolve_inventory_class(item)
    if cls == InventoryClass.FEFO:
        return (models.F(f"{prefix}expiry_date").asc(nulls_last=True), f"{prefix}id")
    if cls == InventoryClass.FIFO:
        return (models.F(f"{prefix}production_date").asc(nulls_last=True), f"{prefix}id")
    return ()


@transaction.atomic
def set_inventory_class(*, request=None, actor=None, item: InventoryItem, inventory_class: str) -> InventoryItem:
    """Reclasifica un producto (manual o por IA futura), validando coherencia."""
    if inventory_class not in InventoryClass.values:
        raise ValueError(f"clase de inventario inválida: {inventory_class}")

    item = InventoryItem.objects.select_for_update().get(pk=item.pk)
    before = item.inventory_class
    item.inventory_class = inventory_class
    item.full_clean()  # valida coherencia FEFO/FIFO con track_lots/track_expiry
    item.save(update_fields=["inventory_class", "updated_at"])

    write_event(
        request=_audit_request(request=request, company=item.company),
        module="INVENTORY",
        event_type="INVENTORY_ITEM_RECLASSIFIED",
        reason_code="INVENTORY_OK",
        actor_user=actor,
        subject_type="INVENTORY_ITEM",
        subject_id=str(item.id),
        before_snapshot={"inventory_class": before},
        after_snapshot={"inventory_class": item.inventory_class},
        metadata={"company_id": str(item.company_id), "sku": item.sku},
    )
    return item


def _audit_request(*, request, company):
    if request is not None:
        return request

    class _Req:
        pass

    req = _Req()
    req.company = company
    req.branch = None
    req.META = {}
    req.path = ""
    req.method = ""
    req.request_id = ""
    return req
