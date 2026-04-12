# Informe técnico profundo del repositorio Necktral/Necktral

## Resumen ejecutivo

Necktral es un ERP/CRM modular con backend Django/DRF y frontend Quasar/Vue, diseñado con una orientación fuerte a **seguridad, trazabilidad (auditoría contractual)** y operación **offline-first** mediante un motor de sincronización por comandos. La base técnica del backend es sólida: dependencias modernas (Django 5.2.x, DRF 3.16.x, cryptography, SimpleJWT, CSP, Axes) fileciteturn74file0L1-L1, configuración de seguridad explícita para producción (HSTS, redirect a HTTPS, cookies Secure, y *fail-fast* si faltan llaves críticas) fileciteturn28file0L1-L1, y una “toolchain” de QA/CI con *gates* deterministas (lint/typecheck/tests/integridad de auditoría) fileciteturn68file0L1-L1.

El punto más crítico (y más valioso) del repo es el “doble stack” de sincronización: **`apps.sync_engine`** (offline-first con Ed25519 por comando, scope multiempresa y política defensiva) fileciteturn31file0L1-L1 y **`apps.sync`** (sync por HMAC a nivel request con anti-replay por nonce, envelope de errores muy pulido y suite de tests fuerte) fileciteturn45file0L1-L1. Ambos están conectados simultáneamente en el API: `/api/sync/` (sync_engine) y `/api/sync-hmac/` (sync) fileciteturn29file0L1-L1. 

El repo ya define un **Contrato Sync v2.0 canónico** cuyo objetivo explícito es que **`/api/sync/batch/` sea el endpoint unificado** con `protocol_version="2"` y que lo legacy sea solo wrapper fileciteturn52file0L1-L1. En el estado actual, ese contrato está **parcialmente alineado** (el core de `sync_engine` es fuerte), pero aún hay una brecha: el esquema *request-level* (`ts/nonce/auth`) y anti-replay del contrato v2 todavía no están integrados en el core y el endpoint HMAC no es wrapper sino implementación paralela fileciteturn52file0L1-L1 fileciteturn45file0L1-L1. 

Diagnóstico ejecutivo: **sí es funcional como sistema ejecutable en dev/prod-compose** (stack Docker, healthchecks, endpoints, tests y CI) fileciteturn19file0L1-L1 fileciteturn25file0L1-L1, y es un proyecto con madurez técnica real en backend/seguridad/QA; la prioridad estratégica es **unificar Sync** (para reducir riesgo y deuda), y elevar consistencia operativa (CI/CD con “quality gate” antes de deploy, y hardening TLS/CSP sin duplicidades).

## Diagnóstico de funcionalidad y madurez

Este diagnóstico es **estático** (lectura de repositorio); no ejecuté contenedores ni probé endpoints en runtime, así que hablo en términos de “lo que el código y la infraestructura muestran” más que de *telemetría real*.

### Funcionalidad observable

El repositorio trae un entorno Docker completo para dev (`compose.yaml`) con Postgres 16.2, backend (Django) y frontend (Node/Quasar), además de healthchecks que validan disponibilidad de `/api/auth/bootstrap/status/` fileciteturn19file0L1-L1. El arranque automatiza migraciones (dev y prod) y en producción además ejecuta `collectstatic` + `check --deploy` antes de levantar Gunicorn fileciteturn26file0L1-L1. 

En prod, el stack usa una imagen `web` basada en Nginx para servir la SPA y proxyear `/api/` hacia el backend fileciteturn20file0L1-L1, con rate limiting y headers de seguridad (CSP, X-Frame-Options, nosniff, etc.) ya declarados en la configuración Nginx fileciteturn24file0L1-L1.

En API, el enrutamiento declara **dos rutas de sync activas**:  
- `/api/sync/` → `apps.sync_engine.urls`  
- `/api/sync-hmac/` → `apps.sync.urls` fileciteturn29file0L1-L1  

### Madurez por área

