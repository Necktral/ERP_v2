#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
MANAGE_PY="${ROOT_DIR}/backend/manage.py"
PYTEST_DB_SLOT="${PYTEST_DB_SLOT:-}"
PYTEST_DB_BASE_NAME="${PYTEST_DB_BASE_NAME:-test_erp_db}"

echo "[1/3] Verificando migraciones aplicadas..."
"${PYTHON_BIN}" "${MANAGE_PY}" migrate --check

echo "[2/3] Verificando que no existan migraciones pendientes..."
"${PYTHON_BIN}" "${MANAGE_PY}" makemigrations --check --dry-run

echo "[3/3] Verificando suites operacionales clave..."
echo "[qa] pytest test_db_slot=${PYTEST_DB_SLOT:-<auto>} test_db_base=${PYTEST_DB_BASE_NAME}"
(
  cd "${ROOT_DIR}/backend"
  PYTEST_DB_SLOT="${PYTEST_DB_SLOT}" PYTEST_DB_BASE_NAME="${PYTEST_DB_BASE_NAME}" pytest -q \
    src/tests/test_phase1_operational_contracts.py \
    src/tests/test_fuel_compensation_phase2.py \
    src/tests/test_phase5_posting_controlled.py \
    src/tests/test_phase5_accounting_api.py \
    src/apps/kernels/facturacion/tests/test_billing_accounting_integration.py \
    src/apps/kernels/inventarios/tests/test_inventory_accounting_integration.py
)

echo "Hygiene checks OK."
