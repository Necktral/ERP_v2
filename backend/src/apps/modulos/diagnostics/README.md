# Módulo `diagnostics` — plataforma de diagnóstico (Mundo B)

Capacidad de **ingeniería/observabilidad** (no cara al usuario del ERP). Convierte los
errores de runtime en un **ledger de evidencia consultable**. Diseño completo en
`docs/design/AI_DIAGNOSTIC_PLATFORM_SPINE_20260610.md`.

> Principio: **evidencia primero, sin IA; los gates bloquean; la IA llega al final.**

## Rebanada B-1 (esta) — `ErrorEvent`
- **Captura automática y best-effort:** un receiver de `got_request_exception` (`capture.py`)
  persiste cada error 500 no manejado. **Nunca altera la respuesta** (todo en try/except, igual
  que el tag de Sentry en `config/middleware/request_id.py`).
- **Dedupe por `stack_hash`:** mismo stack ⇒ misma fila con `occurrence_count++` (no inunda la tabla).
- **Clasificación Necktral:** `domain_map.py` mapea el frame más profundo del repo a un dominio y a
  su clase de riesgo **C1/C2/C3** (dinero/stock/fiscal/permisos/CEC/auditoría = C1).
- **Redacción (J2):** la traza guarda SOLO frames (sin el mensaje crudo, que va hasheado) y se le pasa
  un scrub de `clave=valor` sensibles (`extract.py`).
- **Trazabilidad (J1):** cada evento lleva `correlation_id` (del `X-Request-Id`) + `domain` + `risk_class`.

## API de lectura (ops; permiso `diagnostics.error.read`)
- `GET /api/diagnostics/errors/` — lista (filtros `domain`, `risk_class`, `status`).
- `GET /api/diagnostics/errors/<error_id>/` — detalle (incluye la traza redactada).

## Rebanada B-2 — `SecurityFinding` (ledger de seguridad) + botón de apagado de IA

### `SecurityFinding`
Convierte el JSON efímero de los scanners en un **ledger consultable**, deduplicado por
(`source_tool`, `package`, `vuln_id`). Esta rebanada ingiere los scanners de **dependencias**
(pip-audit + npm-audit; SAST/bandit con dominio en una sub-rebanada siguiente).
- **Ingesta determinista** (`findings.py` + command `ingest_security_findings`): parsea los reports,
  aplica el contrato `qa/contracts/security_exceptions.json` **con vencimiento** (excepción vigente →
  `accepted_risk`; vencida → vuelve a `open` y bloquea), clasifica riesgo (dep high/critical → **C2**,
  no C1 porque la reachability es desconocida), y **reconcilia** (lo que ya no aparece → `fixed`).
- **Respeta el triage humano:** la re-ingesta solo recalcula estados automáticos
  (`open`/`accepted_risk`/`fixed`); nunca pisa `confirmed`/`false_positive`.
- **API:** `GET /api/diagnostics/findings/` (lista + detalle), permiso `diagnostics.finding.read`.

### Botón de apagado de la IA (kill switch)
Requisito del dueño: **toda la IA debe poder apagarse**. Dos capas:
- **`AI_FEATURES_ENABLED`** (entorno, **apagado por defecto** = opt-in): hard switch que sobrevive a
  todo. Si está en `false`, la IA **no corre** (sin tocar la DB).
- **`AIControl`** (singleton runtime, el "botón"): un admin lo apaga/enciende **en caliente** vía
  `GET/POST /api/diagnostics/ai-control/` (POST exige `diagnostics.ai_control.manage`).
- **Regla:** TODA funcionalidad de IA (gateway de Mundo A, motor de diagnóstico B-5, agentes) DEBE
  consultar **`flags.ai_features_enabled()`** = entorno **Y** botón runtime.
- **`DIAGNOSTICS_ENABLED`** (entorno, encendido por defecto): interruptor del subsistema de
  observabilidad determinista; en `false`, la captura de errores deja de registrar.

## Rebanada B-3 — causa raíz (`DiagnosticRun`): el *por qué* del fallo, sin IA

Lo **fundamental** de la plataforma: cuando algo falla, supervisar y explicar **por qué**
(cadena `síntoma → causa`). `diagnose.py` arma, para un `ErrorEvent`, un **paquete de
evidencia DETERMINISTA** (sin IA):
- **Contexto**: archivo/línea/función, dominio, riesgo, endpoint, correlation_id.
- **Timeline**: ocurrencias, primera/última vez, span.
- **Relacionados**: otros `ErrorEvent` del mismo dominio/archivo + `SecurityFinding` en ese archivo.
- **Blast radius** + **señales** (`alta_frecuencia`, `dominio_C1`, `regresion`, `aislado`) + un
  **resumen legible**.
