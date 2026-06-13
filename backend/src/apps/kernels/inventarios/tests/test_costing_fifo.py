"""Motor de costeo FIFO (PEPS) por capas.

Fija: las entradas crean capas; las salidas consumen las más antiguas y el COGS es el
ponderado de lo consumido; el balance queda en el ponderado de las capas restantes; la
reversa (que reusa post_receive/post_issue) mantiene capas y físico cuadrados.
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model

from apps.kernels.inventarios.costing import set_cost_policy
from apps.kernels.inventarios.models import (
    CostingMethod,
    InventoryItem,
    StockBalance,
    StockMovement,
    StockMovementCostLayer,
    UoM,
)
from apps.kernels.inventarios.reversal import reverse_movement
from apps.kernels.inventarios.services import create_warehouse, post_issue, post_receive
from apps.modulos.iam.models import OrgUnit

User = get_user_model()


def _scope():
    s = uuid.uuid4().hex[:6]
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name=f"H_{s}")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name=f"C_{s}", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name=f"B_{s}", parent=company)
    return company, branch


def _actor():
    t = uuid.uuid4().hex[:8]
    return User.objects.create_user(username=f"u_{t}", email=f"u_{t}@t.local", password="x")


def _req(company, branch, user):
    return SimpleNamespace(
        company=company, branch=branch, user=user,
        request_id="", headers={}, META={}, path="", method="POST",
    )


def _item(company):
    return InventoryItem.objects.create(
        company=company, sku=f"SKU{uuid.uuid4().hex[:6]}", name="Café", uom=UoM.UNIT,
    )


def _mov(mid):
    return StockMovement.objects.get(id=mid)


def _setup(method):
    company, branch = _scope()
    actor = _actor()
    req = _req(company, branch, actor)
    set_cost_policy(request=req, actor=actor, company=company, branch=None, method=method)
    wh = create_warehouse(request=req, company=company, branch=branch, actor_user=actor, name="C", code="W1")
    item = _item(company)
    return company, branch, actor, req, wh, item


@pytest.mark.django_db
def test_fifo_issue_consumes_oldest_layers_first():
    company, branch, actor, req, wh, item = _setup(CostingMethod.FIFO)

    post_receive(request=req, actor=actor, warehouse_id=wh.id, item_id=item.id,
                 qty=Decimal("10"), unit_cost=Decimal("5.00"), idempotency_key="r1")
    post_receive(request=req, actor=actor, warehouse_id=wh.id, item_id=item.id,
                 qty=Decimal("10"), unit_cost=Decimal("8.00"), idempotency_key="r2")

    # Dos capas abiertas.
    assert StockMovementCostLayer.objects.filter(company=company, item=item).count() == 2

    # Issue 15 cruza capas: 10×5 + 5×8 = 90 → COGS unit = 6.00.
    res = post_issue(request=req, actor=actor, warehouse_id=wh.id, item_id=item.id,
                     qty=Decimal("15"), idempotency_key="i1")
    mov = _mov(res.movement_id)
    assert mov.unit_cost == Decimal("6.000000")
    assert mov.total_cost == Decimal("-90.000000")

    # Capa vieja agotada; la nueva queda con 5 @ 8 → balance 5 @ 8.00.
    layer1 = StockMovementCostLayer.objects.get(unit_cost=Decimal("5.000000"))
    layer2 = StockMovementCostLayer.objects.get(unit_cost=Decimal("8.000000"))
    assert layer1.qty_remaining == Decimal("0.0000")
    assert layer2.qty_remaining == Decimal("5.0000")
    bal = StockBalance.objects.get(company=company, branch=branch, warehouse=wh, item=item)
    assert bal.qty_on_hand == Decimal("5.0000")
    assert bal.avg_cost == Decimal("8.000000")

    # Vaciar: COGS al costo de la capa restante.
    res = post_issue(request=req, actor=actor, warehouse_id=wh.id, item_id=item.id,
                     qty=Decimal("5"), idempotency_key="i2")
    assert _mov(res.movement_id).unit_cost == Decimal("8.000000")
    bal.refresh_from_db()
    assert bal.qty_on_hand == Decimal("0.0000")
    assert bal.avg_cost == Decimal("0.000000")


@pytest.mark.django_db
def test_fifo_balance_is_weighted_average_of_open_layers():
    company, branch, actor, req, wh, item = _setup(CostingMethod.FIFO)
    post_receive(request=req, actor=actor, warehouse_id=wh.id, item_id=item.id,
                 qty=Decimal("10"), unit_cost=Decimal("5.00"), idempotency_key="r1")
    res = post_receive(request=req, actor=actor, warehouse_id=wh.id, item_id=item.id,
                       qty=Decimal("30"), unit_cost=Decimal("9.00"), idempotency_key="r2")
    # 40 uds: (10×5 + 30×9)/40 = 320/40 = 8.00
    bal = StockBalance.objects.get(company=company, branch=branch, warehouse=wh, item=item)
    assert bal.qty_on_hand == Decimal("40.0000")
    assert bal.avg_cost == Decimal("8.000000")
    assert res.avg_cost == Decimal("8.000000")


@pytest.mark.django_db
def test_fifo_reversal_keeps_layers_and_physical_consistent():
    company, branch, actor, req, wh, item = _setup(CostingMethod.FIFO)
    r1 = post_receive(request=req, actor=actor, warehouse_id=wh.id, item_id=item.id,
                      qty=Decimal("10"), unit_cost=Decimal("5.00"), idempotency_key="r1")
    issue = post_issue(request=req, actor=actor, warehouse_id=wh.id, item_id=item.id,
                       qty=Decimal("4"), idempotency_key="i1")

    # Reversar el ISSUE reintegra 4 uds (vía post_receive al costo del issue) → físico 10.
    reverse_movement(request=req, actor=actor, movement_id=issue.movement_id, reason="error")
    bal = StockBalance.objects.get(company=company, branch=branch, warehouse=wh, item=item)
    assert bal.qty_on_hand == Decimal("10.0000")
    total_layers = sum(
        l.qty_remaining for l in StockMovementCostLayer.objects.filter(company=company, item=item)
    )
    assert total_layers == bal.qty_on_hand  # capas == físico

    # Reversar el RECEIVE original despacha 10 (vía post_issue) → físico 0, capas 0.
    reverse_movement(request=req, actor=actor, movement_id=r1.movement_id, reason="error")
    bal.refresh_from_db()
    assert bal.qty_on_hand == Decimal("0.0000")
    open_qty = sum(
        l.qty_remaining for l in StockMovementCostLayer.objects.filter(company=company, item=item)
    )
    assert open_qty == bal.qty_on_hand == Decimal("0.0000")  # invariante: capas == físico
