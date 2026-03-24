from __future__ import annotations

from typing import Any

from .execution import execute_dataset
from .registry import get_dataset_spec, list_dataset_specs
from .selectors import get_definition_map


def list_catalog() -> list[dict[str, Any]]:
    definitions = get_definition_map()
    rows: list[dict[str, Any]] = []
    for spec in list_dataset_specs():
        db_row = definitions.get(spec.dataset_key)
        rows.append(
            {
                "dataset_key": spec.dataset_key,
                "title": spec.title,
                "description": spec.description,
                "domain_owner": spec.domain_owner,
                "scope_level": spec.scope_level,
                "schema_version": spec.schema_version,
                "semantic_version": spec.semantic_version,
                "freshness_mode": spec.freshness_mode,
                "materialization_policy": spec.materialization_policy,
                "required_permissions": spec.required_permissions,
                "filters_schema": spec.filters_schema,
                "dimensions": spec.dimensions,
                "measures": spec.measures,
                "render_hints": spec.render_hints,
                "export_capabilities": spec.export_capabilities,
                "status": (db_row.status if db_row is not None else spec.status),
                "is_certified": (bool(db_row.is_certified) if db_row is not None else spec.is_certified),
                "is_enabled": (bool(db_row.is_enabled) if db_row is not None else spec.is_enabled),
            }
        )
    return rows


def get_catalog_entry(dataset_key: str) -> dict[str, Any]:
    key = str(dataset_key or "").strip()
    for row in list_catalog():
        if row["dataset_key"] == key:
            return row
    raise KeyError(key)


def run_dataset_from_request(
    *,
    request,
    dataset_key: str,
    filters: dict[str, Any] | None = None,
    consumer_ref: str = "",
    enforce_kernel_permission: bool = True,
) -> tuple[dict[str, Any], str]:
    _ = get_dataset_spec(dataset_key)  # fail fast con DatasetNotFoundError
    cleaned_filters = {
        key: value
        for key, value in (filters or {}).items()
        if value is not None and value != ""
    }
    envelope, run = execute_dataset(
        dataset_key=dataset_key,
        request=request,
        filters=cleaned_filters,
        consumer_type="API",
        consumer_ref=consumer_ref,
        enforce_kernel_permission=enforce_kernel_permission,
    )
    return envelope, str(run.run_id)
