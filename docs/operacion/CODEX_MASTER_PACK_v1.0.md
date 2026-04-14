# CODEX Master Pack v1.0

Version: v1.0  
Fecha: 2026-04-14  
Estado: Politica operativa canonica (vigente)

## Objetivo

Consolidar en un unico documento la ejecucion por slices y la gobernanza estricta para delegacion a Codex en `ERP_CRM`, alineado al objetivo del producto:

- App web remota (internet-first), accesible desde laptop/PC y movil.
- Una sola logica de negocio backend.
- UX separada por dispositivo: `Workbench` (desktop) y `Taskflow` (movil).
- Preservar flujo publico de enroll y contratos existentes.

## Alcance

Aplica a toda delegacion de trabajo en Codex para:

- arquitectura funcional y tecnica,
- definicion y ejecucion incremental por slices,
- cambios de frontend/backend/reporting con validacion de contratos,
- coordinacion de calidad con guards QA.

No reemplaza normas especializadas existentes, pero define la ruta operativa canonica para ejecutar trabajo en este repo.

## Source Of Truth Operativo

- Documento canonico de delegacion: `docs/operacion/CODEX_MASTER_PACK_v1.0.md`.
- Documentos de soporte:
  - `docs/operacion/PROMPTS_STACK_REAL.md`
  - `docs/operacion/CODEX_GOVERNANCE_HANDOFF_v1.0.md`

Regla: ante conflicto operativo en delegacion a Codex, prevalece este Master Pack.

## Context Card

### Objetivo del producto

- Aplicacion web empresarial remota para laptop y movil.
- Logica unica de negocio para ambos dispositivos.
- Experiencia separada por dispositivo:
  - `Workbench` (desktop): operacion densa, tablas, multitarea y analitica.
  - `Taskflow` (movil): tareas cortas, captura, confirmacion y consulta agil.

### Hechos observados del repo

- Existe flujo publico de enrolamiento de dispositivo.
- Existe base de auth/cookies/proxy para operacion web remota.
- Backend por dominios esta mas avanzado que algunas superficies frontend.
- La brecha principal esta en:
  1. separar carril publico vs privado,
  2. formalizar bootstrap post-login/post-enroll,
  3. consolidar dual-shell desktop/movil,
  4. exponer modulos frontend en orden de prioridad.

### Orden operativo oficial

1. Blindar flujo publico de enroll.
2. Crear bootstrap unificado post-login/post-enroll.
3. Separar shell desktop/mobile.
4. Exponer modulos por prioridad: inventarios, facturacion, estacion, dashboard/reportes.

## Reglas No Negociables

1. No editar sin inspeccion previa de arbol, contratos, tests y guards.
2. No crear carriles alternos a la API canonica de reporting:
   - `/api/reporting/catalog/`
   - `/api/reporting/datasets/{dataset_key}/run/`
   - `/api/reporting/runs/*`
   - `/api/reporting/exports/*`
   - `/api/reporting/snapshots/*`
   - `/api/reporting/saved-views/*`
3. No romper contrato de analytics:
   - prefix publico `/analytics`
   - puerto interno Dash `8050`
   - same-origin en produccion
4. Mantener flujo publico de enroll aislado del carril privado de sesion.
5. Prohibido "responsive comprimido" como sustituto de UX movil.
6. `apps.kernels.reporting` es proyeccion/consulta; no ownership transaccional.
7. No backend paralelo ni semantica divergente por dispositivo.
8. Ownership por dominio obligatorio; no mezclar bounded contexts sin declarar blast radius.
9. No agregar dependencias sin justificacion tecnica explicita.
10. Si una decision depende de supuesto no verificable, detener y explicitar.

## Clasificacion De Cambio Y Modo

### Tipo base para integracion multidispositivo

- Clasificacion inicial: `cross_domain`.

### Reglas de reclasificacion

- Si toca modelos/migraciones/cierre de ciclo: `migrations_or_close_cycle`.
- Si toca findings Bandit, secrets o supply chain: `security_or_supply_chain`.

### Modo de ejecucion

- Inicio obligatorio: `Suggest`.
- Paso permitido a `Auto Edit`: solo con diagnostico completo y slice acotado.
- `Full Auto`: prohibido para esta integracion.

## Protocolo De Handoff A-F

Toda entrega de slice DEBE reportar:

A) Diagnostico del area  
B) Alcance exacto del slice  
C) Contratos/guards impactados  
D) Implementacion realizada  
E) Pruebas/validacion  
F) Riesgos remanentes y siguiente paso

## Criterio De Paso Suggest -> Auto Edit

Se autoriza avance a `Auto Edit` solo si:

