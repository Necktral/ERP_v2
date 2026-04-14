# Documentación Operacional

Versión: v1.0  
Fecha: 2026-02-09  
Estado: **Guía operativa (viva)**

## Propósito

Esta sección contiene documentación de **operación del negocio** (playbooks, plantillas y checklists) para ejecutar procesos con disciplina y trazabilidad.

- Está pensada para uso diario (ventas, compras, logística, compliance).
- No reemplaza los contratos técnicos del sistema (auditoría, RBAC, sync), pero puede referenciarlos cuando aplique.

## Índices

- [Importación / Exportación (Import-Export & Sourcing)](import_export/README.md)
- [Templates Import/Export](import_export/templates/README.md)
- [Rotación de secretos](ROTACION_SECRETOS_v1.0.md)
- [CD Deploy (VPS + Docker Compose)](CD_DEPLOY_v1.0.md)
- [Certificación real Fase 4A (Shadow Ledger)](SHADOW_LEDGER_FASE4A_CERTIFICACION_v1.0.md)
- [Certificación real Fase 6 (Adapter B)](ADAPTER_B_FASE6_CERTIFICACION_v1.0.md)
- [Certificación real Fase 7A (GL Core)](GL_FASE7A_CERTIFICACION_v1.0.md)
- [Certificación real Fase 7B (Intercompany + Consolidación)](GL_FASE7B_INTERCOMPANY_CONSOLIDACION_v1.0.md)
- [Ejecución total Staging-First](STAGING_FIRST_EJECUCION_TOTAL_v1.0.md)
- [Matriz Ownership/SLA Fase 6-7B](MATRIZ_OWNERSHIP_SLA_FASE6_7B_v1.0.md)
- [Checklist promoción a producción Fase 6-7B](CHECKLIST_PROMOCION_PRODUCCION_FASE6_7B_v1.0.md)
- [Bug Bounty Local (sin sync remoto)](BUG_BOUNTY_LOCAL_v1.0.md)
- [Go-Live Fase 8 Producción (piloto)](GO_LIVE_FASE8_PRODUCCION_v1.0.md)
- [Go-Live Fase 9 Provider (Adapter B)](GO_LIVE_FASE9_PROVIDER_v1.0.md)
- [Go-Live Fase 10 Procurement 4B (staging)](GO_LIVE_FASE10_PROCUREMENT_v1.0.md)
- [Go-Live Fase 11 Intercompany Avanzado (staging)](GO_LIVE_FASE11_INTERCOMPANY_AVANZADO_v1.0.md)
- [Go-Live Fase 12 Cierre Mensual Continuo (staging)](GO_LIVE_FASE12_CIERRE_MENSUAL_CONTINUO_v1.0.md)
- [Go-Live Fase 4/5 Billing-Inventory (staging/piloto)](GO_LIVE_BILLING_INVENTORY_F4_F5_v1.0.md)
- [Runbook Reporting R8 (gobierno + observabilidad)](REPORTING_R8_GOBIERNO_OBSERVABILIDAD_v1.0.md)
- [Runbook U6 Release Governance + Supply Chain](U6_RELEASE_GOVERNANCE_SUPPLY_CHAIN_v1.0.md)
- [Gobernanza Codex + handoff estructurado](CODEX_GOVERNANCE_HANDOFF_v1.0.md)
- [CODEX Master Pack v1.0 (source of truth operativo para delegacion)](CODEX_MASTER_PACK_v1.0.md)
- [RCA de alertas Release/QA](ALERTAS_RCA_RELEASE_QA_v1.0.md)
- [Retail POS Spine Slice v1.0](RETAIL_POS_SPINE_SLICE_v1.0.md)
- [Centro de Operación Unificada (COU) Multidispositivo v1.0](COU_MULTIDISPOSITIVO_v1.0.md)
- [Norma Interna Multidispositivo (Producto, UX y Gobernanza) v1.0](NORMA_GOBERNANZA_MULTIDISPOSITIVO_v1.0.md)
- [Norma Interna de Diseño y Operación del Sistema Web Empresarial v1.0](NORMA_DISENO_OPERACION_SISTEMA_EMPRESARIAL_v1.0.md)
- [Diseño Empresarial Multidispositivo ERP/CRM (internet-first) v1.0](DISENO_EMPRESARIAL_MULTIDISPOSITIVO_ERP_CRM_v1.0.md)
- [Arquitectura de Implementación Multidispositivo (Frontend + Backend) v1.0](ARQUITECTURA_IMPLEMENTACION_MULTIDISPOSITIVO_v1.0.md)
- [Diseño de Inventario Multidispositivo (core operacional) v1.0](INVENTARIO_MULTIDISPOSITIVO_v1.0.md)
- [Diseño de Facturación Multidispositivo (internet-first) v1](FACTURACION_MULTIDISPOSITIVO_v1.0.md)
- [Diseño de Estación de Servicios Multidispositivo (internet-first) v1](ESTACION_SERVICIOS_MULTIDISPOSITIVO_v1.0.md)
- [Diseño de Reporting y Dashboards Multidispositivo (internet-first) v1.0](REPORTING_DASHBOARDS_MULTIDISPOSITIVO_v1.0.md)
- [Contratos Funcionales Compartidos Laptop/Móvil (ERP Web) v1.0](CONTRATOS_FUNCIONALES_COMPARTIDOS_LAPTOP_MOVIL_v1.0.md)
- [Backlog Profesional Multidispositivo (Inventarios, Facturación, Estación, Reportes, Dashboard) v1.0](BACKLOG_MULTIDISPOSITIVO_INVENTARIO_FACTURACION_ESTACION_REPORTING_DASHBOARD_v1.0.md)
- [Prompts adaptados al stack real (Quasar/Vue/Pinia + Django/DRF)](PROMPTS_STACK_REAL.md)
- [Plan maestro F1-F12 + cierre operativo](PLAN_MAESTRO_F1_F12_CIERRE_OPERATIVO_v1.0.md)
- [Checklist PR release F1-F12](PR_RELEASE_F1_F12_CHECKLIST.md)

