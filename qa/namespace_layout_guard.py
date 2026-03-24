#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


CORE_APPS = (
    "common",
    "audit",
    "rbac",
    "accounts",
    "iam",
    "org",
    "hr",
    "accounting",
    "payments",
    "cec",
    "integration",
    "sync",
    "sync_engine",
)

DOMAIN_APPS = ("facturacion", "inventarios", "estacion_servicios", "compras")
EXPECTED_APPS = set(CORE_APPS + DOMAIN_APPS)

IMPORT_RE = re.compile(
    r"\b(?:from|import)\s+apps\.(?P<app>common|audit|rbac|accounts|iam|org|hr|accounting|payments|cec|integration|sync|sync_engine)\b"
)
DOTTED_RE = re.compile(
    r"['\"]apps\.(?P<app>common|audit|rbac|accounts|iam|org|hr|accounting|payments|cec|integration|sync|sync_engine)\."
)
LEGACY_PATH_RE = re.compile(
    r"backend/src/apps/(?P<app>common|audit|rbac|accounts|iam|org|hr|accounting|payments|cec|integration|sync|sync_engine)(?:/|\b)"
)
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
    extra_dirs = [p.name for p in top_level_dirs if p.name != "modulos"]
    if extra_dirs:
        violations.append(
            "unexpected app directories outside backend/src/apps/modulos: " + ", ".join(sorted(extra_dirs))
        )

    modulos_root = apps_root / "modulos"
    if not modulos_root.exists():
        violations.append("missing backend/src/apps/modulos")
        return violations

    existing = {p.name for p in modulos_root.iterdir() if p.is_dir() and p.name != "__pycache__"}
    missing = sorted(EXPECTED_APPS - existing)
    if missing:
        violations.append("missing expected apps under backend/src/apps/modulos: " + ", ".join(missing))

    return violations


def _check_imports(root: Path) -> list[str]:
    violations: list[str] = []
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
    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate backend namespace/layout cutover to apps.modulos.*")
    parser.add_argument("--root", default=".", help="Repository root path")
    args = parser.parse_args()
    root = Path(args.root).resolve()

    violations = _check_layout(root)
    violations.extend(_check_imports(root))

    if violations:
        print("[qa] namespace/layout guard failed")
        for row in violations:
            print(f" - {row}")
        return 2

    print("[qa] namespace/layout guard passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
