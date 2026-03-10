#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODE="${1:-daily-close}"

PHASE8_START_DATE="${PHASE8_START_DATE:-2026-03-09}"
PHASE8_END_DATE="${PHASE8_END_DATE:-2026-03-22}"
TODAY_LOCAL="${TODAY_LOCAL:-$(date +%F)}"
WEEKDAY="${WEEKDAY:-$(date +%u)}" # 1..7 (Mon..Sun)
TS="${TS:-$(date +%Y%m%d_%H%M%S)}"

OUT_DIR="${OUT_DIR:-${ROOT_DIR}/docs/operacion/evidencia/phase8_go_live_20260309_1040}"
COMPANY_ID="${COMPANY_ID:-5}"
BRANCH_ID="${BRANCH_ID:-6}"
PARENT_COMPANY_ID="${PARENT_COMPANY_ID:-5}"
COMPANY_IDS="${COMPANY_IDS:-5}"
PHASE8_CALENDAR_FILE="${PHASE8_CALENDAR_FILE:-}"
EVENTUAL_REASON_CODE="${EVENTUAL_REASON_CODE:-}"
EVENTUAL_APPROVED_BY="${EVENTUAL_APPROVED_BY:-}"
EVENTUAL_NOTE="${EVENTUAL_NOTE:-}"
LOCK_ROOT="${LOCK_ROOT:-${OUT_DIR}/.locks}"

AUTO_RESET_ON_FAIL="${PHASE8_AUTO_RESET_ON_FAIL:-0}"

resolve_python() {
  if [[ -n "${PYTHON_BIN:-}" ]]; then
    if command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
      printf '%s\n' "${PYTHON_BIN}"
      return 0
    fi
    echo "[phase8-calendar] PYTHON_BIN inválido: ${PYTHON_BIN}" >&2
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
  echo "[phase8-calendar] no se encontró intérprete Python (python3/python)" >&2
  return 1
}

PYTHON_BIN="$(resolve_python)" || exit 127

if [[ ! -d "${OUT_DIR}" ]]; then
  echo "[phase8-calendar] OUT_DIR no existe: ${OUT_DIR}" >&2
  exit 2
fi

if command -v flock >/dev/null 2>&1; then
  mkdir -p "${LOCK_ROOT}"
  LOCK_FILE="${LOCK_ROOT}/phase8_calendar_${MODE}.lock"
  exec 9>"${LOCK_FILE}"
  if ! flock -n 9; then
    echo "[phase8-calendar] lock ocupado para mode=${MODE}, skip seguro"
    exit 0
  fi
fi

