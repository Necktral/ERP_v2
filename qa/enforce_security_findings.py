#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ExceptionRule:
    source: str
    package: str
    vuln_id: str
    expires_on: date


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Enforce security finding policy using versioned exceptions.")
    parser.add_argument("--root", default=".", help="Repository root")
    parser.add_argument("--pip-report", required=True, help="pip-audit JSON report path")
    parser.add_argument("--npm-report", required=True, help="npm audit JSON report path")
    parser.add_argument(
        "--exceptions",
        default="qa/contracts/security_exceptions.json",
        help="Security exceptions contract JSON path",
    )
    parser.add_argument(
        "--output",
        default="qa/reports/security_findings_guard.json",
        help="Output report JSON path",
    )
    return parser.parse_args()


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _pip_is_high_or_critical(vuln: dict[str, Any]) -> bool:
    for entry in (vuln.get("severity") or []):
        if not isinstance(entry, dict):
            continue
        score = entry.get("score")
        try:
            if float(score) >= 7.0:
                return True
        except (TypeError, ValueError):
            continue
    return False


def _load_rules(contract: dict[str, Any]) -> tuple[list[ExceptionRule], list[str]]:
    issues: list[str] = []
    rules: list[ExceptionRule] = []
    today = date.today()

    for idx, row in enumerate(contract.get("exceptions") or []):
        if not isinstance(row, dict):
            issues.append(f"exceptions[{idx}] must be an object")
            continue
        source = str(row.get("source", "")).strip().lower()
        package = str(row.get("package", "")).strip()
        vuln_id = str(row.get("vuln_id", "")).strip()
        raw_exp = str(row.get("expires_on", "")).strip()
        if not source or not package or not vuln_id or not raw_exp:
            issues.append(f"exceptions[{idx}] missing required fields")
            continue
        try:
            exp = date.fromisoformat(raw_exp)
        except ValueError:
            issues.append(f"exceptions[{idx}] invalid expires_on '{raw_exp}'")
            continue
        if exp < today:
            issues.append(f"exceptions[{idx}] expired on {raw_exp}")
            continue
        rules.append(ExceptionRule(source=source, package=package, vuln_id=vuln_id, expires_on=exp))
    return rules, issues


def _is_excepted(source: str, package: str, vuln_id: str, rules: list[ExceptionRule]) -> bool:
    for rule in rules:
        if rule.source != source:
            continue
        if rule.vuln_id != vuln_id:
            continue
        if rule.package not in {"*", package}:
            continue
        return True
    return False


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()
    pip_report_path = (root / args.pip_report).resolve()
    npm_report_path = (root / args.npm_report).resolve()
    exceptions_path = (root / args.exceptions).resolve()
    output_path = (root / args.output).resolve()

    contract = _load_json(exceptions_path)
    rules, issues = _load_rules(contract)

    unresolved: list[dict[str, Any]] = []
    excepted: list[dict[str, Any]] = []

    pip_payload = _load_json(pip_report_path)
    for dep in pip_payload.get("dependencies", []):
        pkg = str(dep.get("name", "")).strip()
        for vuln in dep.get("vulns", []):
            if not isinstance(vuln, dict):
                continue
            vuln_id = str(vuln.get("id", "")).strip()
            if not vuln_id:
                continue
            if not _pip_is_high_or_critical(vuln):
                continue
            if not (vuln.get("fix_versions") or []):
                continue
            finding = {
                "source": "pip",
                "package": pkg,
                "vuln_id": vuln_id,
                "severity": "high_or_critical",
            }
            if _is_excepted("pip", pkg, vuln_id, rules):
                excepted.append(finding)
            else:
                unresolved.append(finding)

    npm_payload = _load_json(npm_report_path)
    for pkg, info in (npm_payload.get("vulnerabilities") or {}).items():
        if not isinstance(info, dict):
            continue
        severity = str(info.get("severity", "")).lower()
        if severity not in {"high", "critical"}:
            continue
        fix_available = info.get("fixAvailable")
        if not fix_available or fix_available is False:
            continue
        vuln_ids: set[str] = set()
        for via in info.get("via") or []:
            if isinstance(via, dict):
                source_id = via.get("source")
                if source_id is not None:
                    vuln_ids.add(str(source_id))
        if not vuln_ids:
            vuln_ids.add(pkg)
        for vuln_id in sorted(vuln_ids):
            finding = {
                "source": "npm",
                "package": str(pkg),
                "vuln_id": vuln_id,
                "severity": severity,
            }
            if _is_excepted("npm", str(pkg), vuln_id, rules):
                excepted.append(finding)
            else:
                unresolved.append(finding)

    status = "failed" if issues or unresolved else "passed"
    report = {
        "status": status,
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "pip_report": pip_report_path.relative_to(root).as_posix() if pip_report_path.exists() else args.pip_report,
        "npm_report": npm_report_path.relative_to(root).as_posix() if npm_report_path.exists() else args.npm_report,
        "exceptions_contract": exceptions_path.relative_to(root).as_posix() if exceptions_path.exists() else args.exceptions,
        "issues": issues,
        "unresolved_findings": unresolved,
        "excepted_findings": excepted,
    }
    _write_json(output_path, report)

    if status == "failed":
        print("[qa] security findings guard failed")
        for issue in issues:
            print(f"[qa] - {issue}")
        for finding in unresolved:
            print(
                f"[qa] - unresolved {finding['source']} {finding['package']} {finding['vuln_id']} severity={finding['severity']}"
            )
        return 1

    print("[qa] security findings guard passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
