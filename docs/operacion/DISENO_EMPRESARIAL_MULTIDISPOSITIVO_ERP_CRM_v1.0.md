# DISENO EMPRESARIAL MULTIDISPOSITIVO ERP/CRM (INTERNET-FIRST) v1.0

Version: v1.0  
Fecha: 2026-04-14  
Estado: Diseno empresarial aprobado para implementacion

## Resumen

Este documento define el marco integral para una aplicacion ERP/CRM web accesible por internet, con una sola logica de negocio backend y dos experiencias de uso diferenciadas:

- `Workbench` para laptop/PC.
- `Taskflow` para movil.

El objetivo es operar en condiciones reales, sin breaking changes de contratos, con trazabilidad end-to-end y entrega priorizada por valor, riesgo y dependencias.

## 1) Arquitectura funcional

1. Modelo rector: `single business logic + dual UX shell`.
2. Dominios backend canonicos:
   - `inventarios`
   - `facturacion`
   - `estacion_servicios`
   - `payments`
   - `reporting`
   - `dashboard`
   - `iam/rbac/audit`
3. Capas frontend canonicas:
   - `app`
   - `router`
   - `layouts`
   - `pages`
   - `features`
   - `widgets`
   - `entities`
   - `services`
   - `stores`
   - `shared`
   - `core`
4. Contratos transversales obligatorios:
   - Comando mutable: `company_id`, `branch_id`, `command_id`, `source_device`, `channel`, `device_class`.
   - Respuesta critica: `trace.request_id`, `trace.audit_event_id`, `trace.channel`, `trace.source_device`.
   - Error uniforme: `error_code`, `cause`, `recommended_action`, `request_id`.
5. Endpoints canonicos:
   - `/api/inventory/*`
   - `/api/billing/*`
   - `/api/fuel/*`
   - `/api/payments/*`
   - `/api/reporting/*`
   - `/api/backend/dashboard/*`

## 2) Criterios para decidir laptop vs movil

1. Una capacidad va en movil si:
   - es frecuente y de ejecucion inmediata,
   - se completa en 3-5 pasos,
   - requiere baja densidad y decision rapida.
2. Una capacidad va en laptop si:
   - es analitica, masiva o de excepcion,
   - requiere comparacion, multipanel o exportables,
   - tiene alto impacto regulatorio o administrativo.
3. Regla obligatoria:
   - La semantica de negocio no cambia por dispositivo.
   - Solo cambia la interaccion y la densidad de informacion.

## 3) Separacion UX por dispositivo

1. `Workbench` (laptop/PC):
   - navegacion lateral completa,
   - tablas densas y filtros compuestos,
   - acciones por lote,
   - drill-down profundo para conciliacion y auditoria.
2. `Taskflow` (movil):
   - una accion principal por pantalla,
   - formularios cortos con validacion inmediata,
   - CTA directos y estados claros,
   - foco en pendientes y alertas del dia.
3. Regla anti-patron:
   - Prohibido usar un "desktop comprimido" como estrategia movil.

## 4) Reglas de seguridad y permisos

1. Rutas publicas:
   - `/login`
   - `/login/2fa`
   - `/bootstrap`
   - `/device/enroll`
   - `/password-change` (segun estado)
2. Rutas privadas:
   - modulos operativos y analiticos.
3. Orden obligatorio de guardias:
   1. bootstrap
   2. sesion
   3. ACL
   4. contexto
   5. permisos por ruta/accion
4. Autorizacion:
   - RBAC/SoD solo en backend por accion y contexto efectivo.
5. Operaciones criticas:
   - step-up auth obligatorio.
6. Contexto:
   - Sin `company_id` y `branch_id` validos no se ejecuta mutacion.

## 5) Reglas de auditoria

1. Toda mutacion critica DEBE registrar actor, contexto, dispositivo y resultado.
2. Correlacion obligatoria:
   - `request_id`
   - `audit_event_id`
   - `actor_id`
   - `company_id`
   - `branch_id`
   - `source_device`
   - `channel`
   - `correlation_id`
   - `causation_id`
