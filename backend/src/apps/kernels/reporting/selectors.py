from __future__ import annotations

from django.db.models import Q

from .models import ReportDatasetDefinition, ReportExportLog, ReportRun, ReportSnapshot, SavedReportView


def get_definition_map() -> dict[str, ReportDatasetDefinition]:
    return {row.dataset_key: row for row in ReportDatasetDefinition.objects.all()}


def list_runs_for_scope(*, company, branch=None):
    qs = ReportRun.objects.select_related("requested_by", "company", "branch").filter(company=company)
    if branch is not None:
        qs = qs.filter(branch=branch)
    return qs.order_by("-created_at", "-id")


def list_exports_for_scope(*, company, branch=None):
    qs = (
        ReportExportLog.objects.select_related(
            "run",
            "run__company",
            "run__branch",
            "requested_by",
        )
        .filter(run__company=company)
        .order_by("-created_at", "-id")
    )
    if branch is not None:
        qs = qs.filter(run__branch=branch)
    return qs


def list_snapshots_for_scope(*, company, branch=None):
    qs = ReportSnapshot.objects.filter(company=company).order_by("-created_at", "-id")
    if branch is not None:
        qs = qs.filter(branch=branch)
    return qs


def list_saved_views_for_scope(*, company, branch=None, user=None):
    qs = SavedReportView.objects.filter(company=company, is_active=True)
    if branch is not None:
        qs = qs.filter(branch=branch)
    if user is not None and getattr(user, "is_authenticated", False):
        qs = qs.filter(Q(requested_by=user) | Q(is_shared=True))
    else:
        qs = qs.filter(is_shared=True)
    return qs.order_by("-updated_at", "-id")


def get_saved_view_for_scope(*, view_id, company, branch=None, user=None):
    qs = SavedReportView.objects.filter(view_id=view_id, company=company, is_active=True)
    if branch is not None:
        qs = qs.filter(branch=branch)
    if user is not None and getattr(user, "is_authenticated", False):
        qs = qs.filter(Q(requested_by=user) | Q(is_shared=True))
    else:
        qs = qs.filter(is_shared=True)
    return qs.first()


def get_run_for_scope(*, run_id, company, branch=None):
    qs = ReportRun.objects.select_related("requested_by", "company", "branch").filter(run_id=run_id)
    if company is not None:
        qs = qs.filter(company=company)
    if branch is not None:
        qs = qs.filter(branch=branch)
    return qs.first()


def get_export_for_scope(*, export_id, company, branch=None):
    qs = ReportExportLog.objects.select_related("run", "run__company", "run__branch").filter(export_id=export_id)
    if company is not None:
        qs = qs.filter(run__company=company)
    if branch is not None:
        qs = qs.filter(run__branch=branch)
    return qs.first()
