#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


def _parse_ruff_errors(content: str) -> int | None:
    match = re.search(r"Found\s+(\d+)\s+error", content)
    if match:
        return int(match.group(1))
    if "All checks passed!" in content:
        return 0
    if re.search(r"^[A-Z]\d{3}\b", content, flags=re.MULTILINE):
        return 1
    return None


def _parse_mypy_errors(content: str) -> int | None:
    match = re.search(r"Found\s+(\d+)\s+errors?\s+in\s+\d+\s+files?", content)
    if match:
        return int(match.group(1))
    if "Success: no issues found" in content:
        return 0
    return None


def _load_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise FileNotFoundError(f"Missing report file: {path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify static analysis reports and fail on hidden errors.")
    parser.add_argument("--reports-dir", default="qa/reports", help="Directory containing ruff.txt and mypy.txt")
    args = parser.parse_args()

    reports_dir = Path(args.reports_dir)
    ruff_path = reports_dir / "ruff.txt"
    mypy_path = reports_dir / "mypy.txt"
    summary_path = reports_dir / "static_gate_summary.json"

    issues: list[str] = []
    status = "passed"
    ruff_errors: int | None = None
    mypy_errors: int | None = None

    try:
        ruff_text = _load_text(ruff_path)
        ruff_errors = _parse_ruff_errors(ruff_text)
        if ruff_errors is None:
            issues.append("Could not determine Ruff status from ruff.txt")
        elif ruff_errors > 0:
            issues.append(f"Ruff reported {ruff_errors} errors")
    except FileNotFoundError as exc:
        issues.append(str(exc))

    try:
        mypy_text = _load_text(mypy_path)
        mypy_errors = _parse_mypy_errors(mypy_text)
        if mypy_errors is None:
            issues.append("Could not determine mypy status from mypy.txt")
        elif mypy_errors > 0:
            issues.append(f"mypy reported {mypy_errors} errors")
    except FileNotFoundError as exc:
        issues.append(str(exc))

    if issues:
        status = "failed"

    summary = {
        "status": status,
        "ruff_errors": ruff_errors,
        "mypy_errors": mypy_errors,
        "issues": issues,
    }
    reports_dir.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if status == "failed":
        print("[qa] static gate verification failed")
        for issue in issues:
            print(f"[qa] - {issue}")
        return 1

    print("[qa] static gate verification passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
