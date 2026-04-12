#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path


USES_RE = re.compile(r"^\s*(?:-\s*)?uses:\s*([^\s#]+)")
HEX40_RE = re.compile(r"^[0-9a-f]{40}$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ensure GitHub Actions uses are pinned to commit SHA.")
    parser.add_argument("--root", default=".", help="Repository root")
    parser.add_argument(
        "--workflows-dir",
        default=".github/workflows",
        help="Relative path to workflows directory",
    )
    parser.add_argument(
        "--output",
        default="qa/reports/action_pin_guard.json",
        help="Output JSON report path",
    )
    return parser.parse_args()


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()
    workflows_dir = (root / args.workflows_dir).resolve()
    output_path = (root / args.output).resolve()

    issues: list[dict[str, object]] = []
    scanned = 0

    workflows = sorted({*workflows_dir.glob("*.yml"), *workflows_dir.glob("*.yaml")})
    for workflow in workflows:
        rel = workflow.relative_to(root).as_posix()
        lines = workflow.read_text(encoding="utf-8").splitlines()
        for lineno, line in enumerate(lines, start=1):
            match = USES_RE.match(line)
            if not match:
                continue
            scanned += 1
            ref = match.group(1).strip()
            if ref.startswith("./"):
                continue
            if "@" not in ref:
                issues.append(
                    {"file": rel, "line": lineno, "ref": ref, "reason": "missing_ref"}
                )
                continue
            _, version = ref.rsplit("@", 1)
            if not HEX40_RE.fullmatch(version):
                issues.append(
                    {
                        "file": rel,
                        "line": lineno,
                        "ref": ref,
                        "reason": "unpinned_action_ref",
                    }
                )

    status = "failed" if issues else "passed"
    report = {
        "status": status,
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "workflows_dir": workflows_dir.relative_to(root).as_posix(),
        "uses_scanned": scanned,
        "issues": issues,
    }
    _write_json(output_path, report)

    if status == "failed":
        print("[qa] action pin guard failed")
        for item in issues[:50]:
            print(
                f"[qa] - {item['file']}:{item['line']} {item['ref']} ({item['reason']})"
            )
        return 1

    print("[qa] action pin guard passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
