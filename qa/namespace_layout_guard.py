#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    from qa.kernel_compat_policy import DEFAULT_POLICY, KERNEL_COMPAT_APPS, allowed_references
except ModuleNotFoundError:  # pragma: no cover - direct script invocation fallback
    from kernel_compat_policy import DEFAULT_POLICY, KERNEL_COMPAT_APPS, allowed_references


MODULOS_CORE_APPS = (
    "common",
    "audit",
    "rbac",
    "accounts",
    "iam",
    "org",
    "hr",
    "cec",
    "integration",
    "dashboard",
    "sync",
    "sync_engine",
    "compras",
    "estacion_servicios",
)
EXPECTED_MODULOS_APPS = set(MODULOS_CORE_APPS + KERNEL_COMPAT_APPS)
EXPECTED_KERNEL_APPS = set(KERNEL_COMPAT_APPS + ("reporting",))

IMPORT_RE = re.compile(
    r"\b(?:from|import)\s+apps\.(?P<app>common|audit|rbac|accounts|iam|org|hr|accounting|payments|cec|integration|sync|sync_engine)\b"
)
DOTTED_RE = re.compile(
    r"['\"]apps\.(?P<app>common|audit|rbac|accounts|iam|org|hr|accounting|payments|cec|integration|sync|sync_engine)\."
)
LEGACY_PATH_RE = re.compile(
    r"backend/src/apps/(?P<app>common|audit|rbac|accounts|iam|org|hr|cec|integration|sync|sync_engine)(?:/|\b)"
)
_KERNEL_COMPAT_PATTERN = "|".join(KERNEL_COMPAT_APPS)
KERNEL_COMPAT_IMPORT_RE = re.compile(
    rf"\b(?:from|import)\s+apps\.modulos\.(?P<app>{_KERNEL_COMPAT_PATTERN})\b"
)
KERNEL_COMPAT_DOTTED_RE = re.compile(
    rf"['\"]apps\.modulos\.(?P<app>{_KERNEL_COMPAT_PATTERN})\."
)
KERNEL_COMPAT_PATH_RE = re.compile(rf"backend/src/apps/modulos/(?P<app>{_KERNEL_COMPAT_PATTERN})")
TEXT_EXTENSIONS = {".py", ".sh", ".yml", ".yaml", ".ini", ".toml", ".txt"}


def _readable_files(root: Path) -> list[Path]:
    files: list[Path] = []
    scan_roots = [
        root / "backend" / "src",
        root / "backend" / "tests",
        root / "qa",
        root / ".github" / "workflows",
        root / "docker",
    ]
    for base in scan_roots:
        if not base.exists():
            continue
        for p in base.rglob("*"):
            if not p.is_file():
                continue
            normalized = str(p).replace("\\", "/")
            if "__pycache__/" in normalized:
                continue
            if p.suffix and p.suffix not in TEXT_EXTENSIONS:
                continue
            if "qa/reports" in normalized:
                continue
            files.append(p)
    for extra in (
        root / "Makefile",
        root / "compose.yaml",
        root / "compose.prod.yaml",
        root / "mypy.ini",
        root / "ruff.toml",
        root / "backend" / "pytest.ini",
    ):
        if extra.exists() and extra.is_file():
            files.append(extra)
    return files


def _check_layout(root: Path) -> list[str]:
    violations: list[str] = []
    apps_root = root / "backend" / "src" / "apps"
    if not apps_root.exists():
        violations.append("missing backend/src/apps")
        return violations

    top_level_dirs = [p for p in apps_root.iterdir() if p.is_dir() and p.name != "__pycache__"]
    extra_dirs = [p.name for p in top_level_dirs if p.name not in {"modulos", "kernels"}]
    if extra_dirs:
        violations.append(
            "unexpected app directories outside backend/src/apps/{modulos,kernels}: "
            + ", ".join(sorted(extra_dirs))
        )

    modulos_root = apps_root / "modulos"
    if not modulos_root.exists():
        violations.append("missing backend/src/apps/modulos")
        return violations

    kernels_root = apps_root / "kernels"
    if not kernels_root.exists():
        violations.append("missing backend/src/apps/kernels")
        return violations

    modulos_existing = {p.name for p in modulos_root.iterdir() if p.is_dir() and p.name != "__pycache__"}
    modulos_missing = sorted(EXPECTED_MODULOS_APPS - modulos_existing)
    if modulos_missing:
        violations.append("missing expected apps under backend/src/apps/modulos: " + ", ".join(modulos_missing))

    kernels_existing = {p.name for p in kernels_root.iterdir() if p.is_dir() and p.name != "__pycache__"}
    kernels_missing = sorted(EXPECTED_KERNEL_APPS - kernels_existing)
    if kernels_missing:
        violations.append("missing expected apps under backend/src/apps/kernels: " + ", ".join(kernels_missing))

    return violations


