# Diseño — Plataforma de diagnóstico, observabilidad y seguridad (Mundo B)

> **Blueprint de ingeniería, no implementación.** Define la espina del Mundo B: convertir "reportes
> sueltos" en un **ledger de evidencia consultable** que gates deterministas custodian y la IA puede
> diagnosticar (advisory). Robustez = profundidad de la evidencia y de los gates, no un dashboard
> bonito. Fecha: 2026-06-10. Autor: Claude (backend).
> Relacionado: `docs/operacion/FACTIBILIDAD_IA_2026-06.md`, `docs/design/AI_PLATFORM_GOVERNANCE_SPINE_20260610.md`.

## 0. Principio rector
```
La IA DIAGNOSTICA con evidencia; los GATES deterministas BLOQUEAN; el HUMANO decide excepciones.
Primero la EVIDENCIA (Fases 1–4, sin IA). El diagnóstico IA es la última capa y es ADVISORY.
```
**Mundo distinto del A:** esto es capacidad de **ingeniería/seguridad**, para el equipo de
desarrollo, no cara al usuario del ERP. Comparte primitivas de bajo nivel con A (audit, gates,
evidencia, confidence) pero **sus Fases 1–4 no dependen de IA ni de Mundo A en absoluto**.

---

## 1. Invariantes no negociables (J1–J9)

| # | Invariante | Cómo se vuelve estructural |
|---|---|---|
| J1 | Todo error/evento **C1** lleva `correlation_id` + `domain` + `risk_class` | Gate `evidence-c1-guard`; el handler central los rellena, no el dev |
| J2 | **Cero secretos/PII** en logs, findings o evidencia | Reusa `audit/redaction.py` en el sink de telemetría/errores |
| J3 | La IA **nunca** cierra findings, reclasifica C1, ni aplica fix sola | Sólo escribe `AIDiagnosis` (advisory); el cambio de estado es acción humana auditada |
| J4 | Los **gates deterministas** son la autoridad; la IA es asesor | El release lo bloquea el gate, no el modelo |
| J5 | Evidencia **inmutable y referenciable** (finding → archivo/línea/símbolo/commit) | `content_hash` + `stack_hash`; el ledger es append-mostly |
| J6 | Funciona **sin IA y sin red** (offline-first) | El ledger + gates son backend puro; Sentry/LLM son sumideros **opcionales** |
| J7 | Source of truth del riesgo = clasificación **Necktral C1/C2/C3**, no CVSS crudo | Traducción explícita CVE/severidad → `risk_class` |
| J8 | Excepciones con **vencimiento**; vencida = bloquea | Ya existe (`security_exceptions.json`, `max_expiry_days: 90`) — se extiende a errores |
| J9 | Trazabilidad punta a punta | `correlation_id`/`causation_id` propagados desde el request hasta el finding |

---

## 2. Modelo de datos (nuevo módulo `apps.modulos.diagnostics`)

> Reusa el **mapa path→dominio que YA existe** (`DomainScope` / `CRITICAL_DOMAIN_SCOPES` en
> `qa/coverage_by_domain_guard.py`) como fuente única de `domain`. No se duplica.

### `TelemetryEvent` (eventos relevantes, NO todo)
`event_id`, `event_name`, `domain`, `module`, `level`, `timestamp`, `company_id`, `branch_id`,
`user_id`, `correlation_id`, `causation_id`, `request_id`, `object_type`/`object_id`,
`payload_redacted`(JSON), `hash`. Eventos como `payments.capture.failed`, `cec.close.blocked`,
`iam.permission.denied`.

### `ErrorEvent` (errores deduplicados → evidencia)
`error_id`, `exception_type`, `message_hash`, **`stack_hash`** (dedupe), `stack_trace_redacted`,
`file_path`, `line_number`, `function_name`, `endpoint`, `http_status`, `domain`, `risk_class`,
`correlation_id`, `occurrence_count`, `first_seen_at`, `last_seen_at`,
`status` (open/triaged/confirmed/fixed/regressed/accepted_risk/false_positive), `owner`,
`related_audit_event`. **Mismo `stack_hash` = misma fila, `occurrence_count++`** (no inunda la tabla).

### `SecurityFinding` (vuln/SAST/SCA persistido — hoy es JSON efímero)
`finding_id`, `source_tool` (bandit/pip-audit/npm-audit/ruff/mypy/static-scan), `rule_id`, `cve_id`,
`cwe_id`, `package`/`version`, `fixed_version`, `file_path`, `line_start/end`, `symbol`, `domain`,
`severity_raw`, **`risk_class`** (C1/C2/C3 Necktral), `reachable` (true/false/unknown — ver §9),
`status`, `owner`, `accepted_risk_reason`, `expires_at`. Alimentado por los importers que **YA
corren** + el contrato `security_exceptions.json` que **ya aplica vencimiento**.

