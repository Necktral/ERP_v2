#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ALLOWED_RISK_CLASSES = {
    "metadata_only",
    "online_safe",
    "backfill",
    "high_lock_risk",
    "destructive",
    "expand",
    "contract",
    "cleanup",
}

RISKY_OPS = {"RemoveField", "DeleteModel", "RemoveConstraint", "RunSQL"}

DEFAULT_BASELINE_OWNER = "db-architecture"
DEFAULT_BASELINE_TICKET = "U5-BASELINE"


@dataclass(frozen=True)
class MigrationFacts:
    relative_path: str
    fingerprint: str
    operation_names: tuple[str, ...]
    uses_add_index_concurrently: bool
    atomic_false: bool


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate migration safety contract with ratchet baseline.")
    parser.add_argument("--root", default=".", help="Repository root")
    parser.add_argument(
        "--baseline",
        default="qa/contracts/migration_safety_baseline.json",
        help="Baseline JSON path (relative to --root when not absolute).",
    )
    parser.add_argument(
        "--output",
        default="qa/reports/migration_safety_guard.json",
        help="Output report path",
    )
    parser.add_argument(
        "--write-baseline",
        action="store_true",
        help="Generate/overwrite baseline from current migrations and exit success.",
    )
    return parser.parse_args()


def _call_name(node: ast.Call) -> str | None:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _extract_atomic_false(tree: ast.AST) -> bool:
    for node in tree.body if isinstance(tree, ast.Module) else []:
        if not isinstance(node, ast.ClassDef) or node.name != "Migration":
            continue
        for stmt in node.body:
            if isinstance(stmt, ast.Assign):
                if len(stmt.targets) != 1 or not isinstance(stmt.targets[0], ast.Name):
                    continue
                if stmt.targets[0].id == "atomic" and isinstance(stmt.value, ast.Constant):
                    return stmt.value.value is False
            if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                if stmt.target.id == "atomic" and isinstance(stmt.value, ast.Constant):
                    return stmt.value.value is False
    return False


def _extract_operation_names(tree: ast.AST) -> tuple[str, ...]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = _call_name(node)
            if name:
                names.add(name)
    return tuple(sorted(names))


def _iter_migration_files(root: Path) -> list[Path]:
    files = []
    for path in sorted((root / "backend" / "src" / "apps").rglob("migrations/*.py")):
        if path.name == "__init__.py":
            continue
        files.append(path)
    return files


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _scan_migrations(root: Path) -> dict[str, MigrationFacts]:
    out: dict[str, MigrationFacts] = {}
    for path in _iter_migration_files(root):
        rel = path.relative_to(root).as_posix()
        content = path.read_text(encoding="utf-8")
        tree = ast.parse(content, filename=str(path))
        operation_names = _extract_operation_names(tree)
        facts = MigrationFacts(
            relative_path=rel,
            fingerprint=_sha256_text(content),
            operation_names=operation_names,
            uses_add_index_concurrently="AddIndexConcurrently" in operation_names,
            atomic_false=_extract_atomic_false(tree),
        )
        out[rel] = facts
    return out


def _suggest_risk_class(facts: MigrationFacts) -> str:
    ops = set(facts.operation_names)
    if "DeleteModel" in ops or "RemoveField" in ops:
        return "destructive"
    if "RunSQL" in ops or "AlterField" in ops or "RemoveConstraint" in ops:
        return "high_lock_risk"
    if facts.uses_add_index_concurrently:
        return "online_safe"
    if "AddIndex" in ops:
        return "high_lock_risk"
    if {
        "CreateModel",
        "AddField",
        "AddConstraint",
        "RenameModel",
        "RenameField",
        "RenameIndex",
        "AlterModelOptions",
    } & ops:
        return "expand"
    return "metadata_only"