def _check_imports(root: Path, *, compat_allowed_references: set[str]) -> tuple[list[str], list[dict[str, object]]]:
    violations: list[str] = []
    compat_usage: list[dict[str, object]] = []
    for file_path in _readable_files(root):
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        rel = file_path.relative_to(root).as_posix()
        for i, line in enumerate(content.splitlines(), start=1):
            m = IMPORT_RE.search(line)
            if m:
                app = m.group("app")
                violations.append(
                    f"{rel}:{i}: legacy import detected (apps.{app}); use apps.modulos.{app}"
                )
            m = DOTTED_RE.search(line)
            if m:
                app = m.group("app")
                violations.append(
                    f"{rel}:{i}: legacy dotted path detected (apps.{app}.*); use apps.modulos.{app}.*"
                )
            m = LEGACY_PATH_RE.search(line)
            if m:
                app = m.group("app")
                violations.append(
                    f"{rel}:{i}: legacy filesystem path backend/src/apps/{app}; use backend/src/apps/modulos/{app}"
                )
            m = KERNEL_COMPAT_IMPORT_RE.search(line)
            if m:
                app = m.group("app")
                is_allowed = rel in compat_allowed_references
                compat_usage.append(
                    {
                        "file": rel,
                        "line": i,
                        "app": app,
                        "usage_type": "import",
                        "status": "allowed" if is_allowed else "prohibited",
                    }
                )
                if (
                    rel != f"backend/src/apps/modulos/{app}/__init__.py"
                    and rel not in compat_allowed_references
                ):
                    violations.append(
                        f"{rel}:{i}: legacy kernel compat import detected (apps.modulos.{app}); "
                        f"use apps.kernels.{app}"
                    )
            m = KERNEL_COMPAT_DOTTED_RE.search(line)
            if m:
                app = m.group("app")
                is_allowed = rel in compat_allowed_references
                compat_usage.append(
                    {
                        "file": rel,
                        "line": i,
                        "app": app,
                        "usage_type": "dotted_path",
                        "status": "allowed" if is_allowed else "prohibited",
                    }
                )
                if (
                    rel != f"backend/src/apps/modulos/{app}/__init__.py"
                    and rel not in compat_allowed_references
                ):
                    violations.append(
                        f"{rel}:{i}: legacy kernel dotted path detected (apps.modulos.{app}.*); "
                        f"use apps.kernels.{app}.*"
                    )
            m = KERNEL_COMPAT_PATH_RE.search(line)
            if m:
                app = m.group("app")
                is_allowed = rel in compat_allowed_references
                compat_usage.append(
                    {
                        "file": rel,
                        "line": i,
                        "app": app,
                        "usage_type": "filesystem_path",
                        "status": "allowed" if is_allowed else "prohibited",
                    }
                )
                if (
                    rel != f"backend/src/apps/modulos/{app}/__init__.py"
                    and rel not in compat_allowed_references
                ):
                    violations.append(
                        f"{rel}:{i}: legacy kernel path backend/src/apps/modulos/{app}; "
                        f"use backend/src/apps/kernels/{app}"
                    )
    return violations, compat_usage


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate backend namespace/layout split to apps.modulos.* + apps.kernels.*"
    )
    parser.add_argument("--root", default=".", help="Repository root path")
    parser.add_argument(
        "--output",
        default="qa/reports/kernel_compat_usage.json",
        help="Output JSON with compat usage inventory",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Strict mode: no legacy compat usage allowed",
    )
    args = parser.parse_args()
    root = Path(args.root).resolve()
    output_path = (root / args.output).resolve()

    enforcement = "strict" if args.strict else DEFAULT_POLICY.enforcement_level
    compat_allowed_refs = allowed_references(enforcement_level=enforcement)

    violations = _check_layout(root)
    import_violations, compat_usage = _check_imports(root, compat_allowed_references=compat_allowed_refs)
    violations.extend(import_violations)

    payload = {
        "status": "failed" if violations else "passed",
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "enforcement_level": enforcement,
        "retirement_deadline": DEFAULT_POLICY.retirement_deadline,
        "allowed_whitelist": sorted(compat_allowed_refs),
        "legacy_compat_apps": list(KERNEL_COMPAT_APPS),
        "compat_usage": compat_usage,
        "allowed_usage_count": sum(1 for row in compat_usage if row["status"] == "allowed"),
        "prohibited_usage_count": sum(1 for row in compat_usage if row["status"] != "allowed"),
        "violations": violations,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if violations:
        print("[qa] namespace/layout guard failed")
        for row in violations:
            print(f" - {row}")
        return 2

    print("[qa] namespace/layout guard passed")
    if compat_usage:
        print(
            f"[qa] kernel compat usage: total={len(compat_usage)} "
            f"allowed={payload['allowed_usage_count']} prohibited={payload['prohibited_usage_count']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
