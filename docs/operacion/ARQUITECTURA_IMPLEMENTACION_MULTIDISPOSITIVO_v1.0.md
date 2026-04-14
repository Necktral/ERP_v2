# ARQUITECTURA DE IMPLEMENTACION MULTIDISPOSITIVO (FRONTEND + BACKEND) v1.0

Version: v1.0  
Fecha: 2026-04-14  
Estado: Diseno tecnico de implementacion (no-breaking)

## Resumen

Esta arquitectura define una implementacion tecnica unica para laptop/PC y movil sobre una sola logica de negocio backend, con UX separada por dispositivo (`Workbench` y `Taskflow`) y trazabilidad obligatoria en operaciones criticas.

## 1) Estructura de modulos

1. `iam_contexto`: autenticacion, sesion, ACL/RBAC, contexto efectivo.
2. `inventarios`: items, bodegas, movimientos, transferencias, balances.
3. `facturacion`: documentos, emision, contingencia, anulacion, estado fiscal.
4. `estacion_servicios`: turnos, despachos, ventas, compensacion, cierres.
5. `pagos_caja`: intents, sesiones de caja, movimientos.
6. `reporting`: catalogo de datasets, runs, snapshots, exports, saved views.
7. `dashboard`: workspaces, alertas, drill-down operativo.
8. `auditoria_trazabilidad`: `request_id`, `audit_event_id`, correlacion E2E.
9. `shared_contracts`: error envelope, trace envelope, metadata de comando.

## 2) Organizacion de carpetas

### Frontend objetivo (alineado al repo actual)

```text
src/
  app/                 # bootstrap global
  router/              # guardias, rutas publicas/privadas
  layouts/             # AuthLayout, MainLayout + shells
  pages/               # contenedores de ruta
  features/            # casos de uso por dominio
  widgets/             # composiciones UI por dominio
  entities/            # DTOs, tipos de dominio, mapeadores
  services/            # clientes API por dominio
  stores/              # auth, acl, context, ui, dominio
  shared/              # contratos HTTP, utilidades, ui base
  core/                # storage, http boot, cross-cutting tecnico
```

### Backend objetivo (alineado al repo actual)

```text
apps/
  kernels/
    inventarios/
    facturacion/
    payments/
    reporting/
  modulos/
    estacion_servicios/
    dashboard/
    accounts/
    iam/
    rbac/
    audit/
    sync_engine/
```

## 3) Separacion entre rutas publicas y privadas

1. Publicas:
   - `/login`
   - `/login/2fa`
   - `/bootstrap`
   - `/device/enroll`
   - `/password-change` (segun estado)
2. Privadas: modulos operativos, reportes, dashboard y auditoria.
3. Guardias obligatorias en orden:
   1. bootstrap state
   2. sesion
   3. ACL
   4. contexto
   5. permisos por ruta
4. Regla: ruta privada sin contexto efectivo redirige a seleccion de contexto.
5. Regla: ruta con permisos faltantes redirige a `403`.

## 4) Separacion entre shell laptop y shell movil

1. Mantener una sola SPA y mismas rutas de negocio.
2. Resolver experiencia por `device_class` y metadatos de ruta, no por logica duplicada.
3. `Workbench` (desktop):
   - densidad alta,
   - multitarea,
   - tablas y filtros avanzados.
4. `Taskflow` (movil):
   - flujo de 3-5 pasos,
   - una accion principal por pantalla.
5. Implementacion recomendada:
   - `MainLayout` con switch interno de shell (`WorkbenchShell` / `TaskflowShell`)
   - override manual de experiencia para QA/soporte.

## 5) Stores o manejo de estado recomendado

1. Base obligatoria Pinia:
   - `auth`
   - `acl`
   - `context`
   - `ui`
2. Stores de dominio por modulo:
   - `inventory`
   - `billing`
   - `fuel`
   - `payments`
   - `reporting`
   - `dashboard`
3. Cada store separa `state` y `actions` de lectura/captura/confirmacion.
4. Regla: el store no implementa reglas de negocio criticas; solo orquestacion cliente.
5. Regla: comandos mutables incluyen `command_id` desde capa de accion.

## 6) Capa de servicios API

1. Servicios por dominio con cliente comun (`api`) y contratos tipados en `entities`.
2. Separar metodos conceptualmente en:
   - `queries` (lectura)
   - `commands` (mutacion)
