# FACTURACION MULTIDISPOSITIVO (INTERNET-FIRST) v1

Version: v1.0  
Fecha: 2026-04-14  
Estado: Diseno funcional empresarial ejecutable (no-breaking)

## Resumen

Este documento define el modulo de facturacion para operacion remota por internet en laptop/PC y movil.

Decisiones cerradas de esta version:

- movil habilitado para emision + cobro + consulta,
- fiscalidad mixta por sucursal (NOOP/A/B) bajo control RBAC,
- UX dual-shell:
  - `Workbench` en desktop,
  - `Taskflow` en movil,
- logica de negocio unica en backend y contratos API canonicos preservados.

## 1) Alcance del modulo

- Gestionar `INVOICE` y `CREDIT_NOTE` con ciclo `DRAFT -> ISSUED -> VOIDED`.
- Soportar emision fiscal por sucursal con estados:
  - `NUMBER_RESERVED`, `ISSUED`, `PRINTED`, `FAILED_PRINT`, `CONTINGENCY`, `VOIDED`.
- Cubrir consulta operativa y flujo de cobro con integracion a pagos/caja.
- Excluir en esta fase:
  - parametrizacion fiscal global avanzada,
  - cierres contables,
  - conciliacion financiera profunda.

## 2) Operaciones criticas

| Operacion | Tipo | Laptop/PC | Movil | Criticidad |
|---|---|---|---|---|
| Crear documento (`/api/billing/docs/`) | Captura | Si | Si (formato corto) | Alta |
| Emitir (`/issue/`) | Confirmacion transaccional | Si | Si | Alta |
| Consultar detalle (`/docs/{id}/`) | Solo lectura | Si | Si (resumen) | Alta |
| Cobro (intent + captura/caja) | Captura + confirmacion transaccional | Si | Si | Alta |
| Impresion fiscal (`/print/`) | Confirmacion transaccional | Si | No | Alta |
| Contingencia (`/contingency/resolve/`) | Confirmacion transaccional | Si | No | Alta |
| Anulacion (`/void/`) | Confirmacion transaccional | Si | No por defecto | Muy alta |
| Config fiscal sucursal (`/fiscal/branch-config/`) | Captura de gobierno | Si | No | Muy alta |

## 3) Tareas recomendadas para laptop

- Emision completa con datos extendidos de cliente, lineas, impuestos y revision de totales.
- Gestion de excepciones fiscales: impresion, contingencia, reintentos, resolucion y anulacion.
- Operacion de control: auditoria, conciliacion de estados fiscales/contables, seguimiento de fallos.
- Cobro no asistido y control de caja/sesiones para escenarios de sucursal y POS.

## 4) Tareas recomendadas para movil

- Emision rapida guiada (3-5 pasos) para venta en campo.
- Cobro inmediato de operacion con confirmacion explicita.
- Consulta rapida de estado de documento, pago y resultado fiscal resumido.
- Reintento seguro de comandos mutables mediante idempotencia.

## 5) Flujos de emision, consulta y cobro

### Flujo emision desktop (canonico)

1. Crear: `POST /api/billing/docs/`.
2. Emitir: `POST /api/billing/docs/{id}/issue/`.
3. Opcional fiscal: `POST /api/billing/docs/{id}/print/` o `POST /api/billing/docs/{id}/contingency/resolve/`.

Resultado: documento emitido con referencia fiscal y estado trazable.

### Flujo emision/cobro movil (taskflow)

1. Crear documento simplificado o ticket.
2. Confirmar emision.
3. Ejecutar cobro y confirmar resultado.

Resultado: documento emitido + cobro aplicado o estado compensable con reintento controlado.

### Flujo consulta

- Lista resumida por estado/fecha/cliente.
- Detalle con bloque fiscal y bloque contable.
- Desktop muestra detalle completo; movil muestra estado + siguiente accion.

### Flujo cobro recomendado

- Crear intencion de pago.
- Capturar pago con referencia de proveedor/canal.
- Registrar movimiento de caja cuando aplique.
- En canal POS usar `api/retail/pos` para checkout con compensacion.

## 6) Permisos y validaciones

### Permisos minimos

- `billing.doc.create`, `billing.doc.read`, `billing.doc.issue`, `billing.doc.void`
- `billing.doc.print`, `billing.doc.contingency`, `billing.doc.contingency.resolve`
- `billing.fiscal.config.read`, `billing.fiscal.config.update`
- `payments.intent.create`, `payments.intent.read`, `payments.cash_session.*`, `payments.cash_movement.create`

### Validaciones obligatorias

- Contexto activo `company_id` + `branch_id` en toda mutacion.
- Lineas validas:
  - `quantity > 0`,
  - `unit_price >= 0`,
  - `tax_rate >= 0`.
- Idempotencia obligatoria para emision/cobro movil (`idempotency_key` o `command_id`).
- Anulacion prohibida en `DRAFT`.
- Transicion fiscal estricta por estado.
- `apply_inventory` requiere `warehouse_id` valido.

### Seguridad

- JWT/sesion segura, RBAC backend y step-up auth en acciones de alto impacto.
- Prohibido confiar en ocultar botones como control de autorizacion.

## 7) Riesgos fiscales y operativos

- Emision en contexto incorrecto (empresa/sucursal equivocada).
- Doble emision o doble cobro por reintentos sin idempotencia efectiva.
- Contingencias fiscales abiertas sin resolucion operativa.
- Anulacion improcedente desde movil.
- Desfase entre documento emitido y cobro/caja.
- Incumplimiento por habilitar configuracion fiscal en movil.

