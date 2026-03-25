#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate versioned reporting dataset contract compatibility.")
    parser.add_argument("--root", default=".", help="Repository root")
    parser.add_argument(
        "--baseline",
        default="qa/contracts/reporting_dataset_contract_baseline.json",
        help="Path to baseline contract manifest (relative to --root when not absolute).",
    )
    parser.add_argument(
        "--output",
        default="qa/reports/reporting_contract_guard.json",
        help="Path to write guard result JSON (relative to --root when not absolute).",
    )
    parser.add_argument(
        "--write-baseline",
        action="store_true",
        help="Overwrite baseline with current registry contract and exit success.",
    )
    return parser.parse_args()


def _resolve_path(root: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return root / path


def _load_current_manifest(root: Path) -> dict[str, Any]:
    backend_src = root / "backend" / "src"
    if not backend_src.exists():
        raise RuntimeError(f"backend src not found: {backend_src}")
    sys.path.insert(0, str(backend_src))

    from apps.kernels.reporting.contract_compat import manifest_from_specs  # noqa: PLC0415
    from apps.kernels.reporting.registry import list_dataset_specs  # noqa: PLC0415

    specs = list_dataset_specs()
    return manifest_from_specs(specs)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n", encoding="utf-8")


def main() -> int:
    args = _parse_args()
    root = Path(args.root).resolve()
    baseline_path = _resolve_path(root, args.baseline)
    output_path = _resolve_path(root, args.output)

    current_manifest = _load_current_manifest(root)

    if args.write_baseline:
        _write_json(baseline_path, current_manifest)
        print(f"[qa] reporting contract baseline updated: {baseline_path}")
        return 0

    issues: list[str] = []
    if not baseline_path.exists():
        issues.append(f"baseline manifest not found: {baseline_path}")
        baseline_manifest: dict[str, Any] = {"manifest_version": 1, "datasets": []}
    else:
        try:
            baseline_manifest = json.loads(baseline_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            issues.append(f"baseline manifest JSON decode error: {exc}")
            baseline_manifest = {"manifest_version": 1, "datasets": []}

    from apps.kernels.reporting.contract_compat import compare_contract_manifests  # noqa: PLC0415

    issues.extend(compare_contract_manifests(baseline=baseline_manifest, current=current_manifest))

    result = {
        "guard": "reporting_contract_version_guard",
        "passed": len(issues) == 0,
        "issue_count": len(issues),
        "issues": issues,
        "baseline_path": str(baseline_path),
        "current_dataset_count": len(current_manifest.get("datasets", [])),
        "baseline_dataset_count": len(baseline_manifest.get("datasets", [])),
    }
    _write_json(output_path, result)

    if issues:
        print("[qa] reporting contract version guard failed")
        for issue in issues:
            print(f"[qa] - {issue}")
        print(f"[qa] report: {output_path}")
        return 1

    print("[qa] reporting contract version guard passed")
    print(f"[qa] report: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
