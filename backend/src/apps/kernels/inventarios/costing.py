"""Política de costo versionada (invariante #8) — resolución y versionado.

Resuelve el método de costeo vigente por scope (sucursal con fallback a empresa)
y permite cambiarlo creando una **versión nueva** (la anterior se cierra), de modo
que los movimientos posteados conservan el costeo de su época. El default —cuando
no hay política configurada— es promedio ponderado móvil (comportamiento actual),
por lo que esto NO altera el costeo existente.
"""
from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.modulos.audit.writer import write_event

from .models import CostingMethod, InventoryCostPolicy, StockMovementCostLayer

_Q_COST = Decimal("0.000001")
_Q_QTY = Decimal("0.0001")


def _q_cost(v) -> Decimal:
    return Decimal(v).quantize(_Q_COST)


def _q_qty(v) -> Decimal:
    return Decimal(v).quantize(_Q_QTY)


def get_active_cost_policy(*, company, branch=None) -> InventoryCostPolicy | None:
    """Política activa: específica de la sucursal o, si no hay, la de empresa."""
    policy = InventoryCostPolicy.objects.filter(company=company, branch=branch, is_active=True).first()
    if policy is None and branch is not None:
        policy = InventoryCostPolicy.objects.filter(company=company, branch__isnull=True, is_active=True).first()
    return policy


def resolve_costing_method(*, company, branch=None) -> str:
    policy = get_active_cost_policy(company=company, branch=branch)
    return policy.method if policy is not None else CostingMethod.WEIGHTED_AVERAGE


def resolve_active_cost_policy_version(*, company, branch=None) -> int:
    """Versión de la política vigente (0 = sin política => default no versionado)."""
    policy = get_active_cost_policy(company=company, branch=branch)
    return policy.version if policy is not None else 0


def _audit_request(*, request, company, branch=None):
    if request is not None:
        return request

    class _Req:
        pass

    req = _Req()
    req.company = company
    req.branch = branch
    req.META = {}
    req.path = ""
    req.method = ""
    req.request_id = ""
    return req


@transaction.atomic
def set_cost_policy(
    *, request=None, actor=None, company, branch=None, method: str, params: dict | None = None, note: str = ""
) -> InventoryCostPolicy:
    """Versionado: cierra la política activa del scope y crea una versión nueva."""
    if method not in CostingMethod.values:
        raise ValueError(f"método de costeo inválido: {method}")

    current = (
        InventoryCostPolicy.objects.select_for_update()
        .filter(company=company, branch=branch, is_active=True)
        .first()
    )
    next_version = 1
    if current is not None:
        current.is_active = False
        current.effective_to = timezone.now()
        current.save(update_fields=["is_active", "effective_to"])
        next_version = int(current.version) + 1

    policy = InventoryCostPolicy.objects.create(
        company=company,
        branch=branch,
        method=method,
        version=next_version,
        params=params or {},
        is_active=True,
        effective_from=timezone.now(),
        note=note or "",
        created_by=actor,
    )

    write_event(
        request=_audit_request(request=request, company=company, branch=branch),
        module="INVENTORY",
        event_type="INVENTORY_COST_POLICY_SET",
        reason_code="INVENTORY_OK",
        actor_user=actor,
        subject_type="INVENTORY_COST_POLICY",
        subject_id=str(policy.id),
        after_snapshot={"method": policy.method, "version": policy.version, "branch_id": branch.id if branch else None},
        metadata={"company_id": str(company.id), "previous_version": str(current.version) if current else "0"},
    )
    return policy


# ---------------------------------------------------------------------------
# Motor FIFO (PEPS) por capas de costo
# ---------------------------------------------------------------------------
#
# Las capas SOLO se materializan cuando la política vigente es FIFO. Cada entrada crea
# una capa; cada salida consume las más antiguas (created_at, id) y el COGS unitario es el
# promedio ponderado de lo consumido. La reversa de movimientos NO necesita lógica propia:
# reusa post_receive/post_issue (ver reversal.py), así que crea/consume capas por la misma
# vía que cualquier entrada/salida y el kardex de costo siempre cuadra con el físico.


def fifo_create_layer(*, company, branch, warehouse, item, lot, movement, unit_cost, qty) -> None:
    """Materializa una capa de costo para una entrada (RECEIVE / TRANSFER_IN / ajuste +)."""
    StockMovementCostLayer.objects.create(
        company=company, branch=branch, warehouse=warehouse, item=item, lot=lot,
        source_movement=movement, unit_cost=_q_cost(unit_cost),
        qty_initial=_q_qty(qty), qty_remaining=_q_qty(qty),
    )


def _open_layers(*, company, branch, warehouse, item):
    return (
        StockMovementCostLayer.objects.select_for_update()
        .filter(company=company, branch=branch, warehouse=warehouse, item=item, qty_remaining__gt=0)
        .order_by("created_at", "id")
    )


def fifo_consume(*, company, branch, warehouse, item, qty, fallback_unit_cost) -> Decimal:
    """Consume ``qty`` de las capas más antiguas y devuelve el COGS unitario ponderado.

    Si las capas no alcanzan (stock negativo permitido vía ``allow_negative``), el faltante
    se cuesta a ``fallback_unit_cost`` (el promedio del balance), de modo que el COGS no se
    parte ante un descubierto puntual.
    """
    qty = _q_qty(qty)
    if qty <= 0:
        return Decimal("0.000000")
    remaining = qty
    total = Decimal("0")
    for layer in _open_layers(company=company, branch=branch, warehouse=warehouse, item=item):
        if remaining <= 0:
            break
        take = layer.qty_remaining if layer.qty_remaining < remaining else remaining
        total += take * layer.unit_cost
        layer.qty_remaining = _q_qty(layer.qty_remaining - take)
        layer.save(update_fields=["qty_remaining"])
        remaining = _q_qty(remaining - take)
    if remaining > 0:
        total += remaining * _q_cost(fallback_unit_cost)
    return _q_cost(total / qty)


def fifo_weighted_cost(*, company, branch, warehouse, item, fallback) -> Decimal:
    """Costo unitario ponderado de las capas abiertas (mantiene ``bal.avg_cost`` exacto en
    FIFO: ``qty_on_hand × avg_cost == Σ capas``). Sin capas abiertas → ``fallback``."""
    tot_qty = Decimal("0")
    tot_val = Decimal("0")
    for qty_rem, unit_cost in StockMovementCostLayer.objects.filter(
        company=company, branch=branch, warehouse=warehouse, item=item, qty_remaining__gt=0
    ).values_list("qty_remaining", "unit_cost"):
        tot_qty += qty_rem
        tot_val += qty_rem * unit_cost
    if tot_qty <= 0:
        return _q_cost(fallback)
    return _q_cost(tot_val / tot_qty)
