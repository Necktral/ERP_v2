# Payments Cash Movement Idempotency

Fecha: 2026-05-04  
Estado: implementado  
Riesgo: alto  
Dominio: Payments / Cash

## Contexto

`POST /api/payments/cash-sessions/{session_id}/movements/` registraba un
`CashMovement` nuevo en cada retry y volvía a mutar `CashSession.expected_amount`.
En caja/POS/offline esto puede duplicar ingresos, egresos o reembolsos.

## Decisión

Agregar idempotencia opcional por `CashSession + idempotency_key`:

- request sin `idempotency_key`: conserva comportamiento histórico;
- request con misma key y mismo payload: retorna el movimiento existente;
- request con misma key y payload distinto: devuelve conflicto;
- el service, no solo la view, aplica la regla.

El payload comparable es:

- `movement_type`;
- `amount`;
- `reference`;
- `reason`.

## Persistencia

`CashMovement` agrega:

- `idempotency_key`;
- índice por `session, idempotency_key`;
- unique constraint condicional `uq_cash_movement_session_idempotency` cuando la key no está vacía.

La migración es compatible con filas existentes porque la key queda en blanco por defecto y el unique constraint excluye `""`.
La metadata de seguridad de migración queda registrada en `qa/contracts/migration_safety_baseline.json`.

## Auditoría y eventos

Para movimientos nuevos se preserva `OutboxEvent` `CashMovementPosted` y se agrega
`AuditEvent` contractual:

- `event_type`: `PAYMENTS_CASH_MOVEMENT_POSTED`;
- `reason_code`: `OK`;
- `subject_type`: `CASH_MOVEMENT`.

Los replays idempotentes no emiten un segundo evento económico.

## Arquitectura

El fix agrega la dependencia explícita `kernels.payments -> modulos.audit` para emitir
el evento audit contractual desde el service que crea el hecho económico. Esta arista
queda registrada en `qa/contracts/architecture_dependency_baseline.json`, siguiendo el
precedente existente de `kernels.facturacion` y `kernels.inventarios` con auditoría.

## Rollback

Rollback operativo:

1. revertir la migración `0003_cashmovement_idempotency`;
2. revertir service/view/serializer/model/audit contract;
3. validar que no existan clientes dependiendo de `idempotency_key` antes de retirar el campo.

No cambia Fuel, POS, Billing, Inventory, Accounting ni Sync.
