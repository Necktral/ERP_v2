from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Any

from django.db.models import Count, Sum

from apps.kernels.facturacion.models import BillingDocument
from apps.kernels.reporting.exceptions import DatasetExecutionError

from .utils import q2, resolve_bounds, resolve_date_range


def _billing_summary_payload(*, company, branch, filters: dict[str, Any]) -> dict[str, Any]:
    date_from, date_to = resolve_date_range(filters)
    start, end = resolve_bounds(date_from=date_from, date_to=date_to)

    qs = BillingDocument.objects.filter(
        company=company,
        branch=branch,
        created_at__gte=start,
        created_at__lte=end,
    )

    agg: dict[tuple[str, str], dict[str, Any]] = defaultdict(dict)
    grouped = (
        qs.values("doc_type", "status")
        .annotate(
            doc_count=Count("id"),
            subtotal_sum=Sum("subtotal"),
            tax_total_sum=Sum("tax_total"),
            total_sum=Sum("total"),
        )
        .order_by("doc_type", "status")
    )
    for row in grouped:
        key = (str(row.get("doc_type") or ""), str(row.get("status") or ""))
        agg[key] = {
            "doc_type": key[0],
            "status": key[1],
            "doc_count": int(row.get("doc_count") or 0),
            "subtotal": Decimal(row.get("subtotal_sum") or Decimal("0.00")),
            "tax_total": Decimal(row.get("tax_total_sum") or Decimal("0.00")),
            "total": Decimal(row.get("total_sum") or Decimal("0.00")),
        }

    rows: list[dict[str, Any]] = []
    grand_doc_count = 0
    grand_subtotal = Decimal("0.00")
    grand_tax_total = Decimal("0.00")
    grand_total = Decimal("0.00")

    for key in sorted(agg.keys()):
        row = agg[key]
        grand_doc_count += int(row["doc_count"])
        grand_subtotal += row["subtotal"]
        grand_tax_total += row["tax_total"]
        grand_total += row["total"]
        rows.append(
            {
                "doc_type": row["doc_type"],
                "status": row["status"],
                "doc_count": int(row["doc_count"]),
                "subtotal": q2(row["subtotal"]),
                "tax_total": q2(row["tax_total"]),
                "total": q2(row["total"]),
            }
        )

    return {
        "grain": "doc_type_status",
        "dimensions": ["doc_type", "status"],
        "measures": ["doc_count", "subtotal", "tax_total", "total"],
        "rows": rows,
        "totals": {
            "doc_count": grand_doc_count,
            "subtotal": q2(grand_subtotal),
            "tax_total": q2(grand_tax_total),
            "total": q2(grand_total),
        },
        "warnings": [],
        "source_summary": {"source_modules": ["BILLING"]},
        "effective_filters": {
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
        },
    }


def run_dataset(*, dataset_key: str, company, branch, filters: dict) -> dict[str, Any]:
    if dataset_key == "billing.summary.period":
        return _billing_summary_payload(company=company, branch=branch, filters=filters)
    raise DatasetExecutionError(f"Dataset Billing no soportado: {dataset_key}")