## Set canónico multidispositivo (orden recomendado)

1. [CODEX Master Pack v1.0 (source of truth operativo)](CODEX_MASTER_PACK_v1.0.md)
2. [Diseño Empresarial Multidispositivo ERP/CRM (internet-first) v1.0](DISENO_EMPRESARIAL_MULTIDISPOSITIVO_ERP_CRM_v1.0.md)
3. [Norma Interna de Diseño y Operación del Sistema Web Empresarial v1.0](NORMA_DISENO_OPERACION_SISTEMA_EMPRESARIAL_v1.0.md)
4. [Arquitectura de Implementación Multidispositivo (Frontend + Backend) v1.0](ARQUITECTURA_IMPLEMENTACION_MULTIDISPOSITIVO_v1.0.md)
5. [Contratos Funcionales Compartidos Laptop/Móvil (ERP Web) v1.0](CONTRATOS_FUNCIONALES_COMPARTIDOS_LAPTOP_MOVIL_v1.0.md)
6. [Backlog Profesional Multidispositivo (Inventarios, Facturación, Estación, Reportes, Dashboard) v1.0](BACKLOG_MULTIDISPOSITIVO_INVENTARIO_FACTURACION_ESTACION_REPORTING_DASHBOARD_v1.0.md)
7. Diseños de módulo:
   - [Inventario Multidispositivo v1.0](INVENTARIO_MULTIDISPOSITIVO_v1.0.md)
   - [Facturación Multidispositivo v1.0](FACTURACION_MULTIDISPOSITIVO_v1.0.md)
   - [Estación de Servicios Multidispositivo v1.0](ESTACION_SERVICIOS_MULTIDISPOSITIVO_v1.0.md)
   - [Reporting y Dashboards Multidispositivo v1.0](REPORTING_DASHBOARDS_MULTIDISPOSITIVO_v1.0.md)

Soporte de delegación (no canónico):
- [Prompts adaptados al stack real](PROMPTS_STACK_REAL.md)
- [Gobernanza Codex + handoff estructurado](CODEX_GOVERNANCE_HANDOFF_v1.0.md)

## Reglas

- Todo en español.
- Documentos cortos, accionables y versionados (título + versión + fecha).
- Plantillas deben ser “copiables”: incluir campos obligatorios y checklist.
- La evidencia operativa pesada en `docs/operacion/evidencia/` no se versiona en GitHub; se mantiene como artefacto local/CI con hash y firma.

## Changelog

