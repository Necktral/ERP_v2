# Contract Pack v1.0 — Guía contractual del sistema

Versión: v1.0  
Fecha: 2026-01-26  
Estado: **Guía de organización (viva)**

## Propósito

Este documento define el **contrato de organización** del ERP/CRM: cómo deben comportarse los kernels y módulos para que el sistema sea consistente, auditable, multiempresa y operable con QA determinista.

- Es una **guía normativa** para diseño e implementación.
- Debe mantenerse alineada con el código (auditoría contractual, RBAC y sync engine).

## Alcance

- Kernels (dominio transversal): facturación, inventarios, cuentas por cobrar/pagar, tesorería, etc.
- Módulos operativos (verticales): p.ej. Estación de Servicios (FUEL).
- Contratos transversales: auditoría, seguridad/RBAC, multiempresa, sync/offline.

## Convenciones del repositorio

- Todo en español.
- Preferencia por servicios de dominio + serializers/DTOs explícitos.
- QA como “puerta” (gates) y CI determinista.

## Contratos transversales (base actual del repo)

### 1) Multiempresa (scope)

- El backend opera en un contexto de **company** y, opcionalmente, **branch**.
- El scope efectivo se aplica en permisos y queries.

> Nota: el detalle exacto de headers y reglas debe mantenerse consistente con el backend.

### 2) Autorización (RBAC)

- Los endpoints deben aplicar permisos por método (lectura/escritura separadas).
- El catálogo estándar vive en `seed_rbac_v01`.

### 3) Auditoría contractual (invariante)

- Los endpoints de escritura deben emitir eventos con:
  - `event_type` permitido por contrato.
  - `reason_code` permitido.
  - `subject_type` permitido.
- La integridad es encadenada por hash y firmada con HMAC en PROD.

Referencias del repo:

- Contrato de eventos/subjects/reasons: `login_module/src/apps/audit/contracts.py`
- Verificación de integridad: `login_module/src/apps/audit/management/commands/audit_verify_chain.py`

### 4) Sync / Offline (precedente)

Existe un precedente implementado para sincronización por lotes con:

- firma Ed25519 por comando,
- canonicalización determinista,
- idempotencia por `command_id`.

Referencias del repo:

- API/serialización: `login_module/src/apps/sync_engine/serializers.py`
- Vistas: `login_module/src/apps/sync_engine/views.py`

## Kernels y módulos

### Kernels (objetivo)

Este repositorio está preparado para crecer a kernels (Billing, Inventory, AR/AP, Treasury). El contrato de organización define:

- Fronteras de responsabilidad (qué pertenece a cada kernel).
- Tipos de documentos/estados y sus transiciones.
- Reglas de auditoría por operación.
- Reglas de sync/outbox cuando aplique.

> Pendiente: pegar aquí el texto completo del Contract Pack v1.0 provisto (normas, entidades, flujos, estados, endpoints).

### Módulos verticales (ejemplo: FUEL)

- Deben integrarse con contratos transversales (RBAC, auditoría contractual, scope).
- Reportes y cierres deben ser reproducibles y auditables.

## Estado actual en este repo (resumen)

- Implementado: ORG/HR/RBAC + auditoría contractual.
- Implementado: sync engine (precedente) para dispositivos.
- Implementado: módulo FUEL (base + endpoints operativos/reportes según MVP).
- Pendiente: kernels de facturación e inventarios como apps reales.

## CI/QA (gates)

- CI principal: `.github/workflows/qa-ci.yml` (QA CI Gates 1–3)
- Snapshot/reporting: `.github/workflows/pm-snapshot.yml` (PM Snapshot)

---

Si vas a modificar este documento: mantener la versión y agregar un changelog breve al final.
