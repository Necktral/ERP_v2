# MIGRATION ONLINE-SAFE U5 v1.0

## Objetivo

Estandarizar cambios de esquema para despliegues seguros, auditables y reversibles, sin romper contratos HTTP.

## Clasificación de riesgo (`risk_class`)

- `metadata_only`: ajustes sin impacto de lock relevante.
- `online_safe`: cambios compatibles con operación en línea.
- `backfill`: relleno de datos con ejecución controlada.
- `high_lock_risk`: cambios con potencial lock alto.
- `destructive`: elimina datos/estructura.
- `expand`: expansión compatible (primera etapa).
- `contract`: cambio contractual controlado.
- `cleanup`: limpieza posterior a transición.

## Reglas de seguridad mínimas (enforced por guard)

- Toda migración nueva/modificada debe tener metadata completa en baseline:
  - `risk_class`, `rollout_strategy`, `rollback_strategy`, `owner`, `ticket_ref`, `fingerprint`.
- Si hay `AddIndexConcurrently`, la migración debe declarar `atomic = False`.
- Si incluye `RemoveField`, `DeleteModel`, `RemoveConstraint` o `RunSQL`, no puede clasificarse como `metadata_only`.

## Estrategia recomendada `expand / migrate / contract`

1. `expand`: agregar estructura compatible.
2. `migrate`: backfill y validación de consistencia.
3. `contract`: retirar estructura legacy cuando no hay consumidores.

## Rollback y roll-forward

- `metadata_only|online_safe|expand`: preferir rollback directo si no hay datos críticos afectados.
- `backfill|high_lock_risk|contract`: preferir roll-forward con corrección controlada.
- `destructive`: requiere ventana aprobada, backup verificado y plan explícito de restauración.

## Rehearsal obligatorio antes de merge (U5-2)

```bash
make qa-migration-rehearsal QA_REPORTS_DIR=qa/reports
```

Artefactos:

- `qa/reports/migration_plan.txt`
- `qa/reports/migration_rehearsal_summary.json`

## Checklist de aprobación

- Guard de migraciones en verde (`qa-migration-safety-guard`).
- `makemigrations --check --dry-run --noinput` en verde.
- Rehearsal completo en DB efímera con estado `passed`.
- Riesgo y estrategia documentados en PR (owner + ticket).