| Área | Evidencia en repo | Diagnóstico de madurez (práctico) | Riesgo principal |
|---|---|---|---|
| Backend core (Django/DRF) | Dependencias modernas y “stack” de seguridad (Axes, CSP, Argon2, JWT, etc.) fileciteturn74file0L1-L1 | **Alta (backend)**: arquitectura y controles presentes, con hardening prod fileciteturn28file0L1-L1 | Complejidad: muchos módulos y contratos; requiere disciplina de releases |
| Seguridad (app) | `prod.py` fuerza HSTS/redirect/cookies seguras + fail-fast de secretos fileciteturn28file0L1-L1 | **Alta (baseline)**, con gaps típicos de TLS “real” si Nginx termina en :80 fileciteturn24file0L1-L1 | “Falsa sensación” si TLS/HSTS no se valida end-to-end |
| QA/CI | Workflow QA CI Gates 1–3 con Docker + reportes fileciteturn68file0L1-L1; Security CI blocking fileciteturn69file0L1-L1 | **Alta (para backend)**: disciplina de gates + artefactos | CD no está acoplado a gates: riesgo de deploy de build no certificado fileciteturn70file0L1-L1 |
| Sync Engine (offline-first) | Pipeline defensivo: firmas Ed25519 por comando, idempotencia, scope, cuarentena, auditoría contractual fileciteturn31file0L1-L1 | **Alta (diseño)**: es el corazón offline-first | Falta integrar anti-replay request-level del contrato v2 fileciteturn52file0L1-L1 |
| Sync HMAC (legacy/alterno) | HMAC request-level + timestamp window + persistencia de nonce anti-replay fileciteturn45file0L1-L1 | **Media/Alta (robustez)**, pero es “motor paralelo” | Duplicación de modelos/idempotencia y divergencia contractual |
| CD/Operación | Workflow CD build+push+deploy por SSH a VPS fileciteturn70file0L1-L1 + runbook deploy fileciteturn81file0L1-L1 | **Media**: deploy funciona, rollback por tag claro | No fuerza “quality gate” antes de deploy |

### Diagnóstico conciso de funcionalidad

El sistema **es funcional** en el sentido de “arranca, migra y expone endpoints” con Docker Compose en dev y en prod-compose, y contiene pruebas automatizadas para flujos críticos de sync y contratos fileciteturn19file0L1-L1 fileciteturn62file0L1-L1 fileciteturn63file0L1-L1. El nivel de madurez de ingeniería (seguridad/QA) es poco común para un proyecto individual y es una fortaleza real. El cuello de botella principal para “subir de nivel” no es “más features”, sino **reducir dualidades (sync), endurecer operación (CD acoplado a gates) y estabilizar contratos**.

## Mejoras técnicas priorizadas

La lógica de priorización aquí es: **reducir riesgo sistémico primero** (seguridad, consistencia contractual, camino único de sync), luego elevar “productividad sostenida” (testing, DX, CI/CD), y después expandir alcance con seguridad (ops y arquitectura de integración).

### Backlog priorizado

