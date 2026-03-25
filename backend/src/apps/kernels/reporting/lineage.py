from __future__ import annotations

from typing import Any


def build_lineage(
    *,
    run_id: str,
    dataset_key: str,
    source_modules: list[str],
    semantic_version: str,
    schema_version: str,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "dataset_key": dataset_key,
        "source_modules": source_modules,
        "semantic_version": semantic_version,
        "schema_version": schema_version,
    }

