#!/bin/bash
set -e

# Default values
TEST_SCRIPT=${1:-auth_load_simulation.js}
VUS=${2:-5}
DURATION=${3:-30s}

echo "--- Iniciando Entorno de Monitorización (Grafana + InfluxDB) ---"
docker compose -f simulacion/docker-compose.monitoring.yaml up -d influxdb grafana

echo "esperando a influxdb..."
sleep 5

echo "--- Ejecutando Simulacion k6 ---"
echo "Script: $TEST_SCRIPT"
echo "VUs: $VUS"
echo "Duration: $DURATION"

# Determine local network for backend
# This assumes the 'erp_crm_default' network exists from the main compose project
NETWORK_NAME="erp_crm_default"

# Run k6 with InfluxDB output AND local file report
mkdir -p "$PWD/simulacion/reports"

docker run --rm -i \
  --network $NETWORK_NAME \
  -v $PWD/simulacion:/simulacion \
  -e K6_OUT=influxdb=http://influxdb:8086/k6 \
  -e BASE_URL=http://backend:8000/api \
  grafana/k6 run \
  --vus $VUS \
  --duration $DURATION \
  --out json=/simulacion/reports/report_$(date +%s).json \
  /simulacion/$TEST_SCRIPT

echo "\n--- Simulacion Finalizada ---"
echo "Reporte guardado en: simulacion/reports/"
echo "Puedes ver los resultados en Grafana: http://localhost:3000"
echo "Dashboard: K6 Load Testing Results (Login: admin/admin si pide, pero esta configurado anonimo)"