| Prioridad | Área | Mejora | Por qué (impacto) | Referencias repo |
|---|---|---|---|---|
| P0 | Arquitectura / Sync | Unificar `apps.sync_engine` y `apps.sync` alrededor del contrato Sync v2 (un solo core, legacy como wrapper) | El doble motor es el mayor riesgo de divergencia y bugs “no reproducibles” | Contrato Sync v2 fileciteturn52file0L1-L1; rutas actuales fileciteturn29file0L1-L1 |
| P0 | Seguridad / Integridad | Integrar anti-replay a nivel request (nonce persistido) en el core v2 | El contrato v2 lo marca como invariante y el stack HMAC ya lo probó fileciteturn52file0L1-L1 | Anti-replay HMAC fileciteturn45file0L1-L1; tests replay fileciteturn63file0L1-L1 |
| P0 | CI/CD | Bloquear CD si QA CI + Security CI no pasan (branch protection o “needs” en workflow) | Evita deploy de builds no certificados; reduce incidentes | CD actual fileciteturn70file0L1-L1; QA CI fileciteturn68file0L1-L1; Security CI fileciteturn69file0L1-L1 |
| P1 | Seguridad | Validación “end-to-end” de TLS/HSTS en despliegue real (y decisión explícita de dónde termina TLS) | Nginx del repo escucha en 80; HSTS depende de HTTPS real fileciteturn24file0L1-L1 | `prod.py` HSTS fileciteturn28file0L1-L1; Nginx listen 80 fileciteturn24file0L1-L1; Django recomienda SSL redirect + cookies secure + HSTS citeturn1search0 |
| P1 | Seguridad | Unificar CSP (evitar doble fuente: Nginx + django-csp) y eliminar `unsafe-inline` donde sea viable | CSP duplicada puede generar inconsistencias; OWASP recomienda nonces/hashes en lugar de `unsafe-inline` citeturn0search0 | Nginx CSP fileciteturn24file0L1-L1; Django CSP settings fileciteturn27file0L1-L1 |
| P1 | QA | Subir el nivel de “contract tests” para Sync v2 + wrappers legacy, con criterios de aceptación cuantificables | Reduce regresiones durante la unificación | Tests sync_engine fileciteturn62file0L1-L1; tests sync-hmac fileciteturn63file0L1-L1 |
| P2 | Seguridad / Supply chain | “Pinning” y endurecimiento supply chain en CI: imágenes y acciones por digest/SHA (evitar `:latest`) | Reduce riesgo de ataque a CI/CD | `security-ci.yml` usa `gitleaks:latest` fileciteturn69file0L1-L1 |
| P2 | Ops | Observabilidad operacional: métricas de sync (latencia, errores por reason_code, replay, duplicates) + dashboards | El contrato v2 exige métricas legacy; operar sync sin métricas es ciego fileciteturn52file0L1-L1 | Logging y request_id ya existen fileciteturn27file0L1-L1 |
| P2 | Arquitectura | Implementar patrón **Transactional Outbox** para integración entre módulos (event backbone) | Alinea con tu blueprint y evita dual-write; patrón estándar citeturn3search5 | Blueprint sugiere outbox/inbox fileciteturn76file0L1-L1 |

Notas técnicas clave para justificar prioridades:
- Tu core `sync_engine` ya tiene pipeline sólido: límites, scope enforcement, canonicalización, verificación Ed25519, idempotencia y auditoría contractual por batch/comando fileciteturn31file0L1-L1.  
- Tu `sync-hmac` ya tiene anti-replay probado con **nonce persistido** y window temporal, con suite de tests enfocada (incluye throttling y envelope) fileciteturn45file0L1-L1 fileciteturn63file0L1-L1.  
La unificación correcta es “tomar lo mejor de ambos”: core offline-first + request-level auth/anti-replay + compatibilidad contractual.

## Plan maestro para unificar sync_engine y sync

Este plan está diseñado para **llegar a un Sync v2 canónico** conforme a `docs/CONTRACT_PACK_v2.0.md` fileciteturn52file0L1-L1, reduciendo riesgo y preservando compatibilidad. El objetivo final es que haya **un solo motor** de aplicación/idempotencia/auditoría (core), y que lo legacy sea únicamente “capa de traducción”.

### Estado actual comparativo

| Dimensión | `apps.sync_engine` (`/api/sync/batch/`) | `apps.sync` (`/api/sync-hmac/batch/`) |
|---|---|---|
| Firma | Ed25519 **por comando**, mensaje determinista sin JSON fileciteturn33file0L1-L1 | HMAC **por request**, `ts+nonce+hash(body)` fileciteturn47file0L1-L1 |
| Anti-replay | No hay nonce persistido (hoy) | Sí: persiste nonce y rechaza replay fileciteturn46file0L1-L1 |
| Scope multi-tenant | Sí: `company_id/branch_id` por comando + enforcement contra device fileciteturn31file0L1-L1 | No aparece modelado (device es global) fileciteturn46file0L1-L1 |
| Idempotencia | `AppliedCommand` global por `command_id` (PK), con `payload_hash` y estados APPLIED/DUPLICATE/REJECTED fileciteturn30file0L1-L1 | `AppliedCommand` por `(device, command_id)` con cache respuesta OK/ERROR fileciteturn46file0L1-L1 |
| Auditoría | Emite eventos `SYNC_*` y guarda `SyncReceipt` por batch fileciteturn31file0L1-L1 fileciteturn30file0L1-L1 | No se observa emisión de auditoría contractual del pipeline (en el snippet principal) fileciteturn45file0L1-L1 |
| Contrato v2 | Parcialmente alineado (endpoint y semántica por comando), pero falta request-level v2 fileciteturn52file0L1-L1 | Implementación paralela; debería convertirse en wrapper según contrato v2 fileciteturn52file0L1-L1 |

