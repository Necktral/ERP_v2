# HANDOFF - GAP-BILLING-UI-001 Staging Smoke (2026-04-16)

## A) Diagnóstico del área
Billing estaba en `parcial` por ausencia de UI dedicada en la línea base. El backend canónico de documentos (`/api/billing/docs/*`) ya existía y se extendió de forma aditiva con `GET /api/billing/docs/` para habilitar operación UI completa (listado, filtros y paginación).

La brecha de cierre estaba concentrada en:
- wiring frontend (ruta, menú, servicio, pantalla),
- acciones operativas (`create`, `issue`, `void`) con ACL,
- evidencia operativa real de smoke para promover el dominio a `cerrado`.

## B) Alcance exacto
Slice ejecutado: `single_domain_code` Billing-only.

Incluido:
- Backend Billing (`kernels.facturacion`): `GET /api/billing/docs/` aditivo con filtros/paginación y permisos por método.
- Frontend Billing UI v1: ruta `/facturacion/documentos`, menú Billing, `BillingDocumentsPage`, `billing.service`, guardas por estado y permiso.
- Pruebas focales backend/frontend del dominio.
- Smoke operativo con 3 perfiles ACL y evidencia versionada.
- Actualización de `CODEX_COMPLETION_MATRIX_v1.md` y `CODEX_GAP_REGISTER_v1.md`.

Excluido explícitamente:
- inventarios, accounting, payments, reporting, fuel, procurement,
- migraciones,
- nuevas dependencias,
- refactor transversal.

## C) Contratos impactados
Contrato canónico Billing (aditivo, sin ruptura):
- `GET /api/billing/docs/` con query `limit, offset, status, doc_type, q, date_from, date_to, ordering`.
- `POST /api/billing/docs/` (create) se mantiene compatible.
- `GET /api/billing/docs/{id}/` se mantiene compatible.
- `POST /api/billing/docs/{id}/issue/` se mantiene compatible.
- `POST /api/billing/docs/{id}/void/` se mantiene compatible.

ACL validada por acción:
- lectura: `billing.doc.read`
- creación: `billing.doc.create`
- emisión: `billing.doc.issue`
- anulación: `billing.doc.void`

## D) Implementación realizada
Backend:
- `backend/src/apps/kernels/facturacion/views.py`
- `backend/src/apps/kernels/facturacion/serializers.py`
- `backend/src/apps/kernels/facturacion/urls.py`
- `backend/src/tests/test_billing_doc_flow.py`

Frontend:
- `frontend/src/pages/BillingDocumentsPage.vue`
- `frontend/src/services/billing.service.ts`
- `frontend/src/services/__tests__/billing.service.spec.ts`
- `frontend/src/router/routes.ts`
- `frontend/src/router/routes.spec.ts`
- `frontend/src/layouts/MainLayout.vue`
- `frontend/src/shared/ui/business-terms.ts`

Evidencia de smoke:
- `qa/reports/billing_ui_v1_smoke_staging.json`

## E) Pruebas / validación
Pruebas técnicas:
- `docker compose exec -T backend bash -lc "cd /app/backend/src && pytest -q tests/test_billing_doc_flow.py"` -> PASS (5/5)
- `cd frontend && npm run test` -> PASS
- `cd frontend && npm run typecheck` -> PASS

Gates del marco operativo:
- `make qa-codex-governance-guard` -> PASS
- `make qa-architecture-dependency-guard` -> PASS
- `make qa-route-contract-guard` -> PASS
- `make qa-reporting-contract-version-guard` -> PASS
- `make qa-migration-safety-guard` -> PASS

Smoke operativo (entorno `staging-local`, company `2`, branch `3`):
- reporte: `qa/reports/billing_ui_v1_smoke_staging.json`
- casos: 18/18 PASS
- transición verificada: `DRAFT -> ISSUED -> VOIDED`
- ACL verificada:
  - Usuario A (`billing_smoke_full_20260416`): listar/crear/issue/void PASS
  - Usuario B (`billing_smoke_read_20260416`): list/detail PASS, create/issue/void FORBIDDEN PASS
  - Usuario C (`billing_smoke_none_20260416`): list/detail/create FORBIDDEN PASS
- filtros/orden/paginación: PASS
- transición inválida: `issue` sobre `VOIDED` devuelve `400` (aceptado en smoke como error de dominio esperado; UI maneja también `409` cuando aplique).

## F) Riesgos remanentes y siguiente paso
Riesgos remanentes:
- El smoke se ejecutó en `staging-local` con dataset operativo local, no en un staging remoto externo.
- El backend actualmente devuelve `400` en transición inválida específica (`issue` sobre `VOIDED`); si el contrato evoluciona a `409`, mantener sincronizada la UI y el smoke.

Siguiente paso recomendado:
1. Ejecutar el mismo smoke sobre staging remoto oficial con credenciales operativas de ambiente y anexar evidencia equivalente.
2. Abrir siguiente slice de convergencia: `GAP-PAYMENTS-UI-001` (Payments/Cash UI v1), manteniendo PR Billing ya cerrado y aislado.

## Blast radius
Acotado a Billing:
- `backend/src/apps/kernels/facturacion/*`
- wiring frontend Billing (`routes`, `layout`, `page`, `service`)
- artefactos operativos de cierre Billing

Sin impacto declarado en bounded contexts de Inventory, Accounting, Payments, Reporting, Fuel o Procurement.

## Plan de rollback
Si se detecta regresión en Billing UI/API:
1. Revertir commit del slice Billing (`git revert <commit_sha>`).
2. Validar inmediatamente:
   - `make qa-route-contract-guard`
   - `make qa-architecture-dependency-guard`
3. Confirmar que `POST/detail/issue/void` de Billing permanecen operativos con pruebas focales.

## Estado de gates
Todos los gates obligatorios del slice quedaron en verde al cierre de este handoff.

## Excepciones de seguridad
No se abrieron excepciones de seguridad en este slice.
