from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Iterable

from .registry import DatasetSpec

_SEMVER_RE = re.compile(r"^(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)$")
_QUALITY_REQUIRED_FIELDS = ("required_totals", "required_dimensions", "allow_empty_rows")
_STRUCTURAL_FIELDS = ("filters_schema", "dimensions", "measures", "export_capabilities")


@dataclass(frozen=True)
class DatasetContractEntry:
    dataset_key: str
    schema_version: str
    semantic_version: str
    filters_schema: dict[str, Any]
    dimensions: list[str]
    measures: list[str]
    quality_policy: dict[str, Any]
    export_capabilities: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset_key": self.dataset_key,
            "schema_version": self.schema_version,
            "semantic_version": self.semantic_version,
            "filters_schema": self.filters_schema,
            "dimensions": self.dimensions,
            "measures": self.measures,
            "quality_policy": self.quality_policy,
            "export_capabilities": self.export_capabilities,
        }


def entry_from_spec(spec: DatasetSpec) -> DatasetContractEntry:
    return DatasetContractEntry(
        dataset_key=str(spec.dataset_key),
        schema_version=str(spec.schema_version),
        semantic_version=str(spec.semantic_version),
        filters_schema=dict(spec.filters_schema),
        dimensions=list(spec.dimensions),
        measures=list(spec.measures),
        quality_policy=dict(spec.quality_policy),
        export_capabilities=list(spec.export_capabilities),
    )


def manifest_from_specs(specs: Iterable[DatasetSpec]) -> dict[str, Any]:
    datasets = [entry_from_spec(spec).to_dict() for spec in specs]
    datasets.sort(key=lambda row: str(row["dataset_key"]))
    return {
        "manifest_version": 1,
        "datasets": datasets,
    }


def _parse_semver(value: Any) -> tuple[int, int, int] | None:
    raw = str(value or "").strip()
    match = _SEMVER_RE.fullmatch(raw)
    if match is None:
        return None
    return (
        int(match.group("major")),
        int(match.group("minor")),
        int(match.group("patch")),
    )


def _is_semver_gt(current: Any, baseline: Any) -> bool:
    current_semver = _parse_semver(current)
    baseline_semver = _parse_semver(baseline)
    if current_semver is None or baseline_semver is None:
        return False
    return current_semver > baseline_semver


def _is_semver_lt(current: Any, baseline: Any) -> bool:
    current_semver = _parse_semver(current)
    baseline_semver = _parse_semver(baseline)
    if current_semver is None or baseline_semver is None:
        return False
    return current_semver < baseline_semver


def _entry_completeness_issues(entry: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    key = str(entry.get("dataset_key") or "").strip()
    label = key or "<dataset_key-empty>"

    if not key:
        issues.append("dataset entry missing dataset_key")

    schema_version = entry.get("schema_version")
    semantic_version = entry.get("semantic_version")
    if _parse_semver(schema_version) is None:
        issues.append(f"{label}: schema_version must be semver (x.y.z)")
    if _parse_semver(semantic_version) is None:
        issues.append(f"{label}: semantic_version must be semver (x.y.z)")

    filters_schema = entry.get("filters_schema")
    if not isinstance(filters_schema, dict):
        issues.append(f"{label}: filters_schema must be dict")

    dimensions = entry.get("dimensions")
    if not isinstance(dimensions, list) or not all(isinstance(v, str) and v for v in dimensions):
        issues.append(f"{label}: dimensions must be non-empty string list")

    measures = entry.get("measures")
    if not isinstance(measures, list) or not all(isinstance(v, str) and v for v in measures):
        issues.append(f"{label}: measures must be non-empty string list")

    quality_policy = entry.get("quality_policy")
    if not isinstance(quality_policy, dict):
        issues.append(f"{label}: quality_policy must be dict")
    else:
        for field in _QUALITY_REQUIRED_FIELDS:
            if field not in quality_policy:
                issues.append(f"{label}: missing quality_policy.{field}")

    export_capabilities = entry.get("export_capabilities")
    if not isinstance(export_capabilities, list) or not all(isinstance(v, str) and v for v in export_capabilities):
        issues.append(f"{label}: export_capabilities must be non-empty string list")

    return issues


def _dataset_map(manifest: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], list[str]]:
    issues: list[str] = []
    datasets = manifest.get("datasets")
    if not isinstance(datasets, list):
        return {}, ["manifest.datasets must be a list"]

    out: dict[str, dict[str, Any]] = {}
    for idx, row in enumerate(datasets):
        if not isinstance(row, dict):
            issues.append(f"manifest.datasets[{idx}] must be object")
            continue
        row_issues = _entry_completeness_issues(row)
        issues.extend(row_issues)
        key = str(row.get("dataset_key") or "").strip()
        if not key:
            continue
        if key in out:
            issues.append(f"duplicate dataset_key in manifest: {key}")
            continue
        out[key] = row
    return out, issues


def compare_contract_manifests(*, baseline: dict[str, Any], current: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    baseline_map, baseline_issues = _dataset_map(baseline)
    current_map, current_issues = _dataset_map(current)
    issues.extend([f"baseline: {x}" for x in baseline_issues])
    issues.extend([f"current: {x}" for x in current_issues])

    baseline_keys = set(baseline_map.keys())
    current_keys = set(current_map.keys())

    removed = sorted(baseline_keys - current_keys)
    for key in removed:
        issues.append(f"{key}: dataset removed from registry baseline")

    added = sorted(current_keys - baseline_keys)
    for key in added:
        row_issues = _entry_completeness_issues(current_map[key])
        if row_issues:
            issues.extend([f"new dataset invalid -> {x}" for x in row_issues])

    for key in sorted(baseline_keys & current_keys):
        old = baseline_map[key]
        new = current_map[key]

        if _is_semver_lt(new.get("schema_version"), old.get("schema_version")):
            issues.append(
                f"{key}: schema_version regressed ({old.get('schema_version')} -> {new.get('schema_version')})"
            )
        if _is_semver_lt(new.get("semantic_version"), old.get("semantic_version")):
            issues.append(
                f"{key}: semantic_version regressed ({old.get('semantic_version')} -> {new.get('semantic_version')})"
            )

        structural_changed_fields = [field for field in _STRUCTURAL_FIELDS if old.get(field) != new.get(field)]
        if structural_changed_fields and not _is_semver_gt(new.get("schema_version"), old.get("schema_version")):
            issues.append(
                f"{key}: structural change in {structural_changed_fields} requires schema_version bump "
                f"({old.get('schema_version')} -> {new.get('schema_version')})"
            )

        semantic_changed = old.get("quality_policy") != new.get("quality_policy")
        if semantic_changed and not _is_semver_gt(new.get("semantic_version"), old.get("semantic_version")):
            issues.append(
                f"{key}: quality_policy change requires semantic_version bump "
                f"({old.get('semantic_version')} -> {new.get('semantic_version')})"
            )

    return issues
