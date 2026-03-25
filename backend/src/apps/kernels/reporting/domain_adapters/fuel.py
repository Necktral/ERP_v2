from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

from django.utils import timezone

from apps.kernels.reporting.exceptions import DatasetExecutionError
from apps.modulos.estacion_servicios.models import FuelDispense, FuelSale, FuelSaleStatus


def _q2(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01")))


def _q4(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.0001")))


def _resolve_date_range(filters: dict[str, Any]) -> tuple[date, date]:
    date_from = filters.get("date_from")
    date_to = filters.get("date_to")
    if date_from and not date_to:
        date_to = date_from
    if date_to and not date_from:
        date_from = date_to
    if not date_from and not date_to:
        today = timezone.localdate()
        return today, today
    return date_from, date_to


def _resolve_bounds(*, date_from: date, date_to: date):
    tz = timezone.get_current_timezone()
    start = timezone.make_aware(datetime.combine(date_from, time.min), tz)
    end = timezone.make_aware(datetime.combine(date_to, time.max), tz)
    return start, end


def _date_key(dt) -> str:
    if dt is None:
        return ""
    return timezone.localtime(dt).date().isoformat()


def _sales_by_shift_payload(*, company, branch, filters: dict[str, Any]) -> dict[str, Any]:
    date_from, date_to = _resolve_date_range(filters)
    start, end = _resolve_bounds(date_from=date_from, date_to=date_to)

    qs = (
        FuelSale.objects.select_related("shift", "dispense")
        .filter(company=company, branch=branch, created_at__gte=start, created_at__lte=end)
        .order_by("shift_id", "id")
    )
    agg: dict[int, dict[str, Any]] = {}
    for sale in qs:
        shift = sale.shift
        row = agg.setdefault(
            int(shift.id),
            {
                "shift_id": int(shift.id),
                "shift_status": str(shift.status),
                "opened_at": shift.opened_at.isoformat() if shift.opened_at else None,
                "closed_at": shift.closed_at.isoformat() if shift.closed_at else None,
                "sales_active": 0,
                "sales_cancelled": 0,
                "total_amount": Decimal("0.00"),
                "liters_sold": Decimal("0.0000"),
            },
        )
        if sale.status == FuelSaleStatus.ACTIVE:
            row["sales_active"] += 1
            row["total_amount"] += Decimal(sale.total_amount)
            row["liters_sold"] += Decimal(getattr(sale.dispense, "liters", Decimal("0.0000")))
        elif sale.status == FuelSaleStatus.CANCELLED:
            row["sales_cancelled"] += 1

    rows = []
    total_amount = Decimal("0.00")
    liters_sold = Decimal("0.0000")
    active_count = 0
    cancelled_count = 0
    for shift_id in sorted(agg.keys()):
        row = agg[shift_id]
        total_amount += row["total_amount"]
        liters_sold += row["liters_sold"]
        active_count += int(row["sales_active"])
        cancelled_count += int(row["sales_cancelled"])
        rows.append(
            {
                "shift_id": row["shift_id"],
                "shift_status": row["shift_status"],
                "opened_at": row["opened_at"],
                "closed_at": row["closed_at"],
                "sales_active": int(row["sales_active"]),
                "sales_cancelled": int(row["sales_cancelled"]),
                "total_amount": _q2(row["total_amount"]),
                "liters_sold": _q4(row["liters_sold"]),
            }
        )
    return {
        "grain": "shift",
        "dimensions": ["shift_id", "shift_status", "opened_at", "closed_at"],
        "measures": ["sales_active", "sales_cancelled", "total_amount", "liters_sold"],
        "rows": rows,
        "totals": {
            "sales_active": int(active_count),
            "sales_cancelled": int(cancelled_count),
            "total_amount": _q2(total_amount),
            "liters_sold": _q4(liters_sold),
        },
        "warnings": [],
        "source_summary": {"source_modules": ["FUEL"]},
        "effective_filters": {
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
        },
    }


def _sales_by_pump_payload(*, company, branch, filters: dict[str, Any]) -> dict[str, Any]:
    date_from, date_to = _resolve_date_range(filters)
    start, end = _resolve_bounds(date_from=date_from, date_to=date_to)
    disp_qs = FuelDispense.objects.filter(
        company=company,
        branch=branch,
        occurred_at__gte=start,
        occurred_at__lte=end,
    )
    sales_qs = (
        FuelSale.objects.select_related("dispense")
        .filter(
            company=company,
            branch=branch,
            created_at__gte=start,
            created_at__lte=end,
            status=FuelSaleStatus.ACTIVE,
        )
        .order_by("id")
    )

    agg: dict[tuple[str, str], dict[str, Any]] = defaultdict(
        lambda: {
            "pump_code": "",
            "product": "",
            "dispense_count": 0,
            "sales_count": 0,
            "liters": Decimal("0.0000"),
            "amount_total": Decimal("0.00"),
        }
    )
    for disp in disp_qs:
        key = (str(disp.pump_code or "").strip(), str(disp.product or "").strip())
        row = agg[key]
        row["pump_code"] = key[0]
        row["product"] = key[1]
        row["dispense_count"] += 1
        row["liters"] += Decimal(disp.liters)
    for sale in sales_qs:
        disp = sale.dispense
        key = (str(disp.pump_code or "").strip(), str(disp.product or "").strip())
        row = agg[key]
        row["pump_code"] = key[0]
        row["product"] = key[1]
        row["sales_count"] += 1
        row["amount_total"] += Decimal(sale.total_amount)

    rows = []
    total_dispenses = 0
    total_sales = 0
    total_liters = Decimal("0.0000")
    total_amount = Decimal("0.00")
    for key in sorted(agg.keys()):
        row = agg[key]
        total_dispenses += int(row["dispense_count"])
        total_sales += int(row["sales_count"])
        total_liters += row["liters"]
        total_amount += row["amount_total"]
        rows.append(
            {
                "pump_code": row["pump_code"],
                "product": row["product"],
                "dispense_count": int(row["dispense_count"]),
                "sales_count": int(row["sales_count"]),
                "liters": _q4(row["liters"]),
                "amount_total": _q2(row["amount_total"]),
            }
        )

    return {
        "grain": "pump_product",
        "dimensions": ["pump_code", "product"],
        "measures": ["dispense_count", "sales_count", "liters", "amount_total"],
        "rows": rows,
        "totals": {
            "dispense_count": int(total_dispenses),
            "sales_count": int(total_sales),
            "liters": _q4(total_liters),
            "amount_total": _q2(total_amount),
        },
        "warnings": [],
        "source_summary": {"source_modules": ["FUEL"]},
        "effective_filters": {
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
        },
    }


def _dispense_vs_sale_payload(*, company, branch, filters: dict[str, Any]) -> dict[str, Any]:
    date_from, date_to = _resolve_date_range(filters)
    start, end = _resolve_bounds(date_from=date_from, date_to=date_to)
    disp_qs = FuelDispense.objects.filter(
        company=company,
        branch=branch,
        occurred_at__gte=start,
        occurred_at__lte=end,
    )
    sales_qs = FuelSale.objects.filter(
        company=company,
        branch=branch,
        created_at__gte=start,
        created_at__lte=end,
    )

    days: dict[str, dict[str, Any]] = {}
    day = date_from
    while day <= date_to:
        key = day.isoformat()
        days[key] = {
            "date": key,
            "dispense_count": 0,
            "sales_count": 0,
            "liters_dispensed": Decimal("0.0000"),
            "amount_sold": Decimal("0.00"),
            "cancelled_sales": 0,
        }
        day += timedelta(days=1)

    for disp in disp_qs:
        key = _date_key(disp.occurred_at)
        row = days.get(key)
        if row is None:
            continue
        row["dispense_count"] += 1
        row["liters_dispensed"] += Decimal(disp.liters)

    for sale in sales_qs:
        key = _date_key(sale.created_at)
        row = days.get(key)
        if row is None:
            continue
        if sale.status == FuelSaleStatus.ACTIVE:
            row["sales_count"] += 1
            row["amount_sold"] += Decimal(sale.total_amount)
        elif sale.status == FuelSaleStatus.CANCELLED:
            row["cancelled_sales"] += 1

    rows = []
    totals = {
        "dispense_count": 0,
        "sales_count": 0,
        "liters_dispensed": Decimal("0.0000"),
        "amount_sold": Decimal("0.00"),
        "cancelled_sales": 0,
    }
    for key in sorted(days.keys()):
        row = days[key]
        totals["dispense_count"] += int(row["dispense_count"])
        totals["sales_count"] += int(row["sales_count"])
        totals["liters_dispensed"] += row["liters_dispensed"]
        totals["amount_sold"] += row["amount_sold"]
        totals["cancelled_sales"] += int(row["cancelled_sales"])
        rows.append(
            {
                "date": row["date"],
                "dispense_count": int(row["dispense_count"]),
                "sales_count": int(row["sales_count"]),
                "liters_dispensed": _q4(row["liters_dispensed"]),
                "amount_sold": _q2(row["amount_sold"]),
                "cancelled_sales": int(row["cancelled_sales"]),
            }
        )

    return {
        "grain": "day",
        "dimensions": ["date"],
        "measures": ["dispense_count", "sales_count", "liters_dispensed", "amount_sold", "cancelled_sales"],
        "rows": rows,
        "totals": {
            "dispense_count": int(totals["dispense_count"]),
            "sales_count": int(totals["sales_count"]),
            "liters_dispensed": _q4(totals["liters_dispensed"]),
            "amount_sold": _q2(totals["amount_sold"]),
            "cancelled_sales": int(totals["cancelled_sales"]),
        },
        "warnings": [],
        "source_summary": {"source_modules": ["FUEL"]},
        "effective_filters": {
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
        },
    }


def run_dataset(*, dataset_key: str, company, branch, filters: dict):
    if dataset_key == "fuel.sales.by_shift.daily":
        return _sales_by_shift_payload(company=company, branch=branch, filters=filters)
    if dataset_key == "fuel.sales.by_pump.daily":
        return _sales_by_pump_payload(company=company, branch=branch, filters=filters)
    if dataset_key == "fuel.dispense_vs_sale.daily":
        return _dispense_vs_sale_payload(company=company, branch=branch, filters=filters)
    raise DatasetExecutionError(f"Dataset Fuel no soportado: {dataset_key}")
