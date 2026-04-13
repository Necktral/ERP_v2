#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODE="${1:-full}"

TS="${TS:-$(date +%Y%m%d_%H%M%S)}"
OUT_DIR="${OUT_DIR:-${ROOT_DIR}/docs/operacion/evidencia/product_lifecycle_${TS}}"

BASE_URL="${BASE_URL:-http://localhost:8000/api}"
FRESH_DB="${FRESH_DB:-1}"
SIM_SEED="${SIM_SEED:-20260412}"
QA_REPORTS_DIR="${QA_REPORTS_DIR:-qa/reports}"
TZ_REF="${TZ:-America/Managua}"

PASSWORD="${PASSWORD:-}"
if [[ -z "${PASSWORD}" ]]; then
  echo "ERROR: PASSWORD es requerido para ejecutar qa-gate3-security/performance." >&2
  exit 2
fi

PRODUCT_LIFECYCLE_ADMIN_USERNAME="${PRODUCT_LIFECYCLE_ADMIN_USERNAME:-root_lifecycle}"
PRODUCT_LIFECYCLE_ADMIN_PASSWORD="${PRODUCT_LIFECYCLE_ADMIN_PASSWORD:-Tmp!Lifecycle2026}"

mkdir -p "${OUT_DIR}" "${ROOT_DIR}/${QA_REPORTS_DIR}"

preflight() {
  echo "[product-lifecycle] preflight fresh_db=${FRESH_DB} base_url=${BASE_URL} seed=${SIM_SEED}"
  if [[ "${FRESH_DB}" == "1" ]]; then
    echo "[product-lifecycle] FRESH_DB=1 -> docker compose down -v --remove-orphans"
    (
      cd "${ROOT_DIR}"
      docker compose down -v --remove-orphans || true
    )
  fi

  (
    cd "${ROOT_DIR}"
    docker compose up -d --build db backend
    docker compose exec -T backend python /app/qa/wait_backend_ready.py
  )

  local api_ready=0
  for attempt in $(seq 1 45); do
    if curl -fsS --max-time 5 "${BASE_URL}/auth/bootstrap/status/" >/dev/null 2>&1; then
      api_ready=1
      break
    fi
    sleep 2
  done
  if [[ "${api_ready}" != "1" ]]; then
    echo "[product-lifecycle] API no disponible en ${BASE_URL}/auth/bootstrap/status/" >&2
    return 2
  fi
}

run_functional() {
  local rc=0
  (
    cd "${ROOT_DIR}"
    python3 qa/product_lifecycle_full_cycle.py \
      --base-url "${BASE_URL}" \
      --out-dir "${OUT_DIR}" \
      --seed "${SIM_SEED}" \
      --admin-username "${PRODUCT_LIFECYCLE_ADMIN_USERNAME}" \
      --admin-password "${PRODUCT_LIFECYCLE_ADMIN_PASSWORD}" \
      --contract qa/contracts/product_lifecycle_full_cycle_contract.json \
      --timezone "${TZ_REF}"
  ) || rc=$?
  echo "[product-lifecycle] functional_rc=${rc}"
  return "${rc}"
}

run_non_functional() {
  local gate3_security_rc=0
  local gate3_performance_rc=0
  local bug_bounty_rc=0
  local bug_ts="${BUG_TS:-${TS}}"

  set +e
  (
    cd "${ROOT_DIR}"
    PASSWORD="${PASSWORD}" make qa-gate3-security
  )
  gate3_security_rc=$?

  (
    cd "${ROOT_DIR}"
    PASSWORD="${PASSWORD}" make qa-gate3-performance
  )
  gate3_performance_rc=$?

  (
    cd "${ROOT_DIR}"
    bash qa/run_bug_bounty_local.sh "${bug_ts}"
  )
  bug_bounty_rc=$?
  set -e

  echo "${gate3_security_rc}" > "${OUT_DIR}/21_gate3_security_rc.txt"
  echo "${gate3_performance_rc}" > "${OUT_DIR}/22_gate3_performance_rc.txt"
  echo "${bug_bounty_rc}" > "${OUT_DIR}/23_bug_bounty_rc.txt"
  echo "${bug_ts}" > "${OUT_DIR}/24_bug_bounty_ts.txt"

  echo "[product-lifecycle] gate3_security_rc=${gate3_security_rc} gate3_performance_rc=${gate3_performance_rc} bug_bounty_rc=${bug_bounty_rc}"
}