- 2026-01-28: Creación de documentación operacional (estructura base + pack Import/Export).
- 2026-02-09: Se agrega guía CD Deploy (VPS + Docker Compose).
- 2026-03-08: Se agrega runbook de certificación real Fase 4A (Shadow Ledger).
- 2026-03-08: Se agrega gate automatizado de go-live Fase 4A (`verify_phase4_go_live`).
- 2026-03-08: Se agrega ciclo operativo automatizado (`run_shadow_ledger_cycle`) con health-gates.
- 2026-03-08: Inicio Fase 5 con aprobación/posting/cierre de período (`approve_journal_drafts`, `post_journal_drafts`, `close_fiscal_period`).
- 2026-03-08: Fase 5 reforzada con SoD real en API contable (`accounting.journal_draft.*`, `accounting.period.*`) y trazabilidad de actor.
- 2026-03-08: Fase 5 agrega reversa contable formal (`reverse_journal_entry`, endpoint `/api/accounting/journal-entries/{entry_id}/reverse/`).
- 2026-03-08: Fase 5 agrega reversa contable masiva (`reverse_journal_entries_batch`, endpoint `/api/accounting/journal-entries/reverse-batch/`).
- 2026-03-08: Se agrega toolchain de certificación/go-live Fase 6 Adapter B (`export_phase6_env_manifest`, `compare_phase6_env_manifests`, `certify_adapter_b_run`, `verify_phase6_go_live`, `run_adapter_b_cycle`) y runbook operativo.
- 2026-03-08: Se implementa Fase 7A GL Core formal (COA, JournalEntryLine, reportes financieros, FX revaluation) con toolchain de certificación/go-live (`export_phase7_env_manifest`, `compare_phase7_env_manifests`, `certify_phase7_gl_run`, `verify_phase7_go_live`, `run_phase7_gl_cycle`) y runbook operativo.
- 2026-03-08: Se implementa Fase 7B backend (intercompany transaccional + consolidación multi-compañía) con comandos operativos/certificación (`run_intercompany_cycle`, `run_consolidated_close`, `certify_phase7b_consolidation`, `verify_phase7b_go_live`).
- 2026-03-08: Se agrega preflight unificado staging-first (`export_staging_preflight_manifest`) y snapshot operacional (`export_finance_operational_snapshot`).
- 2026-03-08: Se agrega hardening de performance por EXPLAIN (`explain_financial_queries`) y runbooks de cierre total, ownership/SLA y checklist de promoción.
- 2026-03-09: Se agrega runbook de bug bounty local con comando canónico `qa/run_bug_bounty_local.sh` y evidencia firmada.
- 2026-03-09: Se agrega runbook operativo de Fase 8 (`GO_LIVE_FASE8_PRODUCCION_v1.0.md`) y comandos de pre-corte/rollback (`verify_phase8_precutover`, `evaluate_phase8_rollback`, `export_phase8_release_baseline`).
- 2026-03-09: Se agrega runner canónico F9 (`qa/run_phase9_go_live.sh`), plantilla cron (`qa/phase9_cycle.cron.example`) y runbook operativo (`GO_LIVE_FASE9_PROVIDER_v1.0.md`).
- 2026-03-09: Se agrega runner canónico F10 (`qa/run_phase10_go_live.sh`), plantilla cron (`qa/phase10_cycle.cron.example`) y runbook operativo (`GO_LIVE_FASE10_PROCUREMENT_v1.0.md`).
- 2026-03-09: Se agrega runner canónico F11 (`qa/run_phase11_go_live.sh`), plantilla cron (`qa/phase11_cycle.cron.example`) y runbook operativo (`GO_LIVE_FASE11_INTERCOMPANY_AVANZADO_v1.0.md`).
- 2026-03-09: F11 cerrado en staging con PASS estricto (`phase11_go_live_20260309_210137`: happy/blocked/gate PASS y estabilidad 2/2).
- 2026-03-09: F12 avanzada implementada (manifiesto/paridad, determinismo v2, gate unificado y política FX `ALERT|BLOCK`) con runner canónico `qa/run_phase12_go_live.sh`, cron `qa/phase12_cycle.cron.example` y runbook operativo.
- 2026-03-09: F12 cerrada en staging con PASS (`phase12_go_live_20260309_222629`: 3 periodos cubiertos, SLO/gate PASS y estabilidad 2/2).
- 2026-03-10: Normalización de publicación GitHub: separación de estado ejecutivo en `docs/contexto_nucleos.md` y exclusión de evidencia masiva del versionado.
- 2026-03-10: Preparación de publicación release F1-F12: inclusión de artefactos QA de auditoría y reubicación de `etup-git` a evidencia operativa versionada.
- 2026-03-10: Se agrega plan maestro de cierre F1-F12 (`PLAN_MAESTRO_F1_F12_CIERRE_OPERATIVO_v1.0.md`) y checklist de PR release.
- 2026-03-11: Se agrega runbook operativo de Fase 4/5 Billing-Inventory (`GO_LIVE_BILLING_INVENTORY_F4_F5_v1.0.md`) con gate k6, rollout por etapas y rollback determinista.
- 2026-03-24: Se agrega runbook operativo R8 de reporting/dashboard (`REPORTING_R8_GOBIERNO_OBSERVABILIDAD_v1.0.md`) con gate WARN→FAIL, telemetría y deprecación legacy contable.
- 2026-03-25: Se agrega runbook U6 de gobernanza de release + supply chain (`U6_RELEASE_GOVERNANCE_SUPPLY_CHAIN_v1.0.md`) con controles bloqueantes, contrato de checks requeridos y evidencia consolidada de release.
- 2026-03-26: Se agrega matriz RCA de alertas Release/QA (`ALERTAS_RCA_RELEASE_QA_v1.0.md`) con clasificación bloqueante/warn/ruido y acciones correctivas.
- 2026-03-26: Se agrega runbook del slice `Retail POS Spine` (`RETAIL_POS_SPINE_SLICE_v1.0.md`) con endpoints, validación y pendientes de fases siguientes.
- 2026-03-26: El slice `Retail POS Spine` agrega fase Edge (challenge/handshake/capabilities) y simulador QA `qa/simulate_retail_pos_edge.py`.
- 2026-03-26: El slice `Retail POS Spine` agrega resiliencia de compensación (retry endpoint/ciclo) y cola offline frontend con backoff y deduplicación.
- 2026-04-11: Se agrega estándar operativo `CODEX_GOVERNANCE_HANDOFF_v1.0.md` y guard bloqueante `qa-codex-governance-guard` para cambios en rutas críticas.
- 2026-04-11: Se endurece estándar Codex a v1.1 por tipo de cambio (clasificación automática, secciones/gates por tipo y validación de modos prohibidos).
- 2026-04-14: Se agrega propuesta operativa `Centro de Operación Unificada (COU) Multidispositivo` (`COU_MULTIDISPOSITIVO_v1.0.md`) para estrategia internet-first con UX diferenciada por dispositivo y lógica de negocio unificada.
- 2026-04-14: Se agrega norma interna vinculante `NORMA_GOBERNANZA_MULTIDISPOSITIVO_v1.0.md` con reglas rectoras de producto, seguridad, UX dual-shell, consistencia de datos, transacciones, trazabilidad y escalabilidad.
- 2026-04-14: Se agrega norma marco `NORMA_DISENO_OPERACION_SISTEMA_EMPRESARIAL_v1.0.md` con objetivo, alcance, principios funcionales/UX, reglas de seguridad, operacion por modulo, auditoria, consistencia, restricciones, decisiones obligatorias y anti-patrones prohibidos.
- 2026-04-14: Se agrega documento maestro `DISENO_EMPRESARIAL_MULTIDISPOSITIVO_ERP_CRM_v1.0.md` con arquitectura funcional, criterios laptop/movil, reglas de seguridad/auditoria, propuesta de navegacion, riesgos y backlog inicial de implementacion.
- 2026-04-14: Se agrega arquitectura tecnica `ARQUITECTURA_IMPLEMENTACION_MULTIDISPOSITIVO_v1.0.md` con estructura modular frontend/backend, rutas publicas/privadas, estrategia dual-shell, stores, capa API, sesion/permisos/contexto, layouts y plan de implementacion paso a paso.
- 2026-04-14: Se agrega diseno ejecutable `INVENTARIO_MULTIDISPOSITIVO_v1.0.md` para modulo core de inventarios con separacion Workbench/Taskflow, validaciones, permisos, trazabilidad y plan de pruebas.
- 2026-04-14: Se agrega diseno funcional empresarial `FACTURACION_MULTIDISPOSITIVO_v1.0.md` para operacion internet-first en desktop/movil con alcance, operaciones criticas, permisos, trazabilidad, riesgos y criterios de aceptacion.
- 2026-04-14: Se agrega diseno operativo `ESTACION_SERVICIOS_MULTIDISPOSITIVO_v1.0.md` para operacion de pista/caja/cierre con UX separada por dispositivo, control de incidencias y trazabilidad end-to-end.
- 2026-04-14: Se agrega diseno operativo `REPORTING_DASHBOARDS_MULTIDISPOSITIVO_v1.0.md` para separacion UX desktop/movil en dashboards y reportes con KPI moviles, analitica avanzada en laptop, limites de densidad y contrato de trazabilidad.
- 2026-04-14: Se agrega contrato funcional maestro `CONTRATOS_FUNCIONALES_COMPARTIDOS_LAPTOP_MOVIL_v1.0.md` para unificar modulos, capacidades, acciones, permisos, contexto, contratos API y eventos auditables cross-device.
- 2026-04-14: Se agrega backlog de delivery `BACKLOG_MULTIDISPOSITIVO_INVENTARIO_FACTURACION_ESTACION_REPORTING_DASHBOARD_v1.0.md` con epicas, capacidades, historias, aceptacion, dependencias, riesgos y orden de implementacion por valor/riesgo/dependencia tecnica.
- 2026-04-14: Cierre de bateria de prompts multidispositivo: se consolida set canonico de documentos y se agrega guia `PROMPTS_STACK_REAL.md` para ejecucion alineada al stack real (Quasar/Vue/Pinia + Django/DRF).
- 2026-04-14: Se consolida `CODEX_MASTER_PACK_v1.0.md` como source of truth operativo para delegacion por slices (context card, reglas no negociables, 4 bloques oficiales, handoff A-F y matriz de gates).
