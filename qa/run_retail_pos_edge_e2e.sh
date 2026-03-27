#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPORTS_REL="${QA_REPORTS_DIR:-qa/reports}"
if [[ "${REPORTS_REL}" = /* ]]; then
  REPORTS_DIR="${REPORTS_REL}"
else
  REPORTS_DIR="${ROOT_DIR}/${REPORTS_REL}"
fi
BASE_URL="${BASE_URL:-http://localhost:8000/api}"
PROFILE="${POS_EDGE_E2E_PROFILE:-fuel}"
CONNECTOR_ID="${POS_EDGE_E2E_CONNECTOR_ID:-edge-e2e-qa}"
CONNECTOR_VERSION="${POS_EDGE_E2E_CONNECTOR_VERSION:-0.2.0}"

mkdir -p "${REPORTS_DIR}"

GUARD_JSON="${REPORTS_DIR}/retail_pos_edge_e2e_guard.json"
TRACE_JSON="${REPORTS_DIR}/retail_pos_edge_e2e_request_response.json"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "${TMP_DIR}"' EXIT

_now_utc() {
  date -u +"%Y-%m-%dT%H:%M:%SZ"
}

timestamp="$(_now_utc)"
failure_stage=""
checks_json="[]"
trace_json="[]"

add_check() {
  local name="$1"
  local status="$2"
  local http_status="$3"
  local latency_ms="$4"
  local detail="$5"
  checks_json="$(python3 - <<'PY' "${checks_json}" "${name}" "${status}" "${http_status}" "${latency_ms}" "${detail}"
import json
import sys

payload = json.loads(sys.argv[1])
payload.append(
    {
        "name": sys.argv[2],
        "status": sys.argv[3],
        "http_status": int(sys.argv[4]) if sys.argv[4].isdigit() else None,
        "latency_ms": int(sys.argv[5]) if sys.argv[5].isdigit() else None,
        "detail": sys.argv[6],
    }
)
print(json.dumps(payload, ensure_ascii=False))
PY
)"
}

add_trace() {
  local name="$1"
  local method="$2"
  local url="$3"
  local request_payload_file="$4"
  local response_body_file="$5"
  local http_status="$6"
  local latency_ms="$7"
  trace_json="$(python3 - <<'PY' "${trace_json}" "${name}" "${method}" "${url}" "${request_payload_file}" "${response_body_file}" "${http_status}" "${latency_ms}"
import json
import sys
from pathlib import Path

payload = json.loads(sys.argv[1])
req_path = Path(sys.argv[5])
res_path = Path(sys.argv[6])
request_data = {}
response_data = {}
if req_path.exists():
    if req_path.is_file():
        raw = req_path.read_text(encoding="utf-8").strip()
        request_data = json.loads(raw) if raw else {}
if res_path.exists():
    if res_path.is_file():
        raw = res_path.read_text(encoding="utf-8").strip()
        response_data = json.loads(raw) if raw else {}
payload.append(
    {
        "name": sys.argv[2],
        "request": {
            "method": sys.argv[3],
            "url": sys.argv[4],
            "payload": request_data,
        },
        "response": {
            "http_status": int(sys.argv[7]) if sys.argv[7].isdigit() else None,
            "latency_ms": int(sys.argv[8]) if sys.argv[8].isdigit() else None,
            "body": response_data,
        },
    }
)
print(json.dumps(payload, ensure_ascii=False))
PY
)"
}

write_outputs() {
  local status="$1"
  python3 - <<'PY' "${GUARD_JSON}" "${TRACE_JSON}" "${status}" "${failure_stage}" "${timestamp}" "${checks_json}" "${trace_json}"
import json
import sys
from pathlib import Path

guard_path = Path(sys.argv[1])
trace_path = Path(sys.argv[2])
status = sys.argv[3]
failure_stage = sys.argv[4]
timestamp = sys.argv[5]
checks = json.loads(sys.argv[6])
trace = json.loads(sys.argv[7])

guard = {
    "status": status,
    "failure_stage": failure_stage or None,
    "timestamp": timestamp,
    "checks": checks,
}
guard_path.write_text(json.dumps(guard, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
trace_path.write_text(json.dumps(trace, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(guard, ensure_ascii=False))
PY
}

fail() {
  local stage="$1"
  local detail="$2"
  failure_stage="${stage}"
  add_check "${stage}" "failed" "${LAST_HTTP_STATUS:-0}" "${LAST_LATENCY_MS:-0}" "${detail}"
  write_outputs "failed"
  exit 1
}

require_http() {
  local expected="$1"
  local stage="$2"
  local detail="$3"
  if [[ "${LAST_HTTP_STATUS}" != "${expected}" ]]; then
    fail "${stage}" "${detail} (http=${LAST_HTTP_STATUS})"
  fi
}

call_api() {
  local stage="$1"
  local method="$2"
  local path="$3"
  local payload_file="$4"
  local auth_token="$5"
  local company_id="$6"
  local branch_id="$7"
  local extra_header="${8:-}"

  local response_file="${TMP_DIR}/${stage}_response.json"
  local headers_file="${TMP_DIR}/${stage}_headers.txt"
  local meta_file="${TMP_DIR}/${stage}_meta.txt"
  local url="${BASE_URL}${path}"
  local args=(
    -sS
    --retry 6
    --retry-all-errors
    --retry-connrefused
    --retry-delay 1
    --retry-max-time 25
    -X "${method}"
    "${url}"
    -H "Accept: application/json"
    -w "\n%{http_code} %{time_total}"
    -o "${response_file}"
    -D "${headers_file}"
  )
  if [[ -n "${payload_file}" ]]; then
    args+=(-H "Content-Type: application/json" --data "@${payload_file}")
  fi
  if [[ -n "${auth_token}" ]]; then
    args+=(-H "Authorization: Bearer ${auth_token}")
  fi
  if [[ -n "${company_id}" ]]; then
    args+=(-H "X-Company-Id: ${company_id}")
  fi
  if [[ -n "${branch_id}" ]]; then
    args+=(-H "X-Branch-Id: ${branch_id}")
  fi
  if [[ -n "${extra_header}" ]]; then
    args+=(-H "${extra_header}")
  fi
  curl "${args[@]}" >"${meta_file}"

  LAST_HTTP_STATUS="$(awk 'END{print $1}' "${meta_file}")"
  local raw_time
  raw_time="$(awk 'END{print $2}' "${meta_file}")"
  LAST_LATENCY_MS="$(python3 - <<'PY' "${raw_time}"
import sys
try:
    print(int(float(sys.argv[1]) * 1000))
except Exception:
    print(0)
PY
)"
  LAST_RESPONSE_FILE="${response_file}"
  LAST_HEADERS_FILE="${headers_file}"
  LAST_URL="${url}"
  add_trace "${stage}" "${method}" "${url}" "${payload_file}" "${response_file}" "${LAST_HTTP_STATUS}" "${LAST_LATENCY_MS}"
}

resolve_secret_b64() {
  if [[ -n "${POS_EDGE_E2E_SECRET_B64:-}" ]]; then
    echo "${POS_EDGE_E2E_SECRET_B64}"
    return 0
  fi
  local env_file="${ROOT_DIR}/.env"
  if [[ -f "${env_file}" ]]; then
    local from_env
    from_env="$(awk -F= '/^POS_EDGE_CONNECTOR_SHARED_SECRET=/{print $2; exit}' "${env_file}" | tr -d '"' | tr -d "'")"
    if [[ -n "${from_env}" ]]; then
      echo "${from_env}"
      return 0
    fi
  fi
  echo "ZWRnZS1zZWNyZXQ="
  return 0
}

echo "[qa-edge-e2e] ensuring backend is running..."
docker compose up -d db backend >/dev/null
docker compose exec -T backend bash -lc "python /app/qa/wait_backend_ready.py" >/dev/null

echo "[qa-edge-e2e] provisioning minimal org/user context..."
SEED_JSON="$(docker compose exec -T backend bash -lc "cd /app/backend && python manage.py shell -c '
import json, uuid
from django.contrib.auth import get_user_model
from apps.modulos.iam.models import OrgUnit, UserMembership
from apps.modulos.rbac.models import Permission, Role, RoleAssignment, RolePermission
User = get_user_model()
u = f\"qa_edge_{uuid.uuid4().hex[:10]}\"
p = \"pass12345\"
user = User.objects.create_user(username=u, email=f\"{u}@test.local\", password=p)
holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name=f\"H-{u}\")
company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name=f\"C-{u}\", parent=holding)
branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name=f\"B-{u}\", parent=company)
UserMembership.objects.create(user=user, org_unit=company, is_active=True)
UserMembership.objects.create(user=user, org_unit=branch, is_active=True)
role = Role.objects.create(name=f\"role_{uuid.uuid4().hex[:8]}\", is_active=True)
for code in [\"retail.pos.peripherals.manage\", \"retail.pos.peripherals.read\"]:
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
python3 - <<'PY' "${SEED_JSON}" "${LOGIN_PAYLOAD}"
import json
import sys

seed = json.loads(sys.argv[1])
payload = {"username": seed["username"], "password": seed["password"]}
with open(sys.argv[2], "w", encoding="utf-8") as fh:
    json.dump(payload, fh)
PY

COMPANY_ID="$(python3 - <<'PY' "${SEED_JSON}"
import json, sys
print(json.loads(sys.argv[1])["company_id"])
PY
)"
BRANCH_ID="$(python3 - <<'PY' "${SEED_JSON}"
import json, sys
print(json.loads(sys.argv[1])["branch_id"])
PY
)"

echo "[qa-edge-e2e] login..."
call_api "login" "POST" "/auth/login/" "${LOGIN_PAYLOAD}" "" "" "" "X-Auth-Transport: header"
require_http "200" "login" "Login failed"
ACCESS_TOKEN="$(python3 - <<'PY' "${LAST_RESPONSE_FILE}"
import json, sys
data = json.load(open(sys.argv[1], "r", encoding="utf-8"))
print(data.get("access", ""))
PY
)"
if [[ -z "${ACCESS_TOKEN}" ]]; then
  ACCESS_TOKEN="$(python3 - <<'PY' "${LAST_HEADERS_FILE}"
import re
import sys

raw = open(sys.argv[1], "r", encoding="utf-8").read()
for line in raw.splitlines():
    if line.lower().startswith("set-cookie:"):
        cookie = line.split(":", 1)[1].strip()
        match = re.match(r"nt_access=([^;]+)", cookie)
        if match:
            print(match.group(1))
            raise SystemExit(0)
print("")
PY
)"
fi
if [[ -z "${ACCESS_TOKEN}" ]]; then
  fail "login" "Access token missing in login response/cookies"
fi
add_check "login" "passed" "${LAST_HTTP_STATUS}" "${LAST_LATENCY_MS}" "JWT token issued"

echo "[qa-edge-e2e] issuing challenge..."
CHALLENGE_PAYLOAD="${TMP_DIR}/challenge_payload.json"
python3 - <<'PY' "${CHALLENGE_PAYLOAD}" "${CONNECTOR_ID}" "${CONNECTOR_VERSION}"
import json, sys
json.dump(
    {
        "connector_id": sys.argv[2],
        "connector_version": sys.argv[3],
        "metadata": {"source": "qa-retail-pos-edge-e2e"},
    },
    open(sys.argv[1], "w", encoding="utf-8"),
)
PY
call_api "challenge_happy" "POST" "/retail/pos/peripherals/edge/challenge/" "${CHALLENGE_PAYLOAD}" "${ACCESS_TOKEN}" "${COMPANY_ID}" "${BRANCH_ID}"
require_http "201" "challenge_happy" "Challenge creation failed"
CHALLENGE_ID="$(python3 - <<'PY' "${LAST_RESPONSE_FILE}"
import json, sys
print(json.load(open(sys.argv[1], "r", encoding="utf-8")).get("challenge_id", ""))
PY
)"
NONCE="$(python3 - <<'PY' "${LAST_RESPONSE_FILE}"
import json, sys
print(json.load(open(sys.argv[1], "r", encoding="utf-8")).get("nonce", ""))
PY
)"
if [[ -z "${CHALLENGE_ID}" || -z "${NONCE}" ]]; then
  fail "challenge_happy" "Challenge response missing challenge_id/nonce"
fi
add_check "challenge_happy" "passed" "${LAST_HTTP_STATUS}" "${LAST_LATENCY_MS}" "Challenge issued"

SECRET_B64="$(resolve_secret_b64)"
if [[ -z "${SECRET_B64}" ]]; then
  fail "secret_resolution" "POS_EDGE_CONNECTOR_SHARED_SECRET missing and no fallback available"
fi

echo "[qa-edge-e2e] posting handshake happy path..."
HANDSHAKE_PAYLOAD="${TMP_DIR}/handshake_payload.json"
python3 "${ROOT_DIR}/qa/simulate_retail_pos_edge.py" \
  --challenge-id "${CHALLENGE_ID}" \
  --nonce "${NONCE}" \
  --company-id "${COMPANY_ID}" \
  --branch-id "${BRANCH_ID}" \
  --connector-id "${CONNECTOR_ID}" \
  --connector-version "${CONNECTOR_VERSION}" \
  --secret-b64 "${SECRET_B64}" \
  --profile "${PROFILE}" \
  --output "${HANDSHAKE_PAYLOAD}" >/dev/null

call_api "handshake_happy" "POST" "/retail/pos/peripherals/edge/handshake/" "${HANDSHAKE_PAYLOAD}" "${ACCESS_TOKEN}" "${COMPANY_ID}" "${BRANCH_ID}"
require_http "201" "handshake_happy" "Handshake happy path failed"
DEVICES_SYNCED="$(python3 - <<'PY' "${LAST_RESPONSE_FILE}"
import json, sys
data = json.load(open(sys.argv[1], "r", encoding="utf-8"))
print(data.get("devices_synced", 0))
PY
)"
if [[ "${DEVICES_SYNCED}" -lt 1 ]]; then
  fail "handshake_happy" "devices_synced must be >= 1"
fi
add_check "handshake_happy" "passed" "${LAST_HTTP_STATUS}" "${LAST_LATENCY_MS}" "Handshake accepted"

echo "[qa-edge-e2e] validating capabilities..."
call_api "capabilities_happy" "GET" "/retail/pos/peripherals/capabilities/" "" "${ACCESS_TOKEN}" "${COMPANY_ID}" "${BRANCH_ID}"
require_http "200" "capabilities_happy" "Capabilities endpoint failed"
python3 - <<'PY' "${LAST_RESPONSE_FILE}"
import json, sys
data = json.load(open(sys.argv[1], "r", encoding="utf-8"))
registry = data.get("registry") or {}
if "THERMAL_PRINTER" not in registry:
    raise SystemExit(1)
if not data.get("count", 0):
    raise SystemExit(1)
PY
if [[ $? -ne 0 ]]; then
  fail "capabilities_happy" "Capabilities registry missing THERMAL_PRINTER or count==0"
fi
add_check "capabilities_happy" "passed" "${LAST_HTTP_STATUS}" "${LAST_LATENCY_MS}" "Capabilities consistent"

echo "[qa-edge-e2e] validating bad-signature rejection..."
call_api "challenge_bad_signature" "POST" "/retail/pos/peripherals/edge/challenge/" "${CHALLENGE_PAYLOAD}" "${ACCESS_TOKEN}" "${COMPANY_ID}" "${BRANCH_ID}"
require_http "201" "challenge_bad_signature" "Challenge for bad-signature scenario failed"
BAD_CHALLENGE_ID="$(python3 - <<'PY' "${LAST_RESPONSE_FILE}"
import json, sys
print(json.load(open(sys.argv[1], "r", encoding="utf-8")).get("challenge_id", ""))
PY
)"
BAD_NONCE="$(python3 - <<'PY' "${LAST_RESPONSE_FILE}"
import json, sys
print(json.load(open(sys.argv[1], "r", encoding="utf-8")).get("nonce", ""))
PY
)"
if [[ -z "${BAD_CHALLENGE_ID}" || -z "${BAD_NONCE}" ]]; then
  fail "challenge_bad_signature" "Missing challenge_id/nonce for bad-signature scenario"
fi

BAD_SIGNATURE_PAYLOAD="${TMP_DIR}/bad_signature_payload.json"
python3 "${ROOT_DIR}/qa/simulate_retail_pos_edge.py" \
  --challenge-id "${BAD_CHALLENGE_ID}" \
  --nonce "${BAD_NONCE}" \
  --company-id "${COMPANY_ID}" \
  --branch-id "${BRANCH_ID}" \
  --connector-id "${CONNECTOR_ID}" \
  --connector-version "${CONNECTOR_VERSION}" \
  --secret-b64 "${SECRET_B64}" \
  --profile "${PROFILE}" \
  --output "${BAD_SIGNATURE_PAYLOAD}" >/dev/null
python3 - <<'PY' "${BAD_SIGNATURE_PAYLOAD}"
import base64
import json
import sys
path = sys.argv[1]
data = json.load(open(path, "r", encoding="utf-8"))
data["signature"] = base64.b64encode(b"bad-signature").decode("utf-8")
with open(path, "w", encoding="utf-8") as fh:
    json.dump(data, fh)
PY

call_api "handshake_bad_signature" "POST" "/retail/pos/peripherals/edge/handshake/" "${BAD_SIGNATURE_PAYLOAD}" "${ACCESS_TOKEN}" "${COMPANY_ID}" "${BRANCH_ID}"
require_http "401" "handshake_bad_signature" "Bad signature should be rejected with 401"
BAD_CODE="$(python3 - <<'PY' "${LAST_RESPONSE_FILE}"
import json, sys
data = json.load(open(sys.argv[1], "r", encoding="utf-8"))
print(data.get("error_code", ""))
PY
)"
if [[ "${BAD_CODE}" != "BAD_SIGNATURE" ]]; then
  fail "handshake_bad_signature" "Expected error_code BAD_SIGNATURE, got ${BAD_CODE:-<empty>}"
fi
add_check "handshake_bad_signature" "passed" "${LAST_HTTP_STATUS}" "${LAST_LATENCY_MS}" "Stable rejection BAD_SIGNATURE"

write_outputs "passed"
echo "[qa-edge-e2e] PASS"
