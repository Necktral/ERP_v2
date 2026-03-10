# Go-Live Fase 8 Producción (Piloto 1 Sucursal)

Versión: v1.0  
Fecha: 2026-03-09  
Estado: Operativo (backend-only)

## Objetivo

Promover F6/F7A/F7B desde staging a producción con gate estricto, evidencia firmada y burn-in de 14 días.

## Scope y defaults

- Piloto: 1 sucursal.
- Ventana: laboral.
- Timezone: `America/Managua`.
- Severidad: cero backlog crítico.
- Adapter B: emulado (provider real pasa a F9).

## Pre-corte (D-2 a D-1)

1. Congelar baseline release:

```bash
python manage.py export_phase8_release_baseline \
  --company-id <COMPANY_ID> \
  --branch-id <BRANCH_ID> \
  --parent-company-id <PARENT_COMPANY_ID> \
  --company-ids <COMPANY_IDS...> \
  --backend-image <IMAGE_TAG> \
  --release-version <RELEASE_VERSION> \
  --environment production \
  --output docs/operacion/evidencia/phase8_go_live_<TS>/01_phase8_release_baseline.json
```

2. Exportar manifiesto F8 en producción y validar paridad con staging.
3. Ejecutar preflight y snapshot en umbrales estrictos.
4. Verificar seguridad vigente (Bug Bounty summary en `PASS`).
5. Ejecutar gate de pre-corte:

```bash
python manage.py verify_phase8_precutover \
  --company-id <COMPANY_ID> \
  --branch-id <BRANCH_ID> \
  --parent-company-id <PARENT_COMPANY_ID> \
  --company-ids <COMPANY_IDS...> \
  --staging-manifest <STAGING_MANIFEST> \
  --prod-manifest <PROD_MANIFEST> \
  --release-baseline <PHASE8_BASELINE> \
  --preflight-report <PREFLIGHT_JSON> \
  --snapshot-report <SNAPSHOT_JSON> \
  --security-summary <BUG_BOUNTY_SUMMARY_JSON> \
  --max-inbox-failed 0 \
  --max-outbox-failed 0 \
  --max-missing-lines 0 \
  --max-stale-revaluation 0 \
  --max-open-intercompany 0 \
  --max-disputed-intercompany 0 \
  --output docs/operacion/evidencia/phase8_go_live_<TS>/05_precutover_gate.json
```

## Cutover (ventana laboral)

1. Desplegar imagen aprobada y correr migraciones.
2. Ejecutar certificaciones happy:
   - `certify_adapter_b_run`
   - `certify_phase7_gl_run`
   - `certify_phase7b_consolidation`
3. Ejecutar gates finales:
   - `verify_phase6_go_live`
   - `verify_phase7_go_live`
   - `verify_phase7b_go_live`
4. Ejecutar certificación cutover F8:

```bash
python manage.py certify_phase8_cutover ... --output 16_phase8_cutover_gate.json
```

Si cualquier gate falla: rollback inmediato.

## Operación post-corte (burn-in 14 días)

- Cada 5 minutos:
  - `run_adapter_b_cycle`
  - `run_phase7_gl_cycle`
  - `run_intercompany_cycle`
- Diario:
  - `run_consolidated_close`
  - `run_phase8_burnin_cycle` (evidencia firmada diaria)
  - `export_finance_operational_snapshot`
- Cierre de burn-in:

```bash
python manage.py verify_phase8_burn_in \
  --evidence-dir docs/operacion/evidencia/phase8_go_live_<TS> \
  --min-days 14 \
  --max-failed-days 0 \
  --strict
```

## Rollback formal

Triggers:

- Gate rojo (`verify_*_go_live` o `certify_phase8_cutover`).
- `inbox_failed > 0` o `outbox_failed > 0` sostenido >15 min.
- `missing_lines > 0` o `stale_revaluation > 0`.
- Excepción CEC bloqueante abierta fuera de SLA.

