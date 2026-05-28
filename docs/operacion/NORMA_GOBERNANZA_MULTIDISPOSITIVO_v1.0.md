# NORMA INTERNA MULTIDISPOSITIVO — PRODUCTO, UX Y GOBERNANZA FUNCIONAL v1.0

Version: v1.0  
Fecha: 2026-04-14  
Estado: Politica operativa vinculante (vigente)  
Propietarios: Arquitectura de Producto, Arquitectura de Software, Seguridad Aplicativa, Operaciones

## Nota operativa de alcance movil (2026-05)

> **El canal movil NO es un mapeo 1:1 del sistema desktop.**
>
> La estrategia movil es selectiva: cada funcionalidad se evalua por viabilidad individual antes de implementarse.
>
> Funcionalidades moviles confirmadas:
> - Facturacion (emision rapida y consulta)
> - Registro de inventario (recepciones/salidas simples)
> - Reportes (consulta basica)
> - Control de asistencias
> - Bitacoras de mantenimiento de transporte
>
> Todo lo demas descrito en este documento como `Taskflow` movil es vision de producto a futuro, no compromiso de implementacion inmediata. Las nuevas funcionalidades moviles se incorporan caso a caso tras analisis de viabilidad.

---

## Marco normativo

### Vocabulario obligatorio

- `DEBE`: requisito mandatorio.
- `NO DEBE`: prohibicion mandatoria.
- `PUEDE`: opcion permitida sin romper esta norma.

### Alcance

Aplica a todo el sistema web empresarial en canal internet para clientes laptop/PC y movil, incluyendo:

- frontend,
- APIs,
- servicios de dominio,
- autenticacion/autorizacion,
- auditoria/observabilidad,
- reportes y dashboards.

### Roles responsables

- Arquitectura de Producto: ownership de reglas de experiencia y priorizacion funcional.
- Arquitectura de Software: ownership de contratos, consistencia tecnica y no-breaking.
- Seguridad Aplicativa: ownership de controles de autenticacion, autorizacion y sesion.
- QA/Gobernanza: ownership de verificacion de cumplimiento y evidencia.
- Operaciones: ownership de monitoreo y respuesta operacional.

---

## 1) Principios rectores del producto

### Premisa

El producto opera en internet publica, con logica de negocio unica y experiencias diferenciadas por dispositivo.

### Reglas obligatorias

- El sistema DEBE ser internet-first para desktop y movil.
- La logica de negocio DEBE residir en backend como source of truth unica.
- El producto NO DEBE divergir semantica funcional entre dispositivos.
- La evolucion funcional DEBE ser no-breaking por defecto.

### Controles de cumplimiento

- Revision de arquitectura por cambio funcional.
- Verificacion de contratos API y compatibilidad.
- Auditoria de paridad funcional cross-device en escenarios criticos.

### Evidencia requerida

- ADR o nota de diseno por cambio relevante.
- Reporte de compatibilidad de contratos.
- Evidencia QA de paridad desktop/movil.

---

## 2) Reglas de acceso remoto

### Premisa

El acceso remoto por internet es la condicion normal de operacion, no un caso especial.

### Reglas obligatorias

- Todo trafico DEBE usar TLS extremo a extremo.
- El perimetro DEBE aplicar WAF y rate-limit en endpoints sensibles.
- El sistema DEBE controlar origenes permitidos por entorno.
- La operacion NO DEBE ejecutarse sin contexto efectivo (`company_id`, `branch_id`) cuando aplique.

### Controles de cumplimiento

- Validacion periodica de configuracion TLS/WAF.
- Revision de listas de origenes permitidos.
- Pruebas de bloqueo sin contexto en endpoints operativos.

### Evidencia requerida

- Snapshot de configuracion de seguridad por entorno.
- Reporte de pruebas de acceso y rate-limit.
- Logs de rechazo por contexto invalido.

---

## 3) Reglas de seguridad y autenticacion

### Premisa

Seguridad aplicativa y control de sesion son obligatorios para continuidad operativa segura.

### Reglas obligatorias

- Toda ruta protegida DEBE requerir autenticacion valida.
- La sesion DEBE ser segura (rotacion, expiracion, revocacion remota por usuario/dispositivo).
- Operaciones de alto impacto DEBEN exigir step-up auth.
- El sistema NO DEBE permitir elevacion de privilegio por cabeceras manipulables.

### Controles de cumplimiento

- Pruebas de autenticacion, refresh y revocacion.
- Pruebas de step-up para rutas criticas.
- Pruebas de denegacion con contexto o permisos alterados.

### Evidencia requerida

- Reporte de pruebas de auth y sesion.
- Matriz de rutas criticas con step-up activo.
- Logs de intentos denegados y respuesta esperada.

---

## 4) Reglas de permisos por rol

