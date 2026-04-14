# ESTACION DE SERVICIOS MULTIDISPOSITIVO (INTERNET-FIRST) v1

Version: v1.0  
Fecha: 2026-04-14  
Estado: Diseno operativo ejecutable (no-breaking)

## Resumen

Este documento define el modulo de estacion de servicios para operacion real en laptop/PC y movil con acceso remoto por internet.

Principios de esta version:

- logica unica en backend,
- UX separada por dispositivo (`Workbench` desktop, `Taskflow` movil),
- trazabilidad completa de punta a punta,
- reduccion de error humano en campo sin perder control operativo/fiscal.

## 1) Procesos del modulo

1. Apertura de turno por sucursal.
2. Registro de despacho fisico (pistola/bomba).
3. Conversion de despacho a venta.
4. Integracion automatica con facturacion e inventario.
5. Operacion de cobro/caja por canal directo o POS.
6. Anulacion con compensacion (billing + inventory) cuando aplique.
7. Cierre de turno y reportes (`shift-close`, `daily-close`).

## 2) Tareas por tipo de usuario

- Operador de pista:
  - registrar despachos,
  - validar datos minimos de vehiculo/punto de despacho,
  - consultar estado de operaciones en curso.
- Cajero/operador de turno:
  - crear ventas desde despachos,
  - ejecutar cobro operativo,
  - revisar tickets/ventas del turno.
- Supervisor de estacion:
  - abrir/cerrar turno,
  - aprobar anulaciones justificadas,
  - gestionar incidencias y reintentos de compensacion.
- Gerencia regional:
  - lectura de reportes diarios/turno,
  - monitoreo de alertas y desviaciones.
- Auditor/soporte:
  - revisar bitacora y correlacion de eventos,
  - investigar compensaciones fallidas.

## 3) Que operaciones van en laptop

- Cierre formal de turno con revision de totales y alertas.
- Reporteria densa y conciliacion (`/api/fuel/reports/shift-close/*`, `/api/fuel/reports/daily-close/`).
- Gestion de incidencias complejas:
  - compensaciones fallidas,
  - reintentos manuales,
  - anulaciones con investigacion.
- Seguimiento multi-sucursal y control operativo avanzado.

## 4) Que operaciones van en movil

- Apertura rapida de turno con checklist corto.
- Registro de despacho en flujo corto con validacion inmediata.
- Creacion de venta y cobro operativo en campo.
- Consulta rapida de estado de turno/venta y errores recuperables.
- Reintentos guiados solo para escenarios de bajo riesgo y con permiso.

## 5) Flujo de apertura

1. Validar sesion y contexto (`company`, `branch`).
2. Validar permiso `fuel.shift.open`.
3. Crear apertura con timestamp y nota.
4. Si ya existe turno abierto:
   - responder idempotente (`idempotency_status: DUPLICATE_PROCESSED`),
   - continuar operacion sin duplicar turno.

Controles obligatorios:

- un solo turno abierto por sucursal,
- bloqueo si no hay `X-Branch-Id`,
- visibilidad de contexto activo en UI.

## 6) Flujo operativo

1. Registrar despacho (`fuel.dispense.create`) con volumen/precio y normalizacion UOM.
2. Crear venta (`fuel.sale.create`) referenciando despacho del mismo turno.
3. Ejecutar integracion automatica:
   - inventario (`post_issue`),
   - facturacion (`create_draft` + `issue_doc`),
   - correlacion de flujo (`flow_correlation_id`).
4. Cobro:
   - canal directo o POS (`/api/retail/pos/*`) segun operacion.

Controles obligatorios:

- turno debe estar `OPEN`,
- un despacho no puede venderse dos veces (one-to-one `dispense -> sale`),
- consistencia de `shift/dispense/company/branch`.

## 7) Flujo de cierre

1. Validar permiso `fuel.shift.close`.
2. Verificar pendientes criticos:
   - ventas `COMPENSATING`,
   - ventas `COMPENSATION_FAILED`,
   - incidencias abiertas.
3. Cerrar turno con nota y actor responsable.
4. Generar/consultar reporte de cierre de turno.
5. Consolidar cierre diario por sucursal.

Regla operativa:

- cierre final se ejecuta en laptop; movil solo pre-cierre y consulta.

## 8) Control de incidencias

Estados de venta:

- `ACTIVE`
- `COMPENSATING`
- `COMPENSATION_FAILED`
- `CANCELLED`

Politica:

