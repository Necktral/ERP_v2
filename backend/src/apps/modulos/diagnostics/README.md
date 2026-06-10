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

## Fuera de estas rebanadas (siguientes)
SAST/bandit con dominio (B-2b), `CodeUnitEvidence` (B-3), gates `evidence-c1-guard`/`regression-sentinel`
(B-4), diagnóstico IA **advisory** que consume el gateway de Mundo A y respeta el kill switch (B-5);
tenant-scoping fino del read API; OpenTelemetry/traces.
