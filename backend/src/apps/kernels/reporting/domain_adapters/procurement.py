from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Any

from apps.modulos.compras.models import PurchaseDocument
from apps.kernels.reporting.exceptions import DatasetExecutionError

from .utils import q2, resolve_bounds, resolve_date_range


def _purchases_payload(*, company, branch, filters: dict[str, Any]) -> dict[str, Any]:
    date_from, date_to = resolve_date_range(filters)
    start, end = resolve_bounds(date_from=date_from, date_to=date_to)

    qs = PurchaseDocument.objects.filter(
        company=company,
        branch=branch,
        created_at__gte=start,
        created_at__lte=end,
    ).order_by("doc_type", "status")

    agg: dict[tuple[str, str], dict[str, Any]] = defaultdict(
        lambda: {
            "doc_type": "",
            "status": "",
            "doc_count": 0,
            "subtotal": Decimal("0.00"),
            "tax_total": Decimal("0.00"),
            "total": Decimal("0.00"),
        }
    )

    for doc in qs:
        key = (str(doc.doc_type), str(doc.status))
        row = agg[key]
        row["doc_type"] = str(doc.doc_type)
        row["status"] = str(doc.status)
        row["doc_count"] += 1
        row["subtotal"] += Decimal(doc.subtotal)
        row["tax_total"] += Decimal(doc.tax_total)
        row["total"] += Decimal(doc.total)

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
        "source_summary": {"source_modules": ["PROCUREMENT"]},
        "effective_filters": {
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
        },
    }


def run_dataset(*, dataset_key: str, company, branch, filters: dict) -> dict[str, Any]:
    if dataset_key == "procurement.purchases.period":
        return _purchases_payload(company=company, branch=branch, filters=filters)
    raise DatasetExecutionError(f"Dataset Procurement no soportado: {dataset_key}")
