from __future__ import annotations

import pytest

from apps.kernels.facturacion.models import BillingDocument, DocStatus
from apps.kernels.inventarios.models import InventoryItem, StockMovement, Warehouse
from apps.modulos.audit.models import AuditEvent
from apps.modulos.estacion_servicios.models import FuelDispense, FuelPaymentMethod, FuelSale
from apps.modulos.iam.models import OrgUnit
from apps.modulos.integration.models import OutboxEvent
from tests.helpers.operational_auth import create_operational_api_actor as _client_with_perms


def _mk_org():
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="H")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="C", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name="B", parent=company)
    return company, branch


@pytest.mark.django_db
def test_fuel_sale_creates_billing_and_inventory_and_reverses_on_cancel():
    company, branch = _mk_org()
    client, _ = _client_with_perms(
        company=company,
        branch=branch,
        email_prefix="fuel",
        perm_codes=[
            "fuel.shift.open",
            "fuel.dispense.create",
            "fuel.sale.create",
            "fuel.sale.void",
            "inventory.balance.read",
        ],
    )

    r = client.post("/api/fuel/shifts/open/", {"note": "turno"}, format="json")
    assert r.status_code == 201
    shift_id = r.data["id"]

    r = client.post(
        "/api/fuel/dispenses/",
        {
            "shift_id": shift_id,
            "product": "DIESEL",
            "liters": "10.0000",
            "unit_price": "42.5000",
        },
        format="json",
    )
    assert r.status_code == 201
    dispense_id = r.data["id"]

    r = client.post(
        "/api/fuel/sales/",
        {
            "shift_id": shift_id,
            "dispense_id": dispense_id,
            "sale_type": "PUBLIC",
            "payment_method": "CASH",
            "customer_name": "Cliente",
        },
        format="json",
    )
    assert r.status_code == 201
    sale_id = r.data["id"]
    flow_correlation_id = str(r.data.get("flow_correlation_id") or "")
    assert r.data.get("billing_doc_id")
    assert r.data.get("inventory_movement_id")
    assert flow_correlation_id
    assert r.data["compensation_pending"] is False
    assert r.data["compensation_attempts"] == 0

    dispense = FuelDispense.objects.get(id=dispense_id)

    doc = BillingDocument.objects.get(id=int(r.data["billing_doc_id"]))
    assert doc.status == DocStatus.ISSUED
    assert doc.series == "FUEL"
    assert doc.total == dispense.amount_canonical
    assert doc.source_module == "FUEL"
    assert doc.source_type == "SALE"
    assert doc.source_id == str(sale_id)
    assert doc.payment_method == FuelPaymentMethod.CASH

    mov = StockMovement.objects.get(id=int(r.data["inventory_movement_id"]))
    assert mov.source_module == "FUEL"
    assert mov.source_type == "SALE"
    assert mov.source_id == str(sale_id)
    assert mov.qty_delta == (dispense.liters * -1)

    issued_ev = (
        OutboxEvent.objects.filter(source_module="BILLING", event_type="DocumentIssued")
        .order_by("-id")
        .first()
    )
    inv_ev = (
        OutboxEvent.objects.filter(source_module="INVENTORY", event_type="InventoryMovementPosted")
        .order_by("-id")
        .first()
    )
    assert issued_ev is not None
    assert inv_ev is not None
    assert str(issued_ev.correlation_id or "") == flow_correlation_id
    assert str(inv_ev.correlation_id or "") == flow_correlation_id

    wh = Warehouse.objects.get(company=company, branch=branch, code="FUEL")
    item = InventoryItem.objects.get(company=company, sku="FUEL-DIESEL")

    r = client.get(f"/api/inventory/balances/?warehouse_id={wh.id}&item_id={item.id}")
    assert r.status_code == 200
    assert r.data["qty_on_hand"] == str(mov.qty_delta)

    r = client.post(f"/api/fuel/sales/{sale_id}/cancel/", {"reason": "test"}, format="json")
    assert r.status_code == 200
    assert r.data["status"] == "CANCELLED"
    assert r.data.get("inventory_reversal_movement_id")
    assert r.data["compensation_pending"] is False
    assert r.data["compensation_attempts"] >= 1

    doc.refresh_from_db()
    assert doc.status == DocStatus.VOIDED

    r = client.get(f"/api/inventory/balances/?warehouse_id={wh.id}&item_id={item.id}")
    assert r.status_code == 200
    assert r.data["qty_on_hand"] == "0.0000"


