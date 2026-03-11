# Go-Live Fase 4/5 — Billing/Inventory/Accounting

Versión: v1.0  
Fecha: 2026-03-11  
Estado: **Operativo (staging/piloto)**

## 1) Objetivo

Ejecutar en orden:
- Fase 4: gate de rendimiento/robustez con SLO balanceado.
- Fase 5: rollout controlado en `1 company / 1 branch` con rollback determinista.

Sin cambios breaking de API; todo aditivo y auditable.

## 2) Prerrequisitos

- Backend activo y accesible (`BASE_URL`, por defecto `http://localhost:8000/api`).
- Usuario operativo con permisos de Billing/Inventory/Accounting y 2FA deshabilitado para k6.
- Variables mínimas:
  - `COMPANY_ID`
  - `BRANCH_ID`
  - `USERNAME`
  - `PASSWORD`

## 3) Ejecución (en orden)

### Paso A — Higiene F0/F1

```bash
./qa/run_operational_hygiene_checks.sh
```

Debe validar:
- `migrate --check`
- `makemigrations --check --dry-run`
- regresión crítica (Fase 1 + Fase 2/3).

### Paso B — Gate Fase 4 (performance)

```bash
COMPANY_ID=<ID> BRANCH_ID=<ID> USERNAME=<USER> PASSWORD=<PASS> \
./qa/run_operational_performance_gate.sh
```

SLO balanceado:
- `billing_write_ms p95 <= 400ms`
- `inventory_write_ms p95 <= 400ms`
- `posting_cycle_ms p95 <= 400ms`
- `operational_error_rate <= 1%`
- sin crecimiento de `FAILED` en outbox (`BILLING`, `INVENTORY`, `ACCOUNTING`).

Evidencia:
- `snapshot_before.json`
- `k6_summary.json`
- `snapshot_after.json`
- `gate_report.json`
- `gate_report.sha256`

### Paso C — Rollout Fase 5 (piloto 1 company / 1 branch)

Etapa 1:

```bash
COMPANY_ID=<ID> BRANCH_ID=<ID> ./qa/run_operational_pilot_rollout.sh stage1
```

Etapa 2:

```bash
COMPANY_ID=<ID> BRANCH_ID=<ID> ./qa/run_operational_pilot_rollout.sh stage2
```

Etapa 3 (estabilización + intento de cierre):

```bash
COMPANY_ID=<ID> BRANCH_ID=<ID> ATTEMPT_CLOSE=1 ./qa/run_operational_pilot_rollout.sh stage3
```

Rollback determinista:

```bash
COMPANY_ID=<ID> BRANCH_ID=<ID> ./qa/run_operational_pilot_rollout.sh rollback
```

El rollback ejecuta:
- desactivación de posting (`DISABLED`) en scope piloto,
- ciclos de drenaje outbox,
- reintentos de compensación Fuel,
- snapshot final de reconciliación/outbox.

## 3.1) Gate final de go-live

Comando canónico:

```bash
python manage.py verify_operational_pilot_go_live \
  --evidence-dir <RUTA_EVIDENCIA> \
  --required-days 7 \
  --output <RUTA_EVIDENCIA>/operational_go_live_gate.json
```

El gate exige evidencia de aprobaciones:
- owner funcional en estado `APPROVED` o `FINAL_APPROVED`,
- owner técnico en estado `APPROVED` o `FINAL_APPROVED`,
- signoff final (`FINAL_APPROVED`).

Registro manual de checklist/signoff:

```bash
python manage.py record_operational_go_live_review --evidence-dir <RUTA_EVIDENCIA> --reviewer <OWNER_FUNCIONAL> --role FUNCTIONAL --status APPROVED --summary "<resumen>"
python manage.py record_operational_go_live_review --evidence-dir <RUTA_EVIDENCIA> --reviewer <OWNER_TECNICO> --role TECHNICAL --status APPROVED --summary "<resumen>"
python manage.py record_operational_go_live_review --evidence-dir <RUTA_EVIDENCIA> --reviewer <OWNER_TECNICO> --role TECHNICAL --status FINAL_APPROVED --summary "<resumen>"
```

Runner QA:

```bash
./qa/run_operational_go_live.sh verify
```

Auto-signoff opcional para QA:

```bash
AUTO_SIGNOFF=1 FUNCTIONAL_REVIEWER=<OWNER_FUNCIONAL> TECHNICAL_REVIEWER=<OWNER_TECNICO> \
./qa/run_operational_go_live.sh verify
```

Overrides de gate final (solo cuando se documenta explícitamente la excepción):

```bash
REQUIRED_DAYS=1 \
MAX_RECONCILIATION_MISMATCH=10 \
MAX_PENDING_OPERATIONAL=500 \
./qa/run_operational_go_live.sh verify
```

Excepción auditable por fuerza mayor (mundo no lineal):

```bash
python manage.py record_operational_go_live_exception \
  --evidence-dir <RUTA_EVIDENCIA> \
  --date <YYYY-MM-DD> \
  --exception-type FORCE_MAJEURE \
  --status APPROVED \
  --reported-by <RESPONSABLE_OPERATIVO> \
  --approved-by <OWNER_APROBADOR> \
  --summary "<motivo>"
```

Uso de ventana no lineal controlada en el gate final:

```bash
ALLOW_EXCUSED_DAYS=1 MAX_EXCUSED_DAYS=2 MAX_CALENDAR_DAYS=9 \
./qa/run_operational_go_live.sh verify
```

Regla:
- `ALLOW_EXCUSED_DAYS=1` permite cubrir días sin operación con excepción `FORCE_MAJEURE` aprobada.
- `MAX_EXCUSED_DAYS` limita cuántos días pueden ser excusados.
- `MAX_CALENDAR_DAYS` limita la ventana calendario consumida para completar los `required_days`.

Por defecto el runner mantiene perfil estricto (`REQUIRED_DAYS=7`, umbrales en `0`).

Ciclo completo + gate final:

```bash
COMPANY_ID=<ID> BRANCH_ID=<ID> USERNAME=<USER> PASSWORD=<PASS> \
./qa/run_operational_go_live.sh full
```

## 4) Criterio de salida

Fase 4:
- gate de performance en `PASS` y evidencia firmada (`sha256`).

Fase 5:
- `stage1`, `stage2`, `stage3` ejecutados sin blockers críticos.
- 7 días de operación estable en piloto.
- checklist de go-live aprobado por owner funcional + owner técnico y `operational_go_live_final_signoff.json` presente.

## 5) Comandos equivalentes Makefile

```bash
make qa-operational-hygiene
make qa-operational-gate COMPANY_ID=<ID> BRANCH_ID=<ID> USERNAME=<USER> PASSWORD=<PASS>
make qa-operational-pilot-stage1 COMPANY_ID=<ID> BRANCH_ID=<ID>
make qa-operational-pilot-stage2 COMPANY_ID=<ID> BRANCH_ID=<ID>
make qa-operational-pilot-stage3 COMPANY_ID=<ID> BRANCH_ID=<ID>
make qa-operational-pilot-rollback COMPANY_ID=<ID> BRANCH_ID=<ID>
```
