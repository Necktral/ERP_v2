## Estado de Ejecucion Backend (Staging First) — 2026-03-10

Este documento mantiene el estado operativo ejecutivo del proyecto.
El blueprint arquitectonico completo vive en:

- [ARQUITECTURA_DOMINIO_Y_CONTROL_v1.0.md](ARQUITECTURA_DOMINIO_Y_CONTROL_v1.0.md)

## Estado por fase (real)

- Fase 1 (Nucleo disciplinado): implementada en backend.
- Fase 2 (Contratos canonicos + event backbone): implementada en backend.
- Fase 3 (CEC operativo D+0): implementada en backend.
- Fase 4 (Shadow Ledger): cerrada con certificacion y gates.
- Fase 5 (Posting controlado): implementada con SoD, cierre de periodo y reversas.
- Fase 6 (Adapter B readiness): cerrada en staging.
- Fase 7A (GL formal + FX): cerrada en staging.
- Fase 7B (Intercompany + consolidacion): cerrada en staging.
- Fase 8 (Go-live controlado): cerrada con burn-in `14/14` y sign-off contador PASS.
- Fase 9 (Adapter B provider): cerrada en staging en carriles `EMULATED` y `HTTP`.
- Fase 10 (Procurement 4B): cerrada en staging con gate estricto.
- Fase 11 (Intercompany avanzado): cerrada en staging con gate estricto.
- Fase 12 (Cierre mensual continuo): cerrada en staging (`required_periods=3`, SLO PASS, gate PASS).

## Toolchain operativo activo (backend-only)

- Fase 8:
  - `verify_phase8_precutover`
  - `evaluate_phase8_rollback`
  - `run_phase8_go_live.sh`
- Fase 9:
  - `export_phase9_env_manifest`
  - `compare_phase9_env_manifests`
  - `certify_adapter_b_provider_run`
  - `verify_phase9_go_live`
  - `run_adapter_b_provider_cycle`
  - `qa/run_phase9_go_live.sh`
- Fase 10:
  - `export_phase10_env_manifest`
  - `certify_phase10_procurement_run`
  - `verify_phase10_go_live`
  - `run_phase10_procurement_cycle`
  - `qa/run_phase10_go_live.sh`
- Fase 11:
  - `export_phase11_env_manifest`
  - `compare_phase11_env_manifests`
  - `certify_phase11_intercompany_sla`
  - `verify_phase11_go_live`
  - `run_phase11_intercompany_cycle`
  - `qa/run_phase11_go_live.sh`
- Fase 12:
  - `export_phase12_env_manifest`
  - `compare_phase12_env_manifests`
  - `run_phase12_monthly_close`
  - `certify_phase12_monthly_determinism`
  - `verify_phase12_operational_slo`
  - `verify_phase12_go_live`
  - `qa/run_phase12_go_live.sh`

## Cierre operativo del release F1-F12

- Rama release publicada: `release/f6-f12-staging-pass-20260310`.
- Checklist de publicacion activa: `docs/operacion/BASELINE_RELEASE_F6_F12_20260310.md`.
- Runner maestro de cierre: `qa/run_master_f1_f12_closure.sh`.

## Pendientes para produccion (sin frontend)

- Cierre de seguridad bloqueante en PASS (`bug_bounty_local` sin hallazgos bloqueantes ni leaks activos).
- Re-certificacion staging pre-produccion con paquete firmado final.
- Cutover productivo controlado (piloto 1 sucursal) + burn-in 14 dias.
- Operacion mensual continua F12 en productivo con evidencia historica.

## Scope y decisiones vigentes

- Frontend fuera de alcance funcional en este bloque.
- Politica de cambios: aditivos, sin breaking changes.
- Timezone operativa de referencia: `America/Managua`.
