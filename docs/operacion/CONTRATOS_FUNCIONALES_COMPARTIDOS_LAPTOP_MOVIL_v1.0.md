# CONTRATOS FUNCIONALES COMPARTIDOS LAPTOP/MOVIL (ERP WEB) v1.0

Version: v1.0  
Fecha: 2026-04-14  
Estado: Diseno tecnico-funcional previo a desarrollo (sin codigo)

## Resumen

Este documento define un contrato funcional unico para operacion web empresarial en laptop/PC y movil:

- misma logica de negocio en backend,
- UX diferenciada por dispositivo,
- trazabilidad obligatoria en toda accion critica,
- evolucion no-breaking por defecto.

## 1) Modulos funcionales

1. `iam_contexto`: autenticacion, sesion, ACL/RBAC, contexto empresa/sucursal.
2. `catalogos_maestros`: clientes, productos/servicios, bodegas, estaciones y listas base.
3. `operacion_transaccional`: inventarios, facturacion, estacion de servicios, pagos/caja.
4. `reporting`: datasets, consultas analiticas, exportables, vistas guardadas.
5. `dashboard`: monitoreo operativo, alertas y priorizacion de acciones.
6. `auditoria_trazabilidad`: bitacora, correlacion request-evento y evidencia operativa.
7. `dispositivos_sync`: enrolamiento, identidad de dispositivo, comando idempotente y revocacion.

## 2) Capacidades por modulo

- `iam_contexto`: login/logout, refresh, bootstrap de contexto, step-up en alto impacto.
- `catalogos_maestros`: ABM controlado, vigencia y versionado funcional.
- `operacion_transaccional`: crear, emitir, anular, transferir y cerrar con reglas de estado.
- `reporting`: ejecutar consultas por filtro/corte, snapshots y export.
- `dashboard`: KPI, alertas deduplicadas y drill-down a fuente.
- `auditoria_trazabilidad`: registrar actor, contexto, dispositivo, causacion y resultado.
- `dispositivos_sync`: identidad criptografica, procesamiento idempotente y revocacion.

## 3) Entidades principales

- `User`, `Role`, `Permission`, `Session`, `StepUpChallenge`
- `Company`, `Branch`, `EffectiveContext`
- `Device`, `Channel`, `Command`, `AppliedCommand`
- `InventoryItem`, `Warehouse`, `Movement`, `Transfer`
- `BillingDocument`, `FiscalState`, `PaymentIntent`, `CashSession`
- `FuelShift`, `Dispense`, `FuelSale`, `CompensationState`
- `ReportRun`, `Snapshot`, `SavedView`, `DashboardAlert`
- `AuditEvent`, `Trace`

## 4) Acciones permitidas (modelo de accion)

- `read`: consulta sin mutacion.
- `capture`: captura preliminar (borrador/intencion).
- `confirm`: mutacion transaccional o irreversible.
- `cancel_or_compensate`: reversa con reglas explicitas de compensacion.
- `admin`: configuracion sensible y operaciones masivas (desktop).

## 5) Reglas de permisos

- RBAC/SoD DEBE validarse solo en backend por accion y contexto efectivo.
- Patron de permiso recomendado: `{modulo}.{recurso}.{accion}`.
- Operaciones criticas (`void`, `close`, `contingency.resolve`, `fiscal.config.update`) requieren:
  1. permiso explicito,
  2. contexto valido,
  3. step-up auth.
- UI NO sustituye autorizacion; ocultar boton no es control de seguridad.

## 6) Reglas de contexto por usuario y dispositivo

- Todo comando mutable DEBE incluir:
  - `company_id`
  - `branch_id`
  - `command_id`
  - `source_device`
  - `channel`
  - `device_class`
- `device_class` (`desktop|mobile`) ajusta UX/shape de respuesta, NO reglas de negocio.
- Cambio de contexto invalida operaciones sensibles en curso.
- Sin contexto efectivo: lectura restringida y mutaciones bloqueadas.
- Movil requiere sesion mas estricta ante riesgo (reauth/step-up en alto impacto).

## 7) Endpoints/servicios recomendados (conceptual)

### Separacion CQRS ligera

1. `Command Services`: `/api/{modulo}/commands/*`
2. `Query Services`: `/api/{modulo}/queries/*`

### Reporting/Dashboard

1. `/api/reporting/catalog`
2. `/api/reporting/runs`
3. `/api/reporting/exports`
4. `/api/dashboard/workspaces`
5. `/api/dashboard/alerts`

### Operacion transaccional

1. `/api/inventory/*`
2. `/api/billing/*`
3. `/api/fuel/*`
4. `/api/payments/*`