3. Incluir metadata transversal en comandos:
   - `company_id`
   - `branch_id`
   - `command_id`
   - `source_device`
   - `channel`
   - `device_class`
4. Exigir envelope de respuesta critica con `trace`.
5. Estandarizar manejo de error envelope:
   - `error_code`
   - `cause`
   - `recommended_action`
   - `request_id`

## 7) Manejo de sesion, permisos y contexto

1. Sesion por cookie segura con refresh automatico y logout duro ante falla de refresh.
2. Carga de ACL post-auth y cache temporal en store.
3. Contexto activo persistido en storage y propagado en headers.
4. Evaluacion de permisos por ruta y por accion antes de comandos.
5. Operaciones de alto impacto con step-up auth y validacion backend obligatoria.

## 8) Estrategia de componentes reutilizables

1. `shared/ui`: componentes atomicos transversales (inputs, tablas base, estados vacios, banners).
2. `widgets/{modulo}`: componentes de negocio reutilizables por paginas del mismo dominio.
3. `features/{modulo}`: composables/hooks de orquestacion e interaccion cliente.
4. Politica: no duplicar componentes desktop/movil; crear variantes de presentacion sobre misma semantica.
5. Politica: toda accion critica usa componentes de confirmacion estandarizados.

## 9) Estrategia de layouts por dispositivo

1. `AuthLayout`: rutas publicas.
2. `MainLayout`: rutas privadas + contexto global.
3. `WorkbenchShell`:
   - navegacion lateral completa,
   - filtros persistentes,
   - paneles paralelos.
4. `TaskflowShell`:
   - navegacion por tareas,
   - acciones rapidas,
   - CTA unicos,
   - densidad reducida.
5. Regla: estado de contexto visible en ambos shells.
6. Regla: errores recuperables visibles y accionables en ambos shells.

## 10) Propuesta de implementacion paso a paso

1. Endurecer contratos transversales cliente-servidor (`metadata`, `trace`, `error envelope`) sin romper endpoints.
2. Unificar guardias de router y policies de contexto/permisos por accion.
3. Implementar switch de shell en layout manteniendo rutas unicas.
4. Crear stores de dominio minimos para inventarios, facturacion, estacion, reporting y dashboard.
5. Normalizar servicios API por dominio con separacion `command/query`.
6. Construir taskflows moviles prioritarios: estacion, emision/cobro, movimientos inventario.
7. Construir workbench desktop prioritario: excepciones, conciliacion, analisis y reportes densos.
8. Integrar dashboard operativo dual con KPI moviles y drill-down desktop.
9. Cerrar trazabilidad E2E y observabilidad por modulo.
10. Ejecutar hardening final de paridad cross-device, rendimiento y accesibilidad operativa.

## Cambios importantes en APIs/interfaces/tipos

1. Metadata de comando obligatoria y homogenea en modulos operativos.
2. `trace` obligatorio en respuestas de mutaciones criticas.
3. Error envelope unico cross-device para endpoints de negocio.
4. Prohibido bifurcar endpoints por dispositivo con semantica divergente.
5. Mantener rutas canonicas existentes:
   - `/api/inventory/*`
   - `/api/billing/*`
   - `/api/fuel/*`
   - `/api/payments/*`
   - `/api/reporting/*`
   - `/api/backend/dashboard/*`

## Test plan y escenarios de aceptacion

1. Router/guardias:
   - publico vs privado
   - bootstrap
   - contexto
   - permisos
   - `403`
2. Paridad funcional:
   - misma operacion desktop/movil => mismo estado backend.
3. Idempotencia:
   - reintento con mismo `command_id` no duplica mutacion.
4. Contratos:
   - validacion de `trace` y `error envelope` en rutas criticas.
5. Seguridad:
   - pruebas negativas RBAC/SoD + step-up en alto impacto.
6. UX movil:
   - flujos criticos completables en <= 5 pasos.
7. Reporting/dashboard:
   - mismo filtro/corte => mismas cifras en ambos dispositivos.
8. Observabilidad:
   - correlacion request-log-auditoria verificable por operacion.

## Supuestos y defaults

1. Se mantiene stack actual:
   - Quasar + Vue + Pinia (frontend)
   - Django + DRF (backend)
2. Una sola SPA y una sola logica de negocio backend.
3. Estrategia UX oficial dual-shell (`Workbench` / `Taskflow`).
4. Politica no-breaking por defecto.
5. Canal principal de operacion: internet publica con TLS y controles perimetrales.
