# GO LIVE Fase 12 Cierre Mensual Consolidado Continuo v1.0

## Objetivo

Cerrar F12 en staging con:

- operación mensual continua y reproducible;
- evidencia firmada por período;
- gate unificado en PASS (`paridad + determinismo + SLO + salud`);
- preparación de promoción a producción sin cambios de API.

## Scope y defaults

- `COMPANY_ID=5`
- `BRANCH_ID=6`
- `PARENT_COMPANY_ID=5`
- `COMPANY_IDS=5`
- `REQUIRED_PERIODS=3`
- `FX_BLOCKED_POLICY=ALERT`
- timezone operativa: `America/Managua`
- severidad de gate: cero backlog crítico

## Runner canónico

```bash
./qa/run_phase12_go_live.sh {precheck|certify|cycle|gate|summary|full}
```

Hardening SRE integrado:

- `PYTHON_BIN -> python3 -> python`
- lock anti-solapamiento con `flock`
- fail-fast en precondiciones
- evidencia única en `docs/operacion/evidencia/phase12_go_live_<TS>/`

## Ejecución recomendada (staging)

```bash
OUT_DIR=docs/operacion/evidencia/phase12_go_live_<TS> \
COMPANY_ID=5 BRANCH_ID=6 PARENT_COMPANY_ID=5 COMPANY_IDS=5 \
REQUIRED_PERIODS=3 FX_BLOCKED_POLICY=ALERT \
./qa/run_phase12_go_live.sh full
```

Artefactos esperados:

- `00_phase12_precheck.json`
- `20_phase12_staging_manifest.json`
- `21_phase12_prod_manifest.json`
- `22_phase12_monthly_close_<YYYYMM>.json` (mínimo 3 períodos)
- `23_phase12_determinism_<YYYYMM>.json`
- `24_phase12_slo_gate.json`
- `25_phase12_gate.json`
- `27_phase12_cycle_<n>.json`
- `30_phase12_summary.json`
- `31_phase12_result_matrix.md`
- `32_phase12_summary.sha256`

## Política FX (F12)

- `FX_BLOCKED_POLICY=ALERT`:
  - `revaluation=BLOCKED` no bloquea por sí sola;
  - debe generar warning trazable en evidencia.
- `FX_BLOCKED_POLICY=BLOCK`:
  - `revaluation=BLOCKED` bloquea gate final.

## SLA y ownership

- `inbox_failed/outbox_failed > 0`: owner Integración, SLA 30 min.
- `missing_lines > 0`: owner Accounting, SLA 30 min.
- `stale_revaluation > 0`: owner Accounting, SLA 30 min.
- `open/disputed intercompany > 0`: owner Contabilidad corporativa, SLA 30 min.
- `blocked_consolidation/open_consolidation_exception > 0`: owner Accounting + CEC, SLA 30 min.

## Triggers de incidente (rollback lógico)

- `verify_phase12_go_live` en rojo;
- `verify_phase12_operational_slo` en rojo;
- dos ciclos consecutivos sin limpieza;
- backlog crítico fuera de SLA.

Acciones:

1. congelar ejecución automática;
2. resolver backlog por dominio (Accounting/Integration/CEC);
3. re-ejecutar `cycle`, luego `gate`, luego `summary`;
4. documentar RCA y ETA en evidencia del día.
