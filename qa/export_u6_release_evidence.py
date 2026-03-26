#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REQUIRED_CONTRACTS = [
    "qa/contracts/github_required_checks.json",
    "qa/contracts/github_master_ruleset.json",
    "qa/contracts/security_exceptions.json",
]

RECOMMENDED_REPORTS = [
    "qa/reports/github_required_checks_guard.json",
    "qa/reports/action_pin_guard.json",
    "qa/reports/runner_hygiene_guard.json",
    "qa/reports/security_exceptions_guard.json",
    "qa/reports/security_findings_guard.json",
    "qa/reports/migration_safety_guard.json",
    "qa/reports/route_contract_report.json",
    "qa/reports/kernel_compat_usage.json",
    "qa/reports/coverage_by_domain.json",
    "qa/reports/pr_blast_radius.json",
]

SUPPLY_CHAIN_ARTIFACTS = [
    "qa_sbom_backend.json",
    "qa_sbom_frontend.json",
    "qa_pip_audit_u6.json",
    "qa_npm_audit_u6.json",
    "qa_security_exceptions_guard_u6.json",
    "qa_security_findings_guard_u6.json",
    "qa_supply_chain_artifacts.sha256",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build U6 release evidence artifact.")
    parser.add_argument("--root", default=".", help="Repository root")
    parser.add_argument(
        "--output",
        default="qa/reports/release_evidence_u6.json",
        help="Output report path",
    )
    parser.add_argument(
        "--ruleset-report",
        default="qa/reports/github_master_ruleset_verify.json",
        help="Ruleset verification report path (optional)",
    )
    return parser.parse_args()


def _run_git(args: list[str], cwd: Path) -> str:
    proc = subprocess.run(["git", *args], check=False, capture_output=True, text=True, cwd=cwd)
    if proc.returncode != 0:
        return ""
    return proc.stdout.strip()


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()
    output_path = (root / args.output).resolve()

    contracts_status = {}
    for rel in REQUIRED_CONTRACTS:
        path = root / rel
        contracts_status[rel] = {
            "exists": path.exists(),
            "size_bytes": path.stat().st_size if path.exists() else 0,
        }

    reports_status = {}
    for rel in RECOMMENDED_REPORTS:
        path = root / rel
        payload = _read_json(path)
        reports_status[rel] = {
            "exists": path.exists(),
            "status": payload.get("status") if isinstance(payload, dict) else None,
        }

    ruleset_report_path = (root / args.ruleset_report).resolve()
    ruleset_report = _read_json(ruleset_report_path)
    supply_chain_status = {}
    for rel in SUPPLY_CHAIN_ARTIFACTS:
        path = root / rel
        supply_chain_status[rel] = {
            "exists": path.exists(),
            "size_bytes": path.stat().st_size if path.exists() else 0,
        }

    gate1_core_reports = RECOMMENDED_REPORTS[:4]
    payload = {
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "git": {
            "branch": _run_git(["branch", "--show-current"], root),
            "head_sha": _run_git(["rev-parse", "HEAD"], root),
            "head_subject": _run_git(["log", "-1", "--pretty=%s"], root),
        },
        "contracts": contracts_status,
        "reports": reports_status,
        "supply_chain_artifacts": supply_chain_status,
        "ruleset_verify": {
            "path": ruleset_report_path.relative_to(root).as_posix(),
            "status": ruleset_report.get("status") if isinstance(ruleset_report, dict) else None,
        },
        "evidence_output": {
            "path": output_path.relative_to(root).as_posix(),
            "status": "generated",
        },
        "summary": {
            "contracts_all_present": all(row["exists"] for row in contracts_status.values()),
            "gate1_core_reports_present": all(reports_status[rel]["exists"] for rel in gate1_core_reports),
            "security_findings_report_present": reports_status["qa/reports/security_findings_guard.json"]["exists"],
            "supply_chain_artifacts_present": all(
                item["exists"] for item in supply_chain_status.values()
            ),
        },
    }

    _write_json(output_path, payload)
    print(f"[qa] release evidence exported: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
