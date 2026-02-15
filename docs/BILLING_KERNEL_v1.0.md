# Billing Kernel v1.0 — Contrato operativo

Versión: v1.0  
Fecha: 2026-02-02  
Estado: **Norma operativa (viva)**

## Propósito

Definir el **contrato mínimo** del kernel de facturación: estados, transiciones, permisos y auditoría. Este documento evita ambigüedad entre endpoints nuevos y legacy.

## Alcance

- Documentos de facturación: `INVOICE`, `CREDIT_NOTE`.
- Estados: `DRAFT` → `ISSUED` → `VOIDED`.
- Endpoints: `/api/billing/docs/` (nuevo) y `/api/billing/invoices/` (legacy, compat).

## Estados y transiciones (invariante)

1. **Crear**: `DRAFT`
   - Se crea documento con líneas y totales calculados.
   - Emite auditoría: `BILLING_DOC_CREATED`.

2. **Emitir**: `DRAFT` → `ISSUED`
   - Asigna número/serie desde secuencia.
   - Emite auditoría: `BILLING_DOC_ISSUED`.

3. **Anular**: `ISSUED` → `VOIDED`
   - No se permite anular un `DRAFT`.
   - Emite auditoría: `BILLING_DOC_VOIDED`.

## Auditoría contractual

- `module = BILLING`
- `event_type` permitidos:
  - `BILLING_DOC_CREATED`
  - `BILLING_DOC_ISSUED`
  - `BILLING_DOC_VOIDED`
  - `BILLING_INVOICE_CREATED` (legacy)
- `reason_code`:
  - `BILLING_OK`, `BILLING_VOID`
- `subject_type`:
  - `BILLING_DOC` (nuevo)
  - `INVOICE` (legacy)

## RBAC (por método)

- `billing.doc.create` — crear documento (draft)
- `billing.doc.read` — leer documento
- `billing.doc.issue` — emitir documento
- `billing.doc.void` — anular documento

Legacy (compat): `billing.invoice.create`.

## Deprecación legacy

Los endpoints legacy (`/api/billing/health-legacy/`, `/api/billing/invoices/`) se mantienen **solo por compatibilidad**.

- **Estado:** legacy activo
- **Deprecación prevista:** v1.1
- **Alternativa recomendada:** `/api/billing/docs/`

El servidor añade headers `X-Deprecated: true` y `X-Deprecation-Notice` en respuestas legacy.

## Criterios de aceptación (verificables)

- Gate 2 y Gate 3 pasan.
- Cobertura del scope (según `.coveragerc`) ≥ 98%.
- Tests de transición (`create → issue → void`) y auditoría contractual pasan.
- No hay regresión en permisos RBAC.
