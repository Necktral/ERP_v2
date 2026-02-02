from types import SimpleNamespace
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.iam.models import OrgUnit
from apps.sync_engine.errors import SyncRejectError
import apps.sync_engine.handlers_inventory as handlers
from modulos.inventarios.models import InventoryItem, MovementType, StockMovement, Warehouse


def _mk_scope():
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="H")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="C", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name="B", parent=company)
    return company, branch


@pytest.mark.django_db
def test_handler_helpers_and_scope_errors():
    payload = {}
    with pytest.raises(SyncRejectError):
        handlers._require_int(payload, "warehouse_id")

    with pytest.raises(SyncRejectError):
        handlers._require_int({"warehouse_id": "x"}, "warehouse_id")

    with pytest.raises(SyncRejectError):
        handlers._require_decimal({"qty": "x"}, "qty")

    assert handlers._optional_str({}, "note") == ""
    assert handlers._optional_bool({}, "flag", default=True) is True

    req = SimpleNamespace()
    with pytest.raises(SyncRejectError):
        handlers._attach_scope_to_request(request=req, company_id=9999, branch_id=None)

    company, branch = _mk_scope()
    req2 = SimpleNamespace()
    handlers._attach_scope_to_request(request=req2, company_id=company.id, branch_id=None)
    assert req2.branch is None

    with pytest.raises(SyncRejectError):
        handlers._attach_scope_to_request(request=req2, company_id=company.id, branch_id=9999)

    err = handlers._map_inventory_error(ValueError("item inválido"))
    assert err.reason_code == "INVENTORY_INVALID_SCOPE"

    err2 = handlers._map_inventory_error(ValueError("from_warehouse_id y to_warehouse_id deben ser distintos"))
    assert err2.reason_code == "INVENTORY_SCHEMA_INVALID"

    assert handlers._namespaced_idempotency_key(command_type="INVENTORY_TRANSFER", company_id=1, branch_id=None, raw_key="") == ""


@pytest.mark.django_db
def test_idempotency_matching_and_transfer_idempotent(monkeypatch):
    company, branch = _mk_scope()
    wh = Warehouse.objects.create(company=company, branch=branch, name="Main", code="M")
    item = InventoryItem.objects.create(company=company, sku="SKU", name="Item", uom="UNIT")

    movement = StockMovement.objects.create(
        company=company,
        branch=branch,
        warehouse=wh,
        item=item,
        movement_type=MovementType.RECEIVE,
        qty_delta=Decimal("1.0000"),
        unit_cost=Decimal("1.000000"),
        total_cost=Decimal("1.000000"),
        idempotency_key="idem-1",
        created_at=timezone.now(),
    )

    assert handlers._movement_matches(
        movement,
        movement_type=MovementType.RECEIVE,
        warehouse_id=wh.id,
        item_id=item.id,
        qty_delta=Decimal("1.0000"),
        unit_cost=Decimal("1.000000"),
    )

    handlers._ensure_idempotency_match(
        company_id=company.id,
        branch_id=branch.id,
        idempotency_key="idem-1",
        movement_type=MovementType.RECEIVE,
        warehouse_id=wh.id,
        item_id=item.id,
        qty_delta=Decimal("1.0000"),
        unit_cost=Decimal("1.000000"),
    )

    with pytest.raises(SyncRejectError):
        handlers._ensure_idempotency_match(
            company_id=company.id,
            branch_id=branch.id,
            idempotency_key="idem-1",
            movement_type=MovementType.RECEIVE,
            warehouse_id=wh.id,
            item_id=item.id,
            qty_delta=Decimal("2.0000"),
            unit_cost=Decimal("1.000000"),
        )

    def _fake_transfer(*_args, **_kwargs):
        return {"idempotent": True, "movement_id": 99}

    monkeypatch.setattr(handlers.inv_services, "post_transfer", _fake_transfer)

    ctx = {
        "request": SimpleNamespace(),
        "company_id": company.id,
        "branch_id": branch.id,
        "command_id": "cmd-x",
        "command_type": "INVENTORY_TRANSFER",
    }
    payload = {
        "from_warehouse_id": wh.id,
        "to_warehouse_id": wh.id + 1,
        "item_id": item.id,
        "qty": "1.0000",
    }

    res = handlers.handle_inventory_transfer(ctx, payload)
    assert res["refs"]["transfer_out_movement_id"] == 99
