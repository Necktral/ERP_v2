"""Reversa de movimientos de inventario de primera clase (Unidad #2).

Convención de inventario alineada al invariante #1 ("no borrar histórico crítico;
solo reversas"): un movimiento posteado nunca se edita ni elimina; se compensa con
un movimiento inverso enlazado (`reversal_of`) y el original queda marcado
(`reversed_at`). Reutiliza `post_receive`/`post_issue` (idempotentes, costeo,
balances, contabilidad y outbox) según el signo del `qty_delta` original.

- Original que REMOVIÓ stock (ISSUE/TRANSFER_OUT/SHRINKAGE/...) -> reversa RECIBE.
- Original que AGREGÓ stock (RECEIVE/TRANSFER_IN/RETURN/...) -> reversa DESPACHA.
"""
from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.modulos.audit.writer import write_event
from apps.modulos.integration.services import publish_outbox_event

from .models import StockMovement
from .services import InventoryConflictError, _require_branch, post_issue, post_receive


class MovementReversalError(InventoryConflictError):
    """Reversa no permitida o movimiento inválido para reversar."""


@transaction.atomic
def reverse_movement(*, request, actor, movement_id: int, reason: str, idempotency_key: str = "") -> StockMovement:
    company = request.company
    branch = _require_branch(request)

    try:
        mov = StockMovement.objects.select_for_update().get(id=movement_id, company=company, branch=branch)
    except StockMovement.DoesNotExist as exc:
        raise MovementReversalError("movimiento no encontrado") from exc

    if mov.reversal_of_id is not None:
        raise MovementReversalError("no se puede reversar un movimiento que ya es una reversa")
    if mov.reversed_at is not None:
        # Idempotente: devolver la reversa existente.
        existing = StockMovement.objects.filter(reversal_of=mov).first()
        if existing is not None:
            return existing

    qty = abs(Decimal(mov.qty_delta))
    if qty <= 0:
        raise MovementReversalError("un movimiento con qty_delta cero no es reversable")

    rev_key = idempotency_key or f"reverse:mov:{mov.id}"
    common = dict(
        request=request,
        actor=actor,
        warehouse_id=mov.warehouse_id,
        item_id=mov.item_id,
        lot_id=mov.lot_id,
        idempotency_key=rev_key,
        note=f"Reversa mov {mov.id}: {reason}"[:255],
        source_module="INVENTORY",
        source_type="MOVEMENT_REVERSAL",
        source_id=str(mov.id),
    )

    if mov.qty_delta < 0:
        res = post_receive(qty=qty, unit_cost=Decimal(mov.unit_cost), **common)
    else:
        res = post_issue(qty=qty, allow_negative=True, **common)

    rev_mov = StockMovement.objects.get(id=res.movement_id)
    rev_mov.reversal_of = mov
    rev_mov.save(update_fields=["reversal_of"])

    mov.reversed_at = timezone.now()
    mov.save(update_fields=["reversed_at"])

    write_event(
        request=request,
        module="INVENTORY",
        event_type="INVENTORY_MOVEMENT_REVERSED",
        reason_code="INVENTORY_OK",
        actor_user=actor,
        subject_type="STOCK_MOVEMENT",
        subject_id=str(mov.id),
        before_snapshot={"movement_id": mov.id, "movement_type": mov.movement_type, "qty_delta": str(mov.qty_delta)},
        after_snapshot={"reversal_movement_id": rev_mov.id, "reversed_at": mov.reversed_at.isoformat()},
        metadata={"reason": reason or "", "company_id": str(company.id), "branch_id": str(branch.id)},
    )
    publish_outbox_event(
        request=request,
        source_module="INVENTORY",
        event_type="InventoryMovementReversed",
        payload={
            "original_movement_id": mov.id,
            "reversal_movement_id": rev_mov.id,
            "movement_type": mov.movement_type,
            "reversal_movement_type": rev_mov.movement_type,
            "qty_delta": str(rev_mov.qty_delta),
            "item_id": mov.item_id,
            "warehouse_id": mov.warehouse_id,
            "reason": reason or "",
        },
        actor_user=actor,
        company=company,
        branch=branch,
    )
    return rev_mov
