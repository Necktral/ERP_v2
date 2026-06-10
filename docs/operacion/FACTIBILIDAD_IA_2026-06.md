# Factibilidad de los 2 sistemas de IA propuestos para ERP_v2

> Documento de **decisión** (no es plan de construcción). Analiza la implementación y la
> verdadera factibilidad de dos propuestas de IA contra el estado **real** del código.
> Fecha: 2026-06-10. Autor: Claude (backend). Estado: **solo análisis** — no se construye nada aún.

## Las dos propuestas

- **Sistema 1 — "IA en el ERP":** plataforma IA transversal gobernada (AI Gateway, Tool Registry,
  RAG, `AgentRun`, `ApprovalRequest`, `DecisionProduct`, `ModelEvaluation`) + catálogo de 120 formas
  de usar IA + 11 topologías + 6 niveles de autonomía + mapa por módulo + 8 fases.
- **Sistema 2 — "IA de observabilidad/seguridad/diagnóstico":** telemetría estructurada + Error
  Intelligence + Security Intelligence + Line Evidence Map + Reachability + AI Diagnostic Engine +
  gates deterministas + 7 fases.

---

## Hallazgo central: substrato REAL vs lo que los docs asumen

### Ya existe en ERP_v2 (verificado en código) — el substrato es inusualmente favorable
- **Backbone de eventos:** `integration.OutboxEvent` / `InboxEvent` (source_module, event_type,
  payload JSON, status, retry) + `dispatch_outbox` y ~15 comandos `run_*_cycle`. Es el bus
  event-driven que ambos docs asumen.
- **Audit hash-chain append-only:** `audit.AuditEvent` con `prev_event_hash`/`event_hash`/`signature`
  (HMAC), actor, device, snapshots, metadata, verificado por `qa-audit-integrity`. Es la "AI audit
  chain" — **ya construida**.
- **Logging estructurado JSON:** `config/logging_utils.py` (`JsonFormatter` + `RequestIdFilter`) ya
  emite `request_id`, `company_id`, `branch_id`, `device_id`, `status_code`, `duration_ms`,
  `audit_event_id`. Es la Fase 2 del Sistema 2 a medio hacer.
- **Security findings con excepciones y vencimiento:** `qa/contracts/security_exceptions.json`,
  `enforce_security_findings.py`, `validate_security_exceptions.py`; importers de
  bandit/pip-audit/npm-audit/ruff/mypy ya corren en el Makefile. Es la "Security Intelligence" con
  C1/C2/C3 + expiry, parcialmente viva.
- **Gates deterministas:** coverage-por-dominio, route/architecture/migration guards. El "gates
  bloquean / IA diagnostica / humano decide" del Sistema 2 **ya es como opera el repo**.
- **Kernels = fuente de verdad:** `EconomicEvent`/`JournalDraft`/Shadow Ledger/CEC/Billing/Inventory/
  Payments. La invariante "la IA no es source of truth" es **arquitectónicamente exigible hoy**.