1. A-C estan completos y verificables.
2. El blast radius esta acotado al slice.
3. No hay contradiccion con contratos congelados.
4. Existe plan de validacion con guards minimos del tipo de cambio.
5. No hay supuestos criticos sin validar.

## Secuencia Oficial De Ejecucion (4 Bloques)

### Bloque 1 - Blindaje flujo publico de enroll

#### Goal

Aislar totalmente `/device/enroll` y endpoints publicos de enroll/sync respecto a la logica global de auth/refresh.

#### Non-goals

- No reescribir todo el sistema de auth.
- No redisenar UX completa.
- No alterar contratos backend sin necesidad minima.

#### AC

1. Ruta publica de enroll no dispara refresh forzado ni redirect a login por 401 irrelevantes.
2. Errores de `/sync/enroll` y `/sync/batch` se tratan como flujo publico.
3. Login normal de rutas privadas no se rompe.
4. Endpoints publicos quedan centralmente identificados y documentados.

#### Test plan

- Unit tests del interceptor/guard de exclusion de endpoints publicos.
- Integration tests de `/device/enroll?code=...` sin sesion.
- Verificacion manual: enroll valido, invalido, expirado y ya usado.

#### Risk notes

- Riesgo de abrir rutas privadas por relajar guards.
- Riesgo de limpiar sesion privada de forma agresiva en errores publicos.
- Riesgo de reintentos excesivos y ruido de red.

#### Ask prompt

```text
Context:
Estamos endureciendo el flujo publico de enrolamiento de dispositivos en una SPA Quasar/Vue. Ya existe una ruta publica de enroll y un interceptor global de auth. Necesito identificar exactamente donde el flujo publico sigue contaminado por la logica global de sesion.

Question(s):
- Que archivos controlan actualmente router guards, boot de auth y manejo global de 401?
- Que endpoints publicos de enroll/sync deben quedar exentos de refresh y redireccion a login?
- Hay logica duplicada de sesion en stores, boot files o interceptores?
- Que puntos del flujo actual podrian seguir forzando me/refresh aunque la ruta sea publica?
```

#### Code prompt

```text
Context:
El sistema tiene una ruta publica de enrolamiento de dispositivo. El objetivo es aislarla totalmente del flujo global de autenticacion. No queremos que una visita a la pantalla publica de enroll dispare refresh o redirecciones a login por el interceptor global.

Task:
Implementa una separacion explicita entre carril publico y carril privado en frontend:
- identifica endpoints publicos de enroll/sync
- evita refresh y redirect-to-login sobre esos endpoints
- conserva el flujo normal de auth para rutas privadas
- centraliza esta regla para que no quede dispersa

Constraints:
- no reescribir todo el sistema de auth
- no cambiar contratos backend salvo necesidad minima
- mantener el comportamiento actual de login en rutas privadas
- documentar la decision en comentarios tecnicos breves donde sea critico

Acceptance criteria:
- abrir la ruta publica de enroll sin sesion no produce contaminacion del flujo privado
- errores de enroll se muestran como errores publicos
- rutas privadas siguen protegidas
- no hay reintentos globales innecesarios en endpoints publicos

Test plan:
- agrega pruebas unitarias/integracion donde aplique
- manualmente verificar enroll valido, invalido, expirado y ya usado
```

### Bloque 2 - Bootstrap unificado post-login/post-enroll

#### Goal

Definir y conectar un bootstrap unico para resolver contexto operativo, capacidades y shell posterior a login o enroll exitoso.

#### Non-goals

- No implementar todos los modulos en este bloque.
- No construir la UI final completa.

#### AC

1. Existe contrato unico de bootstrap con contexto operativo suficiente.
2. Frontend usa bootstrap como fuente unica para modulos visibles y shell.
3. Bootstrap soporta sesion normal y dispositivo enrolado.
4. No hay multiples fuentes contradictorias de contexto.

#### Test plan

- Unit tests de mapeo/serializacion bootstrap.
- Integration tests login -> bootstrap y enroll -> bootstrap.
- Verificacion manual por cambios de rol/contexto.

#### Risk notes

- Riesgo de sobreexponer capacidades.
- Riesgo de drift entre permisos y modulos visibles.
- Riesgo de bootstrap sobredimensionado y lento.

#### Ask prompt

```text
Context:
Necesitamos un bootstrap unificado para una app web multi-dispositivo. Queremos que despues de login o despues de enroll, el frontend resuelva desde un solo contrato el contexto, capacidades y shell a usar.

Question(s):
- Que stores o servicios actualmente resuelven usuario, contexto, permisos y menus?
- Ya existe algun endpoint o composicion parcial que pueda servir como base para un bootstrap unico?
- Donde se decide hoy que modulos o rutas mostrar?
- Que datos minimos faltan para decidir correctamente entre shell mobile y desktop?
```