### Contratos transversales

1. request metadata obligatoria (contexto + idempotencia).
2. response `trace` obligatoria (`request_id`, `audit_event_id`, `channel`, `source_device`).
3. error envelope unico (`error_code`, `cause`, `recommended_action`).

## 8) Diferencias entre lectura, captura y confirmacion

### Lectura

1. Sin side effects.
2. Cacheable segun politicas de datos.
3. Orientada a consulta rapida en movil y analisis amplio en desktop.

### Captura

1. Genera borrador/intencion.
2. Valida datos minimos.
3. Permite correccion antes de impacto transaccional.

### Confirmacion

1. Ejecuta mutacion final.
2. Exige validacion de estado/transicion.
3. Exige idempotencia + auditoria completa.
4. Requiere confirmacion UX explicita y step-up si aplica.

## 9) Eventos auditables obligatorios

### Transversales

1. `AUTH_LOGIN_SUCCEEDED|FAILED`
2. `SESSION_REFRESHED`
3. `STEP_UP_VERIFIED`
4. `CONTEXT_SWITCHED`
5. `COMMAND_APPLIED|DUPLICATE|REJECTED`

### Operacion

1. Inventario: `INVENTORY_RECEIVED|ISSUED|ADJUSTED|TRANSFERRED`
2. Facturacion: `BILLING_DOC_CREATED|ISSUED|VOIDED|CONTINGENCY_*`
3. Estacion: `FUEL_SHIFT_OPENED|DISPENSE_RECORDED|SALE_CREATED|SHIFT_CLOSED`
4. Pagos: `PAYMENT_INTENT_CREATED|PAYMENT_CAPTURED|CASH_SESSION_*`

### Analitica

1. `REPORT_RUN_EXECUTED`
2. `REPORT_EXPORTED`
3. `DASHBOARD_ALERT_RAISED|ACKED`

### Correlacion minima por evento

- `request_id`
- `audit_event_id`
- `actor_id`
- `company_id`
- `branch_id`
- `source_device`
- `channel`
- `correlation_id`
- `causation_id`

## 10) Recomendaciones para no duplicar logica entre laptop y movil

1. Las validaciones y transiciones viven en servicios de dominio backend.
2. Desktop y movil comparten SDK/cliente tipado y catalogo unico de errores.
3. Reusar los mismos command/query contracts; variar solo layout/flujo/densidad.
4. Mantener pruebas de paridad cross-device por caso critico.
5. Prohibir forks API por dispositivo con semantica divergente.
6. Usar `render_hints` y `device_class` para presentacion, no para reglas.

## Cambios de interfaces/tipos (aditivos, no-breaking)

### Request metadata obligatoria en comandos mutables

1. `company_id`
2. `branch_id`
3. `command_id`
4. `source_device`
5. `channel`
6. `device_class`

### Response `trace` obligatoria

1. `trace.request_id`
2. `trace.audit_event_id`
3. `trace.channel`
4. `trace.source_device`

### Error envelope unificado

1. `error_code`
2. `cause`
3. `recommended_action`
4. `request_id`

## Casos de validacion (antes de desarrollo)

1. Paridad: mismo comando desktop/movil produce mismo estado final.
2. Idempotencia: reintento con igual `command_id` no duplica operacion.
3. Seguridad: RBAC/SoD bloquea acciones criticas sin rol/contexto.
4. Trazabilidad: toda mutacion correlaciona API + log + auditoria.
5. UX funcional:
   - movil completa tareas criticas en <= 5 pasos,
   - desktop soporta analisis profundo sin perdida de control.
6. Reportes: mismo filtro/corte produce mismas cifras en ambos dispositivos.

## Supuestos y defaults

1. Canal principal: internet publica con TLS extremo a extremo.
2. Estrategia UX oficial: dual-shell (`Workbench` desktop, `Taskflow` movil).
3. Politica de evolucion: no-breaking por defecto y contratos aditivos.
4. Alto impacto: step-up auth + evidencia de auditoria obligatoria.

## Mapeo referencial al repositorio actual

- IAM/contexto: `api/auth/*` y stores de bootstrap/ACL.
- Operacion transaccional:
  - `api/inventory/*`
  - `api/billing/*`
  - `api/fuel/*`
  - `api/payments/*`
- Reporting/dashboard:
  - `api/reporting/*`
  - `api/backend/dashboard/*`
- Sync/dispositivo:
  - `api/sync/*`
  - `api/sync-hmac/*` (compatibilidad legacy)

Este mapeo existe para evitar drift entre diseno funcional y wiring real.
