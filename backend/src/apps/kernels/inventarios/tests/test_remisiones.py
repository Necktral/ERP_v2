"""Tests de remisiones (despacho + recepción/cotejo con entrada a inventario)."""
from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model

from apps.kernels.inventarios.models import (
    InventoryItem,
    RemisionOriginType,
    RemisionStatus,
    StockBalance,
    Warehouse,
)
from apps.kernels.inventarios.remisiones import (
    RemisionError,
    attach_remision_photo,
    cancel_remision,
    create_remision,
    dispatch_remision,
    receive_remision,
)
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


def _wh(company, branch, code="DEST"):
    return Warehouse.objects.create(company=company, branch=branch, name=code, code=f"{code}{uuid.uuid4().hex[:4]}")


def _item(company, name="Item"):
    return InventoryItem.objects.create(company=company, sku=f"SKU-{uuid.uuid4().hex[:6]}", name=name)


def _qty(company, branch, wh, item) -> Decimal:
    bal = StockBalance.objects.filter(company=company, branch=branch, warehouse=wh, item=item).first()
    return bal.qty_on_hand if bal else Decimal("0.0000")


def _mk_remision(company, branch, user, request, dest_wh, item, qty="10"):
    return create_remision(
        request=request,
        actor=user,
        origin_type=RemisionOriginType.PURCHASE,
        dest_warehouse_id=dest_wh.id,
        source_module="BILLING",
        source_type="INVOICE",
        source_id="123",
        lines=[{"item_id": item.id, "qty_dispatched": qty, "unit_cost": "2.5"}],
    )


@pytest.mark.django_db
def test_create_remision_draft_with_lines():
    company, branch, user, request = _scope()
    dest = _wh(company, branch)
    item = _item(company)
    rem = _mk_remision(company, branch, user, request, dest, item)
    assert rem.status == RemisionStatus.DRAFT
    assert rem.lines.count() == 1
    assert rem.source_module == "BILLING"


@pytest.mark.django_db
def test_full_flow_dispatch_photo_receive_posts_inventory():
    company, branch, user, request = _scope()
    dest = _wh(company, branch)
    item = _item(company)
    rem = _mk_remision(company, branch, user, request, dest, item, qty="10")

    dispatch_remision(request=request, actor=user, remision=rem)
    rem.refresh_from_db()
    assert rem.status == RemisionStatus.DISPATCHED

    photo = attach_remision_photo(
        request=request, actor=user, remision=rem, storage_ref="s3://bucket/photo1.jpg", caption="Carga en camión"
    )
    assert photo.pk is not None
    assert rem.photos.count() == 1

    line = rem.lines.first()
    receive_remision(request=request, actor=user, remision=rem,
                     received_lines=[{"line_id": line.id, "qty_received": "10"}])
    rem.refresh_from_db()
    assert rem.status == RemisionStatus.RECEIVED
    assert rem.has_discrepancy is False
    # Los artículos entraron a inventario en la bodega destino.
    assert _qty(company, branch, dest, item) == Decimal("10.0000")
    line.refresh_from_db()
    assert line.received_movement_id is not None

    ev = OutboxEvent.objects.filter(source_module="INVENTORY", event_type="RemisionReceived").first()
    assert ev is not None


@pytest.mark.django_db
def test_receive_with_discrepancy_flags_and_posts_physical():
    company, branch, user, request = _scope()
    dest = _wh(company, branch)
    item = _item(company)
    rem = _mk_remision(company, branch, user, request, dest, item, qty="10")
    dispatch_remision(request=request, actor=user, remision=rem)

    line = rem.lines.first()
    # Llegaron físicamente 8 de 10 -> discrepancia; entra lo físico (8).
    receive_remision(request=request, actor=user, remision=rem,
                     received_lines=[{"line_id": line.id, "qty_received": "8"}])
    rem.refresh_from_db()
    assert rem.has_discrepancy is True
    assert _qty(company, branch, dest, item) == Decimal("8.0000")
    line.refresh_from_db()
    assert line.discrepancy == Decimal("-2.0000")


@pytest.mark.django_db
def test_cannot_receive_before_dispatch():
    company, branch, user, request = _scope()
    dest = _wh(company, branch)
    item = _item(company)
    rem = _mk_remision(company, branch, user, request, dest, item)
    line = rem.lines.first()
    with pytest.raises(RemisionError):
        receive_remision(request=request, actor=user, remision=rem,
                         received_lines=[{"line_id": line.id, "qty_received": "10"}])


@pytest.mark.django_db
def test_cancel_from_draft():
    company, branch, user, request = _scope()
    dest = _wh(company, branch)
    item = _item(company)
    rem = _mk_remision(company, branch, user, request, dest, item)
    cancel_remision(request=request, actor=user, remision=rem, reason="duplicada")
    rem.refresh_from_db()
    assert rem.status == RemisionStatus.CANCELLED


@pytest.mark.django_db
def test_create_remision_is_idempotent():
    company, branch, user, request = _scope()
    dest = _wh(company, branch)
    item = _item(company)
    key = f"rem-{uuid.uuid4().hex}"
    r1 = create_remision(
        request=request, actor=user, origin_type=RemisionOriginType.INTERNAL_TRANSFER,
        dest_warehouse_id=dest.id, idempotency_key=key,
        lines=[{"item_id": item.id, "qty_dispatched": "5", "unit_cost": "1"}],
    )
    r2 = create_remision(
        request=request, actor=user, origin_type=RemisionOriginType.INTERNAL_TRANSFER,
        dest_warehouse_id=dest.id, idempotency_key=key,
        lines=[{"item_id": item.id, "qty_dispatched": "5", "unit_cost": "1"}],
    )
    assert r1.id == r2.id
