# HANDOFF — Sync Device Branch Scope P0

Version: v1  
Fecha: 2026-05-04  
Estado: cerrado  
PR: https://github.com/Necktral/Necktral/pull/68  
Merge commit: `311cf66e`  
Fix commit: `8fa283c3 fix(sync): enforce branch scope for device administration`

## Objetivo

Cerrar P0 de aislamiento multi-sucursal en administración de dispositivos Sync.

## Problema

Los endpoints administrativos de Sync respetaban `company`, pero no restringían correctamente por `request.branch` cuando el actor operaba bajo scope de sucursal.

Superficies afectadas:

- `EnrollmentChallengeCreateView`
- `DeviceListView`
- `DeviceRevokeView`

## Decisión

Aplicar enforcement por branch efectiva sin cambiar contrato externo.

Reglas finales:

- Actor con `request.branch`:
  - challenge omitido se resuelve a la branch efectiva;
  - challenge para otra branch devuelve `403`;
  - list muestra solo devices de la branch efectiva;
  - revoke solo permite devices de la branch efectiva;
  - cross-branch/company-level revoke devuelve `404`.

- Actor company-level:
  - conserva comportamiento company-level existente.

## Archivos modificados

- `backend/src/apps/modulos/sync_engine/views.py`
- `backend/src/tests/test_sync_device_enrollment_flow.py`
- `backend/src/tests/test_sync_devices_list.py`

## Validación

Local:

```bash
pytest -q tests/test_sync_device_enrollment_flow.py tests/test_sync_devices_list.py
# 9 passed

pytest -q tests/test_sync_v2_contract.py tests/test_sync_v2_pos_commands.py apps/modulos/sync/tests/test_sync_batch.py
# 15 passed

ruff check apps/modulos/sync_engine/views.py tests/test_sync_device_enrollment_flow.py tests/test_sync_devices_list.py
# passed

python -m mypy apps/modulos/sync_engine/views.py
# passed

git diff --check
# passed
```

Remoto:

- `qa`: pass
- `security`: pass
- `supply-chain`: pass
- `snapshot`: pass
- `ai_review_advisory`: pass

Post-merge sanity:

```bash
python -m mypy apps/modulos/sync_engine/views.py
# Success: no issues found in 1 source file
```

## Contratos

No cambia en el corte P0 original:

- URLs
- serializers
- protocolo Sync
- eventos audit
- legacy `/api/sync-hmac/` fue retirado despues del sunset en el corte de hardening posterior.

Cambia:

- semántica de autorización branch-scoped en device administration.

## Riesgos remanentes

P1 pendientes, fuera de este PR:

1. Auditar explícitamente rechazos de request-auth Sync v2:
   - `BAD_SIGNATURE`
   - `REPLAY_DETECTED`
   - `TS_OUT_OF_WINDOW`
   - `DEVICE_ID_MISMATCH`
2. Validar que clientes externos ya no consuman `/api/sync-hmac/`.
3. Normalizar reason codes POS usados por handlers Sync contra contratos audit.
4. Definir política para endpoints `AllowAny` cuando llega JWT/cookie accidental.

## Estado final

P0 cerrado. Sync queda apto para continuar análisis económico y móvil/offline.