3. Eventos minimos por modulo:
   - Inventario: `RECEIVED`, `ISSUED`, `ADJUSTED`, `TRANSFERRED`.
   - Facturacion: `DOC_CREATED`, `DOC_ISSUED`, `DOC_VOIDED`, `DOC_CONTINGENCY_*`.
   - Estacion: `SHIFT_OPENED`, `DISPENSE_RECORDED`, `SALE_CREATED`, `SHIFT_CLOSED`.
   - Pagos: `INTENT_CREATED`, `CAPTURED`, `CASH_SESSION_*`.
   - Reporting/Dashboard: `RUN_EXECUTED`, `EXPORTED`, `ALERT_RAISED`, `ALERT_ACKED`.
4. Regla de logging:
   - Prohibido exponer secretos, firmas o material criptografico.

## 6) Propuesta de navegacion

1. Shell publico: `AuthLayout`.
2. Shell privado: `MainLayout` con switch interno:
   - `WorkbenchShell` (desktop)
   - `TaskflowShell` (movil)
3. Punto de entrada por dispositivo:
   - Desktop: tablero operativo con acceso analitico inmediato.
   - Movil: pendientes/hoy con acciones rapidas.
4. Contexto efectivo visible siempre.
5. Falta de permiso:
   - ruta `403`.
6. Falta de contexto:
   - redireccion a seleccion de contexto.

## 7) Riesgos y mitigaciones

1. Divergencia funcional desktop/movil.
   - Mitigacion: contratos unicos command/query y pruebas de paridad.
2. Duplicidad por reintentos sin idempotencia real.
   - Mitigacion: `command_id` obligatorio y control backend.
3. Operacion sin contexto efectivo.
   - Mitigacion: guardias y validaciones backend bloqueantes.
4. Sobrecarga cognitiva en movil.
   - Mitigacion: taskflows <= 5 pasos y limites de densidad.
5. Deuda de trazabilidad.
   - Mitigacion: `trace` obligatorio + auditoria correlacionada.
6. Riesgo fiscal por acciones sensibles en movil.
   - Mitigacion: restricciones por rol/canal + step-up auth.

## 8) Backlog inicial recomendado

1. Epica E0: Fundaciones transversales.
   - guardias unificados,
   - metadata de comando,
   - `trace`,
   - error envelope,
   - step-up.
2. Epica E1: Dashboard operativo dual.
   - KPI moviles accionables,
   - vistas workbench con drill-down.
3. Epica E2: Estacion de servicios end-to-end.
   - apertura/cierre de turno,
   - despacho,
   - venta/cobro,
   - compensacion.
4. Epica E3: Inventario core.
   - ABM base,
   - recepciones/salidas/ajustes/transferencias,
   - balances.
5. Epica E4: Facturacion + cobro.
   - crear/emitir/consultar,
   - contingencia/void controlado,
   - caja.
6. Epica E5: Reporting analitico.
   - runs,
   - snapshots,
   - saved views,
   - exportables.
7. Endurecimiento final:
   - paridad cross-device,
   - rendimiento,
   - accesibilidad,
   - observabilidad.

## Cambios de API/interfaces/tipos

1. Cambios aditivos y no-breaking.
2. Homologar metadata de comandos en todos los modulos operativos.
3. Homologar `trace` en respuestas criticas.
4. Homologar error envelope de negocio.
5. Prohibido crear APIs distintas por dispositivo con semantica diferente.

## Plan de validacion

1. Router/guardias:
   - publico/privado/bootstrap/contexto/permisos.
2. Paridad funcional desktop vs movil en operaciones criticas.
3. Idempotencia por `command_id`.
4. Validacion de `trace` y error envelope.
5. Pruebas negativas RBAC/SoD y step-up.
6. UX movil:
   - flujos criticos <= 5 pasos.
7. Reporting/dashboard:
   - mismo filtro, misma cifra.
8. Correlacion request-log-auditoria verificable por caso.

## Supuestos y defaults

1. Stack vigente:
   - Quasar + Vue + Pinia (frontend)
   - Django + DRF (backend)
2. Una sola SPA y una sola logica de negocio backend.
3. Estrategia oficial dual-shell (`Workbench` / `Taskflow`).
4. Politica no-breaking por defecto.
5. Operacion remota por internet con TLS y controles perimetrales.
