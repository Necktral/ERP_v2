# Go-Live Fase 10 Procurement 4B (Staging)

Versión: v1.0  
Fecha: 2026-03-09  
Estado: Operativo (backend-only)

## Objetivo

Cerrar F10 en staging con:

- certificación `happy + blocked`;
- determinismo en doble corrida;
- gate estricto en verde;
- operación periódica lista (cron + evidencias firmadas).

## Scope y defaults

- Scope piloto: `company_id=5`, `branch_id=6`.
- Timezone operativa: `America/Managua`.
- Gate estricto: cero backlog crítico.
- Frontend fuera de alcance.

## Runner canónico

Script único:

```bash
./qa/run_phase10_go_live.sh {precheck|certify|cycle|gate|summary|full}
```

Hardening SRE integrado:

- resolución robusta de intérprete (`PYTHON_BIN` -> `python3` -> `python`);
- lock anti-solapamiento con `flock`;
- evidencia consolidada `30/31/32`.

## Ejecución recomendada (staging)

```bash
OUT_DIR=docs/operacion/evidencia/phase10_go_live_<TS> \
COMPANY_ID=5 BRANCH_ID=6 \
./qa/run_phase10_go_live.sh full
```

Evidencias mínimas esperadas:

- `00_phase10_precheck.json`
- `20_phase10_staging_manifest.json`
- `21_phase10_prod_manifest.json`
- `22_phase10_happy.json`
- `23_phase10_blocked.json`
- `24_phase10_cycle_<n>.json`
- `25_phase10_gate.json`
- `30_phase10_summary.json`
- `31_phase10_result_matrix.md`
- `32_phase10_summary.sha256`

## SLA y ownership

- `open_procurement_drafts > 0`: owner Compras, SLA 30 min.
- `open_procurement_blocking_exceptions > 0`: owner Contabilidad/CEC, SLA 30 min.
- `posting_failed > 0`: owner Accounting, SLA 30 min.
- `inbox_failed > 0` o `outbox_failed > 0`: owner Integración, SLA 30 min.

## Triggers de incidente

- `verify_phase10_go_live` en rojo;
- 2 ciclos consecutivos sin limpieza;
- excepción bloqueante de accounting abierta fuera de SLA.

## Playbook de mitigación

1. Ejecutar `summary` para congelar evidencia actual.
2. Ejecutar `cycle` para drenar backlog.
3. Revisar `23_phase10_blocked.json` y `26_phase10_cleanup.json`.
4. Resolver excepciones abiertas de accounting/CEC y re-ejecutar `gate`.
5. Si persiste, detener avance a F11 y abrir incidente con RCA inicial.
