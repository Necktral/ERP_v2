# Ejecucion Total Staging-First (Sin Frontend)

Version: v1.0  
Fecha: 2026-03-08  
Estado: Activo (backend)

## Objetivo

Cerrar operativamente Fase 6, 7A y 7B en staging con evidencia firmada, gates en verde y operacion periodica estable.  
Este bloque no incluye promocion a produccion ni trabajo de frontend.

## 1) Preflight unico

Congelar baseline y validar readiness del piloto:

```bash
python manage.py export_staging_preflight_manifest \
  --company-id <COMPANY_ID> \
  --branch-id <BRANCH_ID> \
  --max-inbox-failed 0 \
  --max-outbox-failed 0 \
  --max-missing-lines 0 \
  --max-stale-revaluation 0 \
  --max-open-intercompany 0 \
  --max-disputed 0 \
  --output docs/operacion/evidencia/staging_preflight.json
```

Validaciones clave:
- branch piloto en modo fiscal B activo;
- `phase7_enabled=true` para company piloto;
- COA activo y posting rules activas;
- salud inicial dentro de umbrales.

## 2) Cierre Fase 6 (Adapter B)

```bash
python manage.py export_phase6_env_manifest --company-id <COMPANY_ID> --branch-id <BRANCH_ID> --output docs/operacion/evidencia/phase6_staging_manifest.json
python manage.py compare_phase6_env_manifests --left docs/operacion/evidencia/phase6_staging_manifest.json --right docs/operacion/evidencia/phase6_staging_manifest.json
python manage.py certify_adapter_b_run --company-id <COMPANY_ID> --branch-id <BRANCH_ID> --output docs/operacion/evidencia/phase6_happy.json
python manage.py certify_adapter_b_run --company-id <COMPANY_ID> --branch-id <BRANCH_ID> --expect-blocked --output docs/operacion/evidencia/phase6_blocked.json
python manage.py verify_phase6_go_live --company-id <COMPANY_ID> --branch-id <BRANCH_ID> --staging-manifest docs/operacion/evidencia/phase6_staging_manifest.json --prod-manifest docs/operacion/evidencia/phase6_staging_manifest.json --happy-evidence docs/operacion/evidencia/phase6_happy.json --blocked-evidence docs/operacion/evidencia/phase6_blocked.json --output docs/operacion/evidencia/phase6_gate.json
```

Operacion periodica (cada 5 min):

```bash
python manage.py run_adapter_b_cycle --company-id <COMPANY_ID> --branch-id <BRANCH_ID> --max-inbox-failed 0 --max-outbox-failed 0 --max-failed-jobs 0 --max-retry-overdue 0 --max-stale-pending 0 --max-open-contingency 0
```

## 3) Cierre Fase 7A (GL + FX)

```bash
python manage.py export_phase7_env_manifest --company-id <COMPANY_ID> --output docs/operacion/evidencia/phase7_staging_manifest.json
python manage.py compare_phase7_env_manifests --left docs/operacion/evidencia/phase7_staging_manifest.json --right docs/operacion/evidencia/phase7_staging_manifest.json
python manage.py certify_phase7_gl_run --company-id <COMPANY_ID> --run-id <RUN_ID> --year <YEAR> --month <MONTH> --output docs/operacion/evidencia/phase7_happy.json
python manage.py certify_phase7_gl_run --company-id <COMPANY_ID> --run-id <RUN_ID> --year <YEAR> --month <MONTH_BLOCKED> --expect-blocked --output docs/operacion/evidencia/phase7_blocked.json
python manage.py verify_phase7_go_live --company-id <COMPANY_ID> --staging-manifest docs/operacion/evidencia/phase7_staging_manifest.json --prod-manifest docs/operacion/evidencia/phase7_staging_manifest.json --happy-evidence docs/operacion/evidencia/phase7_happy.json --blocked-evidence docs/operacion/evidencia/phase7_blocked.json --max-inbox-failed 0 --max-outbox-failed 0 --max-unbalanced-entries 0 --max-missing-lines 0 --max-stale-revaluation 0 --output docs/operacion/evidencia/phase7_gate.json
```

Operacion periodica (cada 5 min):

```bash
python manage.py run_phase7_gl_cycle --company-id <COMPANY_ID> --max-inbox-failed 0 --max-outbox-failed 0 --max-unbalanced-entries 0 --max-missing-lines 0 --max-stale-revaluation 0
```

## 4) Cierre Fase 7B (Intercompany + Consolidacion)

```bash
python manage.py run_intercompany_cycle --company-id <COMPANY_ID> --output docs/operacion/evidencia/phase7b_cycle.json
python manage.py run_consolidated_close --parent-company-id <PARENT_COMPANY_ID> --year <YEAR> --month <MONTH> --company-ids <C1> <C2> --output docs/operacion/evidencia/phase7b_close.json
python manage.py certify_phase7b_consolidation --parent-company-id <PARENT_COMPANY_ID> --year <YEAR> --month <MONTH> --company-ids <C1> <C2> --output docs/operacion/evidencia/phase7b_cert.json
python manage.py verify_phase7b_go_live --company-id <COMPANY_ID> --certification docs/operacion/evidencia/phase7b_cert.json --max-open-intercompany 0 --max-disputed-intercompany 0 --max-blocked-consolidation 0 --max-open-consolidation-exception 0 --max-inbox-failed 0 --max-outbox-failed 0 --output docs/operacion/evidencia/phase7b_gate.json
```

## 5) Observabilidad y performance (backend)

Snapshot operativo unificado:

```bash
python manage.py export_finance_operational_snapshot --company-id <COMPANY_ID> --branch-id <BRANCH_ID> --max-inbox-failed 0 --max-outbox-failed 0 --max-missing-lines 0 --max-stale-revaluation 0 --max-open-intercompany 0 --max-disputed 0 --output docs/operacion/evidencia/finance_snapshot.json
```

EXPLAIN de queries criticas:

```bash
python manage.py explain_financial_queries --company-id <COMPANY_ID> --branch-id <BRANCH_ID> --year <YEAR> --month <MONTH> --company-ids <C1> <C2> --max-critical-scans 0 --output docs/operacion/evidencia/finance_explain.json
```

## 6) Criterio de cierre del bloque

- F6/F7A/F7B con gates en verde.
- Evidencia JSON firmada archivada en `docs/operacion/evidencia/`.
- Dos corridas consecutivas deterministas en certificaciones.
- Operacion periodica estable sin backlog critico.