### Arquitectura objetivo

```mermaid
flowchart LR
  subgraph Clients
    A[Cliente offline v2\n(protocol_version=2)] 
    B[Cliente legacy HMAC\n(headers X-Device-*)]
    C[Cliente legacy Ed25519\n(schema actual sync_engine)]
  end

  subgraph API
    W1[/POST /api/sync/batch/\n(v2 canónico + compat)] 
    W2[/POST /api/sync-hmac/batch/\n(wrapper legacy)] 
  end

  subgraph Core["Core Sync (único)"]
    P[Parser/Normalizer\n(v2, legacy->v2)]
    R[Request Auth + Anti-replay\n(ts/nonce + hmac|ed25519)]
    E[Engine: validate scope + policy\n+ idempotencia + dispatch handlers]
    AU[Auditoría contractual SYNC_*\n+ receipts]
  end

  DB[(PostgreSQL)]

  A --> W1
  C --> W1
  B --> W2 --> P
  W1 --> P --> R --> E --> AU --> DB
  E --> DB
```

La idea explícita del contrato v2 es que *“legacy endpoints sean wrappers”* fileciteturn52file0L1-L1; este diseño cumple eso y además agrega compatibilidad incremental para tus clientes actuales.

### Plan por fases

La tabla siguiente incluye, por fase: metas, entregables, tareas concretas, pruebas, cambios CI, riesgos/rollback, esfuerzo estimado y criterios de aceptación.

