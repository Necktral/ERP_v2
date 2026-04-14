# REPORTING Y DASHBOARDS MULTIDISPOSITIVO (INTERNET-FIRST) v1.0

Version: v1.0  
Fecha: 2026-04-14  
Estado: Diseno operativo ejecutable (no-breaking)

## Resumen

Este documento define como deben verse y operarse los dashboards y reportes del sistema en laptop/PC y movil bajo una sola logica de datos y negocio.

Principios base de esta version:

- movil orientado a lectura rapida, priorizacion y accion inmediata,
- laptop/PC orientado a analisis profundo, comparativo y control operativo,
- semantica unica en backend, UX separada por dispositivo,
- contratos API preservados con cambios aditivos de metadata/trazabilidad.

## 1) Objetivos de los dashboards

1. Mostrar el estado operativo actual en segundos.
2. Priorizar que atender ahora: alertas, desvio, pendientes criticos.
3. Reducir tiempo de reaccion operacional.
4. Servir como entrada a acciones y drill-down controlado.
5. NO reemplazar reporteria de analisis forense.

## 2) Objetivos de los reportes

1. Entregar analisis confiable, auditable y reproducible por filtro/corte.
2. Permitir comparacion entre sucursales, periodos, categorias y responsables.
3. Soportar revision tactica y gerencial con detalle transaccional trazable.
4. Proveer evidencia formal para auditoria, cumplimiento y cierre operativo.

## 3) Diferencias UX entre laptop y movil

### Laptop/PC (`Workbench`)

- vista multipanel y multitarea,
- tablas densas, filtros compuestos y comparacion lateral,
- export y composicion de vistas guardadas,
- drill-down profundo hasta documento/evento.

### Movil (`Taskflow`)

- foco por tarea y lectura accionable,
- navegacion corta con CTA claros,
- confirmaciones explicitas en acciones criticas,
- resumen operativo + siguiente accion recomendada.

Regla obligatoria: movil NO es desktop comprimido; ambos comparten vocabulario, estados y reglas.

## 4) KPI que deben verse en movil

1. Ventas del dia vs meta (% cumplimiento).
2. Cobros del dia y mora critica.
3. Quiebres de stock criticos.
4. Incidencias operativas abiertas.
5. Tickets/ordenes en riesgo SLA.
6. Desvio operativo principal del turno (ej. despacho vs venta).
7. Estado de caja/turno (`OPEN`, `PENDING_CLOSE`, alertas).
8. Alertas de severidad alta no resueltas.

## 5) Analisis que debe reservarse para laptop

1. Comparativos multi-periodo y multi-sucursal.
2. Reportes tabulares extensos con export y pivoteo.
3. Analisis causa-raiz con trazabilidad hasta documento/evento.
4. Construccion/edicion de vistas guardadas y filtros avanzados.
5. Conciliacion operativa, financiera y de auditoria.

## 6) Estructura recomendada de filtros

### Bloques de filtros

1. Contexto obligatorio: `company`, `branch`, `timezone`, `currency`.
2. Temporal: presets (`hoy`, `7d`, `mes`) + rango absoluto.
3. Dimensional: canal, categoria, responsable, estado.
4. Comparativo: `vs_periodo_anterior`, `vs_meta`.

### Reglas de uso por dispositivo

- movil expone filtros rapidos y vistas guardadas,
- laptop habilita composicion completa y guardado de configuraciones complejas,
- mismo filtro/corte DEBE devolver mismas cifras en ambos dispositivos.

## 7) Reglas para tablas, graficos y alertas

### Tablas

- desktop: paginacion real, columnas configurables, orden multi-columna, export.
- movil: resumen de filas clave, columnas minimas, detalle por expansion.

### Graficos

- una pregunta de negocio por visual,
- prohibido mezclar metricas incompatibles en un mismo grafico,
- unidad y periodo visibles siempre.

### Alertas

- severidad normalizada (`HIGH`, `MEDIUM`, `LOW`),
- deduplicacion por ventana temporal y firma de evento,
- owner y estado operativo obligatorios,
- toda alerta critica debe enlazar a accion o reporte de diagnostico.

## 8) Limites de densidad de informacion en movil

