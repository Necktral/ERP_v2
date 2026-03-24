# Branch Governance (Master-Only Trunk)

## Policy
- `master` is the only integration trunk.
- `main` is legacy/frozen (no new integration work).
- No direct push to `master`; all changes go through PR with required checks.
- Auto-delete merged branches is enabled in GitHub settings.

## Active Branch Model
- Long-lived: `master`
- Temporary: `feat/*`, `fix/*`, `release/*`, `sync/*`
- Temporary branches must be deleted after merge.

## Retention and Hygiene
- TTL for non-trunk branches: 14 days without activity.
- Branches older than TTL are candidates for archive+delete.
- Archive convention for historical refs: `archive/<branch>/<YYYYMMDD>` tags.

## Weekly Review
- Workflow: `.github/workflows/branch-hygiene.yml`
- Script: `qa/branch_hygiene_report.py`
- Outputs:
  - `qa/reports/branch_hygiene_report.md`
  - `qa/reports/branch_hygiene_report.json`

## Manual Execution
```bash
git fetch origin --prune
python3 qa/branch_hygiene_report.py \
  --ttl-days 14 \
  --keep "master,main,sync/local-parity-20260324,sync/integration-parity-20260324" \
  --output qa/reports/branch_hygiene_report.md \
  --json-output qa/reports/branch_hygiene_report.json
```

