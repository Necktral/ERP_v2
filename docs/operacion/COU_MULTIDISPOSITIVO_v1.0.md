# CENTRO DE OPERACION UNIFICADA (COU) MULTIDISPOSITIVO v1.0

Version: v1.0  
Fecha: 2026-04-14  
Estado: Decision operativa para implementacion internet-first

## Nota operativa de alcance movil (2026-05)

> **Alcance real del canal movil:** selectivo y por viabilidad.
> El movil NO replica el sistema desktop. Funcionalidades confirmadas: facturacion,
> inventario, reportes, control de asistencias, bitacoras de mantenimiento de transporte.
> Nuevas funcionalidades se incorporan tras analisis individual de viabilidad.
> La matriz de decision de este documento aplica como referencia de priorizacion,
> no como compromiso de implementacion simultanea.

## Resumen

Estrategia base del COU:

- `single business logic`: misma semantica de negocio y seguridad para todos los clientes.
- `dual UX`: experiencia separada para `laptop/PC` (Workbench) y `movil` (Taskflow).

Objetivo: ejecutar operacion real por internet sin degradar control, auditoria ni consistencia transaccional.

## 1) Matriz profesional de decision

| Modulo | Objetivo operativo | Laptop/PC | Movil | Prioridad | Tipo (lectura/captura/confirmacion) | Complejidad UX por dispositivo | Riesgos clave | Recomendacion final |
|---|---|---|---|---|---|---|---|---|
| Inventarios | Control de existencias, movimientos, transferencias y balance | Si (full) | Si (acotado) | P0 | Captura + confirmacion + lectura | Desktop: Alta / Movil: Media | errores de stock por captura rapida, doble envio, contexto equivocado | Desktop para maestros, ajustes complejos y transferencias; movil para recepciones/salidas/ajustes simples con escaneo e idempotencia |
| Facturacion | Emision, control fiscal, contingencias, anulacion | Si (full) | Si (taskflow) | P0 | Captura + confirmacion transaccional + lectura | Desktop: Alta / Movil: Media-Alta | incumplimiento fiscal, anulaciones indebidas, impresion/contingencia mal operadas | Movil para emision rapida y consulta; desktop para fiscal config, contingencia, void y trazabilidad completa |
| Estacion de servicios | Operacion diaria de turno, despacho, venta y cierre operativo | Si (supervision/control) | Si (operacion primaria) | P0 critico | Captura + confirmacion transaccional + lectura | Desktop: Media / Movil: Alta | perdidas por registro tardio, fraude operativo, desalineacion turno-caja | Movil como canal principal de ejecucion; desktop para cockpit, supervision, compensaciones y auditoria |
| Reportes | Consulta analitica, cortes y exportables para decisiones | Si (full) | Si (lectura enfocada) | P1 | Lectura (y export en desktop) | Desktop: Alta / Movil: Baja-Media | decisiones con filtros incorrectos, mala interpretacion de cifras | Desktop para analisis profundo y composicion; movil para snapshots KPI, alertas y drill-down corto |
| Dashboard | Monitoreo operativo ejecutivo y priorizacion de acciones | Si | Si | P0 | Lectura + confirmacion de acciones disparadas | Desktop: Media / Movil: Baja | saturacion de informacion en movil, falta de accionabilidad | Dashboard dual: desktop analitico y movil orientado a "que hacer ahora" con CTA directos |

## 2) Funciones que deben existir solo en laptop

- Configuracion maestra y parametrizacion sensible: reglas fiscales, series, politicas y settings de sucursal.
- Operaciones masivas: cargas por lote, conciliaciones amplias, correcciones bulk y cierres con impacto transversal.
- Gestion avanzada de excepciones: contingencia fiscal, investigacion de incidentes, anulaciones con evidencia.
- Composicion analitica: builder de dashboards/reportes, exportaciones pesadas, comparativos multiperiodo/multisucursal.
- Auditoria forense: trazabilidad completa con filtros avanzados, lineage y correlacion cruzada.

## 3) Funciones que si deben estar en movil

