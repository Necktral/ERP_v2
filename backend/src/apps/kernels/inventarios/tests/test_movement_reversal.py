"""Tests de reversa de movimientos de inventario (reverse_movement)."""
from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model

from apps.kernels.inventarios.models import (
    InventoryItem,
    MovementType,
    StockBalance,
    StockMovement,
    Warehouse,
)
from apps.kernels.inventarios.reversal import MovementReversalError, reverse_movement
from apps.kernels.inventarios.services import post_issue, post_receive
from apps.modulos.iam.models import OrgUnit
from apps.modulos.integration.models import OutboxEvent

User = get_user_model()


def _scope():
    t = uuid.uuid4().hex[:8]
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name=f"H{t}", code=f"H-{t}")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, parent=holding, name=f"C{t}", code=f"C-{t}")
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, parent=company, name=f"B{t}", code=f"B-{t}")
    user = User.objects.create_user(username=f"u_{t}", email=f"u_{t}@test.local", password="Secret123!")
    request = SimpleNamespace(
        company=company, branch=branch, user=user, META={}, headers={},
        path="/t/inv/", method="POST", request_id=f"req-{t}",
    )
    return company, branch, user, request


def _wh_item(company, branch):
    wh = Warehouse.objects.create(company=company, branch=branch, name="Main", code=f"W{uuid.uuid4().hex[:5]}")
    item = InventoryItem.objects.create(company=company, sku=f"SKU-{uuid.uuid4().hex[:6]}", name="Item")
    return wh, item


def _qty(company, branch, wh, item) -> Decimal:
    bal = StockBalance.objects.filter(company=company, branch=branch, warehouse=wh, item=item).first()
    return bal.qty_on_hand if bal else Decimal("0.0000")


@pytest.mark.django_db
def test_reverse_receive_removes_stock_and_links():
    company, branch, user, request = _scope()
    wh, item = _wh_item(company, branch)
    recv = post_receive(
        request=request, actor=user, warehouse_id=wh.id, item_id=item.id,
        qty=Decimal("10.0000"), unit_cost=Decimal("2.500000"), idempotency_key=f"r-{uuid.uuid4().hex}",
    )
    assert _qty(company, branch, wh, item) == Decimal("10.0000")

    rev = reverse_movement(request=request, actor=user, movement_id=recv.movement_id, reason="error de captura")
    assert rev.reversal_of_id == recv.movement_id
    assert rev.movement_type == MovementType.ISSUE
    assert _qty(company, branch, wh, item) == Decimal("0.0000")

    original = StockMovement.objects.get(id=recv.movement_id)
    assert original.reversed_at is not None

    ev = OutboxEvent.objects.filter(source_module="INVENTORY", event_type="InventoryMovementReversed").first()
    assert ev is not None
    assert ev.payload["data"]["original_movement_id"] == recv.movement_id


@pytest.mark.django_db
def test_reverse_issue_restores_stock():
    company, branch, user, request = _scope()
    wh, item = _wh_item(company, branch)
    post_receive(
        request=request, actor=user, warehouse_id=wh.id, item_id=item.id,
        qty=Decimal("10.0000"), unit_cost=Decimal("2.000000"), idempotency_key=f"r-{uuid.uuid4().hex}",
    )
    iss = post_issue(
        request=request, actor=user, warehouse_id=wh.id, item_id=item.id,
        qty=Decimal("4.0000"), idempotency_key=f"i-{uuid.uuid4().hex}",
    )
    assert _qty(company, branch, wh, item) == Decimal("6.0000")

    rev = reverse_movement(request=request, actor=user, movement_id=iss.movement_id, reason="devolución")
    assert rev.movement_type == MovementType.RECEIVE
    assert _qty(company, branch, wh, item) == Decimal("10.0000")


@pytest.mark.django_db
def test_reverse_is_idempotent():
    company, branch, user, request = _scope()
    wh, item = _wh_item(company, branch)
    recv = post_receive(
        request=request, actor=user, warehouse_id=wh.id, item_id=item.id,
        qty=Decimal("5.0000"), unit_cost=Decimal("1.000000"), idempotency_key=f"r-{uuid.uuid4().hex}",
    )
    rev1 = reverse_movement(request=request, actor=user, movement_id=recv.movement_id, reason="x")
    rev2 = reverse_movement(request=request, actor=user, movement_id=recv.movement_id, reason="x")
    assert rev1.id == rev2.id
    assert _qty(company, branch, wh, item) == Decimal("0.0000")  # no se duplica


@pytest.mark.django_db
def test_cannot_reverse_a_reversal():
    company, branch, user, request = _scope()
    wh, item = _wh_item(company, branch)
    recv = post_receive(
        request=request, actor=user, warehouse_id=wh.id, item_id=item.id,
        qty=Decimal("3.0000"), unit_cost=Decimal("1.000000"), idempotency_key=f"r-{uuid.uuid4().hex}",
    )
    rev = reverse_movement(request=request, actor=user, movement_id=recv.movement_id, reason="x")
    with pytest.raises(MovementReversalError):
        reverse_movement(request=request, actor=user, movement_id=rev.id, reason="doble reversa")
