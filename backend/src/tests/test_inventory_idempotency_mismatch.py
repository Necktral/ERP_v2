from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model

from apps.kernels.inventarios.models import InventoryItem, StockMovement, Warehouse
from apps.kernels.inventarios.services import (
    InventoryConflictError,
    post_adjust,
    post_issue,
    post_receive,
    post_transfer,
)
from apps.modulos.iam.models import OrgUnit
from apps.modulos.integration.models import OutboxEvent

User = get_user_model()


def _build_scope():
    token = uuid.uuid4().hex[:8]
    holding = OrgUnit.objects.create(
        unit_type=OrgUnit.UnitType.HOLDING,
        name=f"Holding {token}",
        code=f"H-{token}",
    )
    company = OrgUnit.objects.create(
        unit_type=OrgUnit.UnitType.COMPANY,
        parent=holding,
        name=f"Company {token}",
        code=f"C-{token}",
    )
    branch = OrgUnit.objects.create(
        unit_type=OrgUnit.UnitType.BRANCH,
        parent=company,
        name=f"Branch {token}",
        code=f"B-{token}",
    )
    user = User.objects.create_user(
        username=f"inventory_idem_{token}",
        email=f"inventory_idem_{token}@example.com",
        password="Secret123!",
    )
    request = SimpleNamespace(
        company=company,
        branch=branch,
        user=user,
        META={},
        headers={},
        path="/test/inventory/idempotency/",
        method="POST",
        request_id=f"req-{token}",
    )
    return company, branch, user, request


def _warehouse(*, company: OrgUnit, branch: OrgUnit, code: str) -> Warehouse:
    return Warehouse.objects.create(company=company, branch=branch, name=f"Warehouse {code}", code=code)


def _item(*, company: OrgUnit) -> InventoryItem:
    token = uuid.uuid4().hex[:8]
    return InventoryItem.objects.create(company=company, sku=f"SKU-{token}", name=f"Item {token}")


@pytest.mark.django_db
def test_inventory_receive_rejects_idempotency_payload_mismatch():
    company, branch, user, request = _build_scope()
    warehouse = _warehouse(company=company, branch=branch, code="MAIN")
    item = _item(company=company)

    key = f"recv-{uuid.uuid4().hex}"
    first = post_receive(
        request=request,
        actor=user,
        warehouse_id=warehouse.id,
        item_id=item.id,
        qty=Decimal("10.0000"),
        unit_cost=Decimal("1.750000"),
        idempotency_key=key,
        source_module="FUEL",
        source_type="SALE_REVERSAL",
        source_id="sale-100",
        note="same-note",
    )
    second = post_receive(
        request=request,
        actor=user,
        warehouse_id=warehouse.id,
        item_id=item.id,
        qty=Decimal("10.0000"),
        unit_cost=Decimal("1.750000"),
        idempotency_key=key,
        source_module="FUEL",
        source_type="SALE_REVERSAL",
        source_id="sale-100",
        note="same-note",
    )

    assert second.movement_id == first.movement_id

    with pytest.raises(InventoryConflictError):
        post_receive(
            request=request,
            actor=user,
            warehouse_id=warehouse.id,
            item_id=item.id,
            qty=Decimal("11.0000"),
            unit_cost=Decimal("1.750000"),
            idempotency_key=key,
            source_module="FUEL",
            source_type="SALE_REVERSAL",
            source_id="sale-100",
            note="same-note",
        )

    assert StockMovement.objects.filter(company=company, idempotency_key=key).count() == 1
    assert (
        OutboxEvent.objects.filter(
            source_module="INVENTORY",
            event_type="InventoryMovementPosted",
            payload__data__idempotency_key=key,
        ).count()
        == 1
    )


@pytest.mark.django_db
def test_inventory_issue_rejects_idempotency_payload_mismatch():
    company, branch, user, request = _build_scope()
    warehouse = _warehouse(company=company, branch=branch, code="MAIN")
    item = _item(company=company)
    post_receive(
        request=request,
        actor=user,
        warehouse_id=warehouse.id,
        item_id=item.id,
        qty=Decimal("20.0000"),
        unit_cost=Decimal("2.000000"),
        idempotency_key=f"recv-{uuid.uuid4().hex}",
    )

    key = f"issue-{uuid.uuid4().hex}"
    first = post_issue(
        request=request,
        actor=user,
        warehouse_id=warehouse.id,
        item_id=item.id,
        qty=Decimal("5.0000"),
        allow_negative=False,
        idempotency_key=key,
        source_module="POS",
        source_type="TICKET",
        source_id="ticket-1",
    )
    second = post_issue(
        request=request,
        actor=user,
        warehouse_id=warehouse.id,
        item_id=item.id,
        qty=Decimal("5.0000"),
        allow_negative=False,
        idempotency_key=key,
        source_module="POS",
        source_type="TICKET",
        source_id="ticket-1",
    )

    assert second.movement_id == first.movement_id

    with pytest.raises(InventoryConflictError):
        post_issue(
            request=request,
            actor=user,
            warehouse_id=warehouse.id,
            item_id=item.id,
            qty=Decimal("6.0000"),
            allow_negative=False,
            idempotency_key=key,
            source_module="POS",
            source_type="TICKET",
            source_id="ticket-1",
        )

    assert StockMovement.objects.filter(company=company, idempotency_key=key).count() == 1