Evaluación automática:

```bash
python manage.py evaluate_phase8_rollback \
  --cutover-report docs/operacion/evidencia/phase8_go_live_<TS>/16_phase8_cutover_gate.json \
  --burnin-reports docs/operacion/evidencia/phase8_go_live_<TS>/phase8_burn_*.json \
  --sustained-minutes 15 \
  --output docs/operacion/evidencia/phase8_go_live_<TS>/18_phase8_rollback_eval.json
```

Acciones obligatorias:

1. Deshabilitar ciclos automáticos de la sucursal piloto.
2. Revertir a versión anterior del backend.
3. Re-ejecutar manifests/preflight.
4. Emitir evidencia de incidente + RCA inicial.

## Ejecución automatizada

Script canónico:

```bash
./qa/run_phase8_go_live.sh pre-cut
./qa/run_phase8_go_live.sh cutover
./qa/run_phase8_go_live.sh burnin-day
./qa/run_phase8_go_live.sh verify-burnin
./qa/run_phase8_go_live.sh rollback-check
```

Operación diaria del burn-in (recomendada):

```bash
# Tick operativo (cada 5 minutos)
OUT_DIR=docs/operacion/evidencia/phase8_go_live_<TS_ACTIVO> \
COMPANY_ID=5 BRANCH_ID=6 \
PYTHON_BIN=python3 \
./qa/run_phase8_live_tick.sh

# Cierre diario formal (1 vez por día)
OUT_DIR=docs/operacion/evidencia/phase8_go_live_<TS_ACTIVO> \
COMPANY_ID=5 BRANCH_ID=6 PARENT_COMPANY_ID=5 COMPANY_IDS=5 \
PYTHON_BIN=python3 \
./qa/run_phase8_burnin_daily.sh
```

Hardening SRE aplicado en scripts:

- Resolución robusta de intérprete (`PYTHON_BIN`, fallback `python3/python`).
- Lock anti-solapamiento con `flock` para ejecución segura en cron.

Plantilla de cron:

```bash
cat qa/phase8_burnin.cron.example
```

Modo calendario (14 días, cierre 22-mar-2026):

```bash
# Laboral: tick continuo (cada 5 min)
OUT_DIR=docs/operacion/evidencia/phase8_go_live_<TS_ACTIVO> \
COMPANY_ID=5 BRANCH_ID=6 \
PHASE8_START_DATE=2026-03-09 PHASE8_END_DATE=2026-03-22 \
./qa/run_phase8_calendar_guard.sh live-tick

# Diario: cierre formal (incluye fin de semana)
OUT_DIR=docs/operacion/evidencia/phase8_go_live_<TS_ACTIVO> \
COMPANY_ID=5 BRANCH_ID=6 PARENT_COMPANY_ID=5 COMPANY_IDS=5 \
PHASE8_START_DATE=2026-03-09 PHASE8_END_DATE=2026-03-22 \
./qa/run_phase8_calendar_guard.sh daily-close-full
```

Regla de incidente (max_failed_days=0):

```bash
# Reinicia ventana de burn-in en un nuevo directorio de evidencia
OUT_DIR=docs/operacion/evidencia/phase8_go_live_<TS_ACTIVO> \
REASON=DAILY_GATE_FAILED \
./qa/reset_phase8_window.sh
```

Si deseas automatizar el reinicio cuando falle un cierre diario:

```bash
OUT_DIR=docs/operacion/evidencia/phase8_go_live_<TS_ACTIVO> \
COMPANY_ID=5 BRANCH_ID=6 PARENT_COMPANY_ID=5 COMPANY_IDS=5 \
PHASE8_START_DATE=2026-03-09 PHASE8_END_DATE=2026-03-22 \
PHASE8_AUTO_RESET_ON_FAIL=1 \
./qa/run_phase8_calendar_guard.sh daily-close
```
