#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPORTS_REL="${QA_REPORTS_DIR:-qa/reports}"
REPORTS_DIR="${ROOT_DIR}/${REPORTS_REL}"
BASE_URL="${BASE_URL:-http://localhost:8000/api}"
MODE="${1:-smoke}"

case "${MODE}" in
  smoke|rollback) ;;
  *)
    echo "Uso: $0 [smoke|rollback]" >&2
    exit 2
    ;;
esac

mkdir -p "${REPORTS_DIR}"
SUMMARY_JSON="${REPORTS_DIR}/retail_pos_pilot_${MODE}.json"
TRACE_JSON="${REPORTS_DIR}/retail_pos_pilot_${MODE}_trace.json"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "${TMP_DIR}"' EXIT

timestamp="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
checks="[]"
trace="[]"
failure_stage=""

add_check() {
  local name="$1"
  local status="$2"
  local http="$3"
  local detail="$4"
  checks="$(python3 - <<'PY' "${checks}" "${name}" "${status}" "${http}" "${detail}"
import json, sys
rows = json.loads(sys.argv[1])
rows.append({
  "name": sys.argv[2],
  "status": sys.argv[3],
  "http_status": int(sys.argv[4]) if sys.argv[4].isdigit() else None,
  "detail": sys.argv[5],
})
print(json.dumps(rows, ensure_ascii=False))
PY
)"
}

add_trace() {
  local name="$1"
  local method="$2"
  local url="$3"
  local req="${4:-}"
  local res="${5:-}"
  local http="${6:-0}"
  trace="$(python3 - <<'PY' "${trace}" "${name}" "${method}" "${url}" "${req}" "${res}" "${http}"
import json, sys
from pathlib import Path
rows = json.loads(sys.argv[1])
req_data = {}
res_data = {}
if sys.argv[5] and Path(sys.argv[5]).is_file():
  raw = Path(sys.argv[5]).read_text(encoding="utf-8").strip()
  req_data = json.loads(raw) if raw else {}
if sys.argv[6] and Path(sys.argv[6]).is_file():
  raw = Path(sys.argv[6]).read_text(encoding="utf-8").strip()
  res_data = json.loads(raw) if raw else {}
rows.append({
  "name": sys.argv[2],
  "request": {"method": sys.argv[3], "url": sys.argv[4], "payload": req_data},
  "response": {"http_status": int(sys.argv[7]) if sys.argv[7].isdigit() else None, "body": res_data},
})
print(json.dumps(rows, ensure_ascii=False))
PY
)"
}

