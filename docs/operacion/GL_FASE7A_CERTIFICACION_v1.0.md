# Certificación Real Fase 7A — GL Core Formal (Piloto 1 Compañía)

Versión: v1.0  
Fecha: 2026-03-08  
Estado: **Operativo (staging -> producción)**

## Propósito

Ejecutar certificación real E2E de Fase 7A con:
- posting formal con `JournalEntryLine`,
- reportes financieros (`trial balance`, `general ledger`, `PnL`, `balance sheet`),
- revaluación FX,
- y gate estricto de promoción con evidencia firmada.

## 1) Paridad de entorno

Exportar manifiestos:

```bash
python manage.py export_phase7_env_manifest --company-id <COMPANY_ID> --output artifacts/phase7_staging.json
python manage.py export_phase7_env_manifest --company-id <COMPANY_ID> --output artifacts/phase7_prod.json
```

Comparar:

```bash
python manage.py compare_phase7_env_manifests --left artifacts/phase7_staging.json --right artifacts/phase7_prod.json
```

Si hay drift: **no promover**.

## 2) Certificación funcional

Happy path:

```bash
python manage.py certify_phase7_gl_run \
  --company-id <COMPANY_ID> \
  --run-id <CLOSE_RUN_ID> \
  --year <YEAR> \
  --month <MONTH> \
  --output artifacts/phase7_happy.json
```

Blocking path (revaluación bloqueada en entorno controlado):

```bash
python manage.py certify_phase7_gl_run \
  --company-id <COMPANY_ID> \
  --run-id <CLOSE_RUN_ID> \
  --year <YEAR> \
  --month <MONTH_BLOCKED> \
  --expect-blocked \
  --output artifacts/phase7_blocked.json
```

## 3) Gate de go-live

```bash
python manage.py verify_phase7_go_live \
  --company-id <COMPANY_ID> \
  --staging-manifest artifacts/phase7_staging.json \
  --prod-manifest artifacts/phase7_prod.json \
  --happy-evidence artifacts/phase7_happy.json \
  --blocked-evidence artifacts/phase7_blocked.json \
  --max-inbox-failed 0 \
  --max-outbox-failed 0 \
  --max-unbalanced-entries 0 \
  --max-missing-lines 0 \
  --max-stale-revaluation 0 \
  --output artifacts/phase7_go_live_gate.json
```

## 4) Operación continua (piloto)

```bash
python manage.py run_phase7_gl_cycle \
  --company-id <COMPANY_ID> \
  --posting-limit 500 \
  --dispatch-limit 200 \
  --max-inbox-failed 0 \
  --max-outbox-failed 0 \
  --max-unbalanced-entries 0 \
  --max-missing-lines 0 \
  --max-stale-revaluation 0
```

## 5) Comandos operativos útiles

Revaluación puntual:

```bash
python manage.py run_fx_revaluation --company-id <COMPANY_ID> --year <YEAR> --month <MONTH>
```

Export de reportes sin frontend:

```bash
python manage.py export_gl_report --company-id <COMPANY_ID> --report trial_balance --year <YEAR> --month <MONTH> --format csv --output artifacts/trial_balance.csv
python manage.py export_gl_report --company-id <COMPANY_ID> --report general_ledger --account-code 1101 --year <YEAR> --month <MONTH> --format json --output artifacts/general_ledger_1101.json
```

## 6) Evidencia firmada

Opcional HMAC:

```bash
export PHASE7_EVIDENCE_SECRET="<SECRET>"
```

Si no existe `PHASE7_EVIDENCE_SECRET`, se usa `sha256` determinista.
