#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path


@dataclass
class CleanupRow:
    branch: str
    age_days: int
    last_commit_utc: str
    stale: bool
    action: str
    tag: str | None
    result: str
    detail: str


def _run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, check=check, text=True, capture_output=True)


def _collect_remote_branches(remote: str) -> list[tuple[str, str, datetime]]:
    ref = f"refs/remotes/{remote}"
    proc = _run(
        [
            "git",
            "for-each-ref",
            "--format=%(refname:short)|%(objectname)|%(committerdate:iso8601)",
            ref,
        ]
    )
    rows: list[tuple[str, str, datetime]] = []
    for line in proc.stdout.strip().splitlines():
        ref_name, sha, dt = line.split("|", 2)
        if ref_name == f"{remote}/HEAD":
            continue
        branch = ref_name.removeprefix(f"{remote}/")
        when = datetime.strptime(dt, "%Y-%m-%d %H:%M:%S %z").astimezone(timezone.utc)
        rows.append((branch, sha, when))
    return rows


def _tag_exists(tag_name: str) -> bool:
    proc = _run(["git", "rev-parse", "-q", "--verify", f"refs/tags/{tag_name}"], check=False)
    return proc.returncode == 0


def _next_tag_name(prefix: str, branch: str, stamp: str) -> str:
    base = f"{prefix}/{branch}/{stamp}"
    if not _tag_exists(base):
        return base
    idx = 1
    while True:
        candidate = f"{base}-{idx}"
        if not _tag_exists(candidate):
            return candidate
        idx += 1


def _write_outputs(
    output: str,
    json_output: str,
    *,
    generated_at: datetime,
    ttl_days: int,
    keep: list[str],
    apply_mode: bool,
    rows: list[CleanupRow],
) -> None:
    payload = {
        "generated_at": generated_at.isoformat(),
        "ttl_days": ttl_days,
        "apply_mode": apply_mode,
        "keep": keep,
        "processed_count": len(rows),
        "rows": [asdict(r) for r in rows],
    }

    md = [
        "# Branch Hygiene Cleanup",
        "",
        f"- Generated at: `{payload['generated_at']}`",
        f"- TTL policy: `{ttl_days}` days",
        f"- Apply mode: `{apply_mode}`",
        f"- Keep list: `{', '.join(keep)}`",
        "",
        "| Branch | Age (days) | Stale | Action | Result | Tag | Detail |",
        "|---|---:|---|---|---|---|---|",
    ]
    for row in rows:
        tag = f"`{row.tag}`" if row.tag else "-"
        md.append(
            f"| `{row.branch}` | {row.age_days} | {str(row.stale).lower()} | "
            f"{row.action} | {row.result} | {tag} | {row.detail} |"
        )
    md.append("")

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(md), encoding="utf-8")

    json_path = Path(json_output)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Archive and delete stale remote branches")
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--ttl-days", type=int, default=14)
    parser.add_argument("--keep", default="master,main")
    parser.add_argument("--tag-prefix", default="archive")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--output", required=True)
    parser.add_argument("--json-output", required=True)
    args = parser.parse_args()

    keep = sorted({x.strip() for x in args.keep.split(",") if x.strip()})
    keep_set = set(keep)
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=args.ttl_days)
    stamp = now.strftime("%Y%m%d")

    rows: list[CleanupRow] = []
    for branch, sha, when in sorted(_collect_remote_branches(args.remote), key=lambda x: x[0]):
        if branch in keep_set:
            continue

        age_days = max(0, int((now - when).total_seconds() // 86400))
        stale = when < cutoff
        if not stale:
            rows.append(
                CleanupRow(
                    branch=branch,
                    age_days=age_days,
                    last_commit_utc=when.isoformat(),
                    stale=False,
                    action="none",
                    tag=None,
                    result="skipped",
                    detail=f"within_{args.ttl_days}d",
                )
            )
            continue

        tag_name = _next_tag_name(args.tag_prefix, branch, stamp)
        if not args.apply:
            rows.append(
                CleanupRow(
                    branch=branch,
                    age_days=age_days,
                    last_commit_utc=when.isoformat(),
                    stale=True,
                    action="archive+delete",
                    tag=tag_name,
                    result="planned",
                    detail=f"target_sha={sha}",
                )
            )
            continue

        create_tag = _run(
            ["git", "tag", "-a", tag_name, f"{args.remote}/{branch}", "-m", f"archive {branch}"]
        )
        push_tag = _run(["git", "push", args.remote, f"refs/tags/{tag_name}"])
        delete_branch = _run(["git", "push", args.remote, "--delete", branch])
        rows.append(
            CleanupRow(
                branch=branch,
                age_days=age_days,
                last_commit_utc=when.isoformat(),
                stale=True,
                action="archive+delete",
                tag=tag_name,
                result="done",
                detail=(
                    f"created_tag={create_tag.returncode == 0}, "
                    f"pushed_tag={push_tag.returncode == 0}, "
                    f"deleted_branch={delete_branch.returncode == 0}"
                ),
            )
        )

    _write_outputs(
        args.output,
        args.json_output,
        generated_at=now,
        ttl_days=args.ttl_days,
        keep=keep,
        apply_mode=args.apply,
        rows=rows,
    )
    print(
        "[branch-hygiene-cleanup] "
        f"apply={args.apply} processed={len(rows)} output={args.output} json={args.json_output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
