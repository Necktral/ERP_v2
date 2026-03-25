from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from django.utils import timezone

from .enums import FreshnessMode, MaterializationPolicy, SnapshotStatus
from .models import ReportSnapshot


@dataclass(frozen=True)
class MaterializationResolution:
    strategy: str
    scope_fingerprint: str
    filters_fingerprint: str
    snapshot: ReportSnapshot | None
    should_persist_snapshot: bool


def _stable_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _build_scope_fingerprint(*, company_id: int | None, branch_id: int | None, scope_level: str) -> str:
    return _stable_hash(
        {
            "company_id": int(company_id) if company_id is not None else None,
            "branch_id": int(branch_id) if branch_id is not None else None,
            "scope_level": str(scope_level),
        }
    )


def _build_filters_fingerprint(*, filters: dict[str, Any]) -> str:
    return _stable_hash({"filters": filters})


def _resolve_fresh_until(*, freshness_mode: str):
    now = timezone.now()
    if freshness_mode == FreshnessMode.CACHE_ALLOWED:
        return now + timedelta(minutes=15)
    if freshness_mode == FreshnessMode.SNAPSHOT_REQUIRED:
        return now + timedelta(hours=24)
    return now


def resolve_materialization(
    *,
    dataset_key: str,
    company_id: int | None,
    branch_id: int | None,
    scope_level: str,
    filters: dict[str, Any],
    schema_version: str,
    semantic_version: str,
    freshness_mode: str,
    materialization_policy: str,
    force_refresh: bool = False,
) -> MaterializationResolution:
    scope_fingerprint = _build_scope_fingerprint(
        company_id=company_id,
        branch_id=branch_id,
        scope_level=scope_level,
    )
    filters_fingerprint = _build_filters_fingerprint(filters=filters)

    if materialization_policy == MaterializationPolicy.LIVE_ONLY or freshness_mode == FreshnessMode.LIVE_ONLY:
        return MaterializationResolution(
            strategy="LIVE_EXECUTION",
            scope_fingerprint=scope_fingerprint,
            filters_fingerprint=filters_fingerprint,
            snapshot=None,
            should_persist_snapshot=False,
        )

    qs = ReportSnapshot.objects.filter(
        dataset_key=dataset_key,
        scope_fingerprint=scope_fingerprint,
        filters_fingerprint=filters_fingerprint,
        schema_version=schema_version,
        semantic_version=semantic_version,
        status=SnapshotStatus.ACTIVE,
    ).order_by("-updated_at", "-id")
    snapshot = qs.first()
    now = timezone.now()

    if snapshot is not None and not force_refresh and snapshot.fresh_until >= now:
        return MaterializationResolution(
            strategy="SNAPSHOT_HIT",
            scope_fingerprint=scope_fingerprint,
            filters_fingerprint=filters_fingerprint,
            snapshot=snapshot,
            should_persist_snapshot=False,
        )

    if snapshot is not None and snapshot.fresh_until < now and snapshot.status == SnapshotStatus.ACTIVE:
        snapshot.status = SnapshotStatus.EXPIRED
        snapshot.save(update_fields=["status", "updated_at"])

    strategy = "SNAPSHOT_REBUILD" if materialization_policy == MaterializationPolicy.SNAPSHOT_REQUIRED else "CACHE_REFRESH"
    return MaterializationResolution(
        strategy=strategy,
        scope_fingerprint=scope_fingerprint,
        filters_fingerprint=filters_fingerprint,
        snapshot=None,
        should_persist_snapshot=True,
    )


def persist_snapshot(
    *,
    dataset_key: str,
    company,
    branch,
    scope_fingerprint: str,
    filters_fingerprint: str,
    schema_version: str,
    semantic_version: str,
    freshness_mode: str,
    envelope: dict[str, Any],
) -> ReportSnapshot:
    payload_hash = _stable_hash(envelope)
    defaults = {
        "company": company,
        "branch": branch,
        "snapshot_date": timezone.localdate(),
        "fresh_until": _resolve_fresh_until(freshness_mode=freshness_mode),
        "status": SnapshotStatus.ACTIVE,
        "payload_json": envelope,
        "payload_hash": payload_hash,
        "row_count": len(list(envelope.get("rows") or [])),
    }
    snapshot, _ = ReportSnapshot.objects.update_or_create(
        dataset_key=dataset_key,
        scope_fingerprint=scope_fingerprint,
        filters_fingerprint=filters_fingerprint,
        schema_version=schema_version,
        semantic_version=semantic_version,
        defaults=defaults,
    )
    return snapshot


def envelope_from_snapshot(snapshot: ReportSnapshot) -> dict[str, Any]:
    return dict(snapshot.payload_json or {})