- Flujos transaccionales cortos de alta frecuencia: crear operacion, confirmar, recibir resultado.
- Acciones de campo: despacho/venta, apertura-cierre de turno, capturas rapidas de inventario.
- Consulta operativa minima: estado actual, alertas, pendientes y confirmacion de resultado.
- Confirmaciones criticas con UX explicita: `Confirmar`, `Reintentar`, `Cancelar`.
- Recuperacion de errores operativos: sesion vencida, contexto invalido, permiso denegado, conectividad intermitente.

## 4) Funciones que no deben copiarse a movil

- Tablas densas con edicion masiva y filtros complejos.
- Flujos de mas de 5 pasos o de alta carga cognitiva.
- Parametrizacion regulatoria/fiscal y cambios estructurales.
- Composicion de reportes y exportaciones complejas.
- Operaciones de alto impacto sin step-up auth ni doble confirmacion.

## 5) Cambios de interfaces/tipos recomendados (aditivos, no-breaking)

- Contexto y seguridad por comando: `company_id`, `branch_id`, `command_id`, `source_device`.
- Envelope de trazabilidad obligatorio: `request_id`, `audit_event_id`, `actor_id`, `channel`.
- Perfil de experiencia por cliente: `device_class=desktop|mobile` solo para shape/UI hints, no para reglas de negocio.
- Contrato de errores uniforme cross-device: codigos/causas normalizadas para recuperacion UX.

## 6) Orden de implementacion recomendado

1. Fase A (Fundacion): autenticacion fuerte, contexto obligatorio, RBAC/SoD, auditoria correlacionada y contrato de errores uniforme.
2. Fase B (P0 movil operativo): estacion de servicios Taskflow + dashboard movil accionable.
3. Fase C (P0 transaccional): facturacion movil acotada + inventario movil de captura rapida.
4. Fase D (Workbench desktop): inventario/facturacion avanzados, supervision, bulk y excepciones.
5. Fase E (Analitica): reportes/dashboards avanzados desktop + snapshots moviles de decision.

## 7) Pruebas y escenarios de aceptacion

- Paridad funcional: misma operacion en desktop y movil produce mismo resultado de negocio.
- Seguridad: 100 por ciento de endpoints criticos con auth + autorizacion contextual + auditoria.
- Idempotencia: reintentos moviles no duplican transacciones.
- Trazabilidad E2E: cada transaccion critica correlaciona `request_id` + `audit_event_id` + actor + contexto + dispositivo.
- UX movil: tareas criticas completables en 3-5 pasos con estados de error recuperables.
- Consistencia analitica: mismo filtro/corte produce mismas cifras en desktop y movil.

## 8) Errores de producto graves a evitar

- Disenar movil como desktop comprimido.
- Duplicar reglas de negocio en frontend.
- Divergir semantica entre API desktop y API movil.
- Basar seguridad en ocultar botones en UI.
- Permitir operaciones sin contexto explicito de empresa/sucursal.
- Mezclar comandos transaccionales con consultas analiticas pesadas sin separacion.
- No instrumentar auditoria/correlacion de punta a punta desde inicio.
- Ignorar conectividad movil inestable como condicion normal de operacion.
- Disenar navegacion sin estados recuperables (sesion/contexto/permiso).
- No definir metricas de exito operativo y de seguridad desde la primera iteracion.

## Supuestos y defaults

- Canal principal: internet publica con TLS y controles perimetrales.
- `sync-hmac` fue retirado; los carriles legacy no definen la UX objetivo del COU.
- Politica default: no-breaking, cambios aditivos y endurecimiento de trazabilidad.
- Movil prioriza ejecucion operativa; desktop prioriza control, analitica y gobierno.

## Mapeo al estado actual del repo (referencial)

- Inventarios: `api/inventory/*` (`apps.kernels.inventarios`).
- Facturacion: `api/billing/*` (`apps.kernels.facturacion`).
- Estacion de servicios: `api/fuel/*` (`apps.modulos.estacion_servicios`).
- Reportes: `api/reporting/*` (`apps.kernels.reporting`).
- Dashboard: `api/backend/dashboard/*` + shell frontend analytics.

Este mapeo es para alinear backlog con wiring real y evitar drift de producto.
