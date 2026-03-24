from __future__ import annotations

from .models import ReportDatasetDefinition, ReportRun


def get_definition_map() -> dict[str, ReportDatasetDefinition]:
    return {row.dataset_key: row for row in ReportDatasetDefinition.objects.all()}


def list_runs_for_scope(*, company, branch=None):
    qs = ReportRun.objects.select_related("requested_by", "company", "branch").filter(company=company)
    if branch is not None:
        qs = qs.filter(branch=branch)
    return qs.order_by("-created_at", "-id")

