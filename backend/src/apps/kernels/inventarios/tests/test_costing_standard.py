"""Costeo STANDARD (costo estándar + varianza de compra) y no-regresión del promedio móvil.

STANDARD: el inventario se valúa al costo estándar del ítem; la diferencia con el costo real
de compra se registra como varianza en el movimiento (no muta el estándar); el COGS de salida
es el estándar. Sin política configurada el costeo NO cambia (promedio ponderado móvil) y NO
se materializan capas FIFO.
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


def _setup(method=None, *, standard_cost="0.00"):
    company, branch = _scope()
    actor = _actor()
    req = _req(company, branch, actor)
    if method is not None:
        set_cost_policy(request=req, actor=actor, company=company, branch=None, method=method)
    wh = create_warehouse(request=req, company=company, branch=branch, actor_user=actor, name="C", code="W1")
    item = InventoryItem.objects.create(
        company=company, sku=f"SKU{uuid.uuid4().hex[:6]}", name="Café", uom=UoM.UNIT,
        standard_cost=Decimal(standard_cost),
    )
    return company, branch, actor, req, wh, item


def _mov(mid):
    return StockMovement.objects.get(id=mid)


@pytest.mark.django_db
def test_standard_records_purchase_variance_and_values_at_standard():
    company, branch, actor, req, wh, item = _setup(CostingMethod.STANDARD, standard_cost="6.00")

    # Compra bajo el estándar: varianza favorable (5−6)×10 = −10.
    r1 = post_receive(request=req, actor=actor, warehouse_id=wh.id, item_id=item.id,
                      qty=Decimal("10"), unit_cost=Decimal("5.00"), idempotency_key="r1")
    m1 = _mov(r1.movement_id)
    assert m1.unit_cost == Decimal("5.000000")        # costo real pagado
    assert m1.cost_variance == Decimal("-10.000000")  # (5−6)×10
    bal = StockBalance.objects.get(company=company, branch=branch, warehouse=wh, item=item)
    assert bal.avg_cost == Decimal("6.000000")        # valuado a estándar

    # Compra sobre el estándar: varianza desfavorable (8−6)×10 = 20; el balance sigue a estándar.
    r2 = post_receive(request=req, actor=actor, warehouse_id=wh.id, item_id=item.id,
                      qty=Decimal("10"), unit_cost=Decimal("8.00"), idempotency_key="r2")
    assert _mov(r2.movement_id).cost_variance == Decimal("20.000000")
    bal.refresh_from_db()
    assert bal.avg_cost == Decimal("6.000000")

    # COGS de salida = estándar.
    iss = post_issue(request=req, actor=actor, warehouse_id=wh.id, item_id=item.id,
                     qty=Decimal("5"), idempotency_key="i1")
    mi = _mov(iss.movement_id)
    assert mi.unit_cost == Decimal("6.000000")
    assert mi.total_cost == Decimal("-30.000000")
    bal.refresh_from_db()
    assert bal.avg_cost == Decimal("6.000000")

    # STANDARD no materializa capas FIFO.
    assert StockMovementCostLayer.objects.filter(company=company, item=item).count() == 0


@pytest.mark.django_db
def test_weighted_average_default_is_unchanged_and_creates_no_layers():
    # Sin política → promedio ponderado móvil (comportamiento histórico).
    company, branch, actor, req, wh, item = _setup(method=None)
    post_receive(request=req, actor=actor, warehouse_id=wh.id, item_id=item.id,
                 qty=Decimal("10"), unit_cost=Decimal("5.00"), idempotency_key="r1")
    r2 = post_receive(request=req, actor=actor, warehouse_id=wh.id, item_id=item.id,
                      qty=Decimal("10"), unit_cost=Decimal("8.00"), idempotency_key="r2")
    # (10×5 + 10×8)/20 = 6.5
    assert r2.avg_cost == Decimal("6.500000")

    iss = post_issue(request=req, actor=actor, warehouse_id=wh.id, item_id=item.id,
                     qty=Decimal("5"), idempotency_key="i1")
    mi = _mov(iss.movement_id)
    assert mi.unit_cost == Decimal("6.500000")     # COGS al promedio
    assert mi.cost_variance == Decimal("0.000000")  # sin varianza en promedio
    bal = StockBalance.objects.get(company=company, branch=branch, warehouse=wh, item=item)
    assert bal.avg_cost == Decimal("6.500000")      # promedio se preserva en la salida

    # El default NO crea capas FIFO.
    assert StockMovementCostLayer.objects.filter(company=company, item=item).count() == 0
