#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TS="${1:-$(date +%Y%m%d_%H%M)}"
OUT_DIR="${ROOT_DIR}/docs/operacion/evidencia/bug_bounty_local_${TS}"

mkdir -p "${OUT_DIR}"

echo "[bug-bounty] output=${OUT_DIR}"

{
  echo "git_status:"
  git -C "${ROOT_DIR}" status --short
  echo
  echo "git_head:"
  git -C "${ROOT_DIR}" rev-parse HEAD
  echo
  echo "python_version:"
  python3 --version
  echo
  echo "node_version:"
  node --version
  echo
  echo "docker_version:"
  docker --version
} > "${OUT_DIR}/00_baseline.txt"

gitleaks_rc=0
docker run --rm -v "${ROOT_DIR}:/repo" zricethezav/gitleaks:latest detect \
  --no-git \
  --source /repo \
  --config /repo/.gitleaks.toml \
  --report-format json \
  --report-path "/repo/docs/operacion/evidencia/bug_bounty_local_${TS}/10_gitleaks.json" \
  --exit-code 1 || gitleaks_rc=$?

pip_audit_rc=0
pip-audit -r "${ROOT_DIR}/requirements/base.txt" -r "${ROOT_DIR}/requirements/prod.txt" -f json \
  > "${OUT_DIR}/11_pip_audit.json" || pip_audit_rc=$?

npm_audit_rc=0
(
  cd "${ROOT_DIR}/frontend"
  npm audit --json > "${OUT_DIR}/12_npm_audit.json"
) || npm_audit_rc=$?

if command -v trivy >/dev/null 2>&1; then
  trivy fs --format json --output "${OUT_DIR}/13_trivy_fs.json" "${ROOT_DIR}" || true
else
  echo '{"error":"trivy_not_installed"}' > "${OUT_DIR}/13_trivy_fs.json"
fi

static_scan_rc=0
"${ROOT_DIR}/qa/static_scan_backend.sh" "${ROOT_DIR}" > "${OUT_DIR}/14_static_scan.txt" 2>&1 || static_scan_rc=$?

manage_check_rc=0
(
  cd "${ROOT_DIR}/backend"
  python3 manage.py check > "${OUT_DIR}/20_django_check.txt" 2>&1
) || manage_check_rc=$?

audit_chain_rc=0
(
  cd "${ROOT_DIR}/backend"
  python3 manage.py audit_verify_chain --seed-minimal --format json > "${OUT_DIR}/21_audit_integrity.json" 2>&1
) || audit_chain_rc=$?

security_pytest_rc=0
pytest -q \
  "${ROOT_DIR}/backend/tests/test_axes_lockout.py" \
  "${ROOT_DIR}/backend/tests/test_2fa_challenge.py" \
  "${ROOT_DIR}/backend/tests/test_access_denied_audit.py" \
  "${ROOT_DIR}/backend/tests/test_audit_chain_integrity.py" \
  > "${OUT_DIR}/22_security_pytest.txt" 2>&1 || security_pytest_rc=$?

BUG_BOUNTY_OUT="${OUT_DIR}" \
GITLEAKS_RC="${gitleaks_rc}" \
PIP_AUDIT_RC="${pip_audit_rc}" \
NPM_AUDIT_RC="${npm_audit_rc}" \
STATIC_SCAN_RC="${static_scan_rc}" \
MANAGE_CHECK_RC="${manage_check_rc}" \
AUDIT_CHAIN_RC="${audit_chain_rc}" \
SECURITY_PYTEST_RC="${security_pytest_rc}" \
python3 - <<'PY'
import hashlib
import json
import os
from pathlib import Path

out = Path(os.environ["BUG_BOUNTY_OUT"])

def load_json(path: Path):
    try:
        text = path.read_text(encoding="utf-8")
        return json.loads(text)
    except Exception:
        try:
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1 and end > start:
                return json.loads(text[start : end + 1])
        except Exception:
            return None
        return None

gitleaks = load_json(out / "10_gitleaks.json")
gitleaks_findings = len(gitleaks) if isinstance(gitleaks, list) else None
gitleaks_clean = gitleaks_findings == 0

pip_data = load_json(out / "11_pip_audit.json") or {}
pip_blocking = []
for dep in pip_data.get("dependencies", []):
    name = dep.get("name")
    for vuln in dep.get("vulns", []):
        fix_versions = vuln.get("fix_versions") or []
        if not fix_versions:
            continue
        score = 0.0
        for sev in vuln.get("severity") or []:
            if isinstance(sev, dict):
                raw = sev.get("score")
                try:
                    score = float(raw)
                    break
                except Exception:
                    continue
        if score >= 7.0:
            pip_blocking.append(
                {"dependency": name, "id": vuln.get("id"), "score": score, "fix_versions": fix_versions}
            )