| Fase | Metas | Entregables | Tareas concretas | Pruebas (unit/contract/E2E) | Cambios CI | Riesgo y rollback | Esfuerzo | Criterios de aceptación |
|---|---|---|---|---|---|---|---|---|
| Fase de estabilización contractual | Congelar “cómo debe verse Sync” para que la unificación sea medible y no subjetiva | “Matriz de compatibilidad” Sync (inputs/outputs/códigos), y baseline de métricas | Alinear `docs/CONTRACT_PACK_v2.0.md` con lo que hoy existe y marcar como **GAP** lo que no está implementado (ej. request-level v2 dentro del core) fileciteturn52file0L1-L1. Definir catálogo mínimo de error codes y headers deprecación con fechas reales (Sunset 2026-03-31 está en el contrato) fileciteturn52file0L1-L1 | Unit: validaciones de canonicalización y message-to-sign. Contract: golden tests de errores y responses. E2E: smoke en docker compose (una corrida). | Agregar job “contract-report” (artefacto de compatibilidad) al QA CI fileciteturn68file0L1-L1 | Riesgo: “parálisis por especificación”. Rollback: mantener documento como “informativo” si no se puede cerrar. | S | Documento + tests “golden” pasan, y lista explícita de gaps queda versionada |
| Fase núcleo v2 | Crear **parser/normalizer Sync v2** dentro del core sin romper el esquema actual de `sync_engine` | Serializer v2 + normalizador v2→interno. Soporte “dual” en `/api/sync/batch/` por detección (v2 vs legacy sync_engine) | Implementar `SyncV2BatchIn` (fields `protocol_version`, `device_id`, `ts`, `nonce`, `auth`, `batch_id`, `batch[]`) conforme contrato fileciteturn52file0L1-L1. Normalizar a estructura interna actual (`commands[]` con `command_type/company_id/...`) fileciteturn34file0L1-L1. Mantener soporte del esquema actual (`SyncBatchIn`) como modo legacy | Unit: serializer v2 valida inputs. Contract: respuesta por comando mantiene `APPLIED/REJECTED/DUPLICATE` fileciteturn31file0L1-L1. E2E: inventario offline (receive/issue) sigue pasando fileciteturn62file0L1-L1 | QA Gate 2: sumar tests de v2 al scope de coverage del sync_engine (ya apunta al módulo) fileciteturn60file0L1-L1 | Riesgo: romper clientes existentes. Rollback: feature-flag de aceptación v2 (deshabilitar v2 y aceptar solo legacy). | M | 1) Todos los tests actuales pasan. 2) Nuevos tests v2 pasan. 3) `/api/sync/batch/` acepta legacy y v2 |
| Fase seguridad v2 | Incluir en core el **request-level auth + anti-replay** como invariante v2 | Tabla/Modelo de nonce (único por device), verificación de ventana temporal y signature request-level (hmac|ed25519) | Crear modelo tipo `DeviceRequestNonce` (unique (device, nonce)) inspirado en `apps.sync` fileciteturn46file0L1-L1. Implementar orden v2: 1) ventana temporal, 2) verificar firma, 3) persistir nonce, 4) colisión ⇒ `REPLAY_DETECTED` fileciteturn52file0L1-L1. Para HMAC usar HMAC-SHA256 (especificación HMAC) citeturn1search1; para Ed25519 basarse en EdDSA Ed25519 citeturn2search2. | Unit: firma OK/KO; canonical JSON estable. Contract: códigos `BAD_SIGNATURE`, `TS_OUT_OF_WINDOW`, `REPLAY_DETECTED` fileciteturn52file0L1-L1. E2E: replay detectable con mismo nonce. | Añadir test suite “security-contract” a QA CI + publicar métricas simuladas (artefacto). | Riesgo: falsos positivos por reloj de dispositivo. Rollback: ampliar temporalmente ventana `MAX_SKEW_SECONDS` por env y registrar auditoría. | M | Replays se rechazan consistentemente; la verificación es determinista cross-plataforma; error envelope estable fileciteturn65file0L1-L1 |
| Fase wrapper legacy HMAC | Convertir `/api/sync-hmac/batch/` en **wrapper real** que ejecuta el core v2 | Endpoint legacy conserva headers, pero internamente traduce a v2 y llama al core | Reemplazar lógica paralela de `apps.sync.views.SyncBatchView` fileciteturn45file0L1-L1 por: (a) autenticación legacy (HMAC sobre raw body + headers) para no romper clientes existentes fileciteturn47file0L1-L1, (b) traducción a v2 normalizado, (c) ejecución del core único. Añadir headers `Deprecation/Sunset/Link` (Sunset 2026-03-31T00:00:00Z según contrato) fileciteturn52file0L1-L1 | Contract: todos los tests actuales de `apps.sync` deben seguir pasando (missing headers, replay, throttling envelope, request_id) fileciteturn63file0L1-L1. E2E: mismo batch por /sync-hmac y /sync produce semántica equivalente. | Ajustar coverage: el scope actual mide `sync_engine`; agregar “contract tests” del wrapper aunque queden fuera del scope de coverage (como gate separado) fileciteturn59file0L1-L1 | Riesgo: acoplar “raw-body signature” a “canonical JSON signature”. Rollback: modo dual (endpoint legacy sigue con motor viejo detrás de feature flag por un tiempo corto). | M | 1) Legacy clients no se rompen. 2) Core único recibe la aplicación/idempotencia. 3) Deprecation headers presentes |
| Fase retiro y limpieza | Reducir superficie: un solo set de tablas y un solo “source of truth” | Plan de deprecación ejecutado, métricas de uso legacy, y opcional: migración histórica | Implementar métricas `sync_legacy:requests/errors` como pide contrato fileciteturn52file0L1-L1. Deshabilitar alta de nuevos dispositivos legacy y documentar retiro. (Opcional) migrar `DeviceEnrollment` a `Device` si aplica. | Contract: tests de deprecación (headers y respuestas). E2E: “cutover rehearsal” en staging. | Hacer que CD requiera QA+Security para merges y deploy fileciteturn70file0L1-L1 | Riesgo: clientes olvidados. Rollback: extender ventana legacy; monitoreo de métricas. | L | % de tráfico legacy ≈ 0; endpoint legacy retirado sin pérdida de idempotencia |

### Matriz de riesgos específica de la unificación

