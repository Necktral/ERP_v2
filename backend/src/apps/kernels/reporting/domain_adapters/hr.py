from __future__ import annotations

from collections import defaultdict
from typing import Any

from apps.modulos.hr.models import Employee, EmploymentAssignment
from apps.kernels.reporting.exceptions import DatasetExecutionError


def _headcount_payload(*, company, branch, filters: dict[str, Any]) -> dict[str, Any]:
    employees = Employee.objects.filter(company=company, is_active=True)
    assignments = EmploymentAssignment.objects.select_related("employee", "position").filter(
        employee__company=company, is_active=True
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

    total_active_employees = int(employees.count())

    return {
        "grain": "position",
        "dimensions": ["position_name", "position_code"],
        "measures": ["active_assignments", "unique_employees"],
        "rows": rows,
        "totals": {
            "active_assignments": total_assignments,
            "unique_employees": len(total_unique),
            "total_active_employees": total_active_employees,
        },
        "warnings": [],
        "source_summary": {"source_modules": ["HR"]},
        "effective_filters": {},
    }


def run_dataset(*, dataset_key: str, company, branch, filters: dict) -> dict[str, Any]:
    if dataset_key == "hr.headcount.current":
        return _headcount_payload(company=company, branch=branch, filters=filters)
    raise DatasetExecutionError(f"Dataset HR no soportado: {dataset_key}")
