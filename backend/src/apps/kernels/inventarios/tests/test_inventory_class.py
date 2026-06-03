"""Tests de las tres clases de inventario (FEFO/FIFO/AVERAGE) por producto."""
from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.kernels.inventarios.classification import (
    lot_consumption_ordering,
    resolve_inventory_class,
    set_inventory_class,
)
from apps.kernels.inventarios.models import (
    InventoryClass,
    InventoryItem,
    ItemLot,
)
from apps.modulos.iam.models import OrgUnit

User = get_user_model()


def _company():
    t = uuid.uuid4().hex[:8]
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name=f"H{t}", code=f"H-{t}")
    return OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, parent=holding, name=f"C{t}", code=f"C-{t}")


def _item(company, **kw):
    defaults = dict(sku=f"SKU-{uuid.uuid4().hex[:6]}", name="Item")
    defaults.update(kw)
    return InventoryItem.objects.create(company=company, **defaults)


# --- Resolución de clase (explícita / derivada) -----------------------------

@pytest.mark.django_db
def test_resolve_class_derives_from_flags_when_blank():
    company = _company()
    avg = _item(company)  # sin flags -> AVERAGE
    fifo = _item(company, track_lots=True)  # lotes sin vencimiento -> FIFO
    fefo = _item(company, track_lots=True, track_expiry=True)  # vencimiento -> FEFO
    assert resolve_inventory_class(avg) == InventoryClass.AVERAGE
    assert resolve_inventory_class(fifo) == InventoryClass.FIFO
    assert resolve_inventory_class(fefo) == InventoryClass.FEFO


@pytest.mark.django_db
def test_explicit_class_overrides_derivation():
    company = _company()
    item = _item(company, track_lots=True, track_expiry=True, inventory_class=InventoryClass.FEFO)
    assert resolve_inventory_class(item) == InventoryClass.FEFO


# --- Validación de coherencia -----------------------------------------------

@pytest.mark.django_db
def test_fefo_requires_lots_and_expiry():
    company = _company()
    item = InventoryItem(company=company, sku=f"S{uuid.uuid4().hex[:6]}", name="X", inventory_class=InventoryClass.FEFO)
    with pytest.raises(ValidationError):
        item.full_clean()


@pytest.mark.django_db
def test_set_inventory_class_reclassifies_and_validates():
    company = _company()
    item = _item(company, track_lots=True, track_expiry=True)
    out = set_inventory_class(item=item, inventory_class=InventoryClass.FEFO)
    assert out.inventory_class == InventoryClass.FEFO
    # Reclasificar a FIFO sobre un item con lotes es válido.
    out2 = set_inventory_class(item=item, inventory_class=InventoryClass.FIFO)
    assert out2.inventory_class == InventoryClass.FIFO
    # Clase inválida.
    with pytest.raises(ValueError):
        set_inventory_class(item=item, inventory_class="NOPE")


@pytest.mark.django_db
def test_set_class_fefo_on_non_expiry_item_is_rejected():
    company = _company()
    item = _item(company)  # sin track_lots/expiry
    with pytest.raises(ValidationError):
        set_inventory_class(item=item, inventory_class=InventoryClass.FEFO)


# --- Orden de consumo de lotes (integración) --------------------------------

@pytest.mark.django_db
def test_fefo_ordering_picks_earliest_expiry():
    company = _company()
    item = _item(company, track_lots=True, track_expiry=True, inventory_class=InventoryClass.FEFO)
    today = timezone.localdate()
    late = ItemLot.objects.create(company=company, item=item, lot_number="L2", expiry_date=today + timedelta(days=30))
    soon = ItemLot.objects.create(company=company, item=item, lot_number="L1", expiry_date=today + timedelta(days=5))
    ordering = lot_consumption_ordering(item)
    first = ItemLot.objects.filter(item=item).order_by(*ordering).first()
    assert first.id == soon.id  # el de menor vencimiento primero
    assert late.id != first.id


@pytest.mark.django_db
def test_average_ordering_is_empty():
    company = _company()
    item = _item(company)  # AVERAGE
    assert lot_consumption_ordering(item) == ()
