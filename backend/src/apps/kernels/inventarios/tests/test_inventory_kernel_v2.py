"""Tests para las funciones nuevas del kernel de inventarios v2:
- Múltiples UoM con factor de conversión
- Lotes (ItemLot) y balance por lote (LotBalance)
- Fechas de vencimiento
- Nuevos tipos de movimiento
- Nuevos endpoints GET (warehouses list, items list, stock summary, kardex)
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.modulos.iam.models import OrgUnit, UserMembership
from apps.modulos.rbac.models import Permission, Role, RoleAssignment, RolePermission

User = get_user_model()

ALL_INV_PERMS = [
    "inventory.warehouse.create",
    "inventory.warehouse.read",
    "inventory.item.create",
    "inventory.item.read",
    "inventory.lot.create",
    "inventory.lot.read",
    "inventory.movement.receive",
    "inventory.movement.issue",
    "inventory.movement.adjust",
    "inventory.transfer.create",
    "inventory.balance.read",
    "inventory.movement.read",
]


def _mk_scope():
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name=f"H-{uuid.uuid4().hex[:6]}")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name=f"C-{uuid.uuid4().hex[:6]}", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name=f"B-{uuid.uuid4().hex[:6]}", parent=company)
    return company, branch


def _client(company, branch, perms=None):
    username = f"u_{uuid.uuid4().hex[:10]}"
    user = User.objects.create_user(username=username, password="x")
    UserMembership.objects.create(user=user, org_unit=company, is_active=True)
    UserMembership.objects.create(user=user, org_unit=branch, is_active=True)

    if perms is None:
        perms = ALL_INV_PERMS

    role = Role.objects.create(name=f"r_{uuid.uuid4().hex[:8]}", is_active=True)
    for p in perms:
        perm, _ = Permission.objects.get_or_create(code=p, defaults={"description": p, "is_active": True})
        RolePermission.objects.get_or_create(role=role, permission=perm)
    RoleAssignment.objects.create(user=user, role=role, org_unit=company, is_active=True)
    RoleAssignment.objects.create(user=user, role=role, org_unit=branch, is_active=True)

    c = APIClient()
    login = c.post("/api/auth/login/", {"username": username, "password": "x"}, format="json")
    assert login.status_code == 200
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
    c.defaults["HTTP_X_COMPANY_ID"] = str(company.id)
    c.defaults["HTTP_X_BRANCH_ID"] = str(branch.id)
    return c


# ---------------------------------------------------------------------------
# Warehouse — list y create en el mismo endpoint
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_warehouse_list_and_create():
    company, branch = _mk_scope()
    c = _client(company, branch)

    # Crear
    r = c.post("/api/inventory/warehouses/", {"name": "Bodega General", "code": "BG", "warehouse_type": "GENERAL"}, format="json")
    assert r.status_code == 201
    assert r.data["warehouse_type"] == "GENERAL"
    _ = r.data["id"]

    # Crear agroquímicos
    r = c.post("/api/inventory/warehouses/", {"name": "Bodega Agro", "code": "BA", "warehouse_type": "AGROCHEMICAL"}, format="json")
    assert r.status_code == 201

    # Listar
    r = c.get("/api/inventory/warehouses/")
    assert r.status_code == 200
    assert r.data["count"] == 2

    # Filtrar por tipo
    r = c.get("/api/inventory/warehouses/?warehouse_type=AGROCHEMICAL")
    assert r.status_code == 200
    assert r.data["count"] == 1
    assert r.data["results"][0]["warehouse_type"] == "AGROCHEMICAL"


# ---------------------------------------------------------------------------
# Item — múltiples UoM y campos extendidos
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_item_create_with_extended_fields():
    company, branch = _mk_scope()
    c = _client(company, branch)

    r = c.post("/api/inventory/items/", {
        "sku": "DIESEL-001",
        "name": "Diesel Premium",
        "uom": "LITER",
        "purchase_uom": "GALLON",
        "purchase_uom_factor": "3.785411",
        "category": "Combustible",
        "is_controlled": False,
        "reorder_point": "500.0000",
        "min_stock_qty": "200.0000",
        "track_lots": False,
    }, format="json")
    assert r.status_code == 201
    assert r.data["uom"] == "LITER"
    assert r.data["purchase_uom"] == "GALLON"
    assert Decimal(r.data["purchase_uom_factor"]) == Decimal("3.785411")
    assert r.data["category"] == "Combustible"
    assert Decimal(r.data["reorder_point"]) == Decimal("500.0000")


@pytest.mark.django_db
def test_item_list_with_filters():
    company, branch = _mk_scope()
    c = _client(company, branch)

    c.post("/api/inventory/items/", {"sku": "AGRO-001", "name": "Herbicida X", "category": "Agroquimico", "is_controlled": True}, format="json")
    c.post("/api/inventory/items/", {"sku": "FUEL-001", "name": "Gasolina", "category": "Combustible"}, format="json")

    # Filtrar por categoría
    r = c.get("/api/inventory/items/?category=Agroquimico")
    assert r.status_code == 200
    assert r.data["count"] == 1
    assert r.data["results"][0]["sku"] == "AGRO-001"

    # Filtrar controlados
    r = c.get("/api/inventory/items/?is_controlled=true")
    assert r.status_code == 200
    assert r.data["count"] == 1

    # Búsqueda
    r = c.get("/api/inventory/items/?search=gasolina")
    assert r.status_code == 200
    assert r.data["count"] == 1


# ---------------------------------------------------------------------------
# Lotes — create, list, receive con lote
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_lot_create_and_receive():
    company, branch = _mk_scope()
    c = _client(company, branch)

    # Warehouse y item con track_lots=True
    wh = c.post("/api/inventory/warehouses/", {"name": "Bodega", "code": "B"}, format="json")
    wh_id = wh.data["id"]

    item = c.post("/api/inventory/items/", {
        "sku": "AGRO-LOT",
        "name": "Insecticida con lote",
        "track_lots": True,
        "track_expiry": True,
        "shelf_life_days": 365,
    }, format="json")
    item_id = item.data["id"]

    # Crear lote explícito
    r = c.post("/api/inventory/lots/create/", {
        "item_id": item_id,
        "lot_number": "LOT-2026-001",
        "production_date": "2026-01-15",
        "expiry_date": "2027-01-15",
        "supplier_lot_ref": "PROV-XYZ",
    }, format="json")
    assert r.status_code == 201
    assert r.data["lot_number"] == "LOT-2026-001"
    assert r.data["expiry_date"] == "2027-01-15"
    assert r.data["is_expired"] is False
    lot_id = r.data["id"]

    # Recibir contra el lote
    r = c.post("/api/inventory/movements/receive/", {
        "warehouse_id": wh_id,
        "item_id": item_id,
        "qty": "50.0000",
        "unit_cost": "25.000000",
        "lot_id": lot_id,
        "idempotency_key": f"recv-lot-{uuid.uuid4().hex}",
    }, format="json")
    assert r.status_code == 201
    assert Decimal(r.data["qty_on_hand"]) == Decimal("50.0000")

    # Balance por lote
    r = c.get(f"/api/inventory/stock/lots/?item_id={item_id}")
    assert r.status_code == 200
    assert r.data["count"] == 1
    assert r.data["results"][0]["lot_number"] == "LOT-2026-001"
    assert Decimal(r.data["results"][0]["qty_on_hand"]) == Decimal("50.0000")


@pytest.mark.django_db
def test_issue_decrements_lot_balance_and_records_lot():
    """INV-01: la salida con lote decrementa el LotBalance y registra el lote en el movimiento."""
    from apps.kernels.inventarios.models import MovementType, StockMovement

    company, branch = _mk_scope()
    c = _client(company, branch)

    wh = c.post("/api/inventory/warehouses/", {"name": "Bodega", "code": "BL"}, format="json")
    wh_id = wh.data["id"]
    item = c.post("/api/inventory/items/", {
        "sku": f"LOT-{uuid.uuid4().hex[:5]}", "name": "Con lote",
        "track_lots": True, "track_expiry": True, "shelf_life_days": 365,
    }, format="json")
    item_id = item.data["id"]
    lot = c.post("/api/inventory/lots/create/", {
        "item_id": item_id, "lot_number": "L-001",
        "production_date": "2026-01-15", "expiry_date": "2027-01-15",
    }, format="json")
    lot_id = lot.data["id"]

    c.post("/api/inventory/movements/receive/", {
        "warehouse_id": wh_id, "item_id": item_id, "qty": "50.0000", "unit_cost": "25.000000",
        "lot_id": lot_id, "idempotency_key": f"recv-{uuid.uuid4().hex}",
    }, format="json")

    r = c.post("/api/inventory/movements/issue/", {
        "warehouse_id": wh_id, "item_id": item_id, "qty": "20.0000",
        "lot_id": lot_id, "idempotency_key": f"iss-{uuid.uuid4().hex}",
    }, format="json")
    assert r.status_code == 201
    assert Decimal(r.data["qty_on_hand"]) == Decimal("30.0000")  # balance agregado

    # El balance POR LOTE bajó a 30 (antes del fix quedaba en 50).
    r = c.get(f"/api/inventory/stock/lots/?item_id={item_id}")
    assert r.status_code == 200
    assert Decimal(r.data["results"][0]["qty_on_hand"]) == Decimal("30.0000")

    # El movimiento de salida quedó ligado al lote (trazabilidad).
    mov = StockMovement.objects.filter(item_id=item_id, movement_type=MovementType.ISSUE).latest("id")
    assert mov.lot_id == lot_id


@pytest.mark.django_db
def test_issue_without_lot_picks_fefo_and_decrements():
    """INV-01: sin lote explícito, la salida elige FEFO (menor vencimiento) y lo decrementa."""
    from apps.kernels.inventarios.models import LotBalance

    company, branch = _mk_scope()
    c = _client(company, branch)
    wh = c.post("/api/inventory/warehouses/", {"name": "Bodega", "code": "BF"}, format="json")
    wh_id = wh.data["id"]
    item = c.post("/api/inventory/items/", {
        "sku": f"FEFO-{uuid.uuid4().hex[:5]}", "name": "FEFO",
        "track_lots": True, "track_expiry": True, "shelf_life_days": 365,
    }, format="json")
    item_id = item.data["id"]
    soon = c.post("/api/inventory/lots/create/", {
        "item_id": item_id, "lot_number": "SOON", "expiry_date": "2026-07-01"}, format="json")
    far = c.post("/api/inventory/lots/create/", {
        "item_id": item_id, "lot_number": "FAR", "expiry_date": "2027-07-01"}, format="json")
    for lid in (soon.data["id"], far.data["id"]):
        c.post("/api/inventory/movements/receive/", {
            "warehouse_id": wh_id, "item_id": item_id, "qty": "10.0000", "unit_cost": "5.000000",
            "lot_id": lid, "idempotency_key": f"r-{uuid.uuid4().hex}",
        }, format="json")

    # Despachar 6 SIN lot_id → debe consumir del lote que vence primero (SOON).
    r = c.post("/api/inventory/movements/issue/", {
        "warehouse_id": wh_id, "item_id": item_id, "qty": "6.0000",
        "idempotency_key": f"i-{uuid.uuid4().hex}",
    }, format="json")
    assert r.status_code == 201

    soon_bal = LotBalance.objects.get(item_id=item_id, lot__lot_number="SOON")
    far_bal = LotBalance.objects.get(item_id=item_id, lot__lot_number="FAR")
    assert soon_bal.qty_on_hand == Decimal("4.0000")   # 10 - 6
    assert far_bal.qty_on_hand == Decimal("10.0000")   # intacto


@pytest.mark.django_db
def test_negative_stock_receipt_resets_avg_cost():
    """INV-02: tras stock negativo, el ingreso reinicia el promedio (no mezcla sobre base negativa)."""
    company, branch = _mk_scope()
    c = _client(company, branch)
    wh = c.post("/api/inventory/warehouses/", {"name": "B", "code": "BN"}, format="json").data["id"]
    item = c.post("/api/inventory/items/", {"sku": f"NEG-{uuid.uuid4().hex[:5]}", "name": "Neg"}, format="json").data["id"]

    c.post("/api/inventory/movements/receive/", {
        "warehouse_id": wh, "item_id": item, "qty": "10.0000", "unit_cost": "10.000000",
        "idempotency_key": f"r1-{uuid.uuid4().hex}"}, format="json")
    # Despacho 15 con allow_negative → qty -5 (avg se mantiene en 10).
    c.post("/api/inventory/movements/issue/", {
        "warehouse_id": wh, "item_id": item, "qty": "15.0000", "allow_negative": True,
        "idempotency_key": f"i1-{uuid.uuid4().hex}"}, format="json")
    # Ingreso 20 @ 12 sobre saldo negativo → avg = 12 (no la mezcla distorsionada).
    r = c.post("/api/inventory/movements/receive/", {
        "warehouse_id": wh, "item_id": item, "qty": "20.0000", "unit_cost": "12.000000",
        "idempotency_key": f"r2-{uuid.uuid4().hex}"}, format="json")
    assert r.status_code == 201
    assert Decimal(r.data["qty_on_hand"]) == Decimal("15.0000")   # -5 + 20
    assert Decimal(r.data["avg_cost"]) == Decimal("12.000000")


@pytest.mark.django_db
def test_item_without_lots_rejects_lot_on_receive():
    company, branch = _mk_scope()
    c = _client(company, branch)

    wh = c.post("/api/inventory/warehouses/", {"name": "Bodega", "code": "B2"}, format="json")
    wh_id = wh.data["id"]

    item = c.post("/api/inventory/items/", {"sku": "NOLOT", "name": "Sin lote", "track_lots": False}, format="json")
    item_id = item.data["id"]

    # Intentar recibir con lot_number en un ítem que no trackea lotes
    r = c.post("/api/inventory/movements/receive/", {
        "warehouse_id": wh_id,
        "item_id": item_id,
        "qty": "10.0000",
        "unit_cost": "5.000000",
        "lot_number": "LOT-X",
        "idempotency_key": f"k-{uuid.uuid4().hex}",
    }, format="json")
    assert r.status_code == 400, f"data={r.data}"
    assert "lote" in str(r.data).lower(), f"data={r.data}"


@pytest.mark.django_db
def test_item_with_lots_required_lot_on_receive():
    company, branch = _mk_scope()
    c = _client(company, branch)

    wh = c.post("/api/inventory/warehouses/", {"name": "Bodega", "code": "B3"}, format="json")
    wh_id = wh.data["id"]

    item = c.post("/api/inventory/items/", {"sku": "NEEDSLOT", "name": "Necesita lote", "track_lots": True}, format="json")
    item_id = item.data["id"]

    # Recibir sin lot → error
    r = c.post("/api/inventory/movements/receive/", {
        "warehouse_id": wh_id,
        "item_id": item_id,
        "qty": "10.0000",
        "unit_cost": "5.000000",
        "idempotency_key": f"k-{uuid.uuid4().hex}",
    }, format="json")
    assert r.status_code == 400, f"data={r.data}"
    assert "lote" in str(r.data).lower(), f"data={r.data}"


# ---------------------------------------------------------------------------
# UoM factor — recepción en galones convertida a litros
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_receive_with_uom_factor_conversion():
    company, branch = _mk_scope()
    c = _client(company, branch)

    wh = c.post("/api/inventory/warehouses/", {"name": "Bodega Comb", "code": "BC"}, format="json")
    wh_id = wh.data["id"]

    item = c.post("/api/inventory/items/", {
        "sku": "GAS-UOM",
        "name": "Gasolina con UoM",
        "uom": "LITER",
        "purchase_uom": "GALLON",
        "purchase_uom_factor": "3.785411",
    }, format="json")
    item_id = item.data["id"]

    # Recibir 10 galones → debe registrar 37.8541 litros en base
    r = c.post("/api/inventory/movements/receive/", {
        "warehouse_id": wh_id,
        "item_id": item_id,
        "qty": "10.0000",          # 10 galones
        "unit_cost": "5.000000",   # costo por litro
        "movement_uom": "GALLON",
        "movement_uom_factor": "3.785411",
        "idempotency_key": f"k-uom-{uuid.uuid4().hex}",
    }, format="json")
    assert r.status_code == 201
    # qty_on_hand debe ser 10 * 3.785411 = 37.8541 litros
    qty = Decimal(r.data["qty_on_hand"])
    assert qty > Decimal("37.0000")
    assert qty < Decimal("38.0000")


# ---------------------------------------------------------------------------
# Stock summary y kardex
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_stock_summary_and_kardex():
    company, branch = _mk_scope()
    c = _client(company, branch)

    wh = c.post("/api/inventory/warehouses/", {"name": "Bodega", "code": "BK"}, format="json")
    wh_id = wh.data["id"]

    item = c.post("/api/inventory/items/", {"sku": "KARDEX-1", "name": "Producto Kardex", "reorder_point": "20.0000"}, format="json")
    item_id = item.data["id"]

    c.post("/api/inventory/movements/receive/", {"warehouse_id": wh_id, "item_id": item_id, "qty": "30.0000", "unit_cost": "10.000000", "idempotency_key": "kk1"}, format="json")
    c.post("/api/inventory/movements/issue/", {"warehouse_id": wh_id, "item_id": item_id, "qty": "5.0000", "idempotency_key": "kk2"}, format="json")

    # Stock summary
    r = c.get(f"/api/inventory/stock/?item_id={item_id}")
    assert r.status_code == 200
    assert r.data["count"] == 1
    assert Decimal(r.data["results"][0]["qty_on_hand"]) == Decimal("25.0000")

    # Stock por debajo del reorder_point es false
    r = c.get("/api/inventory/stock/?below_reorder=true")
    assert r.status_code == 200
    assert r.data["count"] == 0  # 25 > 20

    # Kardex
    r = c.get(f"/api/inventory/kardex/?item_id={item_id}")
    assert r.status_code == 200
    assert r.data["count"] == 2  # RECEIVE + ISSUE

    # Filtrar kardex por tipo
    r = c.get(f"/api/inventory/kardex/?item_id={item_id}&movement_type=ISSUE")
    assert r.status_code == 200
    assert r.data["count"] == 1
    assert r.data["results"][0]["movement_type"] == "ISSUE"


# ---------------------------------------------------------------------------
# Backward compat: /balances/ sigue funcionando
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_balances_endpoint_backward_compat():
    company, branch = _mk_scope()
    c = _client(company, branch)

    wh = c.post("/api/inventory/warehouses/", {"name": "BodegaBC", "code": "BBC"}, format="json")
    wh_id = wh.data["id"]
    item = c.post("/api/inventory/items/", {"sku": "COMPAT-1", "name": "Item Compat"}, format="json")
    item_id = item.data["id"]

    c.post("/api/inventory/movements/receive/", {"warehouse_id": wh_id, "item_id": item_id, "qty": "15.0000", "unit_cost": "1.000000", "idempotency_key": "bc1"}, format="json")

    r = c.get(f"/api/inventory/balances/?warehouse_id={wh_id}&item_id={item_id}")
    assert r.status_code == 200
    assert r.data["qty_on_hand"] == "15.0000"
    assert "avg_cost" in r.data


# ---------------------------------------------------------------------------
# Warehouse type coffee y agroquímicos
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_warehouse_types_coffee_and_agrochemical():
    company, branch = _mk_scope()
    c = _client(company, branch)

    c.post("/api/inventory/warehouses/", {"name": "Bodega Café", "code": "CAF", "warehouse_type": "COFFEE"}, format="json")
    c.post("/api/inventory/warehouses/", {"name": "Bodega Agro", "code": "AGR", "warehouse_type": "AGROCHEMICAL"}, format="json")
    c.post("/api/inventory/warehouses/", {"name": "Bodega Gen", "code": "GEN", "warehouse_type": "GENERAL"}, format="json")

    r = c.get("/api/inventory/warehouses/?warehouse_type=COFFEE")
    assert r.data["count"] == 1

    r = c.get("/api/inventory/warehouses/")
    assert r.data["count"] == 3