#### Code prompt

```text
Context:
La aplicacion necesita un bootstrap unificado post-login/post-enroll para decidir contexto operativo, capacidades visibles y experiencia por dispositivo.

Task:
Disena e implementa un flujo de bootstrap unico que:
- reciba o resuelva identidad de usuario/dispositivo
- entregue contexto operativo (org, branch o equivalente)
- entregue capabilities o permisos efectivos
- entregue modulos visibles
- permita al frontend decidir shell mobile o desktop
- reduzca duplicacion de logica en stores/rutas

Constraints:
- no dupliques reglas de negocio en frontend
- manten el contrato compacto y extensible
- no rompas el flujo existente de login
- documenta el shape del bootstrap de forma clara

Acceptance criteria:
- existe un punto unico de bootstrap
- frontend usa el bootstrap como fuente de verdad para navegacion/modulos
- no hay multiples resoluciones paralelas contradictorias
- soporta usuario autenticado y dispositivo enrolado segun aplique

Test plan:
- pruebas unitarias e integracion para bootstrap
- verificaciones manuales de roles/contextos diferentes
```

### Bloque 3 - Dual shell desktop/mobile

#### Goal

Separar experiencia de navegacion/layout en `Workbench` y `Taskflow`, compartiendo auth, servicios y reglas de negocio.

#### Non-goals

- No resolver solo con CSS responsive.
- No duplicar app completa ni contratos.

#### AC

1. Existen shell desktop y shell mobile separados y utilizables.
2. Comparten auth, ACL, servicios API y contratos de negocio.
3. Movil prioriza taskflows cortos; desktop prioriza densidad y multitarea.
4. Seleccion de shell centralizada.

#### Test plan

- Unit tests de seleccion de shell.
- Integration tests de navegacion por dispositivo.
- Verificacion manual en rutas clave laptop/movil.

#### Risk notes

- Riesgo de divergencia de permisos entre shells.
- Riesgo de rutas con acciones sin capability.
- Riesgo de duplicacion innecesaria de bundles.

#### Ask prompt

```text
Context:
Queremos pasar de una sola app web a una arquitectura con desktop shell y mobile shell, compartiendo logica, auth y servicios.

Question(s):
- Que layouts existen hoy y como se conectan al router?
- Donde conviene introducir la decision central de shell?
- Que componentes/paginas son buenos candidatos para reutilizacion y cuales deben ser especificos por dispositivo?
- Que rutas actuales pertenecen naturalmente al shell desktop, al shell mobile o a ambos?
```

#### Code prompt

```text
Context:
La app necesita dos experiencias: desktop shell y mobile shell. Deben compartir servicios, auth, permisos y dominio, pero diferir en layout y navegacion.

Task:
Implementa una separacion explicita de shells:
- crea estructura de layouts/shells para desktop y mobile
- define estrategia central para resolver que shell usar
- conserva reglas de permisos y auth compartidas
- evita duplicar logica de negocio
- deja listo el camino para modulos con UX diferenciada

Constraints:
- no resolver esto solo con CSS responsive
- no duplicar stores ni servicios
- mantener compatibilidad con rutas existentes o migrarlas con criterio claro
- dejar la arquitectura extensible para inventario, facturacion y estacion

Acceptance criteria:
- existen dos shells utilizables
- la seleccion del shell es coherente y centralizada
- las reglas de negocio y permisos no se duplican
- navegacion y layout difieren segun objetivo de dispositivo

Test plan:
- pruebas basicas de routing/guards
- validacion manual en laptop y movil
```

### Bloque 4 - Exposicion gradual de modulos

#### Goal

Aterrizar frontend por prioridad de negocio con semantica `read/capture/commit` y capability gating consistente.

#### Non-goals

- No liberar todos los modulos de una vez.
- No transformar dashboard/reportes en backoffice comprimido movil.

#### AC

1. Cada modulo declara rutas, capabilities y tipo de interaccion.
2. Orden de aterrizaje: inventarios -> facturacion -> estacion -> dashboard/reportes.
3. Estacion/fuel mantiene identidad vertical sin mezcla arbitraria.
4. Dashboard/reportes movil permanece lectura resumida accionable.

#### Test plan

- Unit tests capability -> menu/ruta.
- Integration tests acceso autorizado/denegado por modulo.
- Verificacion manual por rol/dispositivo.

#### Risk notes

- Riesgo de modulos visibles sin capability.
- Riesgo de acciones `commit` sin controles suficientes.
- Riesgo de sobrecarga de dashboard en movil.

#### Ask prompt