### Premisa

Los permisos se gobiernan por RBAC/SoD en backend, no por ocultacion visual en frontend.

### Reglas obligatorias

- Toda accion DEBE validar permiso en backend.
- Los permisos DEBEN evaluarse por accion y contexto efectivo.
- El sistema DEBE aplicar segregacion de funciones (SoD) en operaciones sensibles.
- La UI NO DEBE ser el unico mecanismo de control de autorizacion.

### Controles de cumplimiento

- Pruebas positivas/negativas por permiso y por contexto.
- Verificacion de SoD en acciones de alto impacto.
- Auditoria de rutas con permisos faltantes.

### Evidencia requerida

- Inventario de permisos por accion.
- Reporte de pruebas RBAC/SoD.
- Registro de decisiones de excepcion (si existieran).

---

## 5) Reglas de separacion UX por dispositivo

### Premisa

La separacion UX es funcionalmente consciente: `Workbench` para desktop y `Taskflow` para movil.

### Reglas obligatorias

- Desktop DEBE priorizar analitica, multitarea y control profundo.
- Movil DEBE priorizar flujos de 3-5 pasos y ejecucion rapida.
- Ambos canales DEBEN compartir estados de negocio y consecuencias.
- El movil NO DEBE implementarse como desktop comprimido.

### Controles de cumplimiento

- Revision UX por flujo critico en ambos canales.
- Medicion de pasos por tarea y tiempo de finalizacion.
- Verificacion de consistencia semantica entre shells.

### Evidencia requerida

- Mapa de flujos Workbench vs Taskflow.
- Grabaciones o capturas de recorridos de prueba.
- Indicadores de tiempo/pasos por tarea.

---

## 6) Reglas de consistencia de datos

### Premisa

Consistencia de datos y determinismo operativo son esenciales para confianza empresarial.

### Reglas obligatorias

- Comandos mutables DEBEN ser idempotentes por `command_id`.
- El sistema DEBE mantener invariantes transaccionales del dominio.
- Frontend NO DEBE duplicar reglas criticas de negocio.
- Las operaciones DEBEN registrar contexto completo (`company_id`, `branch_id`, `source_device`, `channel`).

### Controles de cumplimiento

- Pruebas de idempotencia por reintento y duplicidad.
- Pruebas de invariantes por estado/transicion.
- Revision de duplicacion de reglas en frontend.

### Evidencia requerida

- Suite de pruebas de idempotencia.
- Reporte de invariantes criticos.
- Evidencia de metadata contextual en comandos.

---

## 7) Reglas para operaciones transaccionales

### Premisa

Toda transaccion debe ser segura, trazable, reversible cuando aplique y consistente entre dispositivos.

### Reglas obligatorias

- Toda mutacion DEBE validar estado/transicion antes de persistir.
- Toda mutacion DEBE incluir `command_id` y metadata de canal/dispositivo.
- Cada flujo critico DEBE tener estrategia de rollback funcional definida.
- El sistema NO DEBE confirmar operaciones irreversibles sin confirmacion reforzada.

### Controles de cumplimiento

- Pruebas de transicion valida/invalida.
- Pruebas de rollback en escenarios de error.
- Pruebas de confirmacion reforzada en operaciones criticas.

### Evidencia requerida

- Matriz de transiciones permitidas por dominio.
- Runbook de rollback funcional por flujo critico.
- Reporte QA de transacciones por canal.

---

## 8) Reglas para auditoria y trazabilidad

### Premisa

Toda operacion critica debe poder reconstruirse end-to-end.

### Reglas obligatorias

- Toda respuesta operativa DEBE incluir bloque `trace`.
- Bloque `trace` DEBE contener al menos: `request_id`, `audit_event_id`, `channel`, `source_device`.
- Toda accion critica DEBE asociar actor, contexto y dispositivo.
- Logs NO DEBEN exponer secretos, firmas o credenciales.

### Controles de cumplimiento

- Pruebas de correlacion request/log/auditoria.
- Validacion de presencia de `trace` en rutas criticas.
- Reglas de saneamiento de logs y auditoria de secretos.

### Evidencia requerida

- Muestras de trazabilidad correlacionada.
- Reporte de cobertura de `trace` por endpoint critico.
- Resultado de escaneo de secretos en logs.

---

## 9) Reglas de reportes y dashboards

### Premisa

Reportes y dashboards son capa de consulta gobernada, separada de comandos transaccionales.

### Reglas obligatorias

- El sistema DEBE separar comando/consulta (CQRS ligero).
- Misma consulta con mismo filtro/corte DEBE retornar mismas cifras en ambos dispositivos.
- Lectura DEBE controlarse por permiso de dataset y contexto.
- Dashboards moviles DEBEN ser accionables y de baja densidad; desktop DEBE permitir analisis profundo.