- La **hipótesis de causa** queda vacía: la pone un humano o, en el futuro y **solo con el kill
  switch encendido** (`ai_features_enabled()`), el motor IA advisory. La supervisión del *por qué*
  funciona **siempre, con la IA apagada**.
- **API**: `POST /api/diagnostics/errors/<id>/diagnose/` (permiso `diagnostics.diagnose.run`),
  `GET /api/diagnostics/diagnoses/` + detalle (`diagnostics.diagnose.read`).

## Rebanada B-4 — supervisión con dientes: regression-sentinel + gate de release (sin IA)

*"La IA diagnostica con evidencia; los gates bloquean; el humano decide excepciones."*
- **Regression-sentinel** (en la captura): si un `ErrorEvent` ya `fixed` **reaparece** (mismo
  `stack_hash`) → vuelve a **`regressed`** automáticamente. La supervisión detecta que el fallo volvió.
- **Gate de release** (`gates.py` `evaluate_release_gates`): **un C1 abierto** (error de runtime o
  hallazgo de seguridad) **bloquea**; devuelve verdicto + conteos + regresiones.
  - **API**: `GET /api/diagnostics/release-readiness/` (permiso `diagnostics.error.read`).
  - **Command**: `check_release_gates` (falla con exit≠0 si hay C1 abierto) — para el pipeline de
    deploy (que tiene DB), no para el job de tests de CI.

## Rebanada B-5 — motor IA **advisory** (rellena la hipótesis de causa), detrás del kill switch

Primera pieza con IA del Mundo B. **SIEMPRE gateada por `flags.ai_features_enabled()`**: con la IA
apagada (default), el endpoint responde **409** y no toca nada.
- **Proveedor abstraído** (`providers.py`): `RootCauseProvider` (seam) + `HeuristicRootCauseProvider`
  por defecto — **determinista, sin LLM, sin red ni costo** (placeholder honesto, confianza `low`). Un
  proveedor LLM real (con key + gateway de Mundo A) lo reemplaza sin tocar el pipeline, y sigue detrás
  del kill switch.
- **`ai_diagnosis.run_ai_diagnosis`**: rellena `root_cause_hypothesis`/`recommended_fix`/
  `recommended_tests`/`confidence`, marca `ai_assisted=True`, y **deja un `AIAgentRun`** (auditoría:
  invariante "toda corrida de IA deja AgentRun"). Es advisory: la decisión sigue siendo humana.
- **API**: `POST /api/diagnostics/diagnoses/<run_id>/ai-analyze/` (permiso `diagnostics.ai_diagnose.run`).
- **Degradable**: endpoint manual, jamás en la ruta crítica; offline-safe con el heurístico.

## `CodeUnitEvidence` — la línea de falla: ¿la línea que falló está testeada? (sin IA)

Cierra el *por qué*: una línea que falla y **no tiene test** es una causa probable y accionable.
- **No es 'log por línea'**: solo las líneas que importan (donde hay un `ErrorEvent`/`SecurityFinding`),
  anotadas con su **estado de cobertura** desde `coverage.xml` (`covered`/`uncovered`/`unknown`).
- **`coverage.py`** parsea el Cobertura XML que ya genera la suite y normaliza paths (`apps/…`) para
  matchear con `ErrorEvent.file_path`. **`ingest_code_evidence`** (command `ingest_code_evidence`) ata
  cada línea fallida a su cobertura + refs cruzadas.
- **Integrado al diagnóstico (B-3)**: el evidence bundle y el resumen ahora incluyen la cobertura de la
  línea; si está `uncovered` agregan la señal **`linea_sin_test`** ("la línea que falló NO está cubierta").
- **API**: `GET /api/diagnostics/code-evidence/` (permiso `diagnostics.error.read`).

## Fuera de estas rebanadas (siguientes)
SAST/bandit con dominio; proveedor LLM real para B-5 (key + presupuesto/observabilidad del gateway de
Mundo A; sigue apagado por defecto); símbolo/`last_commit` en `CodeUnitEvidence`; tenant-scoping fino;
OpenTelemetry/traces.
