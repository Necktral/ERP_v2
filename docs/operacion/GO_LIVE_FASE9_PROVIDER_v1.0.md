# Go-Live Fase 9 Provider (Adapter B)

Versión: v1.0  
Fecha: 2026-03-09  
Estado: Operativo (backend-only)

## Objetivo

Cerrar F9 en secuencia estricta:

1. Carril A `EMULATED` con gate estricto (cero backlog crítico).
2. Carril B `HTTP` real sobre la misma interfaz (`FiscalAdapter`) sin breaking changes.

## Scope y defaults

- Scope piloto: `company_id=5`, `branch_id=6`.
- Timezone operativa: `America/Managua`.
- Gate: `inbox_failed=0`, `outbox_failed=0`, `failed_jobs=0`, `retry_overdue=0`, `contingency_open=0`.
- Evidencia activa: `docs/operacion/evidencia/phase9_go_live_<TS>/`.

## Runner canónico

Script único:

```bash
./qa/run_phase9_go_live.sh {precheck|certify|cycle|gate|summary|full}
```

Hardening SRE incorporado:

- Resolución robusta de intérprete (`PYTHON_BIN` -> `python3` -> `python`).
- Lock anti-solapamiento (`flock`).
- Evidencia firmada/hash por corrida (`30/31/32`).

## Carril A (EMULATED)

```bash
OUT_DIR=docs/operacion/evidencia/phase9_go_live_<TS> \
COMPANY_ID=5 BRANCH_ID=6 \
F9_PROVIDER_MODE=EMULATED \
./qa/run_phase9_go_live.sh full
```

Evidencia mínima:

- `00_phase9_precheck.json`
- `09_phase9_staging_manifest.json`
- `10_phase9_prod_manifest.json`
- `11_phase9_happy.json`
- `12_phase9_blocked.json`
- `13_phase9_gate.json`
- `20_phase9_cycle_*.json`
- `30_phase9_summary.json`
- `31_phase9_result_matrix.md`
- `32_phase9_summary.sha256`

## Carril B (HTTP real)

Variables obligatorias:

- `F9_PROVIDER_MODE=HTTP`
- `F9_HTTP_BASE_URL`
- `F9_HTTP_API_KEY`
- `F9_HTTP_TIMEOUT_SECONDS` (default sugerido: `15`)
- `F9_HTTP_VERIFY_TLS` (`1`/`0`)

Ejecución:

```bash
OUT_DIR=docs/operacion/evidencia/phase9_go_live_http_<TS> \
COMPANY_ID=5 BRANCH_ID=6 \
F9_PROVIDER_MODE=HTTP \
F9_HTTP_BASE_URL=https://provider.example \
F9_HTTP_API_KEY=*** \
F9_HTTP_TIMEOUT_SECONDS=15 \
F9_HTTP_VERIFY_TLS=1 \
./qa/run_phase9_go_live.sh full
```

Si no hay URL/API key o falla contrato de provider (`test_adapter_b_provider`), el precheck falla y la corrida queda bloqueada.

## SLA y ownership

- `failed_jobs > 0` o `contingency_open > 0`: owner Facturación, SLA 30 min.
- `inbox_failed > 0` o `outbox_failed > 0`: owner Integración, SLA 30 min.
- `provider_check_ok=false`: owner Plataforma/Integración provider, SLA 15 min.
- Gate rojo (`13_phase9_gate.json`): owner de guardia debe detener promoción y abrir incidente.

## Triggers de incidente

- `verify_phase9_go_live` en rojo.
- Dos ciclos seguidos sin limpieza estricta.
- Fallas de provider repetidas fuera de SLA.

## Playbook de mitigación

1. Ejecutar `summary` para congelar evidencia actual.
2. Ejecutar `cycle` para drenar backlog.
3. Revisar `01_phase9_provider_check.txt` y `20_phase9_cycle_*.json`.
4. Si provider HTTP falla, activar contingencia explícita:
   `F9_PROVIDER_MODE=EMULATED` (solo con aprobación operativa y auditoría).
5. Re-ejecutar `gate` y registrar resultado.

