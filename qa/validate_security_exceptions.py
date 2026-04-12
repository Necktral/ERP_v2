#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timezone
from pathlib import Path


ALLOWED_SOURCES = {"pip", "npm"}
ALLOWED_SEVERITIES = {"low", "medium", "high", "critical"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate security exceptions contract (including expiry).")
    parser.add_argument("--root", default=".", help="Repository root")
    parser.add_argument(
        "--contract",
        default="qa/contracts/security_exceptions.json",
        help="Security exceptions JSON path",
    )
    parser.add_argument(
        "--output",
        default="qa/reports/security_exceptions_guard.json",
        help="Output report JSON path",
    )
    return parser.parse_args()


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()
    contract_path = (root / args.contract).resolve()
    output_path = (root / args.output).resolve()

    issues: list[str] = []
    warnings: list[str] = []
    today = date.today()

    if not contract_path.exists():
        issues.append(f"missing contract file: {contract_path}")
        payload: dict[str, object] = {"exceptions": []}
    else:
        payload = json.loads(contract_path.read_text(encoding="utf-8"))

    defaults = payload.get("defaults") if isinstance(payload.get("defaults"), dict) else {}
    max_expiry_days = int(defaults.get("max_expiry_days", 365))

    exceptions = payload.get("exceptions")
    if not isinstance(exceptions, list):
        issues.append("contract invalid: 'exceptions' must be a list")
        exceptions = []

    for idx, row in enumerate(exceptions):
        if not isinstance(row, dict):
            issues.append(f"exceptions[{idx}] must be an object")
            continue
        for key in ("id", "source", "package", "vuln_id", "severity", "reason", "ticket_ref", "expires_on"):
            value = str(row.get(key, "")).strip()
            if not value:
                issues.append(f"exceptions[{idx}] missing '{key}'")

        source = str(row.get("source", "")).strip().lower()
        if source and source not in ALLOWED_SOURCES:
            issues.append(f"exceptions[{idx}] invalid source '{source}'")

        severity = str(row.get("severity", "")).strip().lower()
        if severity and severity not in ALLOWED_SEVERITIES:
            issues.append(f"exceptions[{idx}] invalid severity '{severity}'")

        expires_raw = str(row.get("expires_on", "")).strip()
        if not expires_raw:
            continue
        try:
            expires_on = date.fromisoformat(expires_raw)
        except ValueError:
            issues.append(f"exceptions[{idx}] invalid expires_on '{expires_raw}' (expected YYYY-MM-DD)")
            continue

        if expires_on < today:
            issues.append(f"exceptions[{idx}] expired on {expires_raw}")
            continue

        delta_days = (expires_on - today).days
        if delta_days > max_expiry_days:
            warnings.append(
                f"exceptions[{idx}] expiry {expires_raw} exceeds max_expiry_days={max_expiry_days}"
            )

    status = "failed" if issues else "passed"
    report = {
        "status": status,
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "contract_file": contract_path.relative_to(root).as_posix() if contract_path.exists() else args.contract,
        "max_expiry_days": max_expiry_days,
        "issues": issues,
        "warnings": warnings,
        "exceptions_total": len(exceptions),
    }
    _write_json(output_path, report)

    if status == "failed":
        print("[qa] security exceptions validation failed")
        for issue in issues:
            print(f"[qa] - {issue}")
        return 1

    print("[qa] security exceptions validation passed")
    for warning in warnings:
        print(f"[qa] warning: {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