| Riesgo | Probabilidad | Impacto | Señal temprana (detección) | Mitigación | Plan de rollback |
|---|---:|---:|---|---|---|
| Incompatibilidad de firmas por diferencias de canonicalización | Media | Alta | Aumento de `BAD_SIGNATURE`/`SYNC_INVALID_SIGNATURE` | Canonical JSON estable y cross-language; tests “golden” | Mantener verificación legacy por raw body solo en wrapper HMAC, y no forzar v2 ahí hasta que clientes migren |
| Reloj de dispositivo fuera de ventana | Media | Media | Errores `TS_OUT_OF_WINDOW` | Ventana configurable por env; cuarentena “soft” antes de hard-block | Aumentar ventana temporalmente y auditar |
| Duplicación de DB (nonce table) eleva costo de escritura | Baja | Media | Latencia en endpoint sync | Índices adecuados; limpieza por TTL; particionado si escala | Desactivar anti-replay en staging (feature flag) si hay regresión severa |
| Confusión operacional por endpoints duplicados durante transición | Media | Media | Soporte recibe “¿cuál endpoint uso?” | Documentación + Deprecation header + Link al contrato fileciteturn52file0L1-L1 | Mantener ambos endpoints pero con el mismo core y logs unificados |
| Bugs de idempotencia al mezclar stores | Baja | Alta | Re-aplicaciones o `PAYLOAD_MISMATCH` inesperados | Core único como “source of truth”; dedupe por `command_id` y hash fileciteturn31file0L1-L1 | Modo dual temporal: consulta cruzada con store legacy por 1 release |

## Estrategia de migración y compatibilidad

Aquí hay dos migraciones: **clientes** (protocolos) y **datos** (tablas/modelos). La estrategia correcta minimiza riesgo: primero haces que ambos endpoints ejecuten el mismo core; después retiras el legacy.

### Migración de clientes

**Contexto:**  
- Hoy existen dos APIs: `/api/sync/batch/` con esquema legacy de `sync_engine` (comandos con firma Ed25519 por comando) fileciteturn34file0L1-L1 y `/api/sync-hmac/batch/` con headers HMAC y nonce anti-replay fileciteturn45file0L1-L1.  
- El contrato establece que v2 canónico debe ir por `/api/sync/batch/` con `protocol_version="2"` y auth request-level, y que legacy sea wrapper fileciteturn52file0L1-L1.

**Estrategia recomendada (compatibilidad sin ruptura):**
1. `/api/sync/batch/` acepta ambos:  
   - si viene `protocol_version="2"` ⇒ modo v2  
   - si no viene ⇒ modo legacy (schema actual `SyncBatchIn`) fileciteturn34file0L1-L1  
2. `/api/sync-hmac/batch/` se mantiene “igual por fuera” (headers), pero internamente se vuelve wrapper y ejecuta core v2, agregando headers de deprecación (con Sunset explícito). fileciteturn52file0L1-L1  
3. En cada respuesta legacy, agregar telemetría y headers:
   - `Deprecation: true`
   - `Sunset: 2026-03-31T00:00:00Z`
   - `Link: </docs/CONTRACT_PACK_v2.0.md>; rel="deprecation"` fileciteturn52file0L1-L1  

### Flujos de migración

```mermaid
flowchart TB
  L[Cliente legacy HMAC] -->|POST /api/sync-hmac/batch/\nheaders X-Device-*| W[Wrapper legacy]
  W -->|Verifica HMAC legacy\n+ persiste nonce| N[Normaliza a v2]
  N --> C[Core Sync v2 único]
  C -->|APPLIED/REJECTED/DUPLICATE| W
  W -->|Respuesta legacy + headers Deprecation/Sunset| L

  V2[Cliente Sync v2] -->|POST /api/sync/batch/\nprotocol_version=2| C
  E[Cliente legacy Ed25519] -->|POST /api/sync/batch/\n(schema actual)| C
```

### Migración de datos

En DB hay tablas duplicadas conceptualmente:
- `apps.sync_engine.models.Device` es multi-tenant y guarda public_key, status, secuencia, etc. fileciteturn30file0L1-L1  
- `apps.sync.models.DeviceEnrollment` guarda secreto HMAC base64 e is_active, pero no scope company/branch fileciteturn46file0L1-L1  
- Ambos tienen un `AppliedCommand` distinto que representa idempotencia con reglas diferentes fileciteturn30file0L1-L1 fileciteturn46file0L1-L1  

