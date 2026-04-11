from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

from django.utils import timezone

from apps.kernels.payments.models import CashSession, PaymentIntent
from apps.kernels.reporting.exceptions import DatasetExecutionError


def _q2(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01")))


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


def _collection_payload(*, company, branch, filters: dict[str, Any]) -> dict[str, Any]:
    date_from, date_to = _resolve_date_range(filters)
    start, end = _resolve_bounds(date_from=date_from, date_to=date_to)

    pay_qs = PaymentIntent.objects.filter(
        company=company,
        created_at__gte=start,
        created_at__lte=end,
    )
    if branch is not None:
        pay_qs = pay_qs.filter(branch=branch)

    agg: dict[str, dict[str, Any]] = defaultdict(lambda: {"status": "", "count": 0, "amount": Decimal("0.00")})

    for pi in pay_qs.order_by("status"):
        key = str(pi.status)
        row = agg[key]
        row["status"] = key
        row["count"] += 1
        row["amount"] += Decimal(pi.amount)

    rows: list[dict[str, Any]] = []
    total_count = 0
    total_amount = Decimal("0.00")

    for key in sorted(agg.keys()):
        row = agg[key]
        total_count += int(row["count"])
        total_amount += row["amount"]
        rows.append(
            {
                "status": row["status"],
                "payment_count": int(row["count"]),
                "amount": _q2(row["amount"]),
            }
        )

    cash_qs = CashSession.objects.filter(
        company=company,
        opened_at__gte=start,
        opened_at__lte=end,
    )
    if branch is not None:
        cash_qs = cash_qs.filter(branch=branch)
    sessions_total = int(cash_qs.count())
    sessions_closed = int(cash_qs.filter(status=CashSession.Status.CLOSED).count())

    return {
        "grain": "payment_status",
        "dimensions": ["status"],
        "measures": ["payment_count", "amount"],
        "rows": rows,
        "totals": {
            "payment_count": total_count,
            "amount": _q2(total_amount),
            "cash_sessions_total": sessions_total,
            "cash_sessions_closed": sessions_closed,
        },
        "warnings": [],
        "source_summary": {"source_modules": ["PAYMENTS"]},
        "effective_filters": {
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
        },
    }


def run_dataset(*, dataset_key: str, company, branch, filters: dict) -> dict[str, Any]:
    if dataset_key == "payments.collection.period":
        return _collection_payload(company=company, branch=branch, filters=filters)
    raise DatasetExecutionError(f"Dataset Payments no soportado: {dataset_key}")