@pytest.mark.django_db
@pytest.mark.parametrize(
    "payment_method",
    [FuelPaymentMethod.CASH, FuelPaymentMethod.TRANSFER, FuelPaymentMethod.CREDIT],
)
def test_fuel_sale_snapshots_payment_method_on_billing_document(payment_method: str) -> None:
    company, branch = _mk_org()
    client, _ = _client_with_perms(
        company=company,
        branch=branch,
        email_prefix="fuel",
        perm_codes=[
            "fuel.shift.open",
            "fuel.dispense.create",
            "fuel.sale.create",
        ],
    )

    shift = client.post("/api/fuel/shifts/open/", {"note": f"turno-{payment_method}"}, format="json")
    assert shift.status_code == 201

    dispense = client.post(
        "/api/fuel/dispenses/",
        {
            "shift_id": shift.data["id"],
            "product": "DIESEL",
            "liters": "3.0000",
            "unit_price": "41.0000",
        },
        format="json",
    )
    assert dispense.status_code == 201

    sale = client.post(
        "/api/fuel/sales/",
        {
            "shift_id": shift.data["id"],
            "dispense_id": dispense.data["id"],
            "sale_type": "PUBLIC",
            "payment_method": payment_method,
            "customer_name": "Cliente",
        },
        format="json",
    )
    assert sale.status_code == 201

    doc = BillingDocument.objects.get(id=int(sale.data["billing_doc_id"]))
    assert doc.payment_method == payment_method


@pytest.mark.django_db
def test_fuel_sale_create_is_idempotent_with_external_key_after_shift_closed():
    company, branch = _mk_org()
    client, _ = _client_with_perms(
        company=company,
        branch=branch,
        email_prefix="fuel",
        perm_codes=[
            "fuel.shift.open",
            "fuel.shift.close",
            "fuel.dispense.create",
            "fuel.sale.create",
        ],
    )

    r = client.post("/api/fuel/shifts/open/", {"note": "turno"}, format="json")
    assert r.status_code == 201
    shift_id = r.data["id"]

    r = client.post(
        "/api/fuel/dispenses/",
        {
            "shift_id": shift_id,
            "product": "DIESEL",
            "liters": "10.0000",
            "unit_price": "42.5000",
        },
        format="json",
    )
    assert r.status_code == 201
    dispense_id = r.data["id"]

    payload = {
        "shift_id": shift_id,
        "dispense_id": dispense_id,
        "sale_type": "PUBLIC",
        "payment_method": "CASH",
        "customer_name": "Cliente",
        "idempotency_key": "fuel-sale-api-1",
    }

    first = client.post("/api/fuel/sales/", payload, format="json")
    assert first.status_code == 201
    sale_id = int(first.data["id"])
    billing_doc_id = int(first.data["billing_doc_id"])
    inventory_movement_id = int(first.data["inventory_movement_id"])

    close = client.post(f"/api/fuel/shifts/{shift_id}/close/", {"note": "cierre"}, format="json")
    assert close.status_code == 200

    replay = client.post("/api/fuel/sales/", payload, format="json")
    assert replay.status_code == 200
    assert int(replay.data["id"]) == sale_id
    assert int(replay.data["billing_doc_id"]) == billing_doc_id
    assert int(replay.data["inventory_movement_id"]) == inventory_movement_id

    assert FuelSale.objects.filter(company=company, idempotency_key="fuel-sale-api-1").count() == 1
    assert (
        StockMovement.objects.filter(source_module="FUEL", source_type="SALE", source_id=str(sale_id)).count()
        == 1
    )
    assert (
        BillingDocument.objects.filter(source_module="FUEL", source_type="SALE", source_id=str(sale_id)).count()
        == 1
    )
    assert (
        OutboxEvent.objects.filter(
            source_module="FUEL",
            event_type="FuelSaleCreated",
            payload__data__sale_id=sale_id,
        ).count()
        == 1
    )
    assert (
        AuditEvent.objects.filter(module="FUEL", event_type="FUEL_SALE_CREATED", subject_id=str(sale_id)).count()
        == 1
    )


