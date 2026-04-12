"""Shared utilities for reporting domain adapters.

Centralises date coercion, range resolution, and Decimal formatting used
across all domain-specific adapters to eliminate duplication.
"""

from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

from django.utils import timezone

from apps.kernels.reporting.exceptions import DatasetExecutionError


def q2(value: Decimal) -> str:
    """Quantise a Decimal to 2 decimal places."""
    return str(value.quantize(Decimal("0.01")))


def q4(value: Decimal) -> str:
    """Quantise a Decimal to 4 decimal places."""
    return str(value.quantize(Decimal("0.0001")))


def q6(value: Decimal) -> str:
    """Quantise a Decimal to 6 decimal places."""
    return str(value.quantize(Decimal("0.000001")))


def coerce_filter_date(value: Any, *, field_name: str) -> date | None:
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


def resolve_date_range(filters: dict[str, Any]) -> tuple[date, date]:
    date_from = coerce_filter_date(filters.get("date_from"), field_name="date_from")
    date_to = coerce_filter_date(filters.get("date_to"), field_name="date_to")
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


def resolve_bounds(*, date_from: date, date_to: date):
    tz = timezone.get_current_timezone()
    start = timezone.make_aware(datetime.combine(date_from, time.min), tz)
    end = timezone.make_aware(datetime.combine(date_to, time.max), tz)
    return start, end
