# Retail POS Spine Slice v1.0

## Alcance implementado en este slice

- Nuevo módulo backend `retail_pos` (capa de ejecución, no kernel financiero).
- Endpoints aditivos:
  - `GET /api/retail/pos/health/`
  - `GET /api/retail/pos/sessions/current/`
  - `POST /api/retail/pos/sessions/open/`
  - `POST /api/retail/pos/sessions/{session_id}/close/`
  - `GET|POST /api/retail/pos/tickets/`
  - `POST /api/retail/pos/tickets/{ticket_id}/checkout/`
  - `POST /api/retail/pos/tickets/{ticket_id}/compensate/retry/`
  - `POST /api/retail/pos/checkouts/{ticket_id}/` (alias)
  - `POST /api/retail/pos/voids/{ticket_id}/`
  - `GET|POST /api/retail/pos/peripherals/status/`
  - `POST /api/retail/pos/peripherals/edge/challenge/`
  - `POST /api/retail/pos/peripherals/edge/handshake/`
  - `GET /api/retail/pos/peripherals/capabilities/`
  - `GET /api/retail/pos/cockpit/`
- Integración interdominio en checkout:
  - Fuel (`dispense` y `sale`)
  - Payments/Cash (`payment intent`, captura y movimientos de caja)
  - Outbox/Audit contractual
- Eventos POS publicados:
  - `POSSessionOpened`
  - `POSSessionClosed`
  - `POSTicketOpened`
  - `POSTicketClosed`
  - `POSPaymentCaptured`
  - `POSVoidRequested`
  - `POSCompensationRaised`
  - `POSCompensationRetried`
- Sync v2 extendido con comandos POS:
  - `POS_TICKET`
  - `POS_PAYMENT_INTENT`
  - `POS_VOID`
  - `POS_CASH_COUNT`
  - `POS_COMPENSATION_RETRY`
- RBAC ampliado con permisos `retail.pos.*`.
- Métricas operativas nuevas en `/api/metrics/`:
  - `retail_pos.checkout_total`
  - `retail_pos.checkout_ok`
  - `retail_pos.checkout_error`
  - `retail_pos.checkout_error_by_reason`
  - `retail_pos.checkout_latency_p95_ms`
- Cockpit operativo POS (`/api/retail/pos/cockpit/`) incluye métricas de compensación:
  - `compensation.pending`
  - `compensation.overdue`
  - `compensation.max_pending_age_min`
- Frontend operativo mínimo:
  - `Retail POS · Terminal`
  - `Retail POS · Operational Cockpit`
- Cola offline en frontend POS:
  - persistencia local con `dedupe_key` por ticket,
  - reintentos con backoff exponencial para errores transientes (network/5xx/429),
  - replay manual/automático al recuperar conectividad.
- Edge connector (fase actual):
  - handshake challenge/response firmado con HMAC en secreto compartido (`POS_EDGE_CONNECTOR_SHARED_SECRET`).
  - sesión efímera por conector (`POS_EDGE_SESSION_TTL_SEC`) y challenge de corta vida (`POS_EDGE_CHALLENGE_TTL_SEC`).
  - registry de capacidades consolidado por `device_kind`.

## Compatibilidad y seguridad

- `/api/sync-hmac/batch/` fue retirado despues del sunset; POS usa `/api/sync/batch/` y `/api/v1/sync/batch/`.
- Se mantiene compatibilidad en `/api/sync/batch/` para payloads legacy y `protocol_version="2"`.
- Se mantiene anti-replay request-level para v2.
- Auditoría contractual extendida para eventos `POS_*`.

## Validación ejecutada

- `make qa-sync-pos-validation QA_REPORTS_DIR=qa/reports` (suite canónica Sync+POS del repo)
- `pytest --create-db -q src/tests/test_retail_pos_api.py src/tests/test_sync_v2_pos_commands.py src/tests/test_sync_v2_contract.py`
- `pytest -q src/tests/test_route_collision_guard.py src/tests/test_route_canonical_registry.py`
- `npm run test -- src/router/routes.spec.ts`
- `npm run typecheck`
- `npm run lint`
- `make qa-readme-section-guard QA_REPORTS_DIR=qa/reports`
- `make qa-security-findings-enforce QA_REPORTS_DIR=qa/reports`
- `make qa-export-u6-release-evidence QA_REPORTS_DIR=qa/reports`
- `make qa-ci-gate2 QA_REPORTS_DIR=qa/reports`
- `make qa-retail-pos-backend-contract-guard QA_REPORTS_DIR=qa/reports`
- `make qa-retail-pos-sync-contract-guard QA_REPORTS_DIR=qa/reports`
- `make qa-retail-pos-frontend-queue-contract-guard QA_REPORTS_DIR=qa/reports`
- `make qa-retail-pos-edge-simulator-guard QA_REPORTS_DIR=qa/reports`
- `make qa-retail-pos-edge-e2e-guard QA_REPORTS_DIR=qa/reports`
- `make qa-retail-pos-pilot-smoke QA_REPORTS_DIR=qa/reports`
- `make qa-retail-pos-pilot-rollback QA_REPORTS_DIR=qa/reports`
- `python3 qa/simulate_retail_pos_edge.py --help`
- `pytest -q src/tests/test_retail_pos_api.py src/tests/test_sync_v2_pos_commands.py`
- `npm run test -- src/features/pos/__tests__/offlineQueue.spec.ts`

## Pendientes para fases siguientes

- Expansión por oleadas (sucursal por sucursal) con criterios de salida operativa y contable.
