#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Detect runner residues that should never remain in repo.")
    parser.add_argument("--root", default=".", help="Repository root")
    parser.add_argument(
        "--output",
        default="qa/reports/runner_hygiene_guard.json",
        help="Output JSON report path",
    )
    return parser.parse_args()


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()
    output_path = (root / args.output).resolve()
    backend_src = root / "backend" / "src"

    current_uid = os.getuid()
    issues: list[dict[str, object]] = []

    for path in sorted(backend_src.rglob("*.egg-info")):
        rel = path.relative_to(root).as_posix()
        owner_uid = path.stat().st_uid
        issues.append(
            {
                "path": rel,
                "reason": "forbidden_egg_info_residue",
                "owner_uid": owner_uid,
                "owner_mismatch": owner_uid != current_uid,
            }
        )

    status = "failed" if issues else "passed"
    report = {
        "status": status,
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "issues": issues,
    }
    _write_json(output_path, report)

    if status == "failed":
        print("[qa] runner hygiene guard failed")
        for item in issues:
            suffix = " (owner mismatch)" if item.get("owner_mismatch") else ""
            print(f"[qa] - {item['path']}: {item['reason']}{suffix}")
        return 1

    print("[qa] runner hygiene guard passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