@pytest.mark.django_db
def test_inventory_adjust_rejects_idempotency_payload_mismatch():
    company, branch, user, request = _build_scope()
    warehouse = _warehouse(company=company, branch=branch, code="MAIN")
    item = _item(company=company)
    post_receive(
        request=request,
        actor=user,
        warehouse_id=warehouse.id,
        item_id=item.id,
        qty=Decimal("20.0000"),
        unit_cost=Decimal("2.000000"),
        idempotency_key=f"recv-{uuid.uuid4().hex}",
    )

    key = f"adjust-{uuid.uuid4().hex}"
    first = post_adjust(
        request=request,
        actor=user,
        warehouse_id=warehouse.id,
        item_id=item.id,
        new_qty_on_hand=Decimal("18.0000"),
        idempotency_key=key,
        note="cycle-count",
    )
    second = post_adjust(
        request=request,
        actor=user,
        warehouse_id=warehouse.id,
        item_id=item.id,
        new_qty_on_hand=Decimal("18.0000"),
        idempotency_key=key,
        note="cycle-count",
    )

    assert second.movement_id == first.movement_id

    with pytest.raises(InventoryConflictError):
        post_adjust(
            request=request,
            actor=user,
            warehouse_id=warehouse.id,
            item_id=item.id,
            new_qty_on_hand=Decimal("19.0000"),
            idempotency_key=key,
            note="cycle-count",
        )

    assert StockMovement.objects.filter(company=company, idempotency_key=key).count() == 1


@pytest.mark.django_db
def test_inventory_transfer_rejects_idempotency_payload_mismatch():
    company, branch, user, request = _build_scope()
    from_warehouse = _warehouse(company=company, branch=branch, code="FROM")
    to_warehouse = _warehouse(company=company, branch=branch, code="TO")
    other_warehouse = _warehouse(company=company, branch=branch, code="OTHER")
    item = _item(company=company)
    post_receive(
        request=request,
        actor=user,
        warehouse_id=from_warehouse.id,
        item_id=item.id,
        qty=Decimal("20.0000"),
        unit_cost=Decimal("2.000000"),
        idempotency_key=f"recv-{uuid.uuid4().hex}",
    )

    key = f"transfer-{uuid.uuid4().hex}"
    first = post_transfer(
        request=request,
        actor=user,
        from_warehouse_id=from_warehouse.id,
        to_warehouse_id=to_warehouse.id,
        item_id=item.id,
        qty=Decimal("5.0000"),
        idempotency_key=key,
        note="supply",
    )
    second = post_transfer(
        request=request,
        actor=user,
        from_warehouse_id=from_warehouse.id,
        to_warehouse_id=to_warehouse.id,
        item_id=item.id,
        qty=Decimal("5.0000"),
        idempotency_key=key,
        note="supply",
    )

    assert second["out_movement_id"] == first["out_movement_id"]

    with pytest.raises(InventoryConflictError):
        post_transfer(
            request=request,
            actor=user,
            from_warehouse_id=from_warehouse.id,
            to_warehouse_id=other_warehouse.id,
            item_id=item.id,
            qty=Decimal("5.0000"),
            idempotency_key=key,
            note="supply",
        )

    assert StockMovement.objects.filter(company=company, idempotency_key=key).count() == 1


@pytest.mark.django_db
def test_inventory_receive_without_idempotency_key_preserves_duplicate_behavior():
    company, branch, user, request = _build_scope()
    warehouse = _warehouse(company=company, branch=branch, code="MAIN")
    item = _item(company=company)

    first = post_receive(
        request=request,
        actor=user,
        warehouse_id=warehouse.id,
        item_id=item.id,
        qty=Decimal("3.0000"),
        unit_cost=Decimal("1.000000"),
    )
    second = post_receive(
        request=request,
        actor=user,
        warehouse_id=warehouse.id,
        item_id=item.id,
        qty=Decimal("3.0000"),
        unit_cost=Decimal("1.000000"),
    )

    assert second.movement_id != first.movement_id
    assert StockMovement.objects.filter(company=company, idempotency_key="").count() == 2
