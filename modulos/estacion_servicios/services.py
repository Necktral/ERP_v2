"""Servicios del módulo Fuel (precedente).

Precedente de dominio:
- liters es canónico (para cierres/reportes).
- volume_entered/volume_uom preservan exactamente lo ingresado (trazabilidad).
- unit_price es canónico por litro (base para totales/reporting).
- unit_price_entered/unit_price_uom preservan exactamente lo pactado/capturado (no discutir después).
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from django.db import IntegrityError, transaction
from django.utils import timezone

from rest_framework.exceptions import ValidationError

from apps.audit.writer import write_event

from modulos.estacion_servicios.models import (
    FuelDispense,
    FuelSale,
    FuelSaleStatus,
    FuelShift,
    FuelShiftStatus,
    FuelPriceUOM,
    FuelVolumeUOM,
    GALLON_TO_LITER,
)


MONEY_Q = Decimal("0.01")
VOLUME_Q = Decimal("0.0001")


def _money(x: Decimal) -> Decimal:
    return x.quantize(MONEY_Q, rounding=ROUND_HALF_UP)


def _volume(x: Decimal) -> Decimal:
    return Decimal(x).quantize(VOLUME_Q, rounding=ROUND_HALF_UP)


def _to_liters(*, volume_entered: Decimal, volume_uom: str) -> Decimal:
    """Convierte el volumen ingresado a litros canónicos.

    Regla fuerte:
    - Toda persistencia/reporting usa litros (precisión 4 decimales).
    - Si la unidad no es soportada, se rechaza (evita datos inconsistentes).
    """
    v = _volume(volume_entered)
    if volume_uom == FuelVolumeUOM.LITER:
        return v
    if volume_uom == FuelVolumeUOM.GALLON:
        return _volume(v * GALLON_TO_LITER)
    raise ValidationError({"detail": "Unidad de volumen inválida."})


def _to_unit_price_per_liter(*, unit_price_entered: Decimal, unit_price_uom: str) -> Decimal:
    """Convierte el precio ingresado a precio canónico por litro.

    Regla fuerte:
    - Persistimos unit_price como "precio por litro".
    - Preservamos unit_price_entered + unit_price_uom como lo pactado/capturado.
    """
    p = _volume(unit_price_entered)
    if unit_price_uom == FuelPriceUOM.PER_LITER:
        return p
    if unit_price_uom == FuelPriceUOM.PER_GALLON:
        return _volume(p / GALLON_TO_LITER)
    if unit_price_uom == FuelPriceUOM.PER_GALLON_US:
        return _volume(p / GALLON_TO_LITER)
    raise ValidationError({"detail": "Unidad de precio inválida."})


def _require_branch(branch):
    if branch is None:
        raise ValidationError({"detail": "X-Branch-Id requerido para operación de estación."})
    return branch


@transaction.atomic
def open_shift(*, request=None, company, branch, actor_user, opened_at=None, note: str = "") -> FuelShift:
    branch = _require_branch(branch)

    try:
        shift = FuelShift.objects.create(
            company=company,
            branch=branch,
            opened_by=actor_user,
            opened_at=opened_at or timezone.now(),
            note=note or "",
            status=FuelShiftStatus.OPEN,
        )
    except IntegrityError:
        raise ValidationError({"detail": "Ya existe un turno abierto para esta sucursal."})

    write_event(
        request=request,
        module="FUEL",
        event_type="FUEL_SHIFT_OPENED",
        reason_code="FUEL_OK",
        subject_type="FUEL_SHIFT",
        subject_id=str(shift.id),
        actor_user=actor_user,
        after_snapshot={"note": shift.note, "opened_at": shift.opened_at.isoformat()},
        metadata={"company_id": str(company.id), "branch_id": str(branch.id)},
    )
    return shift


@transaction.atomic
def close_shift(*, request=None, shift: FuelShift, actor_user, closed_at=None, note: str = "") -> FuelShift:
    if shift.status != FuelShiftStatus.OPEN:
        raise ValidationError({"detail": "Shift ya está cerrado."})

    shift.status = FuelShiftStatus.CLOSED
    shift.closed_by = actor_user
    shift.closed_at = closed_at or timezone.now()
    if note:
        shift.note = (shift.note + " | " + note).strip(" |")
    shift.save(update_fields=["status", "closed_by", "closed_at", "note"])

    write_event(
        request=request,
        module="FUEL",
        event_type="FUEL_SHIFT_CLOSED",
        reason_code="SHIFT_CLOSED",
        subject_type="FUEL_SHIFT",
        subject_id=str(shift.id),
        actor_user=actor_user,
        after_snapshot={"note": note, "closed_at": shift.closed_at.isoformat()},
        metadata={"company_id": str(shift.company_id), "branch_id": str(shift.branch_id)},
    )
    return shift


@transaction.atomic
def record_dispense(
    *,
    request=None,
    company,
    branch,
    shift: FuelShift,
    actor_user,
    occurred_at=None,
    product: str,
    volume_entered: Decimal,
    volume_uom: str,
    unit_price_entered: Decimal,
    unit_price_uom: str,
    vehicle_plate: str = "",
    vehicle_ref: str = "",
    driver_name: str = "",
    pump_code: str = "",
    nozzle_code: str = "",
    meter_reading=None,
    external_ref: str = "",
    note: str = "",
) -> FuelDispense:
    branch = _require_branch(branch)

    if shift.status != FuelShiftStatus.OPEN:
        raise ValidationError({"detail": "No se puede despachar: turno cerrado."})

    # Contrato de cálculo (sin ambigüedad):
    # - volume_entered_q + volume_uom: lo que el operador capturó.
    # - liters: canónico (4 decimales) para cierres/reportes.
    # - unit_price_per_liter: canónico (4 decimales) para cierres/reportes.
    # - amount (fuerte): monto operativo (entered) = volume_entered_q * unit_price_entered_q (dinero 2dp).
    # - amount_canonical: monto canónico = liters * unit_price_per_liter (dinero 2dp).
    # - amount_delta: drift por cuantización = amount - amount_canonical.
    volume_entered_q = _volume(volume_entered)
    liters = _to_liters(volume_entered=volume_entered_q, volume_uom=volume_uom)
    gallons_equiv = _volume(Decimal(liters) / GALLON_TO_LITER)

    unit_price_entered_q = _volume(unit_price_entered)
    unit_price_per_liter = _to_unit_price_per_liter(
        unit_price_entered=unit_price_entered_q,
        unit_price_uom=unit_price_uom,
    )

    amount_entered = _money(Decimal(volume_entered_q) * Decimal(unit_price_entered_q))
    amount_canonical = _money(Decimal(liters) * Decimal(unit_price_per_liter))
    amount_delta = _money(Decimal(amount_entered) - Decimal(amount_canonical))

    d = FuelDispense.objects.create(
        company=company,
        branch=branch,
        shift=shift,
        occurred_at=occurred_at or timezone.now(),
        recorded_by=actor_user,
        product=product,
        liters=liters,
        volume_entered=volume_entered_q,
        volume_uom=volume_uom,
        unit_price=unit_price_per_liter,
        unit_price_entered=unit_price_entered_q,
        unit_price_uom=unit_price_uom,
        amount=amount_entered,
        amount_canonical=amount_canonical,
        amount_delta=amount_delta,
        vehicle_plate=vehicle_plate or "",
        vehicle_ref=vehicle_ref or "",
        driver_name=driver_name or "",
        pump_code=pump_code or "",
        nozzle_code=nozzle_code or "",
        meter_reading=meter_reading,
        external_ref=external_ref or "",
        note=note or "",
    )

    write_event(
        request=request,
        module="FUEL",
        event_type="FUEL_DISPENSE_RECORDED",
        reason_code="FUEL_OK",
        subject_type="FUEL_DISPENSE",
        subject_id=str(d.id),
        actor_user=actor_user,
        after_snapshot={
            "shift_id": shift.id,
            "amount": str(amount_entered),
            "amount_canonical": str(amount_canonical),
            "amount_delta": str(amount_delta),
            "product": product,
            "liters": str(liters),
            "gallons_equiv": str(gallons_equiv),
            "volume_entered": str(volume_entered_q),
            "volume_uom": str(volume_uom),
            "unit_price_per_liter": str(unit_price_per_liter),
            "unit_price_per_gallon": str(_volume(Decimal(unit_price_per_liter) * GALLON_TO_LITER)),
            "unit_price_entered": str(unit_price_entered_q),
            "unit_price_uom": str(unit_price_uom),
        },
        metadata={"company_id": str(company.id), "branch_id": str(branch.id)},
    )
    return d


@transaction.atomic
def create_sale(
    *,
    request=None,
    company,
    branch,
    shift: FuelShift,
    dispense: FuelDispense,
    actor_user,
    sale_type: str,
    payment_method: str,
    customer_name: str = "",
    customer_ref: str = "",
    is_fiscal: bool = False,
) -> FuelSale:
    branch = _require_branch(branch)

    if shift.status != FuelShiftStatus.OPEN:
        raise ValidationError({"detail": "No se puede facturar: turno cerrado."})

    if dispense.shift_id != shift.id:
        raise ValidationError({"detail": "Dispense no pertenece a ese turno."})

    if hasattr(dispense, "sale"):
        raise ValidationError({"detail": "Este despacho ya tiene venta asociada."})

    sale = FuelSale.objects.create(
        company=company,
        branch=branch,
        shift=shift,
        dispense=dispense,
        sale_type=sale_type,
        payment_method=payment_method,
        customer_name=customer_name or "",
        customer_ref=customer_ref or "",
        total_amount=dispense.amount,
        created_by=actor_user,
        is_fiscal=bool(is_fiscal),
    )

    write_event(
        request=request,
        module="FUEL",
        event_type="FUEL_SALE_CREATED",
        reason_code="FUEL_OK",
        subject_type="FUEL_SALE",
        subject_id=str(sale.id),
        actor_user=actor_user,
        after_snapshot={
            "dispense_id": dispense.id,
            "amount": str(sale.total_amount),
            "sale_type": sale_type,
            "payment_method": payment_method,
        },
        metadata={"company_id": str(company.id), "branch_id": str(branch.id)},
    )
    return sale


@transaction.atomic
def cancel_sale(*, request=None, sale: FuelSale, actor_user, reason: str = "") -> FuelSale:
    if sale.status != FuelSaleStatus.ACTIVE:
        raise ValidationError({"detail": "Venta ya está anulada."})

    sale.status = FuelSaleStatus.CANCELLED
    sale.cancelled_by = actor_user
    sale.cancelled_at = timezone.now()
    sale.cancel_reason = reason or ""
    sale.save(update_fields=["status", "cancelled_by", "cancelled_at", "cancel_reason"])

    write_event(
        request=request,
        module="FUEL",
        event_type="FUEL_SALE_VOIDED",
        reason_code="FUEL_OK",
        subject_type="FUEL_SALE",
        subject_id=str(sale.id),
        actor_user=actor_user,
        after_snapshot={"reason": sale.cancel_reason, "status": sale.status},
        metadata={"company_id": str(sale.company_id), "branch_id": str(sale.branch_id)},
    )
    return sale
