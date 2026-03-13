# Certificación y Operación Fase 7B (Intercompany + Consolidación)

Versión: v1.0  
Fecha: 2026-03-08  
Estado: Activo (backend)

## Objetivo

Operar Fase 7B con evidencia reproducible y gates de promoción:

- ciclo intercompany transaccional;
- cierre consolidado por período;
- certificación determinista;
- gate de go-live consolidado.

## Gobernanza WRITE (obligatoria)

- Operaciones de escritura intercompany (crear, confirmar, conciliar, cerrar) requieren grant intercompany activo en modo `WRITE`.
- El grant se evalúa por contraparte (`from_company -> to_company`) y permiso:
  - `accounting.intercompany.write`
  - `accounting.intercompany.reconcile`
- Sin grant válido, la operación es rechazada por dominio.

## Comandos

1. Ciclo intercompany:

```bash
python manage.py run_intercompany_cycle --company-id <COMPANY_ID> --limit 200 --output docs/operacion/evidencia/phase7b_cycle.json
```

2. Cierre consolidado:

```bash
python manage.py run_consolidated_close --parent-company-id <PARENT_COMPANY_ID> --year 2026 --month 3 --company-ids <C1> <C2> --output docs/operacion/evidencia/phase7b_close.json
```

3. Certificación consolidación:

```bash
python manage.py certify_phase7b_consolidation --parent-company-id <PARENT_COMPANY_ID> --year 2026 --month 3 --company-ids <C1> <C2> --output docs/operacion/evidencia/phase7b_cert.json
```

4. Gate go-live:

```bash
python manage.py verify_phase7b_go_live --company-id <COMPANY_ID> --certification docs/operacion/evidencia/phase7b_cert.json --output docs/operacion/evidencia/phase7b_gate.json
```

## Criterio de cierre

- `certify_phase7b_consolidation`: `passed=true` y `deterministic_replay=true`.
- `verify_phase7b_go_live`: `go_live_passed=true`.
- Health dentro de umbrales:
  - `open_intercompany_count=0`,
  - `disputed_intercompany_count=0`,
  - `blocked_consolidation_count=0`,
  - `open_consolidation_exception_count=0`.

## Evidencia

Todos los comandos soportan salida JSON firmada con:

- `evidence_hash`
- `signature`
- `signature_type`

Variable opcional para firma HMAC:

```bash
export PHASE7B_EVIDENCE_SECRET="<secret>"
```

## Observabilidad recomendada

```bash
python manage.py export_staging_preflight_manifest --company-id <COMPANY_ID> --branch-id <BRANCH_ID> --output docs/operacion/evidencia/staging_preflight.json
python manage.py export_finance_operational_snapshot --company-id <COMPANY_ID> --branch-id <BRANCH_ID> --output docs/operacion/evidencia/finance_snapshot.json
python manage.py explain_financial_queries --company-id <COMPANY_ID> --branch-id <BRANCH_ID> --year <YEAR> --month <MONTH> --company-ids <C1> <C2> --output docs/operacion/evidencia/finance_explain.json
```
