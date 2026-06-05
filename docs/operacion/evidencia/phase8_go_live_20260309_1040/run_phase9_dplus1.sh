#!/usr/bin/env bash
set -euo pipefail

ROOT="/home/necktral/ERP_CRM"
F8_OUT="${F8_OUT:-$ROOT/docs/operacion/evidencia/phase8_go_live_20260309_1040}"
TS="${TS:-$(date +%Y%m%d_%H%M%S)}"
PHASE9_OUT="${OUT_DIR:-$ROOT/docs/operacion/evidencia/phase9_go_live_${TS}}"

resolve_python() {
  if [[ -n "${PYTHON_BIN:-}" ]]; then
    if command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
      printf '%s\n' "${PYTHON_BIN}"
      return 0
    fi
    echo "[phase9-dplus1] PYTHON_BIN inválido: ${PYTHON_BIN}" >&2
    return 1
  fi
  if command -v python3 >/dev/null 2>&1; then
    printf '%s\n' "python3"
    return 0
  fi
  if command -v python >/dev/null 2>&1; then
    printf '%s\n' "python"
    return 0
  fi
  echo "[phase9-dplus1] no se encontró intérprete Python (python3/python)" >&2
  return 1
}

PYTHON_BIN="$(resolve_python)" || exit 127

COMPANY_ID="${COMPANY_ID:-5}"
BRANCH_ID="${BRANCH_ID:-6}"

PYTHON_BIN="${PYTHON_BIN}" \
OUT_DIR="${PHASE9_OUT}" \
F8_EVIDENCE_DIR="${F8_OUT}" \
COMPANY_ID="${COMPANY_ID}" \
BRANCH_ID="${BRANCH_ID}" \
"${ROOT}/qa/run_phase9_go_live.sh" full

echo "[phase9-dplus1] done out=${PHASE9_OUT}"