- si anular falla parcialmente:
  - marcar `COMPENSATING`,
  - registrar error y `compensation_next_retry_at`,
  - ejecutar ciclo automatico de compensacion.
- permitir retry manual por supervisor (`fuel.sale.void`).
- escalar automaticamente al superar umbral de intentos.

## 9) Auditoria y trazabilidad

Eventos de auditoria obligatorios:

- `FUEL_SHIFT_OPENED`
- `FUEL_DISPENSE_RECORDED`
- `FUEL_SALE_CREATED`
- `FUEL_SALE_VOIDED`
- `FUEL_SHIFT_CLOSED`

Eventos outbox de negocio obligatorios:

- `FuelSaleCreated`
- `FuelSaleCancelRequested`
- `FuelSaleCompensating`
- `FuelSaleCancelled`
- `FuelSaleCompensationFailed`
- `FuelSaleCompensationRetried`

Correlacion minima:

- `request_id`
- `flow_correlation_id`
- `actor_id`
- `company_id`
- `branch_id`
- `sale_id` o `shift_id`
- `causation_id`
- `channel` y `source_device` (cuando aplique en request/trace)

## 10) Validaciones criticas

- contexto (`company`, `branch`) obligatorio en comandos mutables,
- turno abierto para despacho/venta,
- `dispense.shift_id == sale.shift_id`,
- one-to-one `dispense -> sale`,
- reglas de estado para anular/retry (sin transiciones invalidas),
- idempotencia en apertura, venta y reversos por `idempotency_key`,
- validacion estricta de unidades y precision (litros canonicos + valor capturado),
- permisos RBAC backend por accion,
- prohibido delegar seguridad al ocultamiento de botones.

## 11) Pantallas y UX por dispositivo

### Laptop (`Workbench`)

- tablero operativo de estacion,
- gestion de turnos (apertura/cierre),
- bandeja de incidencias/compensaciones,
- reportes y conciliacion con filtros avanzados.

### Movil (`Taskflow`)

- inicio de turno,
- registrar despacho,
- crear venta/cobro,
- estado de operacion y retry guiado.

Patrones anti-error obligatorios:

- una accion primaria por pantalla,
- confirmacion con resumen de impacto,
- bloqueo de doble envio,
- mensajes accionables (`Reintentar`, `Corregir`, `Cambiar contexto`),
- manejo explicito de red intermitente.

## Cambios importantes en interfaces/contratos (aditivos, no-breaking)

- Mantener rutas canonicas:
  - `/api/fuel/*`
  - `/api/retail/pos/*`
  - `/api/billing/*`
  - `/api/inventory/*`
- Estandarizar metadata en comandos criticos:
  - `command_id`, `source_device`, `channel`, `device_class`.
- Estandarizar bloque `trace` en respuestas mutables:
  - `trace.request_id`, `trace.audit_event_id`, `trace.channel`, `trace.source_device`.
- Catalogo unico de errores operativos:
  - `error_code`, `cause`, `recommended_action`.

## Plan de pruebas y escenarios

1. Apertura idempotente de turno (segunda llamada no duplica).
2. Despacho valido/invalido por turno, contexto y UOM.
3. Venta sobre despacho valido y bloqueo de doble venta.
4. Cierre de turno con permisos correctos y rechazo sin permiso.
5. Anulacion con compensacion exitosa.
6. Anulacion con compensacion fallida + retry manual.
7. Ciclo automatico de compensacion procesa pendientes.
8. Reportes de cierre de turno/diario reflejan cancelaciones y alertas.
9. Paridad funcional: misma logica de negocio en desktop/movil.
10. UX movil: flujo critico completable en <= 5 pasos y recuperacion de error.

## Supuestos y defaults

- canal remoto por internet con TLS y autenticacion vigente,
- logica de negocio unica en backend,
- cierre final de turno e incidencias criticas en laptop,
- movil enfocado en operacion de campo, no en administracion sensible,
- prioridad operativa: idempotencia, contexto visible y confirmaciones explicitas.

## Mapeo API actual (referencial)

- `POST /api/fuel/shifts/open/`
- `POST /api/fuel/shifts/{shift_id}/close/`
- `GET /api/fuel/shifts/`
- `POST /api/fuel/dispenses/`
- `GET /api/fuel/dispenses/`
- `POST /api/fuel/sales/`
- `POST /api/fuel/sales/{sale_id}/cancel/`
- `POST /api/fuel/sales/{sale_id}/compensate/retry/`
- `GET /api/fuel/reports/shift-close/{shift_id}/`
- `GET /api/fuel/reports/daily-close/`
