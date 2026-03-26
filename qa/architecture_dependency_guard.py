#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


TRANSACCIONAL_TARGETS = {
    "kernels.accounting",
    "kernels.facturacion",
    "kernels.inventarios",
    "kernels.payments",
    "modulos.estacion_servicios",
}

REPORTING_HARD_BLOCK_PATH_MARKERS = (
    "/execution.py",
    "/services.py",
    "/contracts.py",
    "/registry.py",
    "/api/",
)


@dataclass(frozen=True)
class AppRef:
    layer: str
    app: str

    @property
    def key(self) -> str:
        return f"{self.layer}.{self.app}"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Architecture dependency guard with ratchet baseline.")
    parser.add_argument("--root", default=".", help="Repository root")
    parser.add_argument(
        "--baseline",
        default="qa/contracts/architecture_dependency_baseline.json",
        help="Baseline JSON with allowed existing cross-app dependency edges",
    )
    parser.add_argument(
        "--output",
        default="qa/reports/architecture_dependency_guard.json",
        help="Output JSON report",
    )
    parser.add_argument(
        "--write-baseline",
        action="store_true",
        help="Write baseline with current cross-app edges and exit",
    )
    return parser.parse_args()


def _is_python_source(path: Path) -> bool:
    if not path.name.endswith(".py"):
        return False
    normalized = path.as_posix()
    if "/migrations/" in normalized or "/tests/" in normalized or "__pycache__/" in normalized:
        return False
    return True


def _source_ref_from_path(path: Path) -> AppRef | None:
    marker = "backend/src/apps/"
    norm = path.as_posix()
    if marker not in norm:
        return None
    tail = norm.split(marker, 1)[1]
    parts = tail.split("/")
    if len(parts) < 3:
        return None
    layer, app = parts[0], parts[1]
    if layer not in {"kernels", "modulos"}:
        return None
    return AppRef(layer=layer, app=app)


def _target_ref_from_import(module_name: str) -> AppRef | None:
    parts = module_name.split(".")
    if len(parts) < 3:
        return None
    if parts[0] != "apps":
        return None
    layer, app = parts[1], parts[2]
    if layer not in {"kernels", "modulos"}:
        return None
    return AppRef(layer=layer, app=app)


def _import_modules(tree: ast.AST) -> list[tuple[str, int]]:
    modules: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name:
                    modules.append((alias.name, int(getattr(node, "lineno", 0) or 0)))
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                modules.append((node.module, int(getattr(node, "lineno", 0) or 0)))
    return modules


def _scan_current_edges(root: Path) -> tuple[set[str], list[dict[str, object]], list[dict[str, object]]]:
    apps_root = root / "backend" / "src" / "apps"
    edge_keys: set[str] = set()
    cross_refs: list[dict[str, object]] = []
    hard_violations: list[dict[str, object]] = []

    for path in sorted(apps_root.rglob("*.py")):
        if not _is_python_source(path):
            continue
        src = _source_ref_from_path(path)
        if src is None:
            continue
        rel = path.relative_to(root).as_posix()
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:
            hard_violations.append(
                {
                    "type": "parse_error",
                    "file": rel,
                    "line": int(exc.lineno or 0),
                    "detail": str(exc.msg or "syntax error"),
                }
            )
            continue

        for module_name, lineno in _import_modules(tree):
            dst = _target_ref_from_import(module_name)
            if dst is None:
                continue
            if src.layer == dst.layer and src.app == dst.app:
                continue

            edge_key = f"{src.key}->{dst.key}"
            edge_keys.add(edge_key)
            cross_refs.append(
                {
                    "edge": edge_key,
                    "file": rel,
                    "line": lineno,
                    "import": module_name,
                }
            )

            # Hard rule for reporting: only domain_adapters can import transaccional domains.
            if src.layer == "kernels" and src.app == "reporting" and dst.key in TRANSACCIONAL_TARGETS:
                allowed_by_adapter_path = "/domain_adapters/" in rel
                if not allowed_by_adapter_path:
                    reason = "reporting_non_adapter_transaccional_import"
                    for marker in REPORTING_HARD_BLOCK_PATH_MARKERS:
                        if marker in rel:
                            reason = "reporting_core_layer_transaccional_import"
                            break
                    hard_violations.append(
                        {
                            "type": reason,
                            "edge": edge_key,
                            "file": rel,
                            "line": lineno,
                            "import": module_name,
                        }
                    )

    return edge_keys, cross_refs, hard_violations


def _load_baseline(baseline_path: Path) -> set[str]:
    payload = json.loads(baseline_path.read_text(encoding="utf-8"))
    rows = payload.get("ratchet_edges")
    if not isinstance(rows, list):
        raise ValueError("Invalid baseline: 'ratchet_edges' must be a list")
    cleaned = {str(item).strip() for item in rows if str(item).strip()}
    return cleaned


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    args = _parse_args()
    root = Path(args.root).resolve()
    baseline_path = (root / args.baseline).resolve()
    output_path = (root / args.output).resolve()

    edge_keys, cross_refs, hard_violations = _scan_current_edges(root)
    edge_list = sorted(edge_keys)

    if args.write_baseline:
        baseline_payload = {
            "version": 1,
            "generated_at": datetime.now(tz=timezone.utc).isoformat(),
            "ratchet_edges": edge_list,
            "notes": [
                "Baseline for architecture_dependency_guard ratchet.",
                "Adding new edges requires explicit architecture PR approval.",
            ],
        }
        _write_json(baseline_path, baseline_payload)
        print(f"[qa] wrote baseline: {baseline_path}")
        return 0

    issues: list[str] = []
    if not baseline_path.exists():
        issues.append(f"baseline missing: {baseline_path}")
        baseline_edges: set[str] = set()
    else:
        try:
            baseline_edges = _load_baseline(baseline_path)
        except Exception as exc:  # noqa: BLE001
            issues.append(f"failed to read baseline: {exc}")
            baseline_edges = set()

    new_edges = sorted(edge_keys - baseline_edges)
    removed_edges = sorted(baseline_edges - edge_keys)

    status = "passed"
    if issues or hard_violations or new_edges:
        status = "failed"

    payload: dict[str, object] = {
        "status": status,
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "baseline_file": str(baseline_path.relative_to(root).as_posix()) if baseline_path.exists() else str(args.baseline),
        "cross_dependency_edges_total": len(edge_keys),
        "hard_violations": hard_violations,
        "new_edges": new_edges,
        "removed_edges": removed_edges,
        "issues": issues,
        "sample_cross_references": cross_refs[:200],
    }
    _write_json(output_path, payload)

    if status == "failed":
        print("[qa] architecture dependency guard failed")
        for issue in issues:
            print(f"[qa] - {issue}")
        for row in hard_violations[:20]:
            print(
                "[qa] - hard violation: "
                f"{row.get('file')}:{row.get('line')} {row.get('import')} ({row.get('type')})"
            )
        if new_edges:
            print("[qa] - new cross-app dependency edges detected:")
            for edge in new_edges[:50]:
                print(f"[qa]   - {edge}")
        return 1

    print("[qa] architecture dependency guard passed")
    if removed_edges:
        print(f"[qa] note: {len(removed_edges)} baseline edges no longer present (cleanup opportunity)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