write_outputs() {
  local status="$1"
  python3 - <<'PY' "${SUMMARY_JSON}" "${TRACE_JSON}" "${status}" "${failure_stage}" "${timestamp}" "${checks}" "${trace}"
import json, sys
from pathlib import Path
summary = {
  "status": sys.argv[3],
  "failure_stage": sys.argv[4] or None,
  "timestamp": sys.argv[5],
  "checks": json.loads(sys.argv[6]),
}
Path(sys.argv[1]).write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
Path(sys.argv[2]).write_text(json.dumps(json.loads(sys.argv[7]), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(summary, ensure_ascii=False))
PY
}

fail() {
  local stage="$1"
  local detail="$2"
  failure_stage="${stage}"
  add_check "${stage}" "failed" "${LAST_HTTP_STATUS:-0}" "${detail}"
  write_outputs "failed"
  exit 1
}

call_api() {
  local stage="$1"
  local method="$2"
  local path="$3"
  local req_file="${4:-}"
  local token="${5:-}"
  local company_id="${6:-}"
  local branch_id="${7:-}"
  local extra="${8:-}"

  LAST_RESPONSE_FILE="${TMP_DIR}/${stage}_response.json"
  local meta="${TMP_DIR}/${stage}_meta.txt"
  local url="${BASE_URL}${path}"
  local args=(-sS --retry 4 --retry-all-errors --retry-connrefused --retry-delay 1 --retry-max-time 20 -X "${method}" "${url}" -H "Accept: application/json" -w "\n%{http_code}" -o "${LAST_RESPONSE_FILE}")
  if [[ -n "${req_file}" ]]; then
    args+=(-H "Content-Type: application/json" --data "@${req_file}")
  fi
  if [[ -n "${token}" ]]; then
    args+=(-H "Authorization: Bearer ${token}")
  fi
  if [[ -n "${company_id}" ]]; then
    args+=(-H "X-Company-Id: ${company_id}")
  fi
  if [[ -n "${branch_id}" ]]; then
    args+=(-H "X-Branch-Id: ${branch_id}")
  fi
  if [[ -n "${extra}" ]]; then
    args+=(-H "${extra}")
  fi
  curl "${args[@]}" >"${meta}"
  LAST_HTTP_STATUS="$(awk 'END{print $1}' "${meta}")"
  add_trace "${stage}" "${method}" "${url}" "${req_file}" "${LAST_RESPONSE_FILE}" "${LAST_HTTP_STATUS}"
}

expect_http() {
  local expected="$1"
  local stage="$2"
  local msg="$3"
  if [[ "${LAST_HTTP_STATUS}" != "${expected}" ]]; then
    fail "${stage}" "${msg} (http=${LAST_HTTP_STATUS})"
  fi
}

echo "[qa-pos-pilot] ensure backend..."
docker compose up -d db backend >/dev/null
docker compose exec -T backend bash -lc "python /app/qa/wait_backend_ready.py" >/dev/null

echo "[qa-pos-pilot] seed scoped user/context..."
SEED="$(docker compose exec -T backend bash -lc "cd /app/backend && python manage.py shell -c '
import json, uuid
from django.contrib.auth import get_user_model
from apps.modulos.iam.models import OrgUnit, UserMembership
from apps.modulos.rbac.models import Permission, Role, RoleAssignment, RolePermission
User = get_user_model()
u = f\"qa_pos_pilot_{uuid.uuid4().hex[:8]}\"
p = \"pass12345\"
user = User.objects.create_user(username=u, email=f\"{u}@test.local\", password=p)
holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name=f\"H-{u}\")
company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name=f\"C-{u}\", parent=holding)
branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name=f\"B-{u}\", parent=company)
UserMembership.objects.create(user=user, org_unit=company, is_active=True)
UserMembership.objects.create(user=user, org_unit=branch, is_active=True)
role = Role.objects.create(name=f\"role_{uuid.uuid4().hex[:8]}\", is_active=True)
codes = [
  \"fuel.shift.open\",
  \"retail.pos.session.open\", \"retail.pos.session.read\", \"retail.pos.session.close\",
  \"retail.pos.ticket.open\", \"retail.pos.ticket.read\", \"retail.pos.ticket.checkout\", \"retail.pos.ticket.void\",
]
for code in codes:
  perm, _ = Permission.objects.get_or_create(code=code, defaults={\"description\": code, \"is_active\": True})
  if not perm.is_active:
    perm.is_active = True
    perm.save(update_fields=[\"is_active\"])
  RolePermission.objects.get_or_create(role=role, permission=perm)
RoleAssignment.objects.create(user=user, role=role, org_unit=company, is_active=True)
RoleAssignment.objects.create(user=user, role=role, org_unit=branch, is_active=True)
print(json.dumps({\"username\": u, \"password\": p, \"company_id\": company.id, \"branch_id\": branch.id}))
' " | tail -n 1)"

LOGIN_PAYLOAD="${TMP_DIR}/login_payload.json"
python3 - <<'PY' "${SEED}" "${LOGIN_PAYLOAD}"
import json, sys
seed = json.loads(sys.argv[1])
json.dump({"username": seed["username"], "password": seed["password"]}, open(sys.argv[2], "w", encoding="utf-8"))
PY
COMPANY_ID="$(python3 - <<'PY' "${SEED}"
import json, sys
print(json.loads(sys.argv[1])["company_id"])
PY
)"
BRANCH_ID="$(python3 - <<'PY' "${SEED}"
import json, sys
print(json.loads(sys.argv[1])["branch_id"])
PY
)"

call_api "login" "POST" "/auth/login/" "${LOGIN_PAYLOAD}" "" "" "" "X-Auth-Transport: header"
expect_http "200" "login" "Login failed"
TOKEN="$(python3 - <<'PY' "${LAST_RESPONSE_FILE}"
import json, sys
print(json.load(open(sys.argv[1], "r", encoding="utf-8")).get("access", ""))
PY
)"
if [[ -z "${TOKEN}" ]]; then
  fail "login" "Missing access token"
fi
add_check "login" "passed" "${LAST_HTTP_STATUS}" "JWT issued"

SHIFT_PAYLOAD="${TMP_DIR}/shift_payload.json"
echo '{"note":"pilot-pos-smoke"}' >"${SHIFT_PAYLOAD}"
call_api "open_shift" "POST" "/fuel/shifts/open/" "${SHIFT_PAYLOAD}" "${TOKEN}" "${COMPANY_ID}" "${BRANCH_ID}"
expect_http "201" "open_shift" "Fuel shift open failed"
SHIFT_ID="$(python3 - <<'PY' "${LAST_RESPONSE_FILE}"
import json, sys
print(json.load(open(sys.argv[1], "r", encoding="utf-8")).get("id", ""))
PY
)"
add_check "open_shift" "passed" "${LAST_HTTP_STATUS}" "Shift opened"

SESSION_PAYLOAD="${TMP_DIR}/session_payload.json"
echo '{"opening_amount":"25.00","note":"pilot-open"}' >"${SESSION_PAYLOAD}"
call_api "open_session" "POST" "/retail/pos/sessions/open/" "${SESSION_PAYLOAD}" "${TOKEN}" "${COMPANY_ID}" "${BRANCH_ID}"
expect_http "201" "open_session" "POS session open failed"
SESSION_ID="$(python3 - <<'PY' "${LAST_RESPONSE_FILE}"
import json, sys
print(json.load(open(sys.argv[1], "r", encoding="utf-8")).get("id", ""))
PY
)"
add_check "open_session" "passed" "${LAST_HTTP_STATUS}" "POS session opened"

TICKET_PAYLOAD="${TMP_DIR}/ticket_payload.json"
python3 - <<'PY' "${SHIFT_ID}" "${TICKET_PAYLOAD}"
import json, sys
json.dump(
  {
    "shift_id": int(sys.argv[1]),
    "idempotency_key": "pilot-ticket-001",
    "external_ref": "PILOT-001",
    "payment_method": "CASH",
  },
  open(sys.argv[2], "w", encoding="utf-8"),
)
PY
call_api "open_ticket" "POST" "/retail/pos/tickets/" "${TICKET_PAYLOAD}" "${TOKEN}" "${COMPANY_ID}" "${BRANCH_ID}"
expect_http "201" "open_ticket" "Ticket open failed"
TICKET_ID="$(python3 - <<'PY' "${LAST_RESPONSE_FILE}"
import json, sys
print(json.load(open(sys.argv[1], "r", encoding="utf-8")).get("id", ""))
PY
)"
add_check "open_ticket" "passed" "${LAST_HTTP_STATUS}" "Ticket opened"

CHECKOUT_PAYLOAD="${TMP_DIR}/checkout_payload.json"
cat >"${CHECKOUT_PAYLOAD}" <<'JSON'
{
  "line": {
    "product": "DIESEL",
    "volume": "5.0000",
    "volume_uom": "LITER",
    "unit_price_entered": "40.0000",
    "unit_price_uom": "PER_LITER",
    "metadata": {"source": "pilot"}
  }
}
JSON
call_api "checkout_ticket" "POST" "/retail/pos/tickets/${TICKET_ID}/checkout/" "${CHECKOUT_PAYLOAD}" "${TOKEN}" "${COMPANY_ID}" "${BRANCH_ID}"
expect_http "200" "checkout_ticket" "Ticket checkout failed"
add_check "checkout_ticket" "passed" "${LAST_HTTP_STATUS}" "Ticket closed"

call_api "cockpit_read" "GET" "/retail/pos/cockpit/" "" "${TOKEN}" "${COMPANY_ID}" "${BRANCH_ID}"
expect_http "200" "cockpit_read" "Cockpit read failed"
add_check "cockpit_read" "passed" "${LAST_HTTP_STATUS}" "Cockpit reachable"

if [[ "${MODE}" == "rollback" ]]; then
  VOID_PAYLOAD="${TMP_DIR}/void_payload.json"
  echo '{"reason":"PILOT_ROLLBACK"}' >"${VOID_PAYLOAD}"
  call_api "void_ticket" "POST" "/retail/pos/voids/${TICKET_ID}/" "${VOID_PAYLOAD}" "${TOKEN}" "${COMPANY_ID}" "${BRANCH_ID}"
  expect_http "200" "void_ticket" "Void failed"
  add_check "void_ticket" "passed" "${LAST_HTTP_STATUS}" "Ticket voided"
fi

CLOSE_PAYLOAD="${TMP_DIR}/close_payload.json"
echo '{"counted_amount":"25.00","note":"pilot-close"}' >"${CLOSE_PAYLOAD}"
call_api "close_session" "POST" "/retail/pos/sessions/${SESSION_ID}/close/" "${CLOSE_PAYLOAD}" "${TOKEN}" "${COMPANY_ID}" "${BRANCH_ID}"
expect_http "200" "close_session" "POS session close failed"
add_check "close_session" "passed" "${LAST_HTTP_STATUS}" "POS session closed"

write_outputs "passed"
echo "[qa-pos-pilot] ${MODE} PASS"