consolidate_summary() {
  PRODUCT_LIFECYCLE_OUT_DIR="${OUT_DIR}" \
  PRODUCT_LIFECYCLE_ROOT="${ROOT_DIR}" \
  PRODUCT_LIFECYCLE_QA_REPORTS_DIR="${QA_REPORTS_DIR}" \
  PRODUCT_LIFECYCLE_TS="${TS}" \
  PRODUCT_LIFECYCLE_SEED="${SIM_SEED}" \
  PRODUCT_LIFECYCLE_TZ="${TZ_REF}" \
  python3 - <<'PY'
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

out_dir = Path(os.environ["PRODUCT_LIFECYCLE_OUT_DIR"])
root = Path(os.environ["PRODUCT_LIFECYCLE_ROOT"])
qa_reports_dir = Path(root / os.environ["PRODUCT_LIFECYCLE_QA_REPORTS_DIR"])
ts = os.environ["PRODUCT_LIFECYCLE_TS"]
seed = int(os.environ["PRODUCT_LIFECYCLE_SEED"])
tz_ref = os.environ["PRODUCT_LIFECYCLE_TZ"]

functional_path = out_dir / "20_product_lifecycle_functional.json"
security_summary_path = qa_reports_dir / "gate3_security_summary.json"
performance_summary_path = qa_reports_dir / "gate3_performance_summary.json"
bug_ts_path = out_dir / "24_bug_bounty_ts.txt"
bug_ts = bug_ts_path.read_text(encoding="utf-8", errors="ignore").strip() if bug_ts_path.exists() else ts
bug_summary_path = root / f"docs/operacion/evidencia/bug_bounty_local_{bug_ts}/30_bug_bounty_summary.json"


def load_json(path: Path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def read_rc(path: Path) -> int:
    if not path.exists():
        return 127
    raw = path.read_text(encoding="utf-8", errors="ignore").strip()
    try:
        return int(raw)
    except Exception:
        return 127


functional = load_json(functional_path) or {}
security_gate = load_json(security_summary_path) or {}
performance_gate = load_json(performance_summary_path) or {}
bug_summary = load_json(bug_summary_path) or {}

functional_pass = bool(functional.get("pass") is True)
security_gate_pass = bool(security_gate.get("passed") is True and str(security_gate.get("failure_class") or "none") == "none")
performance_gate_pass = bool(performance_gate.get("passed") is True and str(performance_gate.get("failure_class") or "none") == "none")
bug_pass = str(bug_summary.get("status") or "") == "PASS"

orphan_total = int((functional.get("orphan_checks") or {}).get("total") or 0)

summary = {
    "schema_version": 1,
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "timezone": tz_ref,
    "seed": seed,
    "status": "PASS",
    "functional": {
        "pass": functional_pass,
        "status": str(functional.get("status") or "FAIL"),
        "file": str(functional_path),
        "global_error": str(functional.get("global_error") or ""),
    },
    "load": {
        "pass": bool(security_gate_pass and performance_gate_pass),
        "security_profile": {
            "pass": security_gate_pass,
            "summary_file": str(security_summary_path),
            "failure_class": str(security_gate.get("failure_class") or ""),
            "rc": read_rc(out_dir / "21_gate3_security_rc.txt"),
        },
        "performance_profile": {
            "pass": performance_gate_pass,
            "summary_file": str(performance_summary_path),
            "failure_class": str(performance_gate.get("failure_class") or ""),
            "rc": read_rc(out_dir / "22_gate3_performance_rc.txt"),
        },
    },
    "security": {
        "pass": bug_pass,
        "bug_bounty": {
            "status": str(bug_summary.get("status") or ""),
            "summary_file": str(bug_summary_path),
            "rc": read_rc(out_dir / "23_bug_bounty_rc.txt"),
        },
    },
    "module_results": functional.get("module_results") or {},
    "http_contract": functional.get("http_contract") or {},
    "orphan_checks": functional.get("orphan_checks") or {},
    "intercompany_consistency": functional.get("intercompany_consistency") or {},
    "load_security_results": {
        "gate3_security": security_gate,
        "gate3_performance": performance_gate,
        "bug_bounty": bug_summary,
    },
}

if not functional_pass:
    summary["status"] = "FAIL"
if orphan_total > 0:
    summary["status"] = "FAIL"
if not summary["load"]["pass"]:
    summary["status"] = "FAIL"
if not summary["security"]["pass"]:
    summary["status"] = "FAIL"

summary_path = out_dir / "30_product_lifecycle_summary.json"
summary_raw = json.dumps(summary, ensure_ascii=False, indent=2)
summary_path.write_text(summary_raw + "\n", encoding="utf-8")

log_path = out_dir / "31_product_lifecycle_log.md"
existing_log = ""
if log_path.exists():
    existing_log = log_path.read_text(encoding="utf-8", errors="ignore").rstrip() + "\n\n"

append_lines = [
    "## Non-Functional Consolidation",
    "",
    f"- Functional: **{'PASS' if functional_pass else 'FAIL'}**",
    f"- Orphan checks total: `{orphan_total}`",
    f"- Gate3 security: **{'PASS' if security_gate_pass else 'FAIL'}**",
    f"- Gate3 performance: **{'PASS' if performance_gate_pass else 'FAIL'}**",
    f"- Bug bounty: **{'PASS' if bug_pass else 'FAIL'}**",
    f"- Final status: **{summary['status']}**",
]
log_path.write_text(existing_log + "\n".join(append_lines) + "\n", encoding="utf-8")

sha = hashlib.sha256(summary_path.read_bytes()).hexdigest()
(out_dir / "32_product_lifecycle_manifest.sha256").write_text(
    f"{sha}  30_product_lifecycle_summary.json\n", encoding="utf-8"
)

print(json.dumps({"status": summary["status"], "summary": str(summary_path)}, ensure_ascii=False))
if summary["status"] != "PASS":
    raise SystemExit(1)
PY
}

case "${MODE}" in
  full)
    preflight
    functional_rc=0
    run_functional || functional_rc=$?
    run_non_functional
    consolidate_summary
    if [[ "${functional_rc}" -ne 0 ]]; then
      echo "[product-lifecycle] functional stage ended with rc=${functional_rc}" >&2
      exit "${functional_rc}"
    fi
    ;;
  functional)
    preflight
    run_functional
    ;;
  *)
    echo "Uso: $0 [full|functional]" >&2
    exit 2
    ;;
esac

echo "[product-lifecycle] done mode=${MODE} out=${OUT_DIR}"
