# PROMPTS STACK REAL — ERP/CRM MULTIDISPOSITIVO v1.0

Version: v1.0  
Fecha: 2026-04-14  
Estado: Guia operativa para prompts no-genericos alineados al repo real

## Objetivo

Estandarizar prompts para obtener respuestas alineadas al stack y contratos actuales del proyecto:

- Frontend: Quasar + Vue + Pinia.
- Backend: Django + DRF.
- Ruta operativa: internet-first, UX dual-shell (`Workbench`/`Taskflow`).
- Contratos no-breaking y trazabilidad obligatoria.

## Contexto base obligatorio (copiar en cada prompt)

```text
Contexto tecnico obligatorio:
- Stack frontend: Quasar + Vue + Pinia.
- Stack backend: Django + DRF.
- App unica web por internet.
- UX separada por dispositivo: Workbench (laptop/PC) y Taskflow (movil).
- Logica de negocio unica en backend.
- No proponer breaking changes.
- Usar endpoints canonicos:
  /api/inventory/*, /api/billing/*, /api/fuel/*, /api/payments/*, /api/reporting/*, /api/backend/dashboard/*.
- Contratos transversales:
  - comandos mutables: company_id, branch_id, command_id, source_device, channel, device_class
  - trace de respuesta: request_id, audit_event_id, channel, source_device
  - error envelope: error_code, cause, recommended_action, request_id
```

## Prompts recomendados por fase

### 1) Arquitectura maestra

```text
Actua como arquitecto principal de producto, UX y software para este ERP/CRM real.

[PEGA AQUI "Contexto tecnico obligatorio"]

Disena una propuesta empresarial completa para:
- inventarios
- facturacion
- estacion de servicios
- reportes
- dashboard

Estructura de salida obligatoria:
1. arquitectura funcional
2. criterios para laptop vs movil
3. separacion UX por dispositivo
4. reglas de seguridad y permisos
5. reglas de auditoria
6. propuesta de navegacion
7. riesgos operativos
8. backlog inicial recomendado

No entregues respuesta generica ni responsive comprimido.
```

### 2) Matriz de modulos por dispositivo

```text
Actua como consultor senior de ERP multi-dispositivo.

[PEGA AQUI "Contexto tecnico obligatorio"]

Genera una matriz para inventarios, facturacion, estacion, reportes y dashboard con:
1. objetivo operativo
2. laptop (si/no y alcance)
3. movil (si/no y alcance)
4. prioridad
5. tipo (lectura/captura/confirmacion)
6. complejidad UX por dispositivo
7. riesgos
8. recomendacion final

Incluye:
- funciones solo laptop
- funciones si movil
- funciones prohibidas en movil
- orden de implementacion por valor/riesgo/dependencias
```

### 3) Separacion UX desktop/movil

```text
Actua como experto en UX empresarial y arquitectura frontend.

[PEGA AQUI "Contexto tecnico obligatorio"]

Define reglas implementables para:
1. principios UX desktop
2. principios UX movil
3. navegacion
4. densidad de informacion
5. formularios
6. tablas/filtros/busqueda
7. dashboard/reportes
8. errores y confirmaciones
9. como evitar duplicar logica de negocio
10. anti-patrones

Entregalo orientado a implementacion real en Quasar/Vue.
```

### 4) Norma interna de gobernanza

```text
Actua como arquitecto de reglas de producto y gobernanza funcional.

[PEGA AQUI "Contexto tecnico obligatorio"]

Redacta norma interna vinculante con:
1. principios rectores
2. acceso remoto
3. seguridad y autenticacion
4. permisos por rol
5. separacion UX por dispositivo
6. consistencia de datos
7. operaciones transaccionales
8. auditoria y trazabilidad
9. reportes y dashboards
10. errores/validaciones/mensajes
11. escalabilidad futura

Usa lenguaje normativo DEBE/NO DEBE/PUEDE.
```

### 5) Inventarios

```text
Actua como arquitecto funcional de inventarios.

[PEGA AQUI "Contexto tecnico obligatorio"]

Define:
1. objetivo
2. operaciones
3. laptop
4. movil
5. flujos criticos
6. pantallas
7. validaciones
8. permisos
9. trazabilidad
10. errores frecuentes
11. UX por dispositivo

Clasifica cada operacion como lectura, captura o confirmacion transaccional.
```

### 6) Facturacion