def _build_baseline_payload(migrations_map: dict[str, MigrationFacts]) -> dict[str, Any]:
    migrations: dict[str, Any] = {}
    for rel, facts in sorted(migrations_map.items()):
        migrations[rel] = {
            "risk_class": _suggest_risk_class(facts),
            "rollout_strategy": "baseline_existing_migration",
            "rollback_strategy": "roll_forward_preferred",
            "owner": DEFAULT_BASELINE_OWNER,
            "ticket_ref": DEFAULT_BASELINE_TICKET,
            "fingerprint": facts.fingerprint,
        }
    return {
        "version": 1,
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "migrations": migrations,
        "notes": [
            "U5 migration safety baseline.",
            "Any migration drift/new file requires explicit metadata update in PR.",
        ],
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _validate_entry(rel: str, entry: dict[str, Any], facts: MigrationFacts, issues: list[str]) -> None:
    for field in ("risk_class", "rollout_strategy", "rollback_strategy", "owner", "ticket_ref", "fingerprint"):
        value = str(entry.get(field, "")).strip()
        if not value:
            issues.append(f"{rel}: missing required metadata field '{field}'")

    risk_class = str(entry.get("risk_class", "")).strip()
    if risk_class and risk_class not in ALLOWED_RISK_CLASSES:
        issues.append(f"{rel}: invalid risk_class '{risk_class}'")

    baseline_fp = str(entry.get("fingerprint", "")).strip()
    if baseline_fp and baseline_fp != facts.fingerprint:
        issues.append(
            f"{rel}: fingerprint mismatch (migration changed without baseline update)"
        )

    if facts.uses_add_index_concurrently and not facts.atomic_false:
        issues.append(f"{rel}: uses AddIndexConcurrently but migration.atomic != False")

    if set(facts.operation_names) & RISKY_OPS and risk_class == "metadata_only":
        issues.append(
            f"{rel}: risky operations {sorted(set(facts.operation_names) & RISKY_OPS)} "
            "cannot be classified as metadata_only"
        )


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()
    baseline_path = (root / args.baseline).resolve()
    output_path = (root / args.output).resolve()

    migrations_map = _scan_migrations(root)

    if args.write_baseline:
        payload = _build_baseline_payload(migrations_map)
        _write_json(baseline_path, payload)
        print(f"[qa] migration safety baseline updated: {baseline_path}")
        return 0

    issues: list[str] = []
    missing_entries: list[str] = []
    removed_entries: list[str] = []

    if not baseline_path.exists():
        issues.append(f"missing baseline: {baseline_path}")
        baseline_payload: dict[str, Any] = {"migrations": {}}
    else:
        baseline_payload = json.loads(baseline_path.read_text(encoding="utf-8"))

    baseline_migrations = baseline_payload.get("migrations")
    if not isinstance(baseline_migrations, dict):
        issues.append("invalid baseline format: 'migrations' must be an object")
        baseline_migrations = {}

    for rel, facts in migrations_map.items():
        raw_entry = baseline_migrations.get(rel)
        if not isinstance(raw_entry, dict):
            missing_entries.append(rel)
            continue
        _validate_entry(rel, raw_entry, facts, issues)

    for rel in sorted(baseline_migrations.keys()):
        if rel not in migrations_map:
            removed_entries.append(rel)

    if missing_entries:
        issues.append(
            "missing baseline metadata for migrations: " + ", ".join(missing_entries[:30])
        )

    status = "failed" if issues else "passed"
    payload = {
        "status": status,
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "baseline_path": str(baseline_path.relative_to(root).as_posix()) if baseline_path.exists() else str(args.baseline),
        "migrations_scanned": len(migrations_map),
        "missing_entries": missing_entries,
        "removed_entries": removed_entries,
        "issues": issues,
    }
    _write_json(output_path, payload)

    if status == "failed":
        print("[qa] migration safety guard failed")
        for issue in issues:
            print(f"[qa] - {issue}")
        return 1

    print("[qa] migration safety guard passed")
    if removed_entries:
        print(f"[qa] note: {len(removed_entries)} baseline entries not present anymore")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