**Regla de oro:** el “source of truth” debe ser el `AppliedCommand` del core sync (el contrato v2 lo declara explícitamente) fileciteturn52file0L1-L1.

**Estrategia recomendada (datos):**
- No intentes “fusionar histórico” al inicio. En transición, la prioridad es que **todo comando nuevo** termine en el `AppliedCommand` del core único.  
- Para `DeviceEnrollment` legacy:
  - Opción A (más segura): re-enrolar dispositivos en el sistema nuevo (ed25519/enrollment challenge), porque el legacy no tiene scope multiempresa; esta opción reduce riesgo de mapear mal tenant/sucursal.  
  - Opción B (compatibilidad): extender el modelo `Device` del core para soportar `hmac_secret_b64` opcional y permitir “modo HMAC device” para wrappers; eso permite migrar sin tocar el cliente, pero debes definir cómo asignar scope (manual/admin).  
- Para `DeviceRequestNonce` legacy: se debe reemplazar por la tabla nonce del core (una sola). El contrato v2 requiere unicidad `(device_id, nonce)` fileciteturn52file0L1-L1.

### Contract tests y compatibilidad

Ya tienes excelentes pruebas unitarias/integración para ambos mundos:
- Sync Engine: enrolment + replay como DUPLICATE, firmas inválidas parciales, payload mismatch, etc. fileciteturn61file0L1-L1  
- Sync HMAC: happy path, bad signature, replay nonce, envelope y throttling fileciteturn63file0L1-L1  

La migración debe agregar (sin reemplazar) estos “compat tests”:
- **Equivalencia semántica:** mismo lote (misma intención de comandos) enviado por `/api/sync-hmac/batch/` y por `/api/sync/batch/` debe producir resultados equivalentes (donde aplique).  
- **Estabilidad de códigos:** `BAD_SIGNATURE`, `REPLAY_DETECTED`, `TS_OUT_OF_WINDOW` y `SYNC_PAYLOAD_MISMATCH` deben seguir siendo exactamente esos strings por contrato fileciteturn52file0L1-L1.  
- **Error envelope y request_id:** cada error API debe responder en el envelope estándar con `request_id` correlacionable (ya existe la infraestructura) fileciteturn65file0L1-L1 fileciteturn66file0L1-L1.  
- **Idempotencia cross-endpoint:** si un comando fue aplicado por el wrapper legacy, debe deduplicarse igual si luego llega por v2 (el core único lo garantiza).

## Checklist de hardening para producción

Este checklist combina: (a) lo que ya está en tu repo, (b) lo que falta/conviene, y (c) referencias a estándares/guías oficiales.

