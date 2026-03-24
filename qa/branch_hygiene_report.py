#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path


@dataclass
class BranchRow:
    name: str
    committer_date: str
    age_days: int
    status: str
    reason: str


def _run(cmd: list[str]) -> str:
    return subprocess.check_output(cmd, text=True).strip()


def _collect_remote_branches() -> list[tuple[str, datetime]]:
    raw = _run(
        [
            "git",
            "for-each-ref",
            "--format=%(refname:short)|%(committerdate:iso8601)",
            "refs/remotes/origin",
        ]
    )
    rows: list[tuple[str, datetime]] = []
    for line in raw.splitlines():
        ref, dt = line.split("|", 1)
        if ref == "origin/HEAD":
            continue
        name = ref.removeprefix("origin/")
        when = datetime.strptime(dt, "%Y-%m-%d %H:%M:%S %z")
        rows.append((name, when.astimezone(timezone.utc)))
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Weekly branch hygiene report")
    parser.add_argument("--ttl-days", type=int, default=14)
    parser.add_argument("--keep", default="master,main")
    parser.add_argument("--output", required=True)
    parser.add_argument("--json-output", required=True)
    args = parser.parse_args()

    keep = {x.strip() for x in args.keep.split(",") if x.strip()}
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=args.ttl_days)

    rows: list[BranchRow] = []
    stale_count = 0
    for branch, when in sorted(_collect_remote_branches(), key=lambda x: x[0]):
        age_days = max(0, int((now - when).total_seconds() // 86400))
        if branch in keep:
            rows.append(
                BranchRow(
                    name=branch,
                    committer_date=when.isoformat(),
                    age_days=age_days,
                    status="kept",
                    reason="protected_keep_list",
                )
            )
            continue

        stale = when < cutoff
        if stale:
            stale_count += 1
        rows.append(
            BranchRow(
                name=branch,
                committer_date=when.isoformat(),
                age_days=age_days,
                status="stale" if stale else "active",
                reason=f"older_than_{args.ttl_days}d" if stale else f"within_{args.ttl_days}d",
            )
        )

    payload = {
        "generated_at": now.isoformat(),
        "ttl_days": args.ttl_days,
        "keep": sorted(keep),
        "stale_count": stale_count,
        "branches": [asdict(r) for r in rows],
    }

    md = [
        "# Weekly Branch Hygiene Report",
        "",
        f"- Generated at: `{payload['generated_at']}`",
        f"- TTL policy: `{args.ttl_days}` days",
        f"- Keep list: `{', '.join(sorted(keep))}`",
        f"- Stale branches: **{stale_count}**",
        "",
        "| Branch | Age (days) | Status | Reason | Last Commit (UTC) |",
        "|---|---:|---|---|---|",
    ]
    for r in rows:
        md.append(
            f"| `{r.name}` | {r.age_days} | {r.status} | {r.reason} | `{r.committer_date}` |"
        )
    md.append("")

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(md), encoding="utf-8")

    json_path = Path(args.json_output)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"[branch-hygiene] stale_count={stale_count} output={output_path} json={json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
