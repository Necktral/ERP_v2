# Sync v2 Slice (Day 1) — Matriz de compatibilidad y checklist operativo

Fecha: 2026-03-26  
Estado: implementado en rama `feat/u6-release-supplychain-20260325`

## 1) Matriz de compatibilidad (operativa)

| Canal | Endpoint | Entrada aceptada | Auth efectiva | Motor de negocio | Respuesta |
|---|---|---|---|---|---|
| Canónico legacy | `POST /api/sync/batch/` | esquema legacy (`batch_id`, `commands[]`) | firma por comando Ed25519 | `sync_engine` | `APPLIED/REJECTED/DUPLICATE` por comando |
| Canónico v2 | `POST /api/sync/batch/` | `protocol_version="2"` + `batch[]` + `auth` request-level | request-level (`hmac` o `ed25519`) + nonce único | `sync_engine` | `APPLIED/REJECTED/DUPLICATE` por comando |
| Legacy HMAC | retirado | no aplica | no aplica | retirado | sunset completado |

## 2) Feature flags del slice

- `SYNC_V2_ACCEPT_ENABLED=true`  
  Habilita `protocol_version="2"` en `/api/sync/batch/`.
- `SYNC_V2_REQUEST_AUTH_ENFORCED=true`  
  En v2 fuerza validación request-level (`ts -> firma -> nonce`) y permite `command_sig` opcional.
- `sync-hmac` ya no está montado. Usar `/api/sync/batch/` o `/api/v1/sync/batch/`.
- `SYNC_V2_MAX_SKEW_SECONDS=300`  
  Ventana de reloj para request-level en v2.
- `SYNC_LEGACY_HMAC_SUNSET=2026-03-31T00:00:00Z` fue el corte de retiro.

## 3) Criterios de aceptación (DoD del día)

- `sync/batch` acepta legacy y v2 sin romper contrato existente.
- En v2, errores request-level estables: `BAD_SIGNATURE`, `TS_OUT_OF_WINDOW`, `REPLAY_DETECTED`, `DEVICE_ID_MISMATCH`.
- `sync-hmac` fue retirado después del sunset.
- Gate contractual agregado a QA (`qa-sync-contract-guard`) y ejecutado en Gate 2.

## 4) Checklist de verificación rápida

1. Ejecutar tests del slice:
   - `pytest -q src/tests/test_sync_v2_contract.py`
2. Validar compatibilidad legacy actual:
   - `pytest -q src/apps/modulos/sync/tests/test_sync_batch.py`
3. Validar gate QA contractual:
   - `make qa-sync-contract-guard QA_REPORTS_DIR=qa/reports`
4. Verificar artefacto:
   - `qa/reports/sync_contract_guard.txt`

## 5) Rollback no destructivo (inmediato)

1. Desactivar wrapper legacy:
   - sin ruta `/api/sync-hmac/`
2. Mantener v2 canónico con legacy activo:
   - `SYNC_V2_ACCEPT_ENABLED=true`
3. Si se requiere aislar incidente de request-level:
   - `SYNC_V2_REQUEST_AUTH_ENFORCED=false`
4. No requiere rollback de datos históricos; solo toggles de configuración.
