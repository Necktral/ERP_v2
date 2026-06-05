# Correlación de Auditoría

## Challenge
- `event_type`: `SYNC_ENROLL_CHALLENGE_CREATED`
- `path`: `/api/sync/enrollment/challenges/`
- `trace.audit_event_id`: `2e5e903f-4870-4d20-b20f-a77942986f16`
- Verificación: presente en `AuditEvent` (company=2, branch=3).

## Enroll
- Estado: pendiente de ejecución desde dispositivo físico.
- Evento esperado: `SYNC_DEVICE_ENROLLED`
- Path esperado: `/api/sync/enroll/`

## Batch
- Estado: pendiente de ejecución desde dispositivo físico.
- Evento esperado: `SYNC_BATCH_RECEIVED` y/o `SYNC_COMMAND_APPLIED`
- Path esperado: `/api/sync/batch/`