### `CodeUnitEvidence` (la pieza "cada línea relevante", no log por línea)
`path`, `line_start/end`, `content_hash`, `symbol`, `symbol_type`, `domain`, `coverage_state`,
`test_refs`, `error_refs`, `security_refs`, `last_seen_commit`. Es el cruce que liga un símbolo con
su cobertura + errores + findings. Se construye desde coverage.xml + reports (no necesita GitHub).

### `DiagnosticRun` (corrida de diagnóstico)
`run_id`, `trigger_type` (ci/deploy/runtime_error/security_scan/scheduled/manual), `environment`,
`release_version`, `started/completed_at`, `status`, `tools_used`, `summary`. Puede ser **sin IA**
(sólo agrega evidencia) o **con IA** (genera `AIDiagnosis`).

### `AIDiagnosis` (advisory — única capa que toca IA)
`diagnostic_run`, `subject_type`/`subject_id`, `domain`, `risk_class`, `confidence_score`,
`root_cause_hypothesis`, `blast_radius`, `recommended_fix`, `required_tests`, `evidence_refs`,
`human_review_status`. **Nunca cambia el estado de un finding/error; sólo recomienda.** (J3)

---

## 3. Pipelines (cómo se llena el ledger)

```
P1 Runtime observability
   request → RequestIdMiddleware (correlation_id) → handler central de error
   → ErrorEvent (dedupe por stack_hash, redactado) → opcional sink Sentry/log JSON

P2 Security analysis (CI)
   scanners (bandit/pip-audit/npm-audit/ruff/mypy/static-scan) ya corren
   → normalizar a SecurityFinding → mapear domain (DomainScope) → risk_class C1/C2/C3
   → aplicar security_exceptions.json (vencimiento) → gate decide bloqueo

P3 Code-unit evidence
   build/coverage.xml + reports → indexar símbolos por dominio → CodeUnitEvidence
   (liga cobertura ↔ errores ↔ findings). Origen = filesystem/CI artifact (GitHub OPCIONAL)

P4 AI root-cause (advisory, opcional, offline-diferible)
   ErrorEvent/SecurityFinding + evidencia + coverage → DiagnosticRun
   → AIDiagnosis estructurado (vía gateway de Mundo A) → humano valida/rechaza
```

---

## 4. Enganche con el substrato YA existente (no se reinventa)

| Necesidad | Pieza existente que se reutiliza | Path |
|---|---|---|
| Semilla de correlación | `RequestIdMiddleware` + contextvar `request_id` | `config/middleware/request_id.py` |
| Punto central de error | `ApiErrorEnvelopeMiddleware` + `build_error_envelope` (ya trae `request_id`/`timestamp`) | `config/middleware/api_error_envelope.py`, `config/error_envelope.py` |
| Logging estructurado JSON | `JsonFormatter` + `RequestIdFilter` | `config/logging_utils.py` |
| **Mapa path→dominio** | `DomainScope` / `CRITICAL_DOMAIN_SCOPES` | `qa/coverage_by_domain_guard.py:19` |
| Findings + excepciones con vencimiento | `enforce_security_findings.py` + `security_exceptions.json` | `qa/` |
| Importers que ya corren | bandit/pip-audit/npm-audit/ruff/mypy/static-scan | `Makefile` |
| Captura de errores opcional | Sentry ya configurado (DSN/env/release/traces) | `config/settings/base.py:175` |
| Redacción PII | `audit/redaction.py` | `apps/modulos/audit/redaction.py` |
| Integridad (si se requiere) | patrón hash-chain de `audit/writer.py` | `apps/modulos/audit/` |

**Extensión mínima necesaria:** (a) `RequestIdMiddleware` → propagar también `correlation_id` y
`causation_id` (hoy sólo `request_id`); (b) el handler central → persistir `ErrorEvent` con
`stack_hash` + `domain` (vía `DomainScope`); (c) los importers → escribir filas `SecurityFinding`
además del JSON actual.

---

## 5. Severidad (misma escala que el repo ya usa)
```
C1  dinero · stock · fiscal/billing · contabilidad/GL · permisos/IAM · tenant · CEC · audit · secret leak · vuln crítica alcanzable
C2  error funcional · cobertura faltante en flujo sensible · latencia · API/eventos · reporting · migración riesgosa
C3  estilo · deuda menor · warning · limpieza
```

---

