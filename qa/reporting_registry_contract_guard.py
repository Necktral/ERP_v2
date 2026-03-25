#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate reporting registry contract and adapter coverage.")
    parser.add_argument("--root", default=".", help="Repository root")
    return parser.parse_args()


def _load_registry(root: Path):
    backend_src = root / "backend" / "src"
    sys.path.insert(0, str(backend_src))
    from apps.kernels.reporting.registry import DATASET_REGISTRY  # noqa: PLC0415

    return list(DATASET_REGISTRY)


def _scan_adapter_dataset_keys(root: Path) -> dict[str, set[str]]:
    adapters_dir = root / "backend" / "src" / "apps" / "kernels" / "reporting" / "domain_adapters"
    pattern = re.compile(r'dataset_key\s*==\s*["\']([^"\']+)["\']')
    result: dict[str, set[str]] = {}
    for path in sorted(adapters_dir.glob("*.py")):
        if path.name == "__init__.py":
            continue
        content = path.read_text(encoding="utf-8")
        result[path.stem] = set(pattern.findall(content))
    return result


def main() -> int:
    args = _parse_args()
    root = Path(args.root).resolve()
    issues: list[str] = []

    specs = _load_registry(root)
    keys = [str(row.dataset_key) for row in specs]
    if len(keys) != len(set(keys)):
        issues.append("DATASET_REGISTRY contains duplicate dataset_key values.")

    allowed_export_formats = {"json", "csv", "xlsx", "pdf"}
    for row in specs:
        key = str(row.dataset_key)
        if not key:
            issues.append("DatasetSpec with empty dataset_key.")
            continue

        if not isinstance(row.render_hints, dict) or not row.render_hints.get("default_chart"):
            issues.append(f"{key}: missing render_hints.default_chart")

        if not isinstance(row.drill_metadata, dict):
            issues.append(f"{key}: drill_metadata must be dict")
        else:
            if "supports_drill_down" not in row.drill_metadata:
                issues.append(f"{key}: missing drill_metadata.supports_drill_down")
            if "supports_drill_through" not in row.drill_metadata:
                issues.append(f"{key}: missing drill_metadata.supports_drill_through")

        if not isinstance(row.quality_policy, dict):
            issues.append(f"{key}: quality_policy must be dict")
        else:
            for field in ("required_totals", "required_dimensions", "allow_empty_rows"):
                if field not in row.quality_policy:
                    issues.append(f"{key}: missing quality_policy.{field}")

        export_caps = list(row.export_capabilities or [])
        if not export_caps:
            issues.append(f"{key}: export_capabilities is empty")
        for fmt in export_caps:
            if str(fmt) not in allowed_export_formats:
                issues.append(f"{key}: unsupported export format '{fmt}'")

    adapter_keys = _scan_adapter_dataset_keys(root)
    all_registry_keys = set(keys)

    adapter_declared_keys: set[str] = set()
    for adapter_name, declared_keys in adapter_keys.items():
        adapter_declared_keys |= declared_keys
        unknown = sorted(k for k in declared_keys if k not in all_registry_keys)
        for k in unknown:
            issues.append(f"adapter '{adapter_name}' references dataset_key not in registry: {k}")

    expected_runtime_keys = {
        str(row.dataset_key)
        for row in specs
        if bool(getattr(row, "is_enabled", True)) and str(getattr(row, "domain_owner", "")) in {"ACCOUNTING", "FUEL"}
    }
    missing_handlers = sorted(expected_runtime_keys - adapter_declared_keys)
    for key in missing_handlers:
        issues.append(f"enabled registry dataset has no adapter handler: {key}")

    if issues:
        print("[qa] reporting registry contract guard failed")
        for issue in issues:
            print(f"[qa] - {issue}")
        return 1

    print("[qa] reporting registry contract guard passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
