"""Puente Insumos (finca) → Inventario (#2 Fase 2).

Aplicar un insumo desde stock **descuenta inventario real** vía `kernels.inventarios`
(`post_issue`, que ya calcula costo promedio y postea inventario→GL) y guarda en finca
solo la **referencia** al movimiento + el costo real — sin duplicar el movimiento.
Dependencia unidireccional `modulos.finca → kernels.inventarios` (lectura/escritura de
consumo); idempotente por `idempotency_key` (post_issue) y por `stock_movement_ref`.
"""
from __future__ import annotations

from decimal import Decimal

from django.db import transaction

from apps.kernels.inventarios.models import InventoryItem
from apps.kernels.inventarios.services import post_issue
from apps.modulos.audit.writer import write_event

from .models import InsumoApplication, WorkOrder
from .services import _money, _q


@transaction.atomic
def issue_insumo_from_stock(
    work_order: WorkOrder,
    *,
    warehouse_id: int,
    item_id: int,
    qty,
    request,
    actor=None,
    idempotency_key: str = "",
    note: str = "",
) -> InsumoApplication:
    """Descuenta `qty` del item en la bodega y registra el insumo con el costo real."""
    # F-01: exigir idempotency_key. Sin él, post_issue no es idempotente y un reintento
    # vuelve a descontar stock + duplica la InsumoApplication. La clave la provee el
    # cliente/offline (command_id) o el serializer del endpoint (requerido).
    if not (idempotency_key or "").strip():
        raise ValueError("idempotency_key es requerido para aplicar insumo (idempotencia).")
    company = request.company
    item = InventoryItem.objects.filter(id=item_id, company=company).first()
    if item is None:
        raise ValueError("Item de inventario no encontrado/aplicable.")

    result = post_issue(
        request=request,
        actor=actor,
        warehouse_id=warehouse_id,
        item_id=item_id,
        qty=_q(qty),
        idempotency_key=idempotency_key,
        note=note,
        source_module="FINCA",
        source_type="FINCA_WORKORDER",
        source_id=str(work_order.id),
    )

    movement_ref = str(result.movement_id)
    app, created = InsumoApplication.objects.get_or_create(
        stock_movement_ref=movement_ref,
        defaults={
            "work_order": work_order,
            "source": InsumoApplication.Source.INVENTORY,
            "item_code": item.sku,
            "item_name": item.name,
            "quantity": _q(qty),
            "unit": item.uom,
            "unit_cost": _money(result.avg_cost or Decimal("0.00")),
            "inventory_item_id": item_id,
            "warehouse_id": warehouse_id,
            "notes": note,
        },
    )
    if not created:
        return app

    write_event(
        request=request,
        module="FINCA",
        event_type="FINCA_INSUMO_ISSUED",
        reason_code="FINCA_OK",
        actor_user=actor,
        subject_type="FINCA_WORKORDER",
        subject_id=str(work_order.id),
        metadata={
            "item": item.sku,
            "quantity": str(_q(qty)),
            "unit_cost": str(app.unit_cost),
            "warehouse_id": warehouse_id,
            "stock_movement_ref": movement_ref,
        },
    )
    return app