1. Maximo 4-6 KPI cards en la vista inicial.
2. Maximo 1 visual principal por bloque de scroll.
3. Maximo 3 filtros visibles simultaneamente.
4. Maximo 2 acciones primarias por pantalla.
5. Texto orientado a decision inmediata, no narrativa analitica extensa.

## 9) Riesgos de sobrecargar la interfaz

1. Fatiga cognitiva por exceso de KPI/alertas sin priorizacion.
2. Decisiones erradas por mezcla de contexto/filtros no visibles.
3. Baja adopcion movil por flujo largo o ambiguo.
4. Saturacion visual que oculta eventos criticos.
5. Ruido de alertas sin deduplicacion y sin owner.

Mitigacion obligatoria:

- jerarquia visual clara,
- limites de densidad estrictos,
- umbrales de alerta definidos y auditables,
- diseno por tarea, no por acumulacion de widgets.

## 10) Criterios de calidad visual y funcional

1. Legibilidad: contraste AA, tipografia clara, estados visibles.
2. Rendimiento: dashboard inicial usable en < 3 segundos percibidos.
3. Consistencia: mismo KPI, misma definicion en ambos dispositivos.
4. Trazabilidad: cada dato critico enlazable a su fuente/evento.
5. Recuperacion: errores con accion sugerida, sin callejones sin salida.
6. Accesibilidad operativa:
   - tactil fiable en movil,
   - navegacion por teclado en desktop.

## Aclaracion operativa obligatoria: movil vs laptop

### Lectura rapida en movil

1. Estado actual del negocio.
2. Alertas priorizadas.
3. KPI de turno/dia.
4. Confirmacion de acciones cortas.
5. Consulta puntual con drill-down breve.

### Analisis profundo en laptop

1. Comparativos complejos y multidimensionales.
2. Validacion de consistencia y auditoria.
3. Reporteria extensa, exportables y conciliaciones.
4. Investigacion de desvio con detalle transaccional.

## Cambios de interfaces/tipos (aditivos, no-breaking)

### Bloque `trace` estandar en respuestas

- `trace.request_id`
- `trace.audit_event_id`
- `trace.channel`
- `trace.source_device`

### Metadata estandar de consulta

- `device_class`
- `context_scope`
- `time_preset`
- `filter_hash`

### `render_hints` por dispositivo

- `desktop_variant`
- `mobile_variant`
- `priority`
- `max_items_mobile`

### Catalogo de alertas (contrato minimo)

- `alert_code`
- `severity`
- `owner`
- `recommended_action`
- `expires_at`

## Plan de validacion

1. Paridad de datos: mismo filtro/corte, mismas cifras desktop vs movil.
2. Usabilidad movil: tareas de lectura/decision en <= 30 segundos.
3. Analisis desktop: reporte comparativo sin restricciones funcionales.
4. Alertas: deduplicacion y enrutamiento correcto por severidad.
5. Rendimiento: carga inicial y cambio de filtros dentro de SLO.
6. Trazabilidad: correlacion `request_id` y evento auditado en indicadores criticos.

## Supuestos y defaults

1. Acceso remoto por internet con auth/ACL gobernado por backend.
2. Logica de negocio y definiciones KPI unicas en capa reporting/domain.
3. Estrategia UX oficial dual-shell (`Workbench`/`Taskflow`).
4. Movil prioriza lectura rapida y accion corta; laptop prioriza analisis profundo.
5. Cambios de contrato son aditivos; no se rompen rutas existentes.

## Mapeo API actual (referencial)

- `GET /api/reporting/catalog/`
- `GET /api/reporting/catalog/{dataset_key}/`
- `POST /api/reporting/datasets/{dataset_key}/run/`
- `GET /api/reporting/runs/`
- `GET /api/reporting/runs/{run_id}/`
- `POST /api/reporting/runs/{run_id}/export/`
- `GET /api/reporting/exports/{export_id}/`
- `GET /api/reporting/snapshots/`
- `POST /api/reporting/snapshots/generate/`
- `GET /api/backend/dashboard/workspaces/`
- `POST /api/backend/dashboard/embed-token/`
- `POST /api/backend/dashboard/embed-token/redeem/`
