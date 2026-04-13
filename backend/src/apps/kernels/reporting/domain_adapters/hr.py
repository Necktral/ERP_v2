from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time
from typing import Any

from django.db.models import Q
from django.utils import timezone

from apps.modulos.hr.models import EmploymentAssignment
from apps.kernels.reporting.exceptions import DatasetExecutionError


def _headcount_payload(*, company, branch, filters: dict[str, Any]) -> dict[str, Any]:
    as_of_raw = filters.get("as_of")
    if isinstance(as_of_raw, datetime):
        as_of_dt = as_of_raw
    elif isinstance(as_of_raw, date):
        as_of_dt = datetime.combine(as_of_raw, time.max)
    elif isinstance(as_of_raw, str):
        raw = as_of_raw.strip()
        if not raw:
            as_of_dt = timezone.now()
        else:
            try:
                as_of_dt = datetime.combine(date.fromisoformat(raw), time.max)
            except ValueError as exc:
                raise DatasetExecutionError("as_of debe estar en formato YYYY-MM-DD.") from exc
    else:
        as_of_dt = timezone.now()
    if timezone.is_naive(as_of_dt):
        as_of_dt = timezone.make_aware(as_of_dt, timezone.get_current_timezone())

    assignments = EmploymentAssignment.objects.select_related("employee", "position").filter(
        employee__company=company,
        started_at__lte=as_of_dt,
    ).filter(
        Q(ended_at__isnull=True) | Q(ended_at__gt=as_of_dt)
    )
    if branch is not None:
        assignments = assignments.filter(branch=branch)

    agg: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "position_name": "",
            "position_code": "",
            "active_assignments": 0,
            "unique_employees": set(),
        }
    )

    for assign in assignments:
        pos = assign.position
        key = str(pos.name)
        row = agg[key]
        row["position_name"] = str(pos.name)
        row["position_code"] = str(pos.code or "")
        row["active_assignments"] += 1
        row["unique_employees"].add(int(assign.employee_id))

    rows: list[dict[str, Any]] = []
    total_assignments = 0
    total_unique = set()

    for key in sorted(agg.keys()):
        row = agg[key]
        emp_count = len(row["unique_employees"])
        total_assignments += int(row["active_assignments"])
        total_unique.update(row["unique_employees"])
        rows.append(
            {
                "position_name": row["position_name"],
                "position_code": row["position_code"],
                "active_assignments": int(row["active_assignments"]),
                "unique_employees": emp_count,
            }
        )

    total_active_employees = len(total_unique)

    return {
        "grain": "position",
        "dimensions": ["position_name", "position_code"],
        "measures": ["active_assignments", "unique_employees", "total_active_employees"],
        "rows": rows,
        "totals": {
            "active_assignments": total_assignments,
            "unique_employees": len(total_unique),
            "total_active_employees": total_active_employees,
        },
        "warnings": [],
        "source_summary": {"source_modules": ["HR"]},
        "effective_filters": {"as_of": as_of_dt.date().isoformat()},
    }


def run_dataset(*, dataset_key: str, company, branch, filters: dict) -> dict[str, Any]:
    if dataset_key == "hr.headcount.current":
        return _headcount_payload(company=company, branch=branch, filters=filters)
    raise DatasetExecutionError(f"Dataset HR no soportado: {dataset_key}")
