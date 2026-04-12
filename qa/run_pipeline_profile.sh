#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROFILE_INPUT="${1:-pr}"
MAKE_BIN="${MAKE_BIN:-make}"

resolve_manifest() {
  case "$1" in
    pr|pr_default) echo "qa/manifests/pr_default.yaml" ;;
    release|release_candidate) echo "qa/manifests/release_candidate.yaml" ;;
    go_live|go_live_strict) echo "qa/manifests/go_live_strict.yaml" ;;
    rollback|rollback_rehearsal) echo "qa/manifests/rollback_rehearsal.yaml" ;;
    *) echo "$1" ;;
  esac
}

MANIFEST_REL="$(resolve_manifest "${PROFILE_INPUT}")"
MANIFEST_PATH="${ROOT_DIR}/${MANIFEST_REL}"

if [[ ! -f "${MANIFEST_PATH}" ]]; then
  echo "[qa] manifest not found: ${MANIFEST_PATH}" >&2
  exit 2
fi

read_manifest_field() {
  local key="$1"
  python3 - <<'PY' "${MANIFEST_PATH}" "${key}"
import json
import sys
from pathlib import Path

manifest_path = Path(sys.argv[1])
key = sys.argv[2]
payload = json.loads(manifest_path.read_text(encoding="utf-8"))
value = payload.get(key, "")
if isinstance(value, list):
    print(",".join(str(v) for v in value))
else:
    print(str(value))
PY
}

PROFILE_NAME="$(read_manifest_field profile)"
QA_TARGET="$(read_manifest_field qa_target)"
DEFAULT_REPORTS_DIR="$(read_manifest_field qa_reports_dir)"
DEFAULT_QA_FRESH_DB="$(read_manifest_field qa_fresh_db)"
DEFAULT_QA_KEEP_FRONTEND="$(read_manifest_field qa_keep_frontend)"
ALLOWED_OVERRIDES_CSV="$(read_manifest_field allowed_overrides)"

contains_override() {
  local var_name="$1"
  [[ ",${ALLOWED_OVERRIDES_CSV}," == *",${var_name},"* ]]
}

apply_or_validate_override() {
  local var_name="$1"
  local default_value="$2"
  local current_value="${!var_name:-}"

  if [[ -z "${current_value}" ]]; then
    export "${var_name}=${default_value}"
    return 0
  fi
  if ! contains_override "${var_name}"; then
    echo "[qa] override not allowed by manifest (${MANIFEST_REL}): ${var_name}" >&2
    exit 3
  fi
  OVERRIDES_JSON="$(python3 - <<'PY' "${OVERRIDES_JSON}" "${var_name}" "${current_value}" "${default_value}"
import json
import sys

payload = json.loads(sys.argv[1])
payload.append(
    {
        "var": sys.argv[2],
        "value": sys.argv[3],
        "default": sys.argv[4],
    }
)
print(json.dumps(payload, ensure_ascii=False))
PY
)"
}

OVERRIDES_JSON="[]"
apply_or_validate_override "QA_REPORTS_DIR" "${DEFAULT_REPORTS_DIR}"
apply_or_validate_override "QA_FRESH_DB" "${DEFAULT_QA_FRESH_DB}"
apply_or_validate_override "QA_KEEP_FRONTEND" "${DEFAULT_QA_KEEP_FRONTEND}"

export QA_PIPELINE_PROFILE="${PROFILE_NAME}"
export QA_PIPELINE_MANIFEST="${MANIFEST_REL}"
export QA_PIPELINE_OVERRIDES_JSON="${OVERRIDES_JSON}"

echo "[qa] profile=${QA_PIPELINE_PROFILE} manifest=${QA_PIPELINE_MANIFEST} target=${QA_TARGET}"
echo "[qa] overrides=${QA_PIPELINE_OVERRIDES_JSON}"

cd "${ROOT_DIR}"
"${MAKE_BIN}" "${QA_TARGET}" QA_REPORTS_DIR="${QA_REPORTS_DIR}" QA_FRESH_DB="${QA_FRESH_DB}" QA_KEEP_FRONTEND="${QA_KEEP_FRONTEND}"
