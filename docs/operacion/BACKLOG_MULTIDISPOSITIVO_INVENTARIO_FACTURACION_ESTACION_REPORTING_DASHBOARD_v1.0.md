# BACKLOG PROFESIONAL MULTIDISPOSITIVO (INVENTARIOS, FACTURACION, ESTACION, REPORTES, DASHBOARD) v1.0

Version: v1.0  
Fecha: 2026-04-14  
Estado: Priorizado para delivery tecnico (sin cronograma)

## Resumen

Backlog priorizado por valor operativo, riesgo y dependencia tecnica para laptop/PC y movil, con logica unica backend y UX dual-shell.

Principio rector:

- contratos transversales obligatorios primero,
- capacidades por modulo despues,
- sin duplicar semantica de negocio entre canales.

## Contratos e interfaces clave (no-breaking)

1. Todo comando mutable DEBE incluir:
   - `company_id`, `branch_id`, `command_id`, `source_device`, `channel`, `device_class`.
2. Toda respuesta critica DEBE incluir:
   - `trace.request_id`, `trace.audit_event_id`, `trace.channel`, `trace.source_device`.
3. Error envelope unico cross-device:
   - `error_code`, `cause`, `recommended_action`, `request_id`.
4. RBAC/SoD y contexto efectivo se validan solo en backend.
5. `device_class` ajusta experiencia; NO modifica reglas de negocio.

## 1) Epicas

| ID | Epica | Modulo | Prioridad | Valor de negocio |
|---|---|---|---|---|
| E0 | Fundaciones transversales (seguridad, contexto, trazabilidad, idempotencia) | Cross | P0 | Evita deuda estructural y fallos de consistencia |
| E1 | Dashboard operativo multidispositivo | Dashboard | P0 | Visibilidad inmediata y priorizacion de accion |
| E2 | Operacion de estacion de servicios end-to-end | Estacion | P0 critico | Ingreso operativo diario y control de turno |
| E3 | Inventario core operacional | Inventarios | P0 | Exactitud de existencias y costo operativo |
| E4 | Facturacion y cobro operativo con control fiscal | Facturacion | P0 | Cumplimiento y monetizacion sin friccion |
| E5 | Reporting analitico y exportable | Reportes | P1 | Decision tactica/gerencial auditable |

## 2) Capacidades por epica

| Epica | Capacidades |
|---|---|
| E0 | Bootstrap de contexto, step-up auth, idempotencia por `command_id`, trazabilidad E2E, catalogo de errores unico |
| E1 | KPI moviles de turno/dia, alertas deduplicadas, workspaces desktop, drill-down a fuente |
| E2 | Apertura/cierre de turno, registro de despacho, venta/cobro, cancelacion con compensacion y reintentos |
| E3 | ABM de items/bodegas, recepciones/salidas/ajustes/transferencias, balance y kardex |
| E4 | Crear/emitir/consultar documento, cobro, contingencia/void controlados, estado fiscal por sucursal |
| E5 | Catalogo de datasets, ejecucion por filtros, snapshots, saved views, exportables gobernados |

## 3) Historias funcionales

| ID | Epica | Historia | Tipo |
|---|---|---|---|
| H0-1 | E0 | Como usuario autenticado, puedo operar solo con contexto efectivo empresa/sucursal | Confirmacion |
| H0-2 | E0 | Como sistema, rechazo duplicados de comandos por `command_id` | Confirmacion |
| H0-3 | E0 | Como auditor, correlaciono request, evento y actor en toda mutacion critica | Lectura |
| H1-1 | E1 | Como supervisor movil, veo KPI criticos del dia en una pantalla accionable | Lectura |
| H1-2 | E1 | Como supervisor desktop, navego alertas y abro drill-down al origen | Lectura |
| H1-3 | E1 | Como operacion, las alertas se deduplican y tienen owner/estado | Confirmacion |
| H2-1 | E2 | Como operador, abro turno una sola vez por sucursal de forma idempotente | Confirmacion |
| H2-2 | E2 | Como operador movil, registro despacho y genero venta sin doble aplicacion | Captura + Confirmacion |
| H2-3 | E2 | Como supervisor, cancelo venta con compensacion trazable y reintento controlado | Confirmacion |
| H2-4 | E2 | Como supervisor desktop, cierro turno con verificacion de pendientes criticos | Confirmacion |
| H3-1 | E3 | Como almacenista, registro recepcion/salida con validacion de stock/contexto | Captura + Confirmacion |
| H3-2 | E3 | Como supervisor, ejecuto ajuste con motivo obligatorio y trazabilidad | Confirmacion |
| H3-3 | E3 | Como analista, consulto balances y kardex por bodega/item | Lectura |
| H4-1 | E4 | Como cajero, creo y emito documento en flujo corto movil sin romper reglas fiscales | Captura + Confirmacion |
| H4-2 | E4 | Como operador, cobro documento y registro caja con correlacion completa | Confirmacion |
| H4-3 | E4 | Como supervisor desktop, resuelvo contingencia/void con permisos elevados | Confirmacion |
| H5-1 | E5 | Como analista, ejecuto dataset por filtros consistentes y guardo vista | Lectura |
| H5-2 | E5 | Como gerencia, exporto reporte auditable por periodo/sucursal | Lectura |
| H5-3 | E5 | Como operacion movil, consulto snapshot KPI y alertas accionables | Lectura |

