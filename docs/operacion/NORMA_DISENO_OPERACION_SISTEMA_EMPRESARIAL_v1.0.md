# NORMA INTERNA DE DISENO Y OPERACION DEL SISTEMA WEB EMPRESARIAL v1.0

Version: v1.0  
Fecha: 2026-04-14  
Estado: Vigente (obligatoria)  
Propietarios: Producto, Arquitectura de Software, Seguridad Aplicativa, Operaciones

## Marco normativo

- `DEBE`: requisito mandatorio.
- `NO DEBE`: prohibicion mandatoria.
- `PUEDE`: opcion permitida sin romper esta norma.

---

## 1) Objetivo general

Establecer reglas unificadas de diseno y operacion para un sistema web empresarial con acceso remoto por internet, usado desde laptop/PC y movil, garantizando:

- logica de negocio unica,
- UX diferenciada por dispositivo,
- seguridad y permisos robustos,
- trazabilidad operativa de punta a punta,
- continuidad operativa sin degradar control ni cumplimiento.

## 2) Alcance

Aplica a todo el sistema:

- frontend web (desktop y movil),
- APIs y servicios de dominio,
- autenticacion/autorizacion/sesion,
- modulos de inventarios, facturacion, estacion de servicios, reportes y dashboard,
- auditoria, observabilidad y contratos funcionales transversales.

Queda fuera de alcance:

- canales legacy no canonicos (salvo compatibilidad controlada),
- cambios breaking de contratos publicos sin proceso formal de versionado.

## 3) Principios de arquitectura funcional

1. El backend DEBE ser la unica fuente de verdad para reglas de negocio.
2. El sistema DEBE mantener contratos API no-breaking por defecto.
3. Comandos y consultas DEBEN separarse conceptualmente (CQRS ligero).
4. Los comandos mutables DEBEN incluir metadata transversal:
   - `company_id`, `branch_id`, `command_id`, `source_device`, `channel`, `device_class`.
5. La idempotencia DEBE aplicarse en toda accion mutable de alto impacto o de alta frecuencia.
6. El sistema NO DEBE bifurcar semantica funcional por tipo de dispositivo.

## 4) Principios de UX por dispositivo

### Laptop/PC (`Workbench`)

- DEBE priorizar analitica, multitarea, tablas densas y control operativo profundo.
- DEBE soportar flujos complejos, conciliacion y manejo de excepciones.

### Movil (`Taskflow`)

- DEBE priorizar flujos cortos (3-5 pasos), captura rapida y confirmacion clara.
- DEBE mostrar solo la informacion necesaria para decidir y ejecutar.

### Regla comun

- Ambos canales DEBEN compartir vocabulario de negocio, estados y consecuencias.
- El movil NO DEBE ser una copia comprimida de escritorio.

## 5) Reglas de seguridad y permisos

1. Toda ruta protegida DEBE exigir autenticacion valida.
2. El acceso remoto DEBE operar con TLS extremo a extremo.
3. RBAC/SoD DEBE validarse en backend por accion y contexto efectivo.
4. Operaciones de alto impacto DEBEN requerir step-up auth.
5. El sistema NO DEBE autorizar por ocultacion de botones en UI.
6. El contexto efectivo (`company_id`, `branch_id`) DEBE ser obligatorio en toda mutacion.

## 6) Reglas de operacion por modulo

### 6.1 Inventarios

- DEBE operar con stock consistente por bodega/item y trazabilidad por movimiento.
- Salidas DEBEN bloquearse con stock insuficiente (salvo excepcion formalmente aprobada).
- Ajustes DEBEN exigir motivo obligatorio y actor responsable.

### 6.2 Facturacion

- Emision y cobro DEBEN quedar correlacionados y auditados.
- Contingencia y anulacion DEBEN controlarse con permisos elevados y step-up.
- Configuracion fiscal sensible NO DEBE ejecutarse en movil.

### 6.3 Estacion de servicios

- No DEBE existir mas de un turno abierto por sucursal.
- Un despacho NO DEBE transformarse en venta mas de una vez.
- Cancelaciones DEBEN manejar compensacion y reintento trazable.

### 6.4 Reportes

- DEBEN usar filtros consistentes y reproducibles por contexto/corte.
- Exportables DEBEN preservar lineage y parametros de ejecucion.
- Reportes NO DEBEN mutar estado de negocio.

### 6.5 Dashboard

- DEBE priorizar alertas accionables y KPI operativos.
- Alertas DEBEN deduplicarse por ventana y tener owner/estado.
- El dashboard movil DEBE enfocarse en lectura rapida y siguiente accion.

## 7) Reglas de auditoria

1. Toda accion critica DEBE registrar actor, contexto, dispositivo y resultado.
2. Toda respuesta critica DEBE incluir `trace`:
   - `trace.request_id`, `trace.audit_event_id`, `trace.channel`, `trace.source_device`.
3. Toda operacion DEBE ser reconstruible end-to-end (API + log + auditoria).
4. Logs NO DEBEN exponer secretos, firmas, codigos sensibles ni credenciales.

## 8) Reglas de consistencia y validacion

1. Toda transaccion DEBE validar precondiciones y transiciones de estado.
2. Reintentos con mismo `command_id` NO DEBEN duplicar efectos.
3. Mismo filtro/corte en reportes DEBE producir mismo resultado en desktop y movil.
4. Operaciones sin contexto valido DEBEN rechazarse de forma explicita.
5. Validaciones criticas NO DEBEN delegarse exclusivamente al frontend.

## 9) Restricciones

1. No se permiten cambios breaking de APIs canonicas sin estrategia de versionado.
2. No se permite divergencia funcional entre desktop y movil.
3. No se permite operacion de alto impacto sin evidencia de auditoria.
4. No se permite habilitar administracion sensible en movil sin control reforzado.
5. No se permite degradar trazabilidad para optimizar velocidad de entrega.

## 10) Decisiones de producto obligatorias

1. Internet-first como canal operativo principal.
2. Logica unica backend y UX dual-shell (`Workbench` y `Taskflow`).
3. Priorizacion de entrega por valor operativo, riesgo y dependencia tecnica.
4. Politica no-breaking por defecto con contratos aditivos.
5. Seguridad por defecto: contexto obligatorio, RBAC/SoD y step-up en alto impacto.
6. Trazabilidad obligatoria en toda capacidad critica antes de escalar funcionalidad.

## 11) Lista de anti-patrones prohibidos

1. Duplicar reglas de negocio entre frontend desktop y movil.
2. Crear APIs distintas por dispositivo con semantica incompatible.
3. Autorizar operaciones por visibilidad de UI en lugar de backend.
4. Permitir comandos mutables sin `command_id` o sin contexto efectivo.
5. Diseñar movil como desktop reducido sin flujo task-oriented.
6. Mezclar consultas analiticas pesadas con comandos transaccionales.
7. Omitir `trace` en endpoints criticos.
8. Silenciar errores operativos sin `error_code` y accion recomendada.
9. Escalar features sin pruebas de paridad cross-device.
10. Dejar excepciones operativas sin responsable, evidencia ni criterio de cierre.

---

## Criterio de cumplimiento

Esta norma se considera cumplida cuando:

1. Los modulos operan bajo reglas comunes de seguridad, contexto y trazabilidad.
2. Desktop y movil conservan semantica funcional unica con UX diferenciada.
3. Los artefactos de QA demuestran idempotencia, paridad y auditoria E2E.
