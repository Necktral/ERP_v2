# Documentación — Necktral ERP/CRM

Esta carpeta contiene la documentación funcional y técnica del proyecto.

## Objetivo

- Centralizar “guías de organización” (contratos, estándares y decisiones).
- Mantener alineación con el backend (Django/DRF), la auditoría contractual y el motor de sincronización.
- Servir como referencia para desarrollo, QA y despliegues.

## Documentos actuales

- [ESTANDAR_COMENTARIOS.md](ESTANDAR_COMENTARIOS.md) — Estándar de comentarios en el código.

- [CONTRACT_PACK_v1.0.md](CONTRACT_PACK_v1.0.md) — Guía contractual del sistema (organización de kernels/módulos).
- [ARQUITECTURA_DOMINIO_Y_CONTROL_v1.0.md](ARQUITECTURA_DOMINIO_Y_CONTROL_v1.0.md) — Blueprint maestro de kernels, CEC, adaptadores fiscales y evolución a GL formal.
- [contexto_nucleos.md](contexto_nucleos.md) — Estado ejecutivo por fases y roadmap activo (staging-first).
- [ADDENDUM_OFFLINE_FIRST_v1.0.md](ADDENDUM_OFFLINE_FIRST_v1.0.md) — Reglas offline-first (sync, idempotencia y auditoría).
- [ADDENDUM_SEGURIDAD_v1.0.md](ADDENDUM_SEGURIDAD_v1.0.md) — Plan de mejoras de seguridad y robustez.
- [ADDENDUM_SEGURIDAD_BACKLOG_v1.0.md](ADDENDUM_SEGURIDAD_BACKLOG_v1.0.md) — Backlog ejecutable del addendum de seguridad.
- [BILLING_KERNEL_v1.0.md](BILLING_KERNEL_v1.0.md) — Contrato operativo del kernel de facturación.
- [FUTURAS_MEJORAS.md](FUTURAS_MEJORAS.md) — Roadmap de mejoras futuras (técnicas y de producto).

## Documentación operacional

- [operacion/README.md](operacion/README.md) — Playbooks y plantillas para operar el negocio.
- [operacion/import_export/README.md](operacion/import_export/README.md) — Pack operativo Import/Export & Sourcing (B2B).
- [operacion/ROTACION_SECRETOS_v1.0.md](operacion/ROTACION_SECRETOS_v1.0.md) — Runbook de rotación de secretos.
- [operacion/CD_DEPLOY_v1.0.md](operacion/CD_DEPLOY_v1.0.md) — Deploy continuo en VPS con Docker Compose.
- [operacion/SHADOW_LEDGER_FASE4A_CERTIFICACION_v1.0.md](operacion/SHADOW_LEDGER_FASE4A_CERTIFICACION_v1.0.md) — Certificación real E2E de Fase 4A (paridad, determinismo y go-live).
- [operacion/GL_FASE7A_CERTIFICACION_v1.0.md](operacion/GL_FASE7A_CERTIFICACION_v1.0.md) — Certificación real E2E de Fase 7A (GL formal, reportes y revaluación FX).
- [operacion/GL_FASE7B_INTERCOMPANY_CONSOLIDACION_v1.0.md](operacion/GL_FASE7B_INTERCOMPANY_CONSOLIDACION_v1.0.md) — Operación y certificación real E2E de Fase 7B (intercompany y consolidación).
- [operacion/STAGING_FIRST_EJECUCION_TOTAL_v1.0.md](operacion/STAGING_FIRST_EJECUCION_TOTAL_v1.0.md) — Ejecución integral backend de Fase 6/7A/7B en staging.
- [operacion/MATRIZ_OWNERSHIP_SLA_FASE6_7B_v1.0.md](operacion/MATRIZ_OWNERSHIP_SLA_FASE6_7B_v1.0.md) — Responsables y SLA por alertas críticas del bloque.
- [operacion/CHECKLIST_PROMOCION_PRODUCCION_FASE6_7B_v1.0.md](operacion/CHECKLIST_PROMOCION_PRODUCCION_FASE6_7B_v1.0.md) — Checklist de promoción a producción (sin ejecución automática).

## CI / QA

- CI principal (QA Gates 1–3): `.github/workflows/qa-ci.yml`
- Snapshot/reporting: `.github/workflows/pm-snapshot.yml`
- Security CI (blocking): `.github/workflows/security-ci.yml`
- Simulación de carga auth (k6): `.github/workflows/auth-load-simulation.yml`

## Reglas

- Todo en español.
- Mantener los documentos cortos, accionables y versionados (título + versión + fecha).
- Cuando un documento defina reglas/invariantes, enlazar a los módulos relevantes del código (p.ej. auditoría contractual, RBAC, sync engine).
- No versionar evidencia operativa masiva en Git; solo runbooks, índices y rutas de evidencia.