## 6. Gates deterministas (extienden la batería actual — son la autoridad, J4)
- **`evidence-c1-guard`** (nuevo): un `ErrorEvent`/`SecurityFinding` `risk_class=C1` en estado `open`
  **bloquea release** (salvo excepción aprobada y no vencida). Extiende el `enforce_security_findings`
  actual de "vuln" a "cualquier evidencia C1".
- **`telemetry-hygiene-guard`** (nuevo): evento C1 sin `correlation_id`/`domain` → falla;
  log/finding con patrón de secreto → falla (reusa la lógica de redacción).
- **`regression-sentinel`** (nuevo): un `ErrorEvent` que pasa a `fixed` y vuelve a aparecer
  (mismo `stack_hash`) se marca `regressed` y bloquea.
- **Reuso** `qa-audit-integrity`, `qa-coverage-by-domain-guard`, `qa-static-scan`,
  `validate_security_exceptions` (vencimiento), `migration-safety`, `architecture-dependency`
  (aristas `diagnostics → audit/common`, etc.).

---

## 7. Relación con Mundo A (compartir sin fundir)
- Fases 1–4 (ledger + gates) son **100% independientes**: backend puro, sin LLM, sin tocar
  `ai_platform`.
- Sólo la Fase 4/P4 (AI root-cause **advisory**) consume el **gateway de Mundo A** (`AgentRun`,
  auditoría, `AIBudget`) — porque toda llamada a modelo del proyecto pasa por una sola puerta.
  Eso reutiliza una primitiva de bajo nivel **sin** mezclar los roadmaps: si Mundo A no existe aún,
  el Mundo B igual entrega todo su valor (las 4 fases de evidencia).

---

## 8. Punto de extensión (crecer sin tocar la espina)
- **Nuevo importer** (un scanner más) = una función que normaliza su salida a `SecurityFinding`. El
  resto (domain, risk_class, excepción, gate) aplica solo.
- **Nuevo dominio** = una entrada `DomainScope` (path_prefix → key). Todo el ledger lo hereda.
- **Nuevo tipo de evento** = un `event_name` en `TelemetryEvent`. Sin migración.

---

## 9. Fuera de alcance / baja confianza
- **Reachability automatizada** ("¿la ruta vulnerable se ejecuta?"): exige call-graph → se modela como
  `reachable=unknown` por defecto y **asistido-manual**, nunca auto-afirmado. No se promete.
- **Auto-close de findings / fix automático en prod**: PROHIBIDO (J3).
- **Reclasificar C1 por IA**: PROHIBIDO; sólo humano.
- **Depender de Sentry/GitHub como source of truth**: NO; son sumideros opcionales (J6).
- **OpenTelemetry/traces distribuidos completos**: diferido; el `correlation_id` cubre el 80% del
  valor sin la complejidad operativa (no hay infra async).

---

## 10. Contrato de verificación (tests que prueban los invariantes)
- **J1:** un error C1 simulado produce un `ErrorEvent` con `correlation_id` + `domain` + `risk_class`
  no vacíos; sin ellos, `evidence-c1-guard` falla.
- **J2:** un log/finding con un secreto/PII es redactado antes de persistir (test del sink).
- **J3:** no existe ruta que permita a la IA cambiar `SecurityFinding.status`; `AIDiagnosis` es
  sólo-lectura sobre el ledger.
- **J5:** dos ocurrencias del mismo stack → un `ErrorEvent`, `occurrence_count==2` (dedupe).
- **J6:** con Sentry/LLM apagados, P1–P3 llenan el ledger igual (sin red).
- **J8:** una excepción vencida vuelve a bloquear el finding (reusa `validate_security_exceptions`).
- Transversal: suite pytest + guards en el contenedor Docker canónico; restaurar `qa/reports/`.

---

## 11. Rollout (aditivo, evidencia primero, IA al final)
1. Módulo `diagnostics` registrado (patrón `documents`/`ai_platform`) + migración de los 6 modelos +
   entrada en `migration_safety_baseline.json`.
2. **Fase 1–2 (sin IA):** extender `RequestIdMiddleware` (correlation/causation) + handler central →
   `ErrorEvent`; normalizar los reports de los importers a `SecurityFinding`. `DomainScope` como mapa.
3. **Fase 3 (sin IA):** `CodeUnitEvidence` desde coverage + reports.
4. **Fase 4 (gates):** `evidence-c1-guard` + `telemetry-hygiene-guard` + `regression-sentinel`.
5. **Fase 5 (IA advisory, opcional):** `DiagnosticRun`/`AIDiagnosis` vía gateway de Mundo A — sólo
   cuando exista A y haya red; degradable.

**Valor entregado ya en las Fases 1–4 sin un solo token de IA.** La IA llega al final, como asesor
sobre un ledger que ya es robusto por sí mismo.
