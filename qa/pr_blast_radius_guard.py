#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Classify PR blast radius and enforce governance policy.")
    parser.add_argument("--root", default=".", help="Repository root")
    parser.add_argument("--base-ref", default="", help="Optional base ref (e.g. origin/master)")
    parser.add_argument("--output", default="qa/reports/pr_blast_radius.json", help="Output report path")
    return parser.parse_args()


def _run_git(root: Path, args: list[str]) -> str:
    proc = subprocess.run(["git", *args], cwd=str(root), check=False, capture_output=True, text=True)
    if proc.returncode != 0:
        return ""
    return (proc.stdout or "").strip()


def _resolve_base(root: Path, explicit_base: str) -> str:
    if explicit_base:
        base = _run_git(root, ["merge-base", "HEAD", explicit_base])
        if base:
            return base
    for fallback in ("origin/master", "origin/main"):
        base = _run_git(root, ["merge-base", "HEAD", fallback])
        if base:
            return base
    return _run_git(root, ["rev-parse", "HEAD~1"])


def _changed_files(root: Path, base: str) -> list[str]:
    files: set[str] = set()
    if base:
        out = _run_git(root, ["diff", "--name-only", f"{base}...HEAD"])
        files.update(line.strip().replace("\\", "/") for line in out.splitlines() if line.strip())

    # Include local (unstaged/staged/untracked) drift to keep local gate actionable.
    for cmd in (
        ["diff", "--name-only"],
        ["diff", "--name-only", "--cached"],
        ["ls-files", "--others", "--exclude-standard"],
    ):
        out = _run_git(root, cmd)
        files.update(line.strip().replace("\\", "/") for line in out.splitlines() if line.strip())

    return sorted(files)


def _layer_for_path(rel: str) -> str:
    if rel.startswith("backend/src/apps/kernels/"):
        return "kernel"
    if rel.startswith("backend/src/apps/modulos/dashboard/") or rel.startswith("frontend/"):
        return "dashboard_ui"
    if rel.startswith("backend/src/"):
        return "runtime_backend"
    if rel.startswith("qa/"):
        return "qa"
    if rel.startswith(".github/workflows/") or rel.startswith("docker/") or rel.startswith("compose"):
        return "infra_deploy"
    if rel.startswith("docs/") or rel == "README.md":
        return "docs"
    return "other"


def _domain_for_path(rel: str) -> str | None:
    marker = "backend/src/apps/"
    if marker not in rel:
        return None
    tail = rel.split(marker, 1)[1]
    parts = tail.split("/")
    if len(parts) < 3:
        return None
    layer = parts[0]
    app = parts[1]
    if layer not in {"kernels", "modulos"}:
        return None
    return f"{layer}.{app}"


def _risk_level(*, files_count: int, domains_count: int, layers: set[str], mixed_flags: dict[str, bool]) -> str:
    if files_count == 0:
        return "low"
    if (
        files_count > 100
        or domains_count > 6
        or mixed_flags["kernel_dashboard_infra_mix"]
    ):
        return "extreme"
    if (
        files_count > 50
        or domains_count > 3
        or mixed_flags["runtime_migration_mix"]
        or mixed_flags["api_infra_mix"]
    ):
        return "high"
    if files_count > 15 or domains_count > 1 or len(layers) > 2:
        return "medium"
    return "low"


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    args = _parse_args()
    root = Path(args.root).resolve()
    output_path = (root / args.output).resolve()

    base = _resolve_base(root, args.base_ref)
    changed = _changed_files(root, base)

    layers_counter = Counter(_layer_for_path(path) for path in changed)
    layers = set(layers_counter.keys())

    domains = sorted({domain for path in changed if (domain := _domain_for_path(path))})

    has_runtime = any(path.startswith("backend/src/") for path in changed)
    has_migrations = any("/migrations/" in path for path in changed)
    has_api_shape = any(path.endswith("/urls.py") or "/api/" in path for path in changed)
    has_infra = any(path.startswith(".github/workflows/") or path.startswith("docker/") or path.startswith("compose") for path in changed)
    has_kernel = any(path.startswith("backend/src/apps/kernels/") for path in changed)
    has_dashboard = any(path.startswith("backend/src/apps/modulos/dashboard/") or path.startswith("frontend/") for path in changed)

    mixed_flags = {
        "runtime_migration_mix": has_runtime and has_migrations,
        "api_infra_mix": has_api_shape and has_infra,
        "kernel_dashboard_infra_mix": has_kernel and has_dashboard and has_infra,
    }

    risk = _risk_level(
        files_count=len(changed),
        domains_count=len(domains),
        layers=layers,
        mixed_flags=mixed_flags,
    )

    requires_design_note = risk in {"high", "extreme"}
    design_note_present = any(
        path.startswith("docs/adr/") or path.startswith("docs/design/") or path.endswith("DESIGN_NOTE.md")
        for path in changed
    )
    requires_additional_reviewer = risk in {"high", "extreme"}
    required_label = f"risk:{risk}"

    issues: list[str] = []
    if requires_design_note and not design_note_present:
        issues.append("high/extreme blast radius requires ADR or design note in docs/adr|docs/design")

    status = "failed" if issues else "passed"
    payload = {
        "status": status,
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "base_commit": base,
        "changed_files_count": len(changed),
        "changed_files": changed,
        "layers": dict(sorted(layers_counter.items())),
        "domains_touched": domains,
        "domains_count": len(domains),
        "mixed_flags": mixed_flags,
        "blast_radius_level": risk,
        "policy": {
            "requires_design_note": requires_design_note,
            "design_note_present": design_note_present,
            "requires_additional_reviewer": requires_additional_reviewer,
            "required_label": required_label,
        },
        "issues": issues,
    }
    _write_json(output_path, payload)

    if issues:
        print("[qa] pr blast radius guard failed")
        for issue in issues:
            print(f"[qa] - {issue}")
        return 1

    print("[qa] pr blast radius guard passed")
    print(f"[qa] blast_radius_level={risk} domains={len(domains)} files={len(changed)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
