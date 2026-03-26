#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path


WORKFLOW_NAME_RE = re.compile(r"^name:\s*(.+?)\s*$")
JOB_ID_RE = re.compile(r"^  ([a-zA-Z0-9_-]+):\s*$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate required checks contract against workflow files.")
    parser.add_argument("--root", default=".", help="Repository root")
    parser.add_argument(
        "--contract",
        default="qa/contracts/github_required_checks.json",
        help="Required checks contract JSON path",
    )
    parser.add_argument(
        "--output",
        default="qa/reports/github_required_checks_guard.json",
        help="Output report JSON path",
    )
    return parser.parse_args()


def _parse_workflow_metadata(path: Path) -> dict[str, object]:
    lines = path.read_text(encoding="utf-8").splitlines()
    workflow_name = None
    jobs: set[str] = set()
    in_jobs = False

    for line in lines:
        if workflow_name is None:
            m = WORKFLOW_NAME_RE.match(line)
            if m:
                workflow_name = m.group(1).strip().strip("\"'")
        if line.strip() == "jobs:":
            in_jobs = True
            continue
        if in_jobs:
            if line and not line.startswith(" "):
                in_jobs = False
                continue
            m = JOB_ID_RE.match(line)
            if m:
                jobs.add(m.group(1))

    return {
        "workflow_name": workflow_name or "",
        "jobs": sorted(jobs),
    }


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()
    contract_path = (root / args.contract).resolve()
    output_path = (root / args.output).resolve()

    issues: list[str] = []
    observed: dict[str, object] = {}

    if not contract_path.exists():
        issues.append(f"missing contract file: {contract_path}")
        contract_payload: dict[str, object] = {"required_checks": []}
    else:
        contract_payload = json.loads(contract_path.read_text(encoding="utf-8"))

    required_checks = contract_payload.get("required_checks")
    if not isinstance(required_checks, list):
        issues.append("contract invalid: 'required_checks' must be a list")
        required_checks = []

    for idx, row in enumerate(required_checks):
        if not isinstance(row, dict):
            issues.append(f"required_checks[{idx}] must be an object")
            continue

        workflow_file = str(row.get("workflow_file", "")).strip()
        workflow_name = str(row.get("workflow_name", "")).strip()
        job_id = str(row.get("job_id", "")).strip()
        check_context = str(row.get("check_context", "")).strip()

        if not workflow_file or not workflow_name or not job_id or not check_context:
            issues.append(f"required_checks[{idx}] missing required fields")
            continue

        workflow_path = (root / workflow_file).resolve()
        if not workflow_path.exists():
            issues.append(f"{workflow_file}: file not found")
            continue

        metadata = _parse_workflow_metadata(workflow_path)
        observed[workflow_file] = metadata

        observed_name = str(metadata.get("workflow_name", "")).strip()
        jobs = set(metadata.get("jobs", []))

        if observed_name != workflow_name:
            issues.append(
                f"{workflow_file}: workflow name mismatch (expected='{workflow_name}', found='{observed_name}')"
            )

        if job_id not in jobs:
            issues.append(
                f"{workflow_file}: missing job_id '{job_id}' (found={sorted(jobs)})"
            )

        expected_context = f"{workflow_name} / {job_id}"
        if check_context != expected_context:
            issues.append(
                f"{workflow_file}: check_context mismatch (expected='{expected_context}', found='{check_context}')"
            )

    status = "failed" if issues else "passed"
    report = {
        "status": status,
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "contract_file": contract_path.relative_to(root).as_posix() if contract_path.exists() else args.contract,
        "required_checks_count": len(required_checks),
        "issues": issues,
        "observed_workflows": observed,
    }
    _write_json(output_path, report)

    if status == "failed":
        print("[qa] github required checks guard failed")
        for issue in issues:
            print(f"[qa] - {issue}")
        return 1

    print("[qa] github required checks guard passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
