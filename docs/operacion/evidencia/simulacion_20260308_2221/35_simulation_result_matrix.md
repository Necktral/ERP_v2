# Matriz de Resultados Simulacion E2E

- Fecha UTC: 2026-03-09T04:40:41.181218+00:00
- Estado global: PASS
- Manifest hash: 9366dd093167d0f603607b7a43a8187a1ceb5484059dd1c3ef63878883920aa7

| Area | Estado | Causa raiz | Accion correctiva | ETA | Evidencia |
|---|---|---|---|---|---|
| Baseline preflight | PASS | N/A | N/A | N/A | 01_staging_preflight.json |
| F6 happy path | PASS | Flujo modo B emulado ejecutado con impresion y cierre PACKAGED. | Mantener monitoreo del ciclo run_adapter_b_cycle cada 5 min. | Operativo continuo | 12_phase6_happy.json |
| F6 blocked path | PASS | Escenario controlado de impresion fallida agota reintentos y abre contingencia bloqueante. | Escalar contingencias abiertas y limpiar backlog antes del siguiente ciclo de certificacion. | Antes de siguiente certificacion | 13_phase6_blocked.json |
| F6 go-live gate | PASS | Gate estricto aprobado con excepcion explicita blocked (failed_jobs=2, contingency_open=2). | Mantener tolerancias de blocked solo para certificacion; no usarlas en promocion sin evidencia. | Aplicado | 14_phase6_gate.json |
| F7A happy+blocked+gate | PASS | Posting controlado, lineas contables completas y bloqueo FX validado en ruta controlada. | Mantener revaluacion mensual y SoD activo para cierre. | Cierre mensual | 22_phase7_happy.json,23_phase7_blocked.json,24_phase7_gate.json |
| F7B consolidacion+gate | PASS | Consolidacion completada sin disputas ni bloqueos. | Sostener run_intercompany_cycle y run_consolidated_close en cadencia operativa. | Operativo continuo | 29_phase7b_cert.json,30_phase7b_gate.json |
| Determinismo (doble corrida) | PASS | Hashes y metricas estables en corridas consecutivas por fase. | Investigar inmediatamente cualquier drift en manifest_hash o contadores. | Inmediato ante desviacion | 15_phase6_cycle_1.json,16_phase6_cycle_2.json,25_phase7_cycle_1.json,26_phase7_cycle_2.json,29_phase7b_cert.json,31_phase7b_cert_replay.json |
| Salud operacional cierre | PASS | Thresholds criticos en verde (inbox/outbox/missing_lines/stale_revaluation/open_intercompany/disputed = 0). | Monitoreo permanente con snapshot y alertas cada 5 minutos. | Operativo continuo | 32_finance_snapshot_post.json |
| Regresion backend | PASS | Suite completa de login_module/src en verde. | Mantener gate obligatorio antes de cualquier promocion. | Aplicado | pytest -q login_module/src |