### Controles de cumplimiento

- Pruebas de consistencia de cifras cross-device.
- Pruebas de permisos de lectura por dataset.
- Verificacion de separacion entre rutas transaccionales y analiticas.

### Evidencia requerida

- Reporte de consistencia por dataset.
- Matriz de permisos por dashboard/reporte.
- Evidencia de pruebas de accesos denegados.

---

## 10) Reglas para errores, validaciones y mensajes al usuario

### Premisa

Errores y validaciones deben permitir recuperacion operativa, no solo diagnostico tecnico.

### Reglas obligatorias

- El sistema DEBE usar envelope unico de errores cross-device.
- El catalogo de errores DEBE incluir codigo, causa y accion sugerida.
- Mensajes en movil DEBEN ser breves y accionables; desktop DEBE ofrecer detalle ampliado.
- El sistema DEBE manejar estados recuperables: sesion expirada, contexto invalido, permiso denegado, timeout/red.

### Controles de cumplimiento

- Pruebas de contrato de errores por endpoint.
- Pruebas UX de recuperacion de estado por dispositivo.
- Revision de consistencia de mensajes funcionales.

### Evidencia requerida

- Catalogo oficial de errores de negocio.
- Capturas de respuesta de error por canal.
- Registro de pruebas de recuperacion operativa.

---

## 11) Reglas para escalabilidad futura

### Premisa

La escalabilidad debe preservarse sin bifurcar logica funcional ni romper contratos.

### Reglas obligatorias

- Nuevas capacidades DEBEN activarse con feature flags por experiencia cuando corresponda.
- Evoluciones de contrato DEBEN ser aditivas y versionadas.
- El sistema NO DEBE bifurcar reglas de negocio por canal (`desktop` vs `movil`).
- Toda ampliacion DEBE mantener trazabilidad y compatibilidad operativa.

### Controles de cumplimiento

- Revision de feature flags y alcance por canal.
- Revision de versionado de contratos y compatibilidad.
- Verificacion de ausencia de divergencia funcional por shell.

### Evidencia requerida

- Registro de flags por feature y entorno.
- Manifest de contratos/versiones.
- Reporte de compatibilidad retroactiva.

---

## Contratos normativos aditivos (obligatorios para evolucion futura)

### Metadata minima de comando

Todo comando mutable DEBE transportar:

- `company_id`
- `branch_id`
- `command_id`
- `source_device`
- `channel`
- `device_class` (`desktop|mobile`)

### Bloque minimo de trazabilidad de respuesta

Toda respuesta operativa critica DEBE incluir:

- `trace.request_id`
- `trace.audit_event_id`
- `trace.channel`
- `trace.source_device`

### Catalogo unico de errores cross-device

El catalogo DEBE definir por error:

- `error_code`
- `cause`
- `recommended_action`

El catalogo NO DEBE divergir por canal.

---

## Matriz de cumplimiento

| Regla | Owner | KPI | Evidencia | Frecuencia |
|---|---|---|---|---|
| R1 internet-first + logica unica | Arquitectura de Producto | 0 divergencias funcionales cross-device en QA critico | Reporte de paridad funcional | Por release |
| R2 acceso remoto seguro | Seguridad Aplicativa | 100% endpoints criticos bajo TLS y rate-limit | Snapshot de seguridad por entorno | Mensual |
| R3 auth + step-up en alto impacto | Seguridad Aplicativa | 100% rutas criticas con step-up habilitado | Matriz de rutas criticas y pruebas | Por release |
| R4 RBAC/SoD backend | Arquitectura de Software | 0 acciones sensibles sin validacion backend | Suite RBAC/SoD | Por release |
| R5 UX dual-shell consistente | Arquitectura de Producto | >=95% tareas moviles criticas <=5 pasos | Mapa de flujos y pruebas UX | Trimestral |
| R6 idempotencia y consistencia | Arquitectura de Software | 0 duplicados por reintento en comandos criticos | Pruebas de idempotencia | Por release |
| R7 transacciones con rollback definido | Operaciones + Arquitectura de Software | 100% flujos criticos con rollback documentado | Runbook de rollback | Trimestral |
| R8 trazabilidad E2E obligatoria | QA/Gobernanza | 100% operaciones criticas con `trace` completo | Evidencia request/log/auditoria | Por release |
| R9 consistencia de reportes | Arquitectura de Producto | 0 discrepancias de cifras por mismo filtro/corte | Reporte de consistencia de datasets | Por release |
| R10 errores y mensajes accionables | QA/Gobernanza | >=95% errores criticos con accion sugerida valida | Catalogo de errores y pruebas UX | Mensual |
| R11 escalabilidad no-breaking | Arquitectura de Software | 0 breaking changes sin versionado/aprobacion | Manifest de contratos y ADR | Por release |
