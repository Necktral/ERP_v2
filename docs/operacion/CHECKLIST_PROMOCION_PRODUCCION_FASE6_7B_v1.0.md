# Checklist de Promocion a Produccion (Fase 6, 7A, 7B)

Version: v1.0  
Fecha: 2026-03-08  
Estado: Listo para ejecucion (no ejecutado en este bloque)

## Alcance

Checklist para promover desde staging hacia produccion despues del cierre backend staging-first.

## 1) Precondiciones

- Staging con gates F6/F7A/F7B en verde.
- Evidencias firmadas archivadas en `docs/operacion/evidencia/`.
- Sin incidentes criticos abiertos en matriz SLA.
- Ventana de despliegue aprobada por Operacion + Contabilidad + Tecnologia.

## 2) Paridad obligatoria

- Fase 6:
  - `export_phase6_env_manifest` staging y prod objetivo.
  - `compare_phase6_env_manifests` sin drift.
- Fase 7A:
  - `export_phase7_env_manifest` staging y prod objetivo.
  - `compare_phase7_env_manifests` sin drift.
- Preflight unificado:
  - `export_staging_preflight_manifest` en prod objetivo debe pasar con umbrales aprobados.

## 3) Gate funcional por fase

- Fase 6:
  - `certify_adapter_b_run` happy y blocked validos.
  - `verify_phase6_go_live` en verde.
- Fase 7A:
  - `certify_phase7_gl_run` happy y blocked validos.
  - `verify_phase7_go_live` en verde.
- Fase 7B:
  - `certify_phase7b_consolidation` determinista.
  - `verify_phase7b_go_live` en verde.

## 4) Salud operativa

- `export_finance_operational_snapshot` en verde.
- `inbox_failed=0`.
- `outbox_failed=0` (o tolerancia aprobada en CAB con justificacion).
- `missing_lines=0`.
- `stale_revaluation=0` (en ventana de cierre mensual).
- `open_intercompany=0`.
- `disputed=0`.

## 5) Performance minima

- Ejecutar `explain_financial_queries` para scope piloto.
- Resolver scans criticos fuera de tolerancia antes de promover.

## 6) Post-promocion (obligatorio)

- Ejecutar `run_adapter_b_cycle` y `run_phase7_gl_cycle` en modo estricto.
- Ejecutar `run_intercompany_cycle` y `run_consolidated_close` para periodo piloto.
- Confirmar que no se abren excepciones bloqueantes inesperadas.
- Adjuntar evidencia post-promocion firmada.

## 7) Criterio de rollback

- Gate rojo en cualquiera de F6/F7A/F7B.
- Backlog critico de `FAILED` en print queue/outbox/inbox.
- Bloqueos contables o fiscales sin mitigacion dentro de SLA.

