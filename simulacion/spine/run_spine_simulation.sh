#!/bin/bash
# Orquesta la simulación del spine completo: (1) siembra+conduce el ciclo de negocio
# funcional vía el management command, (2) corre la carga k6 sobre los endpoints del
# spine usando el scope sembrado, (3) junta reportes. Monitoreo Grafana/InfluxDB opcional.
#
# Uso:
#   ./simulacion/spine/run_spine_simulation.sh [TAG] [VUS] [DURATION]
set -e

TAG=${1:-demo}
VUS=${2:-10}
DURATION=${3:-30s}
NETWORK_NAME="erp_crm_default"
TS=$(date +%Y%m%d_%H%M%S)
OUT="$PWD/simulacion/reports/spine_${TS}"
mkdir -p "$OUT"

echo "--- (1) Sembrando y conduciendo el spine funcional (tag=$TAG) ---"
docker compose exec -T backend python manage.py run_business_simulation \
  --tag "$TAG" --report "/tmp/spine_${TAG}.json"
docker compose cp "backend:/tmp/spine_${TAG}.json" "$OUT/functional.json" 2>/dev/null \
  || docker compose exec -T backend cat "/tmp/spine_${TAG}.json" > "$OUT/functional.json"

# Extraer company_id/branch_id del reporte funcional (etapa org_rbac).
COMPANY_ID=$(python3 -c "import json,sys; d=json.load(open('$OUT/functional.json')); s=[x for x in d['stages'] if x['stage']=='org_rbac']; print(s[0]['data'].get('company_id','') if s and 'data' in s[0] else '')" 2>/dev/null || echo "")
BRANCH_ID=$(python3 -c "import json,sys; d=json.load(open('$OUT/functional.json')); s=[x for x in d['stages'] if x['stage']=='org_rbac']; print(s[0]['data'].get('branch_id','') if s and 'data' in s[0] else '')" 2>/dev/null || echo "")
echo "scope sembrado: company_id=$COMPANY_ID branch_id=$BRANCH_ID"

if ! docker network ls | grep -q "$NETWORK_NAME"; then
  echo "Red '$NETWORK_NAME' no encontrada; levanta el backend antes de la carga k6." && exit 1
fi

echo "--- (2) Carga k6 sobre el spine (VUs=$VUS, dur=$DURATION) ---"
docker run --rm -i \
  --network "$NETWORK_NAME" \
  -v "$PWD/simulacion:/simulacion" \
  -e BASE_URL="${BASE_URL:-http://backend:8000/api}" \
  -e SPINE_USERNAME="sim_admin_${TAG}" \
  -e SPINE_PASSWORD="${SPINE_PASSWORD:-sim-pass-x}" \
  -e SPINE_COMPANY_ID="$COMPANY_ID" \
  -e SPINE_BRANCH_ID="$BRANCH_ID" \
  -e VUS_TARGET="$VUS" \
  -e SUSTAIN="$DURATION" \
  grafana/k6 run \
  --out json=/simulacion/reports/spine_${TS}/k6.json \
  /simulacion/spine/spine_load.js | tee "$OUT/k6_summary.txt"

echo "--- Spine finalizado. Reportes en: $OUT ---"
