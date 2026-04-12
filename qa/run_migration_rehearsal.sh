#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPORTS_REL="${QA_REPORTS_DIR:-qa/reports}"
REPORTS_DIR="${ROOT_DIR}/${REPORTS_REL}"
mkdir -p "${REPORTS_DIR}"

PLAN_FILE="${REPORTS_DIR}/migration_plan.txt"
MAKEMIGRATIONS_FILE="${REPORTS_DIR}/migration_makemigrations_check.txt"
MIGRATE_FILE="${REPORTS_DIR}/migration_migrate_apply.txt"
SHOWMIGRATIONS_FILE="${REPORTS_DIR}/migration_showmigrations.txt"
SUMMARY_FILE="${REPORTS_DIR}/migration_rehearsal_summary.json"

RUN_STARTED_AT="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
RUN_START_EPOCH="$(date +%s)"
REHEARSAL_DB_NAME="${MIGRATION_REHEARSAL_DB_NAME:-migration_rehearsal_$(date +%Y%m%d_%H%M%S)_$$}"

status="passed"
failure_step=""
makemigrations_status="skipped"
migrate_plan_status="skipped"
migrate_apply_status="skipped"
showmigrations_status="skipped"

drop_rehearsal_db() {
  docker compose exec -T db sh -lc "psql -v ON_ERROR_STOP=1 -U \"\$POSTGRES_USER\" -d postgres \
    -c \"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='${REHEARSAL_DB_NAME}' AND pid <> pg_backend_pid();\" \
    -c \"DROP DATABASE IF EXISTS \\\"${REHEARSAL_DB_NAME}\\\";\"" >/dev/null
}

cleanup() {
  drop_rehearsal_db || true
}
trap cleanup EXIT

echo "[qa] migration rehearsal start: ${RUN_STARTED_AT}"
echo "[qa] reports_dir=${REPORTS_REL}"
echo "[qa] rehearsal_db=${REHEARSAL_DB_NAME}"

docker compose up -d db backend >/dev/null
docker compose exec -T backend python /app/qa/wait_backend_ready.py >/dev/null

drop_rehearsal_db
docker compose exec -T db sh -lc "psql -v ON_ERROR_STOP=1 -U \"\$POSTGRES_USER\" -d postgres \
  -c \"CREATE DATABASE \\\"${REHEARSAL_DB_NAME}\\\";\"" >/dev/null

if docker compose exec -T backend bash -lc \
  "set -euo pipefail && cd /app/backend && python manage.py makemigrations --check --dry-run --noinput" \
  | tee "${MAKEMIGRATIONS_FILE}"; then
  makemigrations_status="passed"
else
  makemigrations_status="failed"
  status="failed"
  failure_step="makemigrations_check"
fi

if [[ "${status}" == "passed" ]]; then
  if docker compose exec -T backend bash -lc \
    "set -euo pipefail && cd /app/backend && export POSTGRES_DB='${REHEARSAL_DB_NAME}' DB_NAME='${REHEARSAL_DB_NAME}' && python manage.py migrate --plan" \
    | tee "${PLAN_FILE}"; then
    migrate_plan_status="passed"
  else
    migrate_plan_status="failed"
    status="failed"
    failure_step="migrate_plan"
  fi
fi

if [[ "${status}" == "passed" ]]; then
  if docker compose exec -T backend bash -lc \
    "set -euo pipefail && cd /app/backend && export POSTGRES_DB='${REHEARSAL_DB_NAME}' DB_NAME='${REHEARSAL_DB_NAME}' && python manage.py migrate --noinput" \
    | tee "${MIGRATE_FILE}"; then
    migrate_apply_status="passed"
  else
    migrate_apply_status="failed"
    status="failed"
    failure_step="migrate_apply"
  fi
fi

if [[ "${status}" == "passed" ]]; then
  if docker compose exec -T backend bash -lc \
    "set -euo pipefail && cd /app/backend && export POSTGRES_DB='${REHEARSAL_DB_NAME}' DB_NAME='${REHEARSAL_DB_NAME}' && python manage.py showmigrations --list" \
    | tee "${SHOWMIGRATIONS_FILE}"; then
    showmigrations_status="passed"
  else
    showmigrations_status="failed"
    status="failed"
    failure_step="showmigrations"
  fi
fi

RUN_FINISHED_AT="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
RUN_FINISH_EPOCH="$(date +%s)"
DURATION_SEC="$((RUN_FINISH_EPOCH - RUN_START_EPOCH))"

python3 - <<PY
import json
from pathlib import Path

summary = {
    "status": "${status}",
    "failure_step": "${failure_step}" or None,
    "run_started_at": "${RUN_STARTED_AT}",
    "run_finished_at": "${RUN_FINISHED_AT}",
    "duration_seconds": int(${DURATION_SEC}),
    "rehearsal_db_name": "${REHEARSAL_DB_NAME}",
    "steps": {
        "makemigrations_check": "${makemigrations_status}",
        "migrate_plan": "${migrate_plan_status}",
        "migrate_apply": "${migrate_apply_status}",
        "showmigrations": "${showmigrations_status}",
    },
    "artifacts": {
        "makemigrations_check": "${MAKEMIGRATIONS_FILE#${ROOT_DIR}/}",
        "migration_plan": "${PLAN_FILE#${ROOT_DIR}/}",
        "migrate_apply": "${MIGRATE_FILE#${ROOT_DIR}/}",
        "showmigrations": "${SHOWMIGRATIONS_FILE#${ROOT_DIR}/}",
    },
}
Path("${SUMMARY_FILE}").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\\n", encoding="utf-8")
print(f"[qa] migration rehearsal summary: ${SUMMARY_FILE}")
PY

if [[ "${status}" != "passed" ]]; then
  echo "[qa] migration rehearsal FAILED at ${failure_step}"
  exit 1
fi

echo "[qa] migration rehearsal PASSED"
exit 0
