#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


PATTERN = re.compile(r"\bsys\.path\.insert\s*\(")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fail if runtime code under backend/src uses sys.path.insert bootstrap hacks."
    )
    parser.add_argument("--root", default=".", help="Repository root")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()
    backend_src = root / "backend" / "src"

    if not backend_src.exists():
        print(f"[qa] backend/src not found: {backend_src}")
        return 2

    violations: list[str] = []
    for path in sorted(backend_src.rglob("*.py")):
        try:
            content = path.read_text(encoding="utf-8")
        except Exception:
            continue
        for lineno, line in enumerate(content.splitlines(), start=1):
            if PATTERN.search(line):
                rel = path.relative_to(root).as_posix()
                violations.append(f"{rel}:{lineno}: {line.strip()}")

    if violations:
        print("[qa] pythonpath bootstrap guard failed")
        for item in violations:
            print(f"[qa] - {item}")
        return 1

    print("[qa] pythonpath bootstrap guard passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