- **IDP F1 (`documents`):** captura+OCR+revisión ya en master (es el #9/#10 del doc 1).
- **RBAC scopeado + ACL:** substrato de permisos para un futuro Tool Registry.

### NO existe (pese a que el doc 1 afirma "tu diccionario ya contempla…")
- **`AgentRun`, `DecisionProduct`, `ModelEvaluation`, `PromptVersion`, `ToolDef`, `ToolPolicy`,
  `ApprovalRequest`, `AIObservation`, `AIActionProposal`** → **0 como código** (solo en
  `docs/archive/`). La afirmación de que "ya se contemplan" es **aspiracional, no real**.
- **Sin LLM client** (no openai/anthropic en requirements), **sin AI Gateway**, **sin RAG**,
  **sin pgvector/embeddings**.
- **Sin runner async** (no Celery/RQ): solo management commands estilo cron → **techo de cadencia =
  batch/cron**, no realtime.
- **Sin OpenTelemetry / traces / `trace_id` / `correlation_id` / `causation_id` / `stack_hash`** en
  el logging.
- **`ErrorEvent`, `SecurityFinding`, `CodeLineEvidence`, `ReachabilityAssessment`, `DiagnosticRun`,
  `AIDiagnosis`** → no son modelos persistidos; los findings hoy son JSON desechable + guards, no un
  ledger consultable.

---

## Restricciones que ACOTAN la factibilidad (válidas para ambos)
1. **Offline-first** (DB local + Drive + sync) es el determinante #1: una llamada a LLM cloud exige
   conectividad → la IA debe ser **mejora degradable, nunca en la ruta crítica**. Vuelve poco
   prácticos a corto plazo: voz realtime en POS, LLM en edge, streaming. RAG/embeddings locales
   (pgvector) sí caben; modelos grandes en sucursal no.
2. **Throughput de 1 dev backend + Codex ejecutor.** Doc 1 (120 usos × 8 fases) + Doc 2 (7 fases) =
   18–36 meses. **Como entregable único es inviable**; construirlos "completos" estancaría todo lo
   demás.
3. **Sin infra async** → cadencia cron/comando (suficiente para offline-first, pero limita realtime).
4. **Costo LLM + aislamiento multiempresa:** budgets/caps por tenant + redacción PII antes de tocar
   datos reales. Para **un solo holding** el costo es manejable pero no nulo.

---

## Veredicto por sistema

### Sistema 1 (IA transversal)
- **Como plataforma completa: NO factible** a corto/medio plazo (2–3 años). Tratarlo como un bloque
  es el error.
- **Como rebanada delgada gobernada: muy factible** — el substrato está más listo de lo normal
  (outbox + audit chain + RBAC scopes + kernels-como-verdad + IDP F1). Su propio veredicto acierta:
  read-only + extracción documental primero, drafts/tools con aprobación, **nada C1 autónomo**.
- **Corrección honesta al doc:** sobreestima lo que ya existe (las entidades AI no están) y subestima
  offline-first + throughput.

### Sistema 2 (observabilidad/diagnóstico)
- **MÁS factible que el Sistema 1**: ~60% del substrato ya existe (logging JSON, audit hash-chain,
  security-findings con expiry, coverage-por-dominio, batería de gates).
- **Lo que falta y vale construir (backend puro, SIN LLM en Fases 1–4):** persistir
  `ErrorEvent`/`SecurityFinding` como filas consultables; añadir
  `correlation_id`/`causation_id`/`domain`/`stack_hash` al logging + handler central; mapa
  path→dominio.
- **No factible/baja confianza:** **Reachability** real exige call-graph → asistido-manual, no
  automatizado. El **AI Diagnostic Engine** es la única parte LLM-dependiente → advisory, diferible
  offline.

---

## Son DOS MUNDOS DISTINTOS — hacen cosas diferentes
No son un solo proyecto ni se secuencian uno-antes-del-otro. Difieren en **público, dueño, ciclo de
vida y cuándo pagan**:

| | **Mundo A — Sistema 1** | **Mundo B — Sistema 2** |
|---|---|---|
| Qué hace | Capacidad de **producto/negocio**: IA cara al usuario que ayuda a operar (documentos, ventas, cobranza, CEC, reportes) | Capacidad de **ingeniería/plataforma**: observabilidad, seguridad y diagnóstico interno |
| Público | Usuarios del ERP / dueño | Equipo de desarrollo / seguridad |
| Roadmap lo manda | El valor operativo | La confiabilidad / hardening |

**Matiz técnico:** comparten primitivas de **bajo nivel** que ya existen (audit hash-chain, gates,
evidencia, `confidence_score`, revisión humana). Eso permite **reutilizar** esas bases en ambos, pero
**no los funde** en una sola plataforma ni en una sola cola de trabajo. Cada mundo en su propia pista.

---

## Pistas independientes (cada mundo con su orden — NO compiten por el "primer slice")

### Pista A — IA de producto (Sistema 1)
1. **IDP F2 — extracción de campos** sobre lo que F1 ya captura (backend puro, validación
   determinista + revisión humana). Valor inmediato sobre lo landeado.
2. **Esqueleto `ai_platform`** (gobernanza): `AgentRun`/`ApprovalRequest`/`AIObservation` + gateway
   con proveedor abstraído, cableado a outbox + audit chain. L0–L2, **cero C1 autónomo**.
3. *(Diferido)* copiloto read-only sobre reporting/CEC → RAG local (pgvector) → drafts con aprobación.

### Pista B — Plataforma de diagnóstico (Sistema 2)
1. **Ledger de evidencia (Fases 1–4, sin LLM):** persistir `ErrorEvent`/`SecurityFinding` (los
   importers YA corren), `correlation_id`/`causation_id`/`domain`/`stack_hash` en logging + handler
   central, mapa path→dominio.
2. **Gates C1 sobre el ledger:** "finding/ErrorEvent C1 abierto bloquea release" — extensión natural
   de los guards actuales.
3. *(Diferido)* AI Diagnostic Engine **advisory** (degradable offline). Reachability = asistida-manual.

---

## Lo que NO se construiría ahora (premature / fuera de factibilidad)
- Agente de voz realtime, edge LLM, streaming, computer-use/RPA en portales (doc1 #12/#60/#63/#98).
- Cualquier autonomía **L4/L5** o tool que toque dinero/stock/fiscal/permisos sin HITL.
- Microservicio IA separado (doc1 topología 2): el monolito modular con `ai_platform` basta.
- Reachability automatizada y fine-tuning/distillation: diferidos.

---

## Decisión
- **Estado:** solo análisis. **No se construye nada todavía.** La elección de construir (Pista A o B)
  queda como decisión futura del usuario, **mundo por mundo**.
- Cuando se decida arrancar un mundo, el primer slice de cada pista ya está identificado arriba y es
  backend-puro sin LLM en la ruta crítica.
