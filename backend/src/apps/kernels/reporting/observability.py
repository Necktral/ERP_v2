from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from typing import Any

from django.db.models import Count, Q
from django.utils import timezone

from .enums import MaterializationPolicy, RunStatus
from .models import ReportDatasetDefinition, ReportExportLog, ReportRun
from .registry import list_dataset_specs


def _percentile(values: list[int], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    k = (len(ordered) - 1) * p
    lower = int(k)
    upper = min(lower + 1, len(ordered) - 1)
    if lower == upper:
        return float(ordered[lower])
    weight = k - lower
    return float(ordered[lower] * (1.0 - weight) + ordered[upper] * weight)


def _policy_map() -> dict[str, str]:
    from_registry = {row.dataset_key: row.materialization_policy for row in list_dataset_specs()}
    from_db = {
        str(row["dataset_key"]): str(row["materialization_policy"])
        for row in ReportDatasetDefinition.objects.values("dataset_key", "materialization_policy")
    }
    out = dict(from_registry)
    out.update(from_db)
    return out


def _policy_latency_block(values: list[int]) -> dict[str, Any]:
    return {
        "count": int(len(values)),
        "p50_ms": _percentile(values, 0.50),
        "p95_ms": _percentile(values, 0.95),
        "max_ms": max(values) if values else None,
    }


def build_reporting_observability(*, window_hours: int = 24) -> dict[str, Any]:
    hours = max(int(window_hours or 24), 1)
    since = timezone.now() - timedelta(hours=hours)
    runs = ReportRun.objects.filter(created_at__gte=since)

    total_runs = int(runs.count())
    succeeded_runs = int(runs.filter(status=RunStatus.SUCCEEDED).count())
    failed_runs = int(runs.filter(status=RunStatus.FAILED).count())
    error_rate_pct = round((failed_runs / total_runs * 100.0), 4) if total_runs else 0.0

    quality_counts = {
        "PASS": int(runs.filter(quality_status="PASS").count()),
        "WARN": int(runs.filter(quality_status="WARN").count()),
        "FAIL": int(runs.filter(quality_status="FAIL").count()),
    }

    by_policy: dict[str, list[int]] = defaultdict(list)
    near_realtime_cache: list[int] = []
    policy_map = _policy_map()

    for row in runs.filter(status=RunStatus.SUCCEEDED).exclude(duration_ms__isnull=True).values("dataset_key", "duration_ms"):
        dataset_key = str(row["dataset_key"] or "")
        duration_ms = int(row["duration_ms"] or 0)
        policy = str(policy_map.get(dataset_key) or MaterializationPolicy.LIVE_ONLY)
        by_policy[policy].append(duration_ms)
        if policy in {MaterializationPolicy.CACHE_ALLOWED, MaterializationPolicy.LIVE_ONLY}:
            near_realtime_cache.append(duration_ms)

    top_datasets = list(
        runs.values("dataset_key")
        .annotate(
            total=Count("id"),
            failed=Count("id", filter=Q(status=RunStatus.FAILED)),
            quality_fail=Count("id", filter=Q(quality_status="FAIL")),
        )
        .order_by("-total", "dataset_key")[:10]
    )

    exports = list(
        ReportExportLog.objects.filter(created_at__gte=since)
        .values("format")
        .annotate(total=Count("id"))
        .order_by("-total", "format")
    )

    legacy_accounting_runs = int(runs.filter(consumer_ref__startswith="legacy:/api/accounting/reports/").count())

    return {
        "window_hours": hours,
        "runs_total": total_runs,
        "runs_succeeded": succeeded_runs,
        "runs_failed": failed_runs,
        "error_rate_pct": error_rate_pct,
        "quality_status_counts": quality_counts,
        "latency_ms_by_policy": {
            MaterializationPolicy.SNAPSHOT_REQUIRED: _policy_latency_block(by_policy[MaterializationPolicy.SNAPSHOT_REQUIRED]),
            MaterializationPolicy.CACHE_ALLOWED: _policy_latency_block(by_policy[MaterializationPolicy.CACHE_ALLOWED]),
            MaterializationPolicy.LIVE_ONLY: _policy_latency_block(by_policy[MaterializationPolicy.LIVE_ONLY]),
            "near_realtime_cache": _policy_latency_block(near_realtime_cache),
        },
        "top_datasets": [
            {
                "dataset_key": str(row["dataset_key"]),
                "runs": int(row["total"] or 0),
                "failed_runs": int(row["failed"] or 0),
                "quality_fail_runs": int(row["quality_fail"] or 0),
            }
            for row in top_datasets
        ],
        "exports_by_format": [
            {"format": str(row["format"]), "count": int(row["total"] or 0)}
            for row in exports
        ],
        "legacy_accounting_report_runs": legacy_accounting_runs,
    }
