# Plan Maestro F1-F12 + Cierre Operativo

Version: v1.0  
Fecha: 2026-03-10  
Estado: Activo

## Objetivo

Cerrar publicacion, seguridad, recertificacion staging y preparacion de produccion para el bloque F1-F12, con evidencia firmada y gates estrictos.

## Secuencia obligatoria

1. Cierre de publicacion GitHub:
- PR `release/f6-f12-staging-pass-20260310 -> master`
- checklist de riesgos/rollback
- squash merge + tag `release-f1-f12-staging-pass-20260310`

2. Cierre de seguridad bloqueante:
- `./qa/run_bug_bounty_local.sh <ts>`
- criterio: `30_bug_bounty_summary.json` en `PASS`
- si falla: corregir y repetir

3. Re-certificacion staging pre-produccion:
- `python manage.py export_staging_preflight_manifest` (umbrales en cero)
- `python manage.py export_finance_operational_snapshot` (umbrales en cero)
- `./qa/run_post_f8_phases.sh all`
- criterio: gates F9/F10/F11/F12 en PASS y evidencia determinista

4. Preparacion go-live produccion (piloto):
- pre-corte -> cutover -> burn-in 14 dias
- rollback automatico por triggers criticos
- cierre solo con backlog critico en cero fuera de SLA

5. Operacion continua mensual:
- F12 mensual (`required_periods=3`)
- evidencia firmada por periodo
- control de salud: inbox/outbox/missing_lines/stale_revaluation/open/disputed

## Comando maestro

- `./qa/run_master_f1_f12_closure.sh all`

El comando maestro ejecuta seguridad + recertificacion staging + resumen consolidado firmado.

## Criterio de salida

- Release listo para merge.
- Seguridad en PASS.
- Staging recertificado en PASS.
- Paquete final de evidencia generado y hashado.
