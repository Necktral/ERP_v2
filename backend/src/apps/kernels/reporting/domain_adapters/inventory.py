from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

from django.utils import timezone

from apps.kernels.inventarios.models import StockBalance, StockMovement
from apps.kernels.reporting.exceptions import DatasetExecutionError


def _q2(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01")))


def _q4(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.0001")))


def _q6(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.000001")))


def _coerce_filter_date(value: Any, *, field_name: str) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        try:
            return date.fromisoformat(raw)
        except ValueError as exc:
            raise DatasetExecutionError(f"{field_name} debe estar en formato YYYY-MM-DD.") from exc
    raise DatasetExecutionError(f"{field_name} inválido.")


def _resolve_date_range(filters: dict[str, Any]) -> tuple[date, date]:
    date_from = _coerce_filter_date(filters.get("date_from"), field_name="date_from")
    date_to = _coerce_filter_date(filters.get("date_to"), field_name="date_to")
    if date_from and not date_to:
        date_to = date_from
    if date_to and not date_from:
        date_from = date_to
    if not date_from and not date_to:
        today = timezone.localdate()
        return today, today
    if date_from is None or date_to is None:
        raise DatasetExecutionError("Rango de fechas inválido.")
    return date_from, date_to


def _resolve_bounds(*, date_from: date, date_to: date):
    tz = timezone.get_current_timezone()
    start = timezone.make_aware(datetime.combine(date_from, time.min), tz)
    end = timezone.make_aware(datetime.combine(date_to, time.max), tz)
    return start, end


def _stock_balance_payload(*, company, branch, filters: dict[str, Any]) -> dict[str, Any]:
    qs = (
        StockBalance.objects.select_related("warehouse", "item")
        .filter(company=company, branch=branch)
        .order_by("warehouse__code", "item__sku")
    )

    rows: list[dict[str, Any]] = []
    total_qty = Decimal("0.0000")
    total_value = Decimal("0.00")

    for bal in qs:
        qty = Decimal(bal.qty_on_hand)
        avg_cost = Decimal(bal.avg_cost)
        value = (qty * avg_cost).quantize(Decimal("0.01"))
        total_qty += qty
        total_value += value
        rows.append(
            {
                "warehouse_code": str(bal.warehouse.code),
                "warehouse_name": str(bal.warehouse.name),
                "sku": str(bal.item.sku),
                "item_name": str(bal.item.name),
                "uom": str(bal.item.uom),
                "qty_on_hand": _q4(qty),
                "avg_cost": _q6(avg_cost),
                "stock_value": _q2(value),
            }
        )

    return {
        "grain": "warehouse_item",
        "dimensions": ["warehouse_code", "warehouse_name", "sku", "item_name", "uom"],
        "measures": ["qty_on_hand", "avg_cost", "stock_value"],
        "rows": rows,
        "totals": {
            "qty_on_hand": _q4(total_qty),
            "stock_value": _q2(total_value),
        },
        "warnings": [],
        "source_summary": {"source_modules": ["INVENTORY"]},
        "effective_filters": {},
    }


def _movements_payload(*, company, branch, filters: dict[str, Any]) -> dict[str, Any]:
    date_from, date_to = _resolve_date_range(filters)
    start, end = _resolve_bounds(date_from=date_from, date_to=date_to)

    qs = (
        StockMovement.objects.select_related("warehouse", "item")
        .filter(company=company, branch=branch, created_at__gte=start, created_at__lte=end)
        .order_by("created_at", "id")
    )

    rows: list[dict[str, Any]] = []
    total_qty_delta = Decimal("0.0000")
    total_cost = Decimal("0.00")
    movement_count = 0

    for mov in qs:
        qty_delta = Decimal(mov.qty_delta)
        total_c = Decimal(mov.total_cost)
        total_qty_delta += qty_delta
        total_cost += total_c
        movement_count += 1
        rows.append(
            {
                "movement_type": str(mov.movement_type),
                "warehouse_code": str(mov.warehouse.code),
                "sku": str(mov.item.sku),
                "item_name": str(mov.item.name),
                "qty_delta": _q4(qty_delta),
                "unit_cost": _q6(Decimal(mov.unit_cost)),
                "total_cost": _q2(total_c),
                "source_module": str(mov.source_module or ""),
                "created_at": mov.created_at.isoformat() if mov.created_at else None,
            }
        )

    return {
        "grain": "movement",
        "dimensions": ["movement_type", "warehouse_code", "sku", "item_name", "source_module"],
        "measures": ["qty_delta", "unit_cost", "total_cost"],
        "rows": rows,
        "totals": {
            "movement_count": movement_count,
            "qty_delta": _q4(total_qty_delta),
            "total_cost": _q2(total_cost),
        },
        "warnings": [],
        "source_summary": {"source_modules": ["INVENTORY"]},
        "effective_filters": {
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
        },
    }


def run_dataset(*, dataset_key: str, company, branch, filters: dict) -> dict[str, Any]:
    if dataset_key == "inventory.stock_balance.current":
        return _stock_balance_payload(company=company, branch=branch, filters=filters)
    if dataset_key == "inventory.movements.period":
        return _movements_payload(company=company, branch=branch, filters=filters)
    raise DatasetExecutionError(f"Dataset Inventory no soportado: {dataset_key}")
