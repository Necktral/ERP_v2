# Plan Faseado: Billing/Inventory Avanzado con Flujos Contables (No-MVP)

## Resumen
- Objetivo: evolucionar `apps.kernels.facturacion` y `apps.kernels.inventarios` de MVP a operación avanzada, conectados formalmente con `apps.kernels.accounting`.
- Decisiones fijadas:
  - `Posting model`: **Híbrido**.
  - `Fase 1`: **Factura + Inventario + Asiento**.
  - `Costo base`: **Moving Weighted Average** con diseño preparado para FIFO futuro.
- Entregable de contexto: este documento se mantiene como referencia viva en `docs/PLAN_BILLING_INVENTORY_CONTABLE_AVANZADO_v1.0.md`.

## Estado Actual (implementado en backend)

### Completado
- Fase 0 cerrada (contrato y hardening base):
  - Contrato canónico de eventos operacionales-contables congelado en outbox con `schema_version`, `correlation_id`, `causation_id` y campos contables/fuente explícitos para eventos Billing/Inventory soportados.
  - Hygiene checks operativos definidos (`migrate --check`, `makemigrations --check --dry-run`) y suite de regresión consolidada.
- Configuración base de posting operacional:
  - Flags en settings: `ACCOUNTING_POSTING_MODE`, `ACCOUNTING_POSTING_ENABLE_BILLING`, `ACCOUNTING_POSTING_ENABLE_INVENTORY`, `ACCOUNTING_POSTING_AUTO_POST_ON_WRITE`.
  - Modelo `OperationalPostingConfig` por `company`/`branch`.
- Fase 1 cerrada (integración contable core):
  - Cobertura funcional ampliada para `issue/void/credit_note`, idempotencia y validación contractual de payload en Billing/Inventory.
  - Pruebas modulares de `apps/kernels/facturacion/tests` y `apps/kernels/inventarios/tests` integradas a la corrida estándar de `pytest`.
- Enlace contable en Billing:
  - `BillingDocument` ahora guarda `accounting_status`, `accounting_error`, `accounting_economic_event`, `accounting_journal_draft`, `accounting_journal_entry`.
  - `issue_doc` y `void_doc` generan enlace contable en la misma operación y devuelven estado contable.
- Enlace contable en Inventory:
  - `StockMovement` ahora guarda `accounting_status`, `accounting_error`, `accounting_economic_event`, `accounting_journal_draft`, `accounting_journal_entry`.
  - Operaciones `receive`, `issue`, `adjust`, `transfer` generan/actualizan enlace contable.
  - Transferencia aplica el mismo resultado contable al movimiento salida/entrada.
- APIs aditivas (sin ruptura):
  - Billing `issue/void`: incluyen `accounting_status`, `accounting_error`, `journal_draft_id`, `journal_entry_id`.
  - Inventory `receive/issue/adjust/transfer`: incluyen metadata contable equivalente.
  - Nuevo endpoint de reconciliación: `GET /api/accounting/reports/operational-reconciliation/`.
- Fase 3 (delta final) cerrada:
  - Gates centralizados en `evaluate_period_close_gates(...)` como fuente única de evaluación.
  - `force=true` con bypass parcial: solo omite bloqueo por `pending_drafts`.
  - Bloqueo estricto por `FAILED_OUTBOX` (`BILLING`, `INVENTORY`, `ACCOUNTING`) y por descuadres de conciliación.
  - Evento de auditoría `ACCOUNTING.PeriodCloseBlocked` con `gate_summary` estructurado.
  - API `POST /api/accounting/periods/close/` y comando `close_fiscal_period` con salida enriquecida (`gate_summary`, `force_applied`).
- Fase 2 cerrada:
  - `apps/modulos/estacion_servicios` queda explícitamente como vertical orquestador (no kernel).
  - Correlación transversal Fuel ↔ Inventory ↔ Billing con `flow_correlation_id` y referencias `source_*`.
  - Compensación híbrida en cancelación de venta Fuel (`sync + retry`) con estados `COMPENSATING` y `COMPENSATION_FAILED`.
  - Endpoint de retry y comando batch para recuperación idempotente de compensaciones.
  - Eventos canónicos outbox `FUEL.*` para trazabilidad operativa (sin entrar a gates de cierre contable).

### En progreso
- Fase 4 (rendimiento y robustez):
  - Suite k6 operacional para flujos Billing/Inventory/Accounting.
  - Runner de gate balanceado (`qa/run_operational_performance_gate.sh`) con evidencia JSON + hash y snapshot before/after.
- Fase 5 (rollout controlado):
  - Comando de pilotaje por etapa (`manage_operational_posting_pilot`) y runner `qa/run_operational_pilot_rollout.sh`.
  - Snapshot operativo reusable (`export_operational_load_snapshot`) con outbox/reconciliación/compensaciones Fuel.
  - Rollback reforzado con ciclo determinista (drenaje outbox + retry compensaciones Fuel).
  - Gate final endurecido con validación de aprobaciones owner (`FUNCTIONAL`/`TECHNICAL`) + signoff final (`FINAL_APPROVED`) mediante `verify_operational_pilot_go_live`.
  - Registro de checklist/signoff por comando `record_operational_go_live_review` y soporte opcional `AUTO_SIGNOFF=1` en `qa/run_operational_go_live.sh`.
  - Soporte de ventana no lineal auditable por fuerza mayor:
    - comando `record_operational_go_live_exception`,
    - `ALLOW_EXCUSED_DAYS` con límites `MAX_EXCUSED_DAYS` y `MAX_CALENDAR_DAYS` en gate final.
  - Runbook operativo de ejecución y checklist en `docs/operacion/GO_LIVE_BILLING_INVENTORY_F4_F5_v1.0.md`.

