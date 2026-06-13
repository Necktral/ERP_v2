"""Tanques de combustible — control básico de nivel (Ola G).

Nivel = Σ movimientos. Recepciones suman, despachos restan, ajustes corrigen.
Sin varillaje ni conciliación de mermas (alcance v1). El descuento por despacho
se engancha de forma ADITIVA en `record_dispense`: si la sucursal tiene un tanque
activo del producto, se postea un movimiento DISPENSE; si no, no pasa nada.
"""
from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.modulos.audit.writer import write_event

from .models import FuelProduct, FuelTank, FuelTankMovement

Q4 = Decimal("0.0001")


def _q4(v) -> Decimal:
    return Decimal(v).quantize(Q4)


def list_tanks(*, company, branch=None):
    qs = FuelTank.objects.filter(company=company)
    if branch is not None:
        qs = qs.filter(branch=branch)
    return list(qs.order_by("branch_id", "code"))


@transaction.atomic
def create_tank(*, request=None, company, branch, actor, code, product, capacity_l, low_level_l=Decimal("0")):
    if product not in FuelProduct.values:
        raise ValidationError({"product": "Producto inválido."})
    if not str(code or "").strip():
        raise ValidationError({"code": "El código es obligatorio."})
    tank = FuelTank(
        company=company,
        branch=branch,
        code=str(code).strip(),
        product=product,
        capacity_l=Decimal(capacity_l or 0),
        low_level_l=Decimal(low_level_l or 0),
    )
    tank.save()
    _audit(request, actor, "FUEL_TANK_CREATED", tank, {"code": tank.code, "product": product})
    return tank


@transaction.atomic
def update_tank(*, request=None, company, actor, tank_id, **fields):
    tank = FuelTank.objects.select_for_update().filter(id=tank_id, company=company).first()
    if tank is None:
        raise ValidationError({"detail": "Tanque no encontrado."})
    for f in ("capacity_l", "low_level_l", "is_active"):
        if f in fields and fields[f] is not None:
            setattr(tank, f, fields[f])
    tank.save()
    return tank


def _post_movement(*, tank, kind, liters, actor, unit_cost=None, supplier_name="", document_ref="", dispense=None, note=""):
    """Crea el movimiento y actualiza el nivel del tanque (con bloqueo)."""
    mv = FuelTankMovement.objects.create(
        tank=tank,
        kind=kind,
        liters=_q4(liters),
        unit_cost=Decimal(unit_cost) if unit_cost is not None else None,
        supplier_name=supplier_name or "",
        document_ref=document_ref or "",
        dispense=dispense,
        note=note or "",
        created_by=actor,
    )
    tank.current_volume_l = _q4(Decimal(tank.current_volume_l) + Decimal(mv.liters))
    tank.save(update_fields=["current_volume_l", "updated_at"])
    return mv


@transaction.atomic
def receive_fuel(*, request=None, company, actor, tank_id, liters, unit_cost=None, supplier_name="", document_ref="", note=""):
    tank = FuelTank.objects.select_for_update().filter(id=tank_id, company=company).first()
    if tank is None:
        raise ValidationError({"detail": "Tanque no encontrado."})
    qty = _q4(liters)
    if qty <= 0:
        raise ValidationError({"liters": "Los litros recibidos deben ser mayores a cero."})
    if tank.capacity_l and (Decimal(tank.current_volume_l) + qty) > Decimal(tank.capacity_l):
        raise ValidationError({"liters": "La recepción excede la capacidad del tanque."})
    mv = _post_movement(
        tank=tank, kind=FuelTankMovement.Kind.RECEIPT, liters=qty, actor=actor,
        unit_cost=unit_cost, supplier_name=supplier_name, document_ref=document_ref, note=note,
    )
    _audit(request, actor, "FUEL_TANK_RECEIVED", tank, {"liters": str(qty), "supplier": supplier_name})
    return mv


@transaction.atomic
def adjust_tank(*, request=None, company, actor, tank_id, liters, reason):
    tank = FuelTank.objects.select_for_update().filter(id=tank_id, company=company).first()
    if tank is None:
        raise ValidationError({"detail": "Tanque no encontrado."})
    qty = _q4(liters)
    if qty == 0:
        raise ValidationError({"liters": "El ajuste no puede ser cero."})
    if not str(reason or "").strip():
        raise ValidationError({"reason": "Indicá el motivo del ajuste."})
    mv = _post_movement(
        tank=tank, kind=FuelTankMovement.Kind.ADJUSTMENT, liters=qty, actor=actor, note=reason.strip(),
    )
    _audit(request, actor, "FUEL_TANK_ADJUSTED", tank, {"liters": str(qty), "reason": reason.strip()})
    return mv


def apply_dispense_to_tank(*, request=None, company, branch, product, liters, dispense, actor):
    """Hook ADITIVO desde record_dispense: descuenta del tanque activo del producto.

    Si la sucursal no tiene tanque activo de ese producto, no hace nada (no rompe
    el flujo de despacho existente cuando no se usa el control de tanques).
    """
    tank = (
        FuelTank.objects.select_for_update()
        .filter(company=company, branch=branch, product=product, is_active=True)
        .first()
    )
    if tank is None:
        return None
    return _post_movement(
        tank=tank, kind=FuelTankMovement.Kind.DISPENSE, liters=-_q4(liters), actor=actor,
        dispense=dispense, note="Despacho",
    )


def tank_movements(tank, *, limit=200):
    return list(tank.movements.select_related("created_by")[:limit])


def _audit(request, actor, event_type, tank, extra):
    write_event(
        request=request,
        module="FUEL",
        event_type=event_type,
        reason_code="FUEL_OK",
        actor_user=actor,
        subject_type="FUEL_TANK",
        subject_id=str(tank.id),
        metadata={"company_id": str(tank.company_id), "branch_id": str(tank.branch_id), **extra},
    )
