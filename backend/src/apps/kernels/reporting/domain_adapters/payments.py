from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Any

from apps.kernels.payments.models import CashSession, PaymentIntent
from apps.kernels.reporting.exceptions import DatasetExecutionError

from .utils import q2, resolve_bounds, resolve_date_range


def _collection_payload(*, company, branch, filters: dict[str, Any]) -> dict[str, Any]:
    date_from, date_to = resolve_date_range(filters)
    start, end = resolve_bounds(date_from=date_from, date_to=date_to)

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
                "amount": q2(row["amount"]),
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
        "measures": ["payment_count", "amount", "cash_sessions_total", "cash_sessions_closed"],
        "rows": rows,
        "totals": {
            "payment_count": total_count,
            "amount": q2(total_amount),
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
