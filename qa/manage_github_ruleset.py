#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply or verify GitHub master protection policy (U6).")
    parser.add_argument("--root", default=".", help="Repository root")
    parser.add_argument(
        "--contract",
        default="qa/contracts/github_master_ruleset.json",
        help="Ruleset contract path",
    )
    parser.add_argument(
        "--mode",
        choices=("apply", "verify"),
        required=True,
        help="Apply or verify ruleset",
    )
    parser.add_argument(
        "--output",
        default="qa/reports/github_master_ruleset_verify.json",
        help="Output report path",
    )
    parser.add_argument("--owner", default="", help="Override GitHub owner")
    parser.add_argument("--repo", default="", help="Override GitHub repository")
    parser.add_argument("--branch", default="", help="Override protected branch")
    return parser.parse_args()


def _run_gh(args: list[str]) -> tuple[int, str, str]:
    proc = subprocess.run(["gh", *args], check=False, capture_output=True, text=True)
    return proc.returncode, proc.stdout, proc.stderr


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _get_contract(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _build_branch_protection_payload(contract: dict[str, Any]) -> dict[str, Any]:
    policy = contract.get("policy") or {}
    contexts = contract.get("required_status_contexts") or []
    checks = [{"context": ctx} for ctx in contexts]
    return {
        "required_status_checks": {
            "strict": True,
            "checks": checks,
        },
        "enforce_admins": bool(policy.get("enforce_admins", True)),
        "required_pull_request_reviews": {
            "required_approving_review_count": int(policy.get("required_approving_review_count", 1)),
            "dismiss_stale_reviews": False,
            "require_code_owner_reviews": bool(policy.get("require_code_owner_reviews", True)),
            "require_last_push_approval": False,
        },
        "restrictions": None,
        "allow_force_pushes": bool(policy.get("allow_force_pushes", False)),
        "allow_deletions": bool(policy.get("allow_deletions", False)),
        "required_conversation_resolution": bool(policy.get("required_conversation_resolution", True)),
        "lock_branch": False,
        "allow_fork_syncing": True,
    }


def _is_enabled(value: Any) -> bool:
    if isinstance(value, dict):
        return bool(value.get("enabled", False))
    return bool(value)


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()
    contract_path = (root / args.contract).resolve()
    output_path = (root / args.output).resolve()
    contract = _get_contract(contract_path)

    repo_cfg = contract.get("repository") or {}
    owner = args.owner or str(repo_cfg.get("owner", "")).strip()
    repo = args.repo or str(repo_cfg.get("repo", "")).strip()
    branch = args.branch or str(contract.get("branch", "master")).strip()
    if not owner or not repo or not branch:
        raise SystemExit("owner/repo/branch missing in contract or args")

    required_contexts = list(contract.get("required_status_contexts") or [])
    payload = _build_branch_protection_payload(contract)
    issues: list[str] = []
    details: dict[str, Any] = {}

    code, _, stderr = _run_gh(["auth", "status"])
    if code != 0:
        issues.append("gh auth status failed. Run 'gh auth login' first.")
        details["gh_auth_error"] = stderr.strip()

    if args.mode == "apply" and not issues:
        proc = subprocess.run(
            ["gh", "api", "--method", "PUT", f"repos/{owner}/{repo}/branches/{branch}/protection", "--input", "-"],
            input=json.dumps(payload),
            check=False,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            issues.append("failed to apply branch protection payload")
            details["apply_error"] = proc.stderr.strip()

        repo_patch = {"delete_branch_on_merge": bool((contract.get("policy") or {}).get("delete_branch_on_merge", True))}
        proc_repo = subprocess.run(
            ["gh", "api", "--method", "PATCH", f"repos/{owner}/{repo}", "--input", "-"],
            input=json.dumps(repo_patch),
            check=False,
            capture_output=True,
            text=True,
        )
        if proc_repo.returncode != 0:
            issues.append("failed to apply repository delete_branch_on_merge setting")
            details["repo_patch_error"] = proc_repo.stderr.strip()

    if not issues:
        code, stdout, stderr = _run_gh(["api", f"repos/{owner}/{repo}/branches/{branch}/protection"])
        if code != 0:
            issues.append("failed to fetch branch protection")
            details["verify_error"] = stderr.strip()
        else:
            protection = json.loads(stdout)
            details["protection"] = protection
            seen_contexts = sorted(
                [row.get("context", "") for row in ((protection.get("required_status_checks") or {}).get("checks") or [])]
            )
            expected_contexts = sorted(required_contexts)
            if seen_contexts != expected_contexts:
                issues.append(
                    f"required status checks mismatch (expected={expected_contexts}, found={seen_contexts})"
                )

            required_reviews = protection.get("required_pull_request_reviews") or {}
            if not required_reviews.get("require_code_owner_reviews"):
                issues.append("require_code_owner_reviews is not enabled")

            if not _is_enabled(protection.get("required_conversation_resolution")):
                issues.append("required_conversation_resolution is not enabled")

            if not _is_enabled(protection.get("enforce_admins")):
                issues.append("enforce_admins is not enabled")

        code, stdout, stderr = _run_gh(["api", f"repos/{owner}/{repo}"])
        if code != 0:
            issues.append("failed to fetch repository settings")
            details["repo_verify_error"] = stderr.strip()
        else:
            repo_payload = json.loads(stdout)
            details["repo"] = {
                "default_branch": repo_payload.get("default_branch"),
                "delete_branch_on_merge": repo_payload.get("delete_branch_on_merge"),
            }
            if not repo_payload.get("delete_branch_on_merge", False):
                issues.append("delete_branch_on_merge is not enabled")

    status = "failed" if issues else "passed"
    report = {
        "status": status,
        "mode": args.mode,
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "contract_file": contract_path.relative_to(root).as_posix(),
        "owner": owner,
        "repo": repo,
        "branch": branch,
        "issues": issues,
        "details": details,
    }
    _write_json(output_path, report)

    if status == "failed":
        print("[qa] github ruleset manage failed")
        for issue in issues:
            print(f"[qa] - {issue}")
        return 1

    print("[qa] github ruleset verify passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
