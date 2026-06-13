"""Costos reales por activo de flota (Ola G — captura manual).

Combustible (con consumo km/L o L/h), órdenes de mantenimiento con costo y otros
gastos. El resumen agrega todo por período y calcula costo por km/hora y rendimiento.
Sin enlace automático con la estación (registro manual, por decisión del dueño).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.modulos.audit.writer import write_event

from .models import (
    FleetAsset,
    FleetExpense,
    FuelLog,
    MaintenanceType,
    MaintenanceWorkOrder,
    MeterBasis,
)
from .services import FleetError


def _q2(v) -> Decimal:
    return Decimal(str(v)).quantize(Decimal("0.01"))


def _get_asset(company, asset_id: int) -> FleetAsset:
    asset = FleetAsset.objects.filter(id=asset_id, company=company).first()
    if asset is None:
        raise FleetError("FLEET_ASSET_NOT_FOUND")
    return asset


def _audit(request, actor, event_type, asset, extra):
    write_event(
        request=request, module="FLEET", event_type=event_type, reason_code="FLEET_OK",
        actor_user=actor, subject_type="FLEET_ASSET", subject_id=str(asset.id),
        metadata={"company_id": str(asset.company_id), **extra},
    )


@transaction.atomic
def record_fuel_log(
    *, request=None, company, actor, asset_id, liters, unit_cost, meter_reading=None,
    occurred_at=None, station_ref="", driver_id=None, note="",
):
    asset = FleetAsset.objects.select_for_update().filter(id=asset_id, company=company).first()
    if asset is None:
        raise FleetError("FLEET_ASSET_NOT_FOUND")
    liters_q = _q2(liters)
    if liters_q <= 0:
        raise FleetError("FLEET_FUEL_LITERS_INVALID")
    unit_cost_d = Decimal(str(unit_cost))
    if unit_cost_d < 0:
        raise FleetError("FLEET_FUEL_COST_INVALID")
    total = _q2(liters_q * unit_cost_d)

    # Consumo desde la carga anterior según el medidor.
    distance = None
    reading = Decimal(str(meter_reading)) if meter_reading is not None else None
    if reading is not None:
        prev = (
            FuelLog.objects.filter(asset=asset, meter_reading__isnull=False)
            .order_by("-occurred_at", "-id")
            .first()
        )
        base = prev.meter_reading if prev is not None else (
            asset.current_odometer_km if asset.meter_basis == MeterBasis.ODOMETER_KM else asset.current_hourmeter
        )
        if base is not None and reading >= base:
            distance = _q2(reading - base)
        # Avanza el medidor del activo.
        if asset.meter_basis == MeterBasis.ODOMETER_KM and reading > asset.current_odometer_km:
            asset.current_odometer_km = reading
            asset.save(update_fields=["current_odometer_km", "updated_at"])
        elif asset.meter_basis != MeterBasis.ODOMETER_KM and reading > asset.current_hourmeter:
            asset.current_hourmeter = reading
            asset.save(update_fields=["current_hourmeter", "updated_at"])

    log = FuelLog.objects.create(
        company=company, asset=asset, occurred_at=occurred_at or timezone.now(),
        liters=liters_q, unit_cost=unit_cost_d, total_cost=total,
        meter_basis=asset.meter_basis, meter_reading=reading, distance_since_last=distance,
        station_ref=station_ref or "", driver_id=driver_id, note=note or "", created_by=actor,
    )
    _audit(request, actor, "FLEET_FUEL_LOG_RECORDED", asset, {"liters": str(liters_q), "total": str(total)})
    return log


@transaction.atomic
def record_work_order(
    *, request=None, company, actor, asset_id, description, labor_cost=Decimal("0"),
    parts_cost=Decimal("0"), maintenance_type_id=None, status="DONE", meter_reading=None,
    completed_at=None, vendor="", note="",
):
    asset = _get_asset(company, asset_id)
    if not str(description or "").strip():
        raise FleetError("FLEET_WO_DESCRIPTION_REQUIRED")
    if status not in MaintenanceWorkOrder.Status.values:
        raise FleetError("FLEET_WO_STATUS_INVALID")
    mtype = None
    if maintenance_type_id is not None:
        mtype = MaintenanceType.objects.filter(id=maintenance_type_id, company=company).first()
    labor = _q2(labor_cost or 0)
    parts = _q2(parts_cost or 0)
    total = _q2(labor + parts)
    completed = completed_at
    if status == MaintenanceWorkOrder.Status.DONE and completed is None:
        completed = timezone.now()
    wo = MaintenanceWorkOrder.objects.create(
        company=company, asset=asset, maintenance_type=mtype, status=status,
        description=description.strip(), labor_cost=labor, parts_cost=parts, total_cost=total,
        meter_reading=Decimal(str(meter_reading)) if meter_reading is not None else None,
        completed_at=completed, vendor=vendor or "", note=note or "", created_by=actor,
    )
    _audit(request, actor, "FLEET_MAINTENANCE_RECORDED", asset, {"total": str(total), "status": status})
    return wo


@transaction.atomic
def record_expense(*, request=None, company, actor, asset_id, category, amount, occurred_on=None, vendor="", note=""):
    asset = _get_asset(company, asset_id)
    amt = _q2(amount)
    if amt <= 0:
        raise FleetError("FLEET_EXPENSE_AMOUNT_INVALID")
    if category not in [c[0] for c in FleetExpense._meta.get_field("category").choices]:
        raise FleetError("FLEET_EXPENSE_CATEGORY_INVALID")
    exp = FleetExpense.objects.create(
        company=company, asset=asset, category=category, amount=amt,
        occurred_on=occurred_on or timezone.localdate(), vendor=vendor or "", note=note or "", created_by=actor,
    )
    _audit(request, actor, "FLEET_EXPENSE_RECORDED", asset, {"category": category, "amount": str(amt)})
    return exp


def asset_cost_summary(*, company, asset_id: int, date_from: date | None = None, date_to: date | None = None) -> dict:
    asset = _get_asset(company, asset_id)

    fuel_qs = FuelLog.objects.filter(asset=asset)
    wo_qs = MaintenanceWorkOrder.objects.filter(asset=asset).exclude(status=MaintenanceWorkOrder.Status.CANCELLED)
    exp_qs = FleetExpense.objects.filter(asset=asset)
    if date_from:
        fuel_qs = fuel_qs.filter(occurred_at__date__gte=date_from)
        wo_qs = wo_qs.filter(opened_at__date__gte=date_from)
        exp_qs = exp_qs.filter(occurred_on__gte=date_from)
    if date_to:
        fuel_qs = fuel_qs.filter(occurred_at__date__lte=date_to)
        wo_qs = wo_qs.filter(opened_at__date__lte=date_to)
        exp_qs = exp_qs.filter(occurred_on__lte=date_to)

    fuel_total = _q2(fuel_qs.aggregate(s=Sum("total_cost"))["s"] or 0)
    liters_total = _q2(fuel_qs.aggregate(s=Sum("liters"))["s"] or 0)
    distance_total = _q2(fuel_qs.aggregate(s=Sum("distance_since_last"))["s"] or 0)
    maint_total = _q2(wo_qs.aggregate(s=Sum("total_cost"))["s"] or 0)
    expense_total = _q2(exp_qs.aggregate(s=Sum("amount"))["s"] or 0)
    grand_total = _q2(fuel_total + maint_total + expense_total)

    cost_per_unit = _q2(grand_total / distance_total) if distance_total > 0 else None
    consumption = _q2(distance_total / liters_total) if liters_total > 0 else None  # km/L o h/L
    is_km = asset.meter_basis == MeterBasis.ODOMETER_KM

    return {
        "asset_id": asset.id,
        "asset_code": asset.code,
        "asset_name": asset.name,
        "meter_basis": asset.meter_basis,
        "fuel_total": str(fuel_total),
        "maintenance_total": str(maint_total),
        "expense_total": str(expense_total),
        "grand_total": str(grand_total),
        "liters_total": str(liters_total),
        "distance_total": str(distance_total),
        "cost_per_unit": str(cost_per_unit) if cost_per_unit is not None else None,
        "cost_per_unit_label": "Costo/km" if is_km else "Costo/hora",
        "consumption": str(consumption) if consumption is not None else None,
        "consumption_label": "km/L" if is_km else "h/L",
    }