```text
Actua como arquitecto funcional de facturacion empresarial.

[PEGA AQUI "Contexto tecnico obligatorio"]

Define:
1. alcance
2. operaciones criticas
3. laptop
4. movil
5. flujos de emision/consulta/cobro
6. permisos y validaciones
7. riesgos fiscales y operativos
8. UX por dispositivo
9. eventos auditables
10. criterios de aceptacion

Aclara que procesos van solo desktop y cuales si van en movil.
```

### 7) Estacion de servicios

```text
Actua como especialista en estacion de servicios multi-dispositivo.

[PEGA AQUI "Contexto tecnico obligatorio"]

Estructura:
1. procesos
2. tareas por usuario
3. operaciones laptop
4. operaciones movil
5. apertura
6. operacion
7. cierre
8. incidencias
9. auditoria
10. validaciones criticas
11. pantallas/UX

Prioriza reduccion de error humano en campo.
```

### 8) Reporting y dashboard

```text
Actua como arquitecto de reporting/dashboard empresarial.

[PEGA AQUI "Contexto tecnico obligatorio"]

Define:
1. objetivos dashboards
2. objetivos reportes
3. UX desktop vs movil
4. KPIs minimos en movil
5. analitica reservada desktop
6. estructura de filtros
7. reglas tablas/graficos/alertas
8. limites de densidad movil
9. riesgos de sobrecarga
10. criterios de calidad visual/funcional
```

### 9) Contratos funcionales y APIs (sin codigo)

```text
Actua como arquitecto de software y contratos funcionales.

[PEGA AQUI "Contexto tecnico obligatorio"]

Disena sin codigo:
1. modulos funcionales
2. capacidades
3. entidades
4. acciones permitidas
5. permisos
6. reglas de contexto por usuario/dispositivo
7. endpoints conceptuales
8. diferencias lectura/captura/confirmacion
9. eventos auditables
10. reglas para no duplicar logica
```

### 10) Backlog profesional

```text
Actua como director de producto y delivery tecnico.

[PEGA AQUI "Contexto tecnico obligatorio"]

Genera backlog para inventarios, facturacion, estacion, reportes y dashboard:
1. epicas
2. capacidades
3. historias funcionales
4. criterios de aceptacion
5. dependencias
6. riesgos
7. orden recomendado de implementacion

Sin cronograma ni fechas; prioriza valor/riesgo/dependencias.
```

### 11) Norma consolidada final

```text
Convierte todo el planteamiento en una norma interna de diseno y operacion.

[PEGA AQUI "Contexto tecnico obligatorio"]

Debe incluir:
1. objetivo general
2. alcance
3. principios de arquitectura funcional
4. principios UX por dispositivo
5. reglas de seguridad/permisos
6. reglas de operacion por modulo
7. reglas de auditoria
8. reglas de consistencia/validacion
9. restricciones
10. decisiones de producto obligatorias
11. anti-patrones prohibidos
```

### 12) Paso a arquitectura de implementacion

```text
Actua como arquitecto frontend y backend senior.

[PEGA AQUI "Contexto tecnico obligatorio"]

Sin escribir codigo, entrega:
1. estructura de modulos
2. organizacion de carpetas
3. rutas publicas y privadas
4. separacion shell desktop/movil
5. stores/estado
6. capa servicios API
7. sesion/permisos/contexto
8. componentes reutilizables
9. layouts por dispositivo
10. implementacion paso a paso
```

## Orden recomendado de uso

1. Arquitectura maestra.
2. Matriz de modulos por dispositivo.
3. Separacion UX desktop/movil.
4. Norma interna de gobernanza.
5. Prompts por modulo (inventarios, facturacion, estacion, reporting/dashboard).
6. Contratos funcionales y APIs.
7. Backlog profesional.
8. Arquitectura de implementacion.

## Checklist de calidad para evaluar respuestas

1. Respeta stack real (Quasar/Vue/Pinia + Django/DRF).
2. No introduce breaking changes.
3. Mantiene logica de negocio unica backend.
4. Separa UX Workbench/Taskflow sin desktop comprimido.
5. Usa contratos transversales (`metadata`, `trace`, `error envelope`).
6. Define seguridad (RBAC/SoD, step-up, contexto efectivo).
7. Incluye trazabilidad y eventos auditables.
8. Prioriza por valor/riesgo/dependencias.