## 4) Criterios de aceptacion

| ID | Criterios de aceptacion |
|---|---|
| H0-1 | Mutaciones bloqueadas sin contexto; lectura restringida; evidencia en auditoria |
| H0-2 | Reintento con mismo `command_id` no duplica efecto; respuesta determinista |
| H0-3 | 100% rutas criticas con `trace` completo y correlacion verificable |
| H1-1 | Vista movil carga KPI criticos en < 3s percibidos y muestra CTA claros |
| H1-2 | Drill-down desktop conserva filtro/corte y abre fuente sin perdida de contexto |
| H1-3 | Alertas no duplicadas por ventana; owner y estado obligatorios |
| H2-1 | No existen dos turnos abiertos por sucursal; segundo intento retorna estado idempotente |
| H2-2 | Un despacho no puede venderse dos veces; validacion de turno/contexto obligatoria |
| H2-3 | Cancelacion deja estado consistente (`CANCELLED` o `COMPENSATING`) y evidencia de reintento |
| H2-4 | Cierre bloqueado con pendientes criticos; cierre exitoso genera reporte de turno |
| H3-1 | Salida bloqueada con stock insuficiente; recepcion/salida requieren contexto y permisos |
| H3-2 | Ajuste sin motivo es rechazado; actor y motivo quedan auditados |
| H3-3 | Balance y kardex coherentes con movimientos confirmados |
| H4-1 | Emision movil completable en <= 5 pasos con reglas fiscales por sucursal validas |
| H4-2 | Cobro registrado sin duplicidad y correlacionado con documento y sesion de caja |
| H4-3 | Contingencia/void solo con permisos y step-up; transicion de estado valida |
| H5-1 | Mismo filtro/corte produce mismas cifras en laptop y movil |
| H5-2 | Export conserva lineage y parametros de consulta |
| H5-3 | Snapshot movil prioriza estado y alertas sin sobrecarga de densidad |

## 5) Dependencias

| Bloque | Depende de | Motivo |
|---|---|---|
| E1 | E0 | KPI/alertas requieren trazabilidad y contexto seguro |
| E2 | E0 | Operacion de turno necesita idempotencia, permisos y auditoria |
| E3 | E0 | Movimientos requieren invariantes, contexto y `command_id` idempotente |
| E4 | E0, E3, pagos | Facturacion con `apply_inventory` y cobro exige base transaccional consistente |
| E5 | E1, E2, E3, E4 | Reportes/datasets consumen hechos operativos estabilizados |

## 6) Riesgos

| Riesgo | Impacto | Mitigacion |
|---|---|---|
| Divergencia funcional desktop/movil | Alto | Un solo contrato command/query y pruebas de paridad |
| Duplicidad transaccional por reintento | Alto | Idempotencia obligatoria por `command_id` |
| Operacion sin contexto efectivo | Alto | Validacion backend obligatoria en toda mutacion |
| Sobrecarga UX movil | Medio-Alto | Limites de densidad y flujos <= 5 pasos |
| Deuda de trazabilidad | Alto | `trace` obligatorio + auditoria correlacionada |
| Riesgo fiscal en movil | Alto | Step-up y restricciones de operaciones sensibles en desktop |

## 7) Orden recomendado de implementacion

1. E0 Fundaciones transversales (bloqueante para todo).
2. E1 Dashboard operativo minimo (valor rapido + observabilidad).
3. E2 Estacion de servicios operativo movil + control desktop.
4. E3 Inventario core (consistencia de stock para operacion/cobro).
5. E4 Facturacion + cobro con controles fiscales y excepciones.
6. E5 Reporting analitico/exportable sobre base estabilizada.
7. Endurecimiento final: paridad cross-device, SLO UX y cierre de riesgos residuales.

## Supuestos y defaults

1. Canal principal: internet publica con TLS y controles perimetrales.
2. Estrategia UX oficial: `Workbench` (desktop) y `Taskflow` (movil).
3. Politica de producto: no-breaking por defecto.
4. Priorizacion aplicada: primero cimientos + operacion critica diaria, luego analitica profunda.

## Mapeo referencial al estado actual del repo

- Inventarios: `api/inventory/*`.
- Facturacion: `api/billing/*`.
- Estacion: `api/fuel/*`.
- Pagos/caja: `api/payments/*`.
- Reporting: `api/reporting/*`.
- Dashboard: `api/backend/dashboard/*`.

Este mapeo se incluye para mantener alineacion entre backlog de delivery y wiring real.