### Cierre técnico ejecutado (local, 2026-03-10)
- Evidencia generada en:
  - `docs/operacion/evidencia/operational_go_live_20260310_221149/performance/*`
  - `docs/operacion/evidencia/operational_go_live_20260310_221149/pilot/*`
  - `docs/operacion/evidencia/operational_go_live_20260310_221149/operational_go_live_gate.json`
- Estado:
  - Gate de performance F4 en `PASS` con profile balanceado.
  - Stage1/Stage2/Stage3 ejecutados y checklist owner funcional/técnico + final signoff emitidos.
  - Verificación final de go-live en `PASS` para ventana local `required_days=1`.
- Nota de auditoría:
  - Para esta corrida local, el gate final se verificó con tolerancias explícitas (`max_reconciliation_mismatch=10`, `max_pending_operational=500`) y quedan documentadas en `stability_thresholds` del reporte.
  - El cierre productivo definitivo mantiene objetivo estricto (`7 días`, tolerancias en cero).

## Fases de Implementación

### 1. Fase 0 — Contrato y hardening base (1 semana, cerrada)
- Congelar contratos canónicos de eventos entre Billing/Inventory/Accounting (`schema_version` explícito).
- Definir `posting_mode=HYBRID` por configuración y feature flags por company/branch.
- Agregar referencias contables en entidades operativas (`economic_event`/`journal_draft`/`journal_entry`).
- Criterio de salida: migraciones aplicadas, contratos versionados, compatibilidad backward mantenida.

### 2. Fase 1 — Integración contable core (2 semanas, cerrada)
- Billing (`issue/void/credit_note`) genera **EconomicEvent + JournalDraft** en la misma operación transaccional.
- Inventory (`receive/issue/adjust/transfer`) genera **EconomicEvent + JournalDraft** con valuación por promedio ponderado.
- Posting híbrido:
  - Síncrono: creación/validación del draft contable.
  - Asíncrono: posting a JournalEntry por ciclo controlado (outbox/dispatcher).
- Criterio de salida: toda operación de facturación/inventario queda trazada con borrador contable y estado de posting.

### 3. Fase 2 — Orquestación inter-módulo y compensaciones (1 semana, cerrada)
- Unificar flujo Fuel ↔ Inventory ↔ Billing ↔ Accounting con correlación única (`correlation_id`, `source_module`, `source_id`).
- Implementar compensaciones formales en anulaciones/reversas para mantener integridad operativa y contable.
- Criterio de salida: create/cancel en flujos cruzados deja asientos y reversas consistentes.

### 4. Fase 3 — Controles de cierre y reconciliación (1 semana, cerrada)
- Reglas de bloqueo: no cerrar período con drafts pendientes, outbox fallido o descuadres operativos-contables.
- Endpoint/reportes de reconciliación operacional vs contable por rango y por sucursal.
- Criterio de salida: cierre determinista con gate automático y reporte auditable.

### 5. Fase 4 — Rendimiento y robustez (1 semana)
- Pruebas de carga para rutas reales de Billing/Inventory/Accounting (no solo auth).
- Tuning de índices y latencia en tablas de movimientos, documentos, eventos y asientos.
- Criterio de salida: SLO de latencia/error definido y cumplido bajo carga objetivo.
 - Perfil activo: balanceado (`p95 <= 400ms`, `error_rate <= 1%`, sin crecimiento de `FAILED` en outbox).

### 6. Fase 5 — Rollout controlado (1 semana)
- Activación progresiva por sucursal con feature flags.
- Monitoreo de errores de posting, tiempos de reconciliación y tasa de compensaciones.
- Criterio de salida: operación estable en piloto + checklist de go-live aprobado.
 - Piloto activo: `1 company / 1 branch`.

## Cambios de APIs/Interfaces (aditivos, sin ruptura)
- `POST /api/billing/docs/{id}/issue/` y `POST /api/billing/docs/{id}/void/` devuelven estado contable: `accounting_status`, `journal_draft_id`, `journal_entry_id`.
- Endpoints de movimientos de inventario devuelven metadata contable equivalente.
- Endpoint de conciliación operacional-contable en `apps.accounting` para ver diferencias y pendientes.
- Eventos `DocumentIssued`, `DocumentVoided`, `InventoryMovementPosted` incluyen referencias contables y `schema_version` fijo.

## Plan de Pruebas y Aceptación
1. Unit tests de reglas de posting y mapping contable por tipo de documento/movimiento.
2. Integration tests de ciclo completo:
   - emitir factura -> movimiento inventario -> draft contable -> posting.
   - anular/revertir -> reversa operativa -> reversa contable.
3. Tests de idempotencia:
   - reintentos de issue/void/movements no duplican asientos.
4. Tests de fallos y compensaciones:
   - fallo en posting asíncrono deja estado `pending/failed` visible y reintento seguro.
5. Tests de reconciliación y cierre:
   - bloqueo de cierre con pendientes/descuadres; cierre exitoso con invariantes cumplidas.
6. Pruebas de carga:
   - escenarios k6/QA para endpoints de billing+inventory+posting con umbrales definidos.
7. Hygiene/migraciones:
   - `python manage.py migrate --check`.
   - `python manage.py makemigrations --check --dry-run`.
   - runner consolidado: `qa/run_operational_hygiene_checks.sh`.

## Supuestos y Defaults
- Moneda y fiscalidad actual se mantienen; cambios son aditivos.
- No se incluye AR/AP completo en esta ola; queda para fase posterior.
- Promedio ponderado queda como política activa; se introduce capa de estrategia para habilitar FIFO sin reescritura estructural.
- Frontend en esta ola se enfoca en visibilidad de estados contables y reconciliación; expansión funcional completa después de estabilizar backend.
