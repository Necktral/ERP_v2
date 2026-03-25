#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
import re
import sys
from pathlib import Path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate reporting registry contract and adapter coverage.")
    parser.add_argument("--root", default=".", help="Repository root")
    parser.add_argument(
        "--mode",
        choices=("auto", "django", "ast"),
        default="auto",
        help="Registry loading mode: django import, AST fallback, or auto (django->ast).",
    )
    return parser.parse_args()


@dataclass(frozen=True)
class GuardSpec:
    dataset_key: str
    domain_owner: str
    is_enabled: bool
    render_hints: dict
    drill_metadata: dict
    quality_policy: dict
    export_capabilities: list


def _load_registry_django(root: Path) -> list[GuardSpec]:
    backend_src = root / "backend" / "src"
    sys.path.insert(0, str(backend_src))
    from apps.kernels.reporting.registry import DATASET_REGISTRY  # noqa: PLC0415

    out: list[GuardSpec] = []
    for row in DATASET_REGISTRY:
        out.append(
            GuardSpec(
                dataset_key=str(getattr(row, "dataset_key", "")).strip(),
                domain_owner=str(getattr(row, "domain_owner", "")),
                is_enabled=bool(getattr(row, "is_enabled", True)),
                render_hints=dict(getattr(row, "render_hints", {}) or {}),
                drill_metadata=dict(getattr(row, "drill_metadata", {}) or {}),
                quality_policy=dict(getattr(row, "quality_policy", {}) or {}),
                export_capabilities=list(getattr(row, "export_capabilities", []) or []),
            )
        )
    return out


def _find_registry_assignment(tree: ast.Module) -> ast.AST | None:
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "DATASET_REGISTRY":
                    return node.value
        if isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.target.id == "DATASET_REGISTRY":
                return node.value
    return None


def _literal(node: ast.AST) -> object:
    return ast.literal_eval(node)


def _load_registry_ast(root: Path) -> tuple[list[GuardSpec], list[str]]:
    registry_path = root / "backend" / "src" / "apps" / "kernels" / "reporting" / "registry.py"
    if not registry_path.exists():
        return [], [f"registry file not found: {registry_path}"]

    tree = ast.parse(registry_path.read_text(encoding="utf-8"), filename=str(registry_path))
    value = _find_registry_assignment(tree)
    if value is None:
        return [], ["DATASET_REGISTRY assignment not found in registry.py"]
    if not isinstance(value, (ast.Tuple, ast.List)):
        return [], ["DATASET_REGISTRY must be tuple/list literal"]

    specs: list[GuardSpec] = []
    issues: list[str] = []
    for idx, element in enumerate(value.elts):
        if not isinstance(element, ast.Call):
            issues.append(f"entry[{idx}] in DATASET_REGISTRY is not a DatasetSpec call")
            continue

        kw = {k.arg: k.value for k in element.keywords if k.arg}
        try:
            dataset_key = str(_literal(kw["dataset_key"])).strip()
            domain_owner = str(_literal(kw["domain_owner"]))
            is_enabled = bool(_literal(kw["is_enabled"])) if "is_enabled" in kw else True
            render_hints = _literal(kw["render_hints"])
            drill_metadata = _literal(kw["drill_metadata"])
            quality_policy = _literal(kw["quality_policy"])
            export_capabilities = _literal(kw["export_capabilities"])
        except KeyError as exc:
            issues.append(f"entry[{idx}] missing required keyword: {exc.args[0]}")
            continue
        except Exception as exc:  # noqa: BLE001
            issues.append(f"entry[{idx}] literal parse failed: {exc}")
            continue

        specs.append(
            GuardSpec(
                dataset_key=dataset_key,
                domain_owner=domain_owner,
                is_enabled=is_enabled,
                render_hints=render_hints if isinstance(render_hints, dict) else {},
                drill_metadata=drill_metadata if isinstance(drill_metadata, dict) else {},
                quality_policy=quality_policy if isinstance(quality_policy, dict) else {},
                export_capabilities=export_capabilities if isinstance(export_capabilities, list) else [],
            )
        )

    return specs, issues


def _load_registry(root: Path, mode: str) -> tuple[list[GuardSpec], list[str]]:
    if mode == "django":
        return _load_registry_django(root), []
    if mode == "ast":
        return _load_registry_ast(root)

    try:
        return _load_registry_django(root), []
    except Exception as exc:  # noqa: BLE001
        print(f"[qa] registry guard fallback to AST: {exc.__class__.__name__}: {exc}")
        return _load_registry_ast(root)


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

    specs, load_issues = _load_registry(root, args.mode)
    issues.extend(load_issues)

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