## 8) UX recomendada por dispositivo

### Workbench (laptop/PC)

- Tabla densa, filtros compuestos, busqueda avanzada y detalle integral.
- Panel de excepciones fiscales y estados de impresion/contingencia.
- Confirmaciones con resumen de impacto fiscal/contable.

### Taskflow (movil)

- Un objetivo por pantalla y CTA principal inequivoco.
- Formularios cortos con validacion inmediata.
- Estados recuperables: sesion expirada, permiso denegado, red intermitente.
- Confirmacion final con resumen minimo: documento, total, estado de cobro.

### Regla comun

- Mismo vocabulario de negocio, mismos estados y mismas consecuencias.

## 9) Eventos que deben quedar auditados

### Facturacion

- `BILLING_DOC_CREATED`
- `BILLING_DOC_ISSUED`
- `BILLING_DOC_VOIDED`
- `BILLING_DOC_CONTINGENCY_RECORDED`

### Pagos/Caja

- `PaymentIntentCreated`
- `PaymentCaptured`
- `CashSessionOpened`
- `CashSessionClosed`
- `CashMovementPosted`

### POS operativo (si aplica)

- `POSTicketOpened`
- `POSPaymentCaptured`
- `POSTicketClosed`
- `POSVoidRequested`
- `POS_TICKET_VOIDED`

### Correlacion obligatoria

Cada evento transaccional DEBE incluir correlacion por:

- `request_id`, `audit_event_id`, `correlation_id`, `causation_id`,
- `actor_id`, `company_id`, `branch_id`,
- `source_device`, `channel`.

## 10) Criterios de aceptacion

- Paridad funcional: misma operacion en desktop y movil produce mismo estado de negocio.
- Seguridad: 100% de operaciones criticas con auth + RBAC + contexto efectivo.
- Idempotencia: reintento movil no duplica emision ni cobro.
- Cumplimiento fiscal: transiciones de estado validas y auditables.
- Trazabilidad E2E: correlacion entre respuesta, auditoria y evento operacional.
- UX movil: emision/cobro completables en <= 5 pasos en escenario normal.

## Procesos que NO deben ejecutarse desde movil

- Configuracion fiscal por sucursal.
- Resolucion avanzada de contingencia fiscal.
- Anulacion documental como operacion estandar.
- Operaciones masivas, reprocesos historicos y cambios estructurales.

## Procesos que SI conviene resolver desde movil

- Emision rapida de venta/factura corta.
- Cobro inmediato de campo.
- Consulta de estado de documento y pago.
- Confirmaciones transaccionales de bajo/medio riesgo.

## Como evitar errores en dispositivos pequenos

- Forzar secuencia guiada y bloquear navegacion cruzada durante la transaccion.
- Prevalidar contexto activo antes de captura.
- Confirmaciones explicitas con resumen de importes/estado.
- Reintento seguro con idempotencia visible al operador.
- Mensajeria accionable: `Reintentar`, `Corregir dato`, `Volver a contexto`.
- Exigir step-up + doble confirmacion en acciones de alto impacto.

## Cambios importantes de interfaces/tipos (aditivos, no-breaking)

### Metadata obligatoria en comandos mutables

- `company_id`
- `branch_id`
- `command_id`
- `source_device`
- `channel`
- `device_class`

### Bloque `trace` de respuesta

- `trace.request_id`
- `trace.audit_event_id`
- `trace.channel`
- `trace.source_device`

### Catalogo unico de errores de dominio

- `error_code`
- `cause`
- `recommended_action`

### Recomendacion aditiva de cobro general

Si se habilita cobro directo fuera de POS, exponer captura explicita de intent en API de pagos para mantener trazabilidad uniforme de punta a punta.

## Plan de pruebas y escenarios

1. Emision desktop y movil: crear + emitir documento valido.
2. Idempotencia: reintentos no duplican emision/cobro.
3. Fiscal: `issue -> print` y `issue -> contingency -> resolve`.
4. Fiscal: rechazo de transiciones invalidas y conflictos.
5. Cobro: intent + captura + movimiento de caja con conciliacion de montos.
6. Fallos: escenario compensable con reintento controlado.
7. Seguridad: pruebas negativas por permisos y contexto cross-company/branch.
8. Auditoria: eventos obligatorios + correlacion completa.
9. UX: desktop multitarea; movil <= 5 pasos y recuperacion de errores.

## Supuestos y defaults

- Acceso remoto por internet publica con TLS extremo a extremo.
- Logica de negocio unica backend; UX separada por shell.
- Modo fiscal mixto por sucursal con controles RBAC.
- Movil habilitado para emision + cobro + consulta.
- Gobierno fiscal y excepciones avanzadas quedan en desktop.
- `/api/legacy/billing/*` se mantiene solo para compatibilidad, no como canal objetivo.

## Mapeo API actual (referencial)

- `POST /api/billing/docs/`
- `GET /api/billing/docs/{id}/`
- `POST /api/billing/docs/{id}/issue/`
- `POST /api/billing/docs/{id}/print/`
- `POST /api/billing/docs/{id}/contingency/`
- `POST /api/billing/docs/{id}/contingency/resolve/`
- `POST /api/billing/docs/{id}/void/`
- `GET/PUT /api/billing/fiscal/branch-config/`
- `POST /api/payments/intents/`
- `POST /api/payments/cash-sessions/open/`
- `POST /api/payments/cash-sessions/{id}/movements/`
- `POST /api/retail/pos/tickets/{id}/checkout/`
