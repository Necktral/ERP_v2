"""Tests de tanques (Ola G): nivel sube con recepción, baja con despacho, ajustes,
tope de capacidad, y el hook de descuento desde record_dispense."""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from rest_framework.exceptions import ValidationError

from apps.modulos.estacion_servicios.models import (
    FuelProduct,
    FuelShift,
    FuelShiftStatus,
    FuelTank,
    FuelTankMovement,
)
from apps.modulos.estacion_servicios.services import record_dispense
from apps.modulos.estacion_servicios.tank_service import (
    adjust_tank,
    apply_dispense_to_tank,
    create_tank,
    receive_fuel,
)
from apps.modulos.iam.models import OrgUnit

User = get_user_model()
UT = OrgUnit.UnitType


def _mk_org():
    s = uuid.uuid4().hex[:6]
    holding = OrgUnit.objects.create(unit_type=UT.HOLDING, name=f"H_{s}")
    company = OrgUnit.objects.create(unit_type=UT.COMPANY, name=f"C_{s}", parent=holding)
    branch = OrgUnit.objects.create(unit_type=UT.BRANCH, name=f"B_{s}", parent=company)
    return company, branch


def _mk_user():
    u = f"fuel_{uuid.uuid4().hex[:8]}"
    return User.objects.create_user(username=u, email=f"{u}@t.local", password="pass12345")


def _tank(company, branch, actor, product=FuelProduct.DIESEL, capacity="5000"):
    return create_tank(
        company=company, branch=branch, actor=actor, code=f"T{uuid.uuid4().hex[:4]}",
        product=product, capacity_l=Decimal(capacity),
    )


@pytest.mark.django_db
def test_receive_raises_level():
    company, branch = _mk_org()
    actor = _mk_user()
    tank = _tank(company, branch, actor)
    receive_fuel(company=company, actor=actor, tank_id=tank.id, liters=Decimal("1000"), supplier_name="Pipa S.A.")
    tank.refresh_from_db()
    assert tank.current_volume_l == Decimal("1000.0000")
    assert tank.movements.filter(kind=FuelTankMovement.Kind.RECEIPT).count() == 1


@pytest.mark.django_db
def test_receive_over_capacity_rejected():
    company, branch = _mk_org()
    actor = _mk_user()
    tank = _tank(company, branch, actor, capacity="1000")
    with pytest.raises(ValidationError):
        receive_fuel(company=company, actor=actor, tank_id=tank.id, liters=Decimal("1200"))


@pytest.mark.django_db
def test_adjust_changes_level():
    company, branch = _mk_org()
    actor = _mk_user()
    tank = _tank(company, branch, actor)
    receive_fuel(company=company, actor=actor, tank_id=tank.id, liters=Decimal("500"))
    adjust_tank(company=company, actor=actor, tank_id=tank.id, liters=Decimal("-30"), reason="Derrame")
    tank.refresh_from_db()
    assert tank.current_volume_l == Decimal("470.0000")


@pytest.mark.django_db
def test_apply_dispense_discounts_active_tank():
    company, branch = _mk_org()
    actor = _mk_user()
    tank = _tank(company, branch, actor, product=FuelProduct.DIESEL)
    receive_fuel(company=company, actor=actor, tank_id=tank.id, liters=Decimal("1000"))
    mv = apply_dispense_to_tank(
        company=company, branch=branch, product=FuelProduct.DIESEL, liters=Decimal("120"), dispense=None, actor=actor
    )
    tank.refresh_from_db()
    assert mv is not None
    assert tank.current_volume_l == Decimal("880.0000")


@pytest.mark.django_db
def test_apply_dispense_no_tank_is_noop():
    company, branch = _mk_org()
    actor = _mk_user()
    # Sin tanque del producto → no hace nada (no rompe el flujo de despacho).
    mv = apply_dispense_to_tank(
        company=company, branch=branch, product=FuelProduct.GASOLINE, liters=Decimal("50"), dispense=None, actor=actor
    )
    assert mv is None


@pytest.mark.django_db
def test_record_dispense_discounts_tank_end_to_end():
    company, branch = _mk_org()
    actor = _mk_user()
    tank = _tank(company, branch, actor, product=FuelProduct.DIESEL)
    receive_fuel(company=company, actor=actor, tank_id=tank.id, liters=Decimal("1000"))
    shift = FuelShift.objects.create(company=company, branch=branch, status=FuelShiftStatus.OPEN, opened_by=actor)

    record_dispense(
        company=company, branch=branch, shift=shift, actor_user=actor,
        product=FuelProduct.DIESEL, volume_entered=Decimal("50"), volume_uom="LITER",
        unit_price_entered=Decimal("1.00"), unit_price_uom="PER_LITER",
    )
    tank.refresh_from_db()
    assert tank.current_volume_l == Decimal("950.0000")
    assert tank.movements.filter(kind=FuelTankMovement.Kind.DISPENSE).count() == 1


@pytest.mark.django_db
def test_one_active_tank_per_product_per_branch():
    company, branch = _mk_org()
    actor = _mk_user()
    _tank(company, branch, actor, product=FuelProduct.DIESEL)
    # Segundo tanque activo DIESEL en la misma sucursal viola la unicidad.
    from django.db.utils import IntegrityError

    with pytest.raises(IntegrityError):
        FuelTank.objects.create(
            company=company, branch=branch, code="DUP", product=FuelProduct.DIESEL, is_active=True
        )