resolve_day_mode() {
  "${PYTHON_BIN}" - <<'PY'
from __future__ import annotations

import json
import os
from datetime import date

today_raw = str(os.environ.get("TODAY_LOCAL", "") or "").strip()
if today_raw:
    try:
        today = date.fromisoformat(today_raw)
    except Exception:
        today = date.today()
else:
    today = date.today()

weekday_raw = str(os.environ.get("WEEKDAY", "") or "").strip()
try:
    weekday = int(weekday_raw) if weekday_raw else today.isoweekday()
except Exception:
    weekday = today.isoweekday()
start = date.fromisoformat(str(os.environ.get("PHASE8_START_DATE", "2026-03-09")))
end = date.fromisoformat(str(os.environ.get("PHASE8_END_DATE", "2026-03-22")))
calendar_file = str(os.environ.get("PHASE8_CALENDAR_FILE", "") or "").strip()

def normalize_mode(raw: object) -> str:
    value = str(raw or "").strip().upper()
    if value in {"FULL", "MINIMAL", "SKIP"}:
        return value
    return ""


def parse_dates(raw):
    out = set()
    for item in raw or []:
        if isinstance(item, str):
            try:
                out.add(date.fromisoformat(item).isoformat())
            except Exception:
                continue
    return out

if calendar_file:
    try:
        with open(calendar_file, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
        if isinstance(payload, dict):
            mode = str(payload.get("mode") or "").strip().upper()
            # v2 HYBRID: manual_days override + profile semanal
            if mode == "HYBRID":
                w_start = str(payload.get("window_start") or "").strip()
                w_end = str(payload.get("window_end") or "").strip()
                try:
                    start_h = date.fromisoformat(w_start) if w_start else start
                except Exception:
                    start_h = start
                try:
                    end_h = date.fromisoformat(w_end) if w_end else end
                except Exception:
                    end_h = end

                if today < start_h or today > end_h:
                    print("SKIP")
                    raise SystemExit(0)

                manual_days = payload.get("manual_days") or {}
                if isinstance(manual_days, dict):
                    manual_mode = normalize_mode(manual_days.get(today.isoformat()))
                    if manual_mode:
                        print(manual_mode)
                        raise SystemExit(0)

                week_profile = payload.get("default_week_profile") or {}
                if isinstance(week_profile, dict):
                    weekday_name = (
                        "monday",
                        "tuesday",
                        "wednesday",
                        "thursday",
                        "friday",
                        "saturday",
                        "sunday",
                    )[today.isoweekday() - 1]
                    resolved = normalize_mode(week_profile.get(weekday_name))
                    if not resolved:
                        resolved = normalize_mode(week_profile.get(str(today.isoweekday())))
                    if resolved:
                        print(resolved)
                        raise SystemExit(0)
                print("SKIP")
                raise SystemExit(0)

            # Formato soportado:
            # 1) work_days/minimal_days como arrays de YYYY-MM-DD
            # 2) days: [{date, mode}] con mode FULL|MINIMAL
            work_days = parse_dates(payload.get("work_days"))
            minimal_days = parse_dates(payload.get("minimal_days"))
            for row in payload.get("days", []) or []:
                if not isinstance(row, dict):
                    continue
                ds = str(row.get("date") or "").strip()
                mode = str(row.get("mode") or "FULL").strip().upper()
                try:
                    parsed = date.fromisoformat(ds).isoformat()
                except Exception:
                    continue
                if mode == "MINIMAL":
                    minimal_days.add(parsed)
                else:
                    work_days.add(parsed)
            today_iso = today.isoformat()
            if today_iso in work_days:
                print("FULL")
                raise SystemExit(0)
            if today_iso in minimal_days:
                print("MINIMAL")
                raise SystemExit(0)
            print("SKIP")
            raise SystemExit(0)
    except Exception:
        # Fallback al comportamiento por ventana/weekday.
        pass

if today < start or today > end:
    print("SKIP")
elif weekday >= 6:
    print("MINIMAL")
else:
    print("FULL")
PY
}

DAY_MODE="$(resolve_day_mode)"
if [[ "${MODE}" != "final-verify" && "${MODE}" != "eventual-close" && "${DAY_MODE}" == "SKIP" ]]; then
  echo "[phase8-calendar] fuera de calendario (today=${TODAY_LOCAL}), skip"
  exit 0
fi

emit_incident() {
  local reason="$1"
  local details="$2"
  local path="${OUT_DIR}/58_phase8_incident_${TS}.json"
  "${PYTHON_BIN}" - <<'PY'
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

path = os.environ["INCIDENT_PATH"]
reason = os.environ["INCIDENT_REASON"]
details = os.environ["INCIDENT_DETAILS"]
today = os.environ["TODAY_LOCAL"]
payload = {
    "schema_version": 1,
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "date_local": today,
    "incident": reason,
    "details": details,
}
with open(path, "w", encoding="utf-8") as fh:
    json.dump(payload, fh, ensure_ascii=False, indent=2, sort_keys=True)
    fh.write("\n")
PY
  echo "${path}"
}

run_daily_close() {
  local eventual="$1"
  set +e
  OUT_DIR="${OUT_DIR}" \
  COMPANY_ID="${COMPANY_ID}" \
  BRANCH_ID="${BRANCH_ID}" \
  PARENT_COMPANY_ID="${PARENT_COMPANY_ID}" \
  COMPANY_IDS="${COMPANY_IDS}" \
  PHASE8_CALENDAR_FILE="${PHASE8_CALENDAR_FILE}" \
  DAY_MODE_RESOLVED="${DAY_MODE}" \
  TODAY_LOCAL="${TODAY_LOCAL}" \
  EVENTUAL_CLOSE_APPLIED="${eventual}" \
  EVENTUAL_REASON_CODE="${EVENTUAL_REASON_CODE}" \
  EVENTUAL_APPROVED_BY="${EVENTUAL_APPROVED_BY}" \
  EVENTUAL_NOTE="${EVENTUAL_NOTE}" \
  TS="${TS}" \
  "${ROOT_DIR}/qa/run_phase8_burnin_daily.sh"
  rc=$?
  set -e
  return "${rc}"
}

case "${MODE}" in
  day-mode)
    echo "[phase8-calendar] day=${TODAY_LOCAL} mode=${DAY_MODE}"
    ;;
  live-tick)
    if [[ "${DAY_MODE}" != "FULL" ]]; then
      echo "[phase8-calendar] día no laboral completo (${TODAY_LOCAL}) live-tick skip"
      exit 0
    fi
    OUT_DIR="${OUT_DIR}" \
    COMPANY_ID="${COMPANY_ID}" \
    BRANCH_ID="${BRANCH_ID}" \
    PHASE8_CALENDAR_FILE="${PHASE8_CALENDAR_FILE}" \
    "${ROOT_DIR}/qa/run_phase8_live_tick.sh"
    ;;
  daily-close-full)
    if [[ "${DAY_MODE}" != "FULL" ]]; then
      echo "[phase8-calendar] día no FULL (${TODAY_LOCAL}) daily-close-full skip"
      exit 0
    fi
    run_daily_close "0"
    rc=$?
    if [[ ${rc} -ne 0 ]]; then
      INCIDENT_PATH="${OUT_DIR}/58_phase8_incident_${TS}.json" \
      INCIDENT_REASON="DAILY_CLOSE_FULL_FAILED" \
      INCIDENT_DETAILS="run_phase8_burnin_daily.sh rc=${rc}" \
      TODAY_LOCAL="${TODAY_LOCAL}" \
      emit_incident "DAILY_CLOSE_FULL_FAILED" "run_phase8_burnin_daily.sh rc=${rc}" >/dev/null
      exit ${rc}
    fi
    ;;
  daily-close-minimal)
    if [[ "${DAY_MODE}" != "MINIMAL" ]]; then
      echo "[phase8-calendar] día no MINIMAL (${TODAY_LOCAL}) daily-close-minimal skip"
      exit 0
    fi
    run_daily_close "0"
    rc=$?
    if [[ ${rc} -ne 0 ]]; then
      INCIDENT_PATH="${OUT_DIR}/58_phase8_incident_${TS}.json" \
      INCIDENT_REASON="DAILY_CLOSE_MINIMAL_FAILED" \
      INCIDENT_DETAILS="run_phase8_burnin_daily.sh rc=${rc}" \
      TODAY_LOCAL="${TODAY_LOCAL}" \
      emit_incident "DAILY_CLOSE_MINIMAL_FAILED" "run_phase8_burnin_daily.sh rc=${rc}" >/dev/null
      exit ${rc}
    fi
    ;;
  daily-close)
    run_daily_close "0"
    rc=$?
    if [[ ${rc} -ne 0 ]]; then
      INCIDENT_PATH="${OUT_DIR}/58_phase8_incident_${TS}.json" \
      INCIDENT_REASON="DAILY_CLOSE_FAILED" \
      INCIDENT_DETAILS="run_phase8_burnin_daily.sh rc=${rc}" \
      TODAY_LOCAL="${TODAY_LOCAL}" \
      emit_incident "DAILY_CLOSE_FAILED" "run_phase8_burnin_daily.sh rc=${rc}" >/dev/null

      if [[ "${AUTO_RESET_ON_FAIL}" == "1" ]]; then
        new_out="$(
          OUT_DIR="${OUT_DIR}" \
          TS="${TS}" \
          REASON="DAILY_CLOSE_FAILED:${TODAY_LOCAL}" \
          "${ROOT_DIR}/qa/reset_phase8_window.sh"
        )"
        echo "[phase8-calendar] reset window created: ${new_out}"
      fi
      exit ${rc}
    fi
    ;;
  eventual-close)
    if [[ -z "${EVENTUAL_REASON_CODE}" ]]; then
      echo "[phase8-calendar] EVENTUAL_REASON_CODE es requerido" >&2
      exit 2
    fi
    if [[ -z "${EVENTUAL_APPROVED_BY}" ]]; then
      echo "[phase8-calendar] EVENTUAL_APPROVED_BY es requerido" >&2
      exit 2
    fi
    note_len="$(printf '%s' "${EVENTUAL_NOTE}" | wc -m | tr -d ' ')"
    if [[ "${note_len}" -lt 20 ]]; then
      echo "[phase8-calendar] EVENTUAL_NOTE debe tener al menos 20 caracteres" >&2
      exit 2
    fi

    run_daily_close "1"
    rc=$?

    if [[ ${rc} -ne 0 ]]; then
      INCIDENT_PATH="${OUT_DIR}/58_phase8_incident_${TS}.json" \
      INCIDENT_REASON="EVENTUAL_CLOSE_FAILED" \
      INCIDENT_DETAILS="run_phase8_burnin_daily.sh rc=${rc}" \
      TODAY_LOCAL="${TODAY_LOCAL}" \
      emit_incident "EVENTUAL_CLOSE_FAILED" "run_phase8_burnin_daily.sh rc=${rc}" >/dev/null
      exit ${rc}
    fi
    ;;
  final-verify)
    OUT_DIR="${OUT_DIR}" \
    COMPANY_ID="${COMPANY_ID}" \
    BRANCH_ID="${BRANCH_ID}" \
    PARENT_COMPANY_ID="${PARENT_COMPANY_ID}" \
    COMPANY_IDS="${COMPANY_IDS}" \
    PHASE8_CALENDAR_FILE="${PHASE8_CALENDAR_FILE}" \
    "${ROOT_DIR}/qa/run_phase8_go_live.sh" verify-burnin
    ;;
  *)
    echo "Usage: $0 {day-mode|live-tick|daily-close-full|daily-close-minimal|daily-close|eventual-close|final-verify}" >&2
    exit 2
    ;;
esac

echo "[phase8-calendar] done mode=${MODE} day=${TODAY_LOCAL} out=${OUT_DIR}"
