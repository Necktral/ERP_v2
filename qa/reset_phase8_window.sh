#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CURRENT_OUT_DIR="${OUT_DIR:-${ROOT_DIR}/docs/operacion/evidencia/phase8_go_live_20260309_1040}"
TS="${TS:-$(date +%Y%m%d_%H%M%S)}"
REASON="${REASON:-DAILY_GATE_FAILED}"

if [[ ! -d "${CURRENT_OUT_DIR}" ]]; then
  echo "[phase8-reset] OUT_DIR no existe: ${CURRENT_OUT_DIR}" >&2
  exit 2
fi

TARGET_OUT_DIR="${ROOT_DIR}/docs/operacion/evidencia/phase8_go_live_${TS}"
mkdir -p "${TARGET_OUT_DIR}"

resolve_python() {
  if [[ -n "${PYTHON_BIN:-}" ]]; then
    if command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
      printf '%s\n' "${PYTHON_BIN}"
      return 0
    fi
    echo "[phase8-reset] PYTHON_BIN inválido: ${PYTHON_BIN}" >&2
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
  echo "[phase8-reset] no se encontró intérprete Python (python3/python)" >&2
  return 1
}

PYTHON_BIN="$(resolve_python)" || exit 127

copy_if_exists() {
  local name="$1"
  if [[ -f "${CURRENT_OUT_DIR}/${name}" ]]; then
    cp "${CURRENT_OUT_DIR}/${name}" "${TARGET_OUT_DIR}/${name}"
  fi
}

# Baseline mínimo para mantener continuidad de F8 sin re-ejecutar pre-cut/cutover.
for f in \
  00_phase8_staging_manifest.json \
  01_phase8_release_baseline.json \
  02_phase8_prod_manifest.json \
  03_preflight.json \
  04_snapshot.json \
  05_precutover_gate.json \
  10_phase6_happy.json \
  11_phase7_happy.json \
  12_phase7b_cert.json \
  13_phase6_gate.json \
  14_phase7_gate.json \
  15_phase7b_gate.json \
  16_phase8_cutover_gate.json
do
  copy_if_exists "${f}"
done

export CURRENT_OUT_DIR TARGET_OUT_DIR REASON TS

"${PYTHON_BIN}" - <<'PY'
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

current_out_dir = os.environ["CURRENT_OUT_DIR"]
target_out_dir = os.environ["TARGET_OUT_DIR"]
reason = os.environ.get("REASON", "DAILY_GATE_FAILED")
ts = os.environ.get("TS", "")

payload = {
    "schema_version": 1,
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "event": "PHASE8_BURNIN_WINDOW_RESET",
    "reason": reason,
    "source_out_dir": current_out_dir,
    "target_out_dir": target_out_dir,
    "target_ts": ts,
}

path = os.path.join(target_out_dir, "59_phase8_window_reset.json")
with open(path, "w", encoding="utf-8") as fh:
    json.dump(payload, fh, ensure_ascii=False, indent=2, sort_keys=True)
    fh.write("\n")
PY

echo "${TARGET_OUT_DIR}"