```text
Context:
Queremos alinear el frontend con los dominios existentes y priorizar modulos utiles para laptop y movil.

Question(s):
- Que modulos ya tienen frontend real hoy y cuales solo existen en backend?
- Que rutas, paginas y menus actuales corresponden a inventarios, facturacion, fuel, dashboard y reportes?
- Que capabilities o permisos ya existen y cuales faltan?
- Que partes del dashboard/reporting actual son demasiado densas para movil?
```

#### Code prompt

```text
Context:
Necesitamos exponer modulos frontend en un orden de valor y con reglas claras por dispositivo, compartiendo logica de negocio.

Task:
Organiza e implementa la exposicion progresiva de modulos:
1. inventarios
2. facturacion
3. estacion de servicios
4. dashboard/reportes

Para cada modulo:
- define rutas
- define capability gating
- clasifica acciones en read/capture/commit
- adapta UX a desktop y mobile shell
- evita mezclar verticales de forma arbitraria

Constraints:
- no construir un backoffice responsive gigante
- no duplicar reglas de negocio
- fuel debe mantener su identidad de vertical
- dashboard/reportes en movil deben ser de lectura resumida

Acceptance criteria:
- los modulos quedan priorizados y estructurados
- capability gating consistente
- mobile y desktop tienen UX coherente
- inventarios y facturacion quedan listos antes de ampliar reportes

Test plan:
- pruebas por modulo y permisos
- verificacion manual por dispositivo y rol
```

## Matriz Minima De Gates Por Tipo De Cambio

| Tipo de cambio | Gates minimos obligatorios | Gates condicionales |
|---|---|---|
| `docs_only` | `make qa-codex-governance-guard`, `make qa-readme-section-guard`, `make qa-pr-blast-radius-guard` | N/A |
| `single_domain_code` | `make qa-codex-governance-guard`, `make qa-architecture-dependency-guard`, `make qa-route-contract-guard` | si toca python: `make qa-backend-bandit`, `make qa-backend-ruff`, `make qa-backend-mypy` |
| `cross_domain` | `make qa-codex-governance-guard`, `make qa-architecture-dependency-guard`, `make qa-route-contract-guard`, `make qa-pr-blast-radius-guard` | si toca reporting/analytics: `make qa-analytics-contract-guard`, `make qa-reporting-registry-guard`, `make qa-reporting-contract-version-guard` |
| `migrations_or_close_cycle` | `make qa-codex-governance-guard`, `make qa-architecture-dependency-guard`, `make qa-makemigrations-check`, `make qa-migration-safety-guard` | si toca python: `make qa-backend-bandit`, `make qa-backend-ruff`, `make qa-backend-mypy` |
| `security_or_supply_chain` | `make qa-codex-governance-guard`, `make qa-validate-security-exceptions`, `make qa-security-findings-enforce` | si toca rutas/arquitectura: `make qa-route-contract-guard`, `make qa-architecture-dependency-guard` |

### Gates adicionales para rendimiento de reporting (cuando aplique)

- `make qa-reporting-r8-gate`
- `make qa-verify-reporting-r8-gate-artifact`

## Plantilla Canonica De Sesion (copiar/pegar)

```text
INSTRUCCIONES PARA CODEX - ERP_CRM

ROL
Actua como Software Engineer ejecutor bajo direccion de arquitectura.

OBJETIVO
[resultado esperado del slice]

TIPO DE CAMBIO
[docs_only | single_domain_code | cross_domain | migrations_or_close_cycle | security_or_supply_chain]

MODO
[Suggest | Auto Edit]

ALCANCE
INCLUIR:
- [items]
EXCLUIR:
- [items]

REGLAS
1) inspeccion previa obligatoria
2) no romper contratos canonicos
3) no mezclar bounded contexts sin declarar blast radius
4) reporting sigue siendo proyeccion/consulta
5) mantener carril publico enroll aislado

SALIDA OBLIGATORIA
A) Diagnostico del area
B) Alcance exacto
C) Contratos impactados
D) Implementacion realizada
E) Pruebas / validacion
F) Riesgos remanentes y siguiente paso

VALIDACION MINIMA
- [lista de make targets por tipo de cambio]
```

## Criterio De Cierre Del Slice

Un slice se considera cerrado cuando:

1. Handoff A-F completo.
2. Gates obligatorios del tipo de cambio en verde.
3. Sin ruptura de contratos canonicos.
4. Siguiente paso propuesto con blast radius acotado.

## Referencias

- `docs/operacion/CODEX_GOVERNANCE_HANDOFF_v1.0.md`
- `docs/operacion/PROMPTS_STACK_REAL.md`
- `docs/operacion/REPORTING_R8_GOBIERNO_OBSERVABILIDAD_v1.0.md`
- `frontend/src/ARCHITECTURE_SPA_MODULAR.md`