| Control | Estado en repo (según archivos) | Recomendación de hardening (concreta) | Fuentes |
|---|---|---|---|
| TLS real (HTTPS) | `docker/web.Dockerfile` y `default.conf` exponen Nginx en **80** fileciteturn23file0L1-L1 fileciteturn24file0L1-L1 | Decidir explícitamente: (1) TLS termina en un LB/Cloudflare/caddy externo, o (2) TLS termina en este Nginx. En ambos casos, validar con `curl -I` que *toda* ruta crucial redirige a HTTPS y no hay mixed content. Django recomienda redirigir HTTP→HTTPS y usar cookies `Secure`. citeturn1search0 |
| HSTS | Django prod configura HSTS y redirect (SECURE_SSL_REDIRECT, SECURE_HSTS_SECONDS, includeSubDomains) fileciteturn28file0L1-L1 | Confirmar que HSTS realmente se emite bajo HTTPS. RFC 6797 define `max-age` y que `max-age=0` desactiva HSTS citeturn0search4. Para “preload”, sólo activar si **todos** los subdominios soportan HTTPS (riesgo real de bloqueo). citeturn0search1turn4search4 |
| Cookies (Secure/HttpOnly/SameSite) | Base define cookies de auth (nombres `nt_access/nt_refresh/nt_csrf`) y flags; prod fuerza `Secure`. fileciteturn27file0L1-L1 fileciteturn28file0L1-L1 | Validar en runtime que cookies sensibles siempre estén con `Secure` y `HttpOnly` (cuando aplique); OWASP recomienda `Secure` y `HttpOnly` para evitar robo por MITM/XSS citeturn0search2. Si alguna cookie necesita `SameSite=None`, debe llevar `Secure` (MDN) citeturn4search0turn4search6 |
| CSRF | Settings incluyen CSRF trusted origins y middleware CSRF/cookie-csrf fileciteturn27file0L1-L1 | Confirmar que el frontend usa header CSRF y que `CSRF_TRUSTED_ORIGINS` está correcto. Django documenta settings de CSRF y rotación de token tras login citeturn1search2 |
| CSP | Nginx añade CSP fuerte pero con `style-src 'unsafe-inline'` fileciteturn24file0L1-L1; Django también configura CSP (enforce + report-only) fileciteturn27file0L1-L1 | Evitar doble autoridad (Nginx + Django) o alinear ambas. OWASP recomienda usar hashes/nonces en lugar de `unsafe-inline` para scripts y limitar `connect-src` citeturn0search0. Donde uses iframes, `frame-ancestors` controla embedding (MDN) citeturn4search7 |
| Rate limiting | Nginx `limit_req_zone` + `limit_req` por rutas /api/auth y /api/ fileciteturn24file0L1-L1 y DRF throttles por scope fileciteturn27file0L1-L1 | Confirmar si el código HTTP para limit es 429/503; Nginx por defecto usa 503 pero es configurable citeturn2search1. Alinear “contractualmente” a 429 para UI (tu envelope ya mapea 429) fileciteturn65file0L1-L1 |
| Rotación de secretos | Hay runbook de rotación dual-key para auditoría y secretos sync fileciteturn80file0L1-L1 | Formalizar periodicidad y automatizar evidencia. OWASP recomienda rotación, revocación y expiración cuando sea posible citeturn2search0 |
| Supply chain (CI) | Security CI corre gitleaks, pip-audit, npm audit fileciteturn69file0L1-L1 | “Pinning” de versiones/SHAs y evitar `:latest` en herramientas críticas de CI (reduce riesgo de ataques a pipeline). |
| Observabilidad | Logging con request_id y JSON formatter en prod/entorno no debug fileciteturn27file0L1-L1; Sentry opcional fileciteturn27file0L1-L1 | Definir métricas mínimas del sync (latencia, rejects por reason_code, replay, duplicates). Para outbox, patrón recomendado evita inconsistencias de dual-write citeturn3search5 |

### Nota específica sobre HSTS y cookies (importante)

Para que HSTS + cookies `Secure` sean realmente efectivos, **primero** debe existir HTTPS end-to-end. Django lo remarca: redirigir a HTTPS (`SECURE_SSL_REDIRECT=True`) y marcar `SESSION_COOKIE_SECURE`/`CSRF_COOKIE_SECURE` evita filtración de cookies en conexiones inseguras citeturn1search0. El estándar HSTS define que el navegador cachea la política por `max-age` citeturn0search4, por lo que activarlo sin tener TLS bien resuelto puede bloquear usuarios (especialmente si se aplica a subdominios). citeturn4search4turn0search1

### Nota específica sobre criptografía de Sync (para decisiones)

- HMAC (RFC 2104) es un mecanismo estándar de autenticación de mensajes basado en hash y secreto compartido citeturn1search1. Su principal trade-off es operacional: el servidor debe custodiar el secreto (impacto si DB/secret store se compromete).  
- Ed25519 (EdDSA, RFC 8032) es firma asimétrica; el servidor sólo necesita clave pública para verificar citeturn2search2. Para tu caso offline-first multi-tenant, Ed25519 es una base más “limpia” porque reduce superficie de secretos en servidor.  

Tu repo ya usa Ed25519 por comando con validación estricta de tamaños (32 bytes pubkey, 64 bytes firma) y canonicalización estable fileciteturn33file0L1-L1. La unificación debería mantener eso como “camino premium”, y mantener HMAC principalmente como compatibilidad.

