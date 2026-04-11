from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

from django.utils import timezone

from apps.modulos.compras.models import PurchaseDocument
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


def _purchases_payload(*, company, branch, filters: dict[str, Any]) -> dict[str, Any]:
    date_from, date_to = _resolve_date_range(filters)
    start, end = _resolve_bounds(date_from=date_from, date_to=date_to)

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
                "subtotal": _q2(row["subtotal"]),
                "tax_total": _q2(row["tax_total"]),
                "total": _q2(row["total"]),
            }
        )

    return {
        "grain": "doc_type_status",
        "dimensions": ["doc_type", "status"],
        "measures": ["doc_count", "subtotal", "tax_total", "total"],
        "rows": rows,
        "totals": {
            "doc_count": grand_doc_count,
            "subtotal": _q2(grand_subtotal),
            "tax_total": _q2(grand_tax_total),
            "total": _q2(grand_total),
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