npm_data = load_json(out / "12_npm_audit.json") or {}
npm_blocking = []
for name, info in (npm_data.get("vulnerabilities") or {}).items():
    severity = info.get("severity")
    fix = info.get("fixAvailable")
    has_fix = bool(fix) and fix is not False
    if severity in ("high", "critical") and has_fix:
        npm_blocking.append({"name": name, "severity": severity, "fix": fix})

check_text = (out / "20_django_check.txt").read_text(encoding="utf-8", errors="ignore")
manage_check_pass = "System check identified no issues" in check_text

audit_data = load_json(out / "21_audit_integrity.json")
audit_chain_pass = bool(isinstance(audit_data, dict) and audit_data.get("ok") is True)

security_pytest = (out / "22_security_pytest.txt").read_text(encoding="utf-8", errors="ignore")
security_pytest_pass = "failed" not in security_pytest.lower()

static_scan_text = (out / "14_static_scan.txt").read_text(encoding="utf-8", errors="ignore")
static_scan_pass = "Static scan OK:" in static_scan_text

summary = {
    "status": "PASS",
    "evidence_dir": str(out),
    "checks": {
        "gitleaks_clean": bool(gitleaks_clean),
        "gitleaks_findings": gitleaks_findings,
        "pip_audit_blocking_clean": len(pip_blocking) == 0,
        "pip_audit_blocking_count": len(pip_blocking),
        "npm_audit_blocking_clean": len(npm_blocking) == 0,
        "npm_audit_blocking_count": len(npm_blocking),
        "manage_check_pass": manage_check_pass,
        "audit_chain_pass": audit_chain_pass,
        "security_pytest_pass": security_pytest_pass,
        "static_scan_pass": static_scan_pass,
    },
    "tool_exit_codes": {
        "gitleaks_rc": int(os.environ["GITLEAKS_RC"]),
        "pip_audit_rc": int(os.environ["PIP_AUDIT_RC"]),
        "npm_audit_rc": int(os.environ["NPM_AUDIT_RC"]),
        "static_scan_rc": int(os.environ["STATIC_SCAN_RC"]),
        "manage_check_rc": int(os.environ["MANAGE_CHECK_RC"]),
        "audit_chain_rc": int(os.environ["AUDIT_CHAIN_RC"]),
        "security_pytest_rc": int(os.environ["SECURITY_PYTEST_RC"]),
    },
    "blocking_findings": {
        "pip": pip_blocking,
        "npm": npm_blocking,
    },
}

required = [
    summary["checks"]["gitleaks_clean"],
    summary["checks"]["pip_audit_blocking_clean"],
    summary["checks"]["npm_audit_blocking_clean"],
    summary["checks"]["manage_check_pass"],
    summary["checks"]["audit_chain_pass"],
    summary["checks"]["security_pytest_pass"],
]
if not all(required):
    summary["status"] = "FAIL"

(out / "30_bug_bounty_summary.json").write_text(
    json.dumps(summary, indent=2, ensure_ascii=False),
    encoding="utf-8",
)

lines = [
    "# Bug Bounty Findings (Local Only)",
    "",
    f"- Status: **{summary['status']}**",
    f"- Evidence dir: `{out}`",
    "",
    "## Gate",
    f"- gitleaks_clean: {'PASS' if summary['checks']['gitleaks_clean'] else 'FAIL'}",
    f"- pip_audit_blocking_clean: {'PASS' if summary['checks']['pip_audit_blocking_clean'] else 'FAIL'}",
    f"- npm_audit_blocking_clean: {'PASS' if summary['checks']['npm_audit_blocking_clean'] else 'FAIL'}",
    f"- manage_check_pass: {'PASS' if summary['checks']['manage_check_pass'] else 'FAIL'}",
    f"- audit_chain_pass: {'PASS' if summary['checks']['audit_chain_pass'] else 'FAIL'}",
    f"- security_pytest_pass: {'PASS' if summary['checks']['security_pytest_pass'] else 'FAIL'}",
    "",
    "## Blocking Findings",
]

if not pip_blocking and not npm_blocking:
    lines.append("- No blocking dependency findings (HIGH/CRITICAL with fix available).")
else:
    for item in pip_blocking:
        lines.append(
            f"- PIP {item['dependency']} {item['id']} score={item['score']} fixes={item['fix_versions']}"
        )
    for item in npm_blocking:
        lines.append(
            f"- NPM {item['name']} severity={item['severity']} fix={item['fix']}"
        )

(out / "31_bug_bounty_findings.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

digest = hashlib.sha256((out / "30_bug_bounty_summary.json").read_bytes()).hexdigest()
(out / "32_bug_bounty_manifest_hash.txt").write_text(
    f"sha256={digest}\n", encoding="utf-8"
)
PY

echo "[bug-bounty] summary: ${OUT_DIR}/30_bug_bounty_summary.json"
