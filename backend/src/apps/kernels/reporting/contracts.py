from __future__ import annotations

from datetime import datetime
from typing import Any


CANONICAL_DATASET_ENVELOPE_FIELDS = (
    "dataset_key",
    "title",
    "description",
    "schema_version",
    "semantic_version",
    "generated_at",
    "freshness_mode",
    "scope",
    "filters",
    "grain",
    "dimensions",
    "measures",
    "rows",
    "totals",
    "warnings",
    "lineage",
    "render_hints",
    "export_capabilities",
)


def build_dataset_envelope(
    *,
    dataset_key: str,
    title: str,
    description: str,
    schema_version: str,
    semantic_version: str,
    freshness_mode: str,
    scope: dict[str, Any],
    filters: dict[str, Any],
    grain: str,
    dimensions: list[str],
    measures: list[str],
    rows: list[dict[str, Any]],
    totals: dict[str, Any],
    warnings: list[dict[str, Any]] | list[str] | None = None,
    lineage: dict[str, Any] | None = None,
    render_hints: dict[str, Any] | None = None,
    export_capabilities: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "dataset_key": dataset_key,
        "title": title,
        "description": description,
        "schema_version": schema_version,
        "semantic_version": semantic_version,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "freshness_mode": freshness_mode,
        "scope": scope,
        "filters": filters,
        "grain": grain,
        "dimensions": dimensions,
        "measures": measures,
        "rows": rows,
        "totals": totals,
        "warnings": warnings or [],
        "lineage": lineage or {},
        "render_hints": render_hints or {},
        "export_capabilities": export_capabilities or [],
    }