@pytest.mark.django_db
def test_fuel_sale_create_rejects_idempotency_payload_mismatch():
    company, branch = _mk_org()
    client, _ = _client_with_perms(
        company=company,
        branch=branch,
        email_prefix="fuel",
        perm_codes=[
            "fuel.shift.open",
            "fuel.dispense.create",
            "fuel.sale.create",
        ],
    )

    r = client.post("/api/fuel/shifts/open/", {"note": "turno"}, format="json")
    assert r.status_code == 201
    shift_id = r.data["id"]

    dispense_ids: list[int] = []
    for ext in ("D-1", "D-2"):
        r = client.post(
            "/api/fuel/dispenses/",
            {
                "shift_id": shift_id,
                "product": "DIESEL",
                "liters": "10.0000",
                "unit_price": "42.5000",
                "external_ref": ext,
            },
            format="json",
        )
        assert r.status_code == 201
        dispense_ids.append(int(r.data["id"]))

    payload = {
        "shift_id": shift_id,
        "dispense_id": dispense_ids[0],
        "sale_type": "PUBLIC",
        "payment_method": "CASH",
        "customer_name": "Cliente",
        "idempotency_key": "fuel-sale-api-conflict",
    }
    first = client.post("/api/fuel/sales/", payload, format="json")
    assert first.status_code == 201
    sale_id = int(first.data["id"])

    mismatch = {**payload, "dispense_id": dispense_ids[1]}
    second = client.post("/api/fuel/sales/", mismatch, format="json")
    assert second.status_code == 409
    assert "payload distinto" in str(second.data)

    assert FuelSale.objects.filter(company=company, idempotency_key="fuel-sale-api-conflict").count() == 1
    assert not FuelSale.objects.filter(dispense_id=dispense_ids[1]).exists()
    assert (
        StockMovement.objects.filter(source_module="FUEL", source_type="SALE", source_id=str(sale_id)).count()
        == 1
    )


@pytest.mark.django_db
def test_fuel_sale_without_external_idempotency_preserves_duplicate_dispense_validation():
    company, branch = _mk_org()
    client, _ = _client_with_perms(
        company=company,
        branch=branch,
        email_prefix="fuel",
        perm_codes=[
            "fuel.shift.open",
            "fuel.dispense.create",
            "fuel.sale.create",
        ],
    )

    r = client.post("/api/fuel/shifts/open/", {"note": "turno"}, format="json")
    assert r.status_code == 201
    shift_id = r.data["id"]

    r = client.post(
        "/api/fuel/dispenses/",
        {
            "shift_id": shift_id,
            "product": "DIESEL",
            "liters": "10.0000",
            "unit_price": "42.5000",
        },
        format="json",
    )
    assert r.status_code == 201
    dispense_id = r.data["id"]

    payload = {
        "shift_id": shift_id,
        "dispense_id": dispense_id,
        "sale_type": "PUBLIC",
        "payment_method": "CASH",
        "customer_name": "Cliente",
    }

    first = client.post("/api/fuel/sales/", payload, format="json")
    assert first.status_code == 201

    second = client.post("/api/fuel/sales/", payload, format="json")
    assert second.status_code == 422
    assert FuelSale.objects.filter(company=company, idempotency_key="").count() == 1
