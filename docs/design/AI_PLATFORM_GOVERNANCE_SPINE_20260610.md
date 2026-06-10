# Diseño — `ai_platform`: espina de gobernanza de IA (Mundo A)

> **Blueprint de ingeniería, no implementación.** Define el contrato, los invariantes, el modelo de
> datos, el ciclo de vida y los gates de la **espina** sobre la que colgará toda capacidad de IA de
> producto. Robustez = profundidad de esta espina, no cantidad de features.
> Fecha: 2026-06-10. Autor: Claude (backend). Relacionado: `docs/operacion/FACTIBILIDAD_IA_2026-06.md`.

## 0. Principio rector
```
La IA NUNCA es source of truth.
La IA OBSERVA y PROPONE; el dominio EJECUTA; el humano APRUEBA lo sensible;
la audit chain REGISTRA todo; los gates BLOQUEAN; nada C1 corre solo.
```
Si una sola de esas cláusulas no se puede garantizar para una capacidad, esa capacidad **no se
habilita**. La espina existe para hacer esas garantías **estructurales** (no dependientes de buena
voluntad del que programe la próxima feature).

---

## 1. Invariantes no negociables (lo que hace robusta a la espina)

| # | Invariante | Cómo se vuelve estructural |
|---|---|---|
| **I0** | **Botón de apagado global**: toda la IA se puede apagar | `flags.ai_features_enabled()` = `AI_FEATURES_ENABLED` (entorno, **off por defecto**) **Y** `AIControl` runtime (el "botón", apagable en caliente); el gateway lo chequea antes de cualquier llamada a modelo. **Ya implementado** en `apps.modulos.diagnostics` (B-2) |
| I1 | **Toda** corrida de IA produce un `AgentRun` persistido | El gateway es el ÚNICO punto de entrada; sin `AgentRun` abierto, no hay llamada a modelo |
| I2 | Toda acción con efecto produce `AuditEvent` **encadenado** | Reutiliza `audit/writer.py` (hash-chain HMAC ya existente) — `module="AI"` |
| I3 | **Cero autonomía C1**: dinero/stock/fiscal/permisos/CEC requieren `ApprovalRequest` + humano | Gate `ai-autonomy-guard` + `ToolPolicy.risk_class` + check en el bridge al dominio |
| I4 | La IA **no escribe en tablas core**: solo emite `AIActionProposal` → comando de dominio existente | El bridge sólo puede invocar *domain commands* allowlisted, nunca ORM directo |
| I5 | Aislamiento multiempresa duro | Todo registro lleva `org_unit_id`/`company_id`; el contexto se hereda del request, no lo elige la IA |
| I6 | **Degradable offline**: si no hay red/proveedor, la operación de negocio sigue | El gateway tiene timeout + fallback "sin IA"; la IA nunca está en la ruta crítica |
| I7 | Redacción PII antes de salir al proveedor | Guardrail de entrada obligatorio en el gateway (reusa `audit/redaction.py`) |
| I8 | Trazabilidad total | `correlation_id`/`causation_id` propagados desde el request hasta el `AuditEvent` |
| I9 | Presupuesto/costo acotado por tenant | `AIBudget` + corte duro cuando se excede (la corrida falla cerrada, no abierta) |
| I10 | Reproducibilidad | `PromptVersion` + `model_id` + `input_refs`/`output_refs` quedan en el `AgentRun` |

---

## 2. Escalera de autonomía (enforced, no decorativa)

```
L0 informativa     → responde/resume/explica. Permitida casi siempre. Sin escritura.
L1 analítica       → detecta/clasifica/correlaciona. Sólo lectura + AIObservation.
L2 borrador        → genera AIActionProposal. NO ejecuta. Humano confirma.
L3 ejecutor superv.→ invoca domain command vía tool, con ApprovalRequest aprobada (HITL).
L4 autónoma LOW    → sólo acciones LOW-risk explicitadas (nota interna, etiqueta no crítica).
L5 autónoma C1     → PROHIBIDA por diseño. No hay ruta de código que la permita.
```
El nivel máximo de una capacidad se declara en su `ToolDef.max_autonomy` y se **verifica en runtime**:
una `AIActionProposal` cuyo `risk_class=C1` nunca puede auto-promoverse a ejecución; el bridge exige
una `ApprovalRequest` en estado `GRANTED` emitida por un humano con el permiso correspondiente.

---

## 3. Modelo de datos (mínimo robusto — nuevo módulo `apps.modulos.ai_platform`)

> Todos los modelos: `org_unit`/`company_id` FK, `created_at`, `correlation_id`, `causation_id`.
> Cero modelos de más: estos 9 son la espina; las capacidades NO agregan tablas core, sólo `ToolDef`.

### `AIModelProvider` / `AIModel`
Catálogo de proveedores y modelos. `provider` (local/cloud), `endpoint`, `is_offline_capable`,
`status` (active/disabled), `cost_per_1k_in/out`. Permite **router** y abstracción (I6).

### `PromptVersion`
`prompt_id`, `version`, `owner_domain`, `risk_class`, `input_schema`(JSON), `output_schema`(JSON),
`model_id`, `approval_status`, `template_hash`. Inmutable una vez `approved` (I10).

### `ToolDef` (Tool Registry)
`code` (p.ej. `sales.quote.draft`), `kind` (read_only/draft/proposal/approved_action),
`required_permission` (código RBAC existente), `allowed_org_scope`, `max_autonomy` (L0–L4),
`risk_class` (C1/C2/C3), `idempotency_required` (bool), `domain_command` (allowlist del comando real
que puede invocar), `is_enabled`. **Una tool nunca toca ORM; sólo nombra un domain command.**

### `ToolPolicy`
Política por tool/rol/tenant: `approval_required` (bool), `daily_call_limit`, `rate_limit`,
`active`. Separada de `ToolDef` para poder endurecer sin redeploy.

### `AgentRun`  ← corazón (I1)
`run_id`, `agent_name`, `model_id`, `prompt_version`, `trigger_type`
(api/event/scheduled/manual), `input_refs`, `output_refs`, `status`
(started/completed/failed/blocked), `confidence_score`, `cost_estimate`, `latency_ms`,
`tokens_in/out`, `safety_flags`, `audit_event_id`, `actor_user`. **Lo abre el gateway, siempre.**

### `AIObservation` (L0/L1)
Hallazgo sin acción: `agent_run`, `subject_type`/`subject_id`, `domain`, `risk_class`, `summary`,
`evidence_refs`, `confidence_score`. Es lo que consume el copiloto read-only.

### `AIActionProposal` (L2/L3)
Borrador de acción: `agent_run`, `tool` (FK `ToolDef`), `proposed_command`, `proposed_payload`(JSON),
`risk_class`, `status` (draft/submitted/approved/rejected/executed/expired), `confidence_score`,
`evidence_refs`, `idempotency_key`. **Nunca ejecuta sola.**

### `ApprovalRequest` (HITL — I3)
`proposal`, `required_permission`, `requested_by`(=sistema/IA), `decided_by`(humano),
`decision` (granted/rejected), `reason`, `decided_at`. Para C1 exige `decided_by` ≠ null y permiso
segregado. Emite su propio `AuditEvent`.

### `AIBudget` (I9)
`org_unit`, `period`, `cap_amount`, `spent_amount`, `hard_stop` (bool). Excedido → `AgentRun` falla
cerrado.

---

## 4. Ciclo de vida de una acción (el camino feliz robusto)

```
request/evento entra (lleva correlation_id, company_id, branch_id, actor)
  └─> AIGateway.run(agent_name, prompt_version, inputs)
        ├─ abre AgentRun (status=started)            [I1]
        ├─ guardrail entrada: redacción PII + scope   [I5,I7]
        ├─ check AIBudget (hard_stop?)                [I9]
        ├─ llama AIModel (timeout + fallback offline) [I6]
        ├─ guardrail salida: valida output_schema     [I10]
        └─ persiste AgentRun (completed) + AuditEvent  [I2,I8]

  Si la corrida sólo OBSERVA  → AIObservation. FIN. (L0/L1)

  Si la corrida PROPONE acción → AIActionProposal (status=submitted). (L2)
        └─ ¿risk_class C1 o ToolPolicy.approval_required?
              SÍ → ApprovalRequest → espera decisión HUMANA      [I3]
                     granted → ejecutar │ rejected → fin auditado
              NO (sólo LOW/L4) → ejecutar
        └─ EJECUTAR = invocar el DOMAIN COMMAND allowlisted       [I4]
              (Sales/Billing/Inventory/Payments… aplican SUS invariantes)
              → el dominio emite su DomainEvent normal vía OutboxEvent
              → AuditEvent encadenado de la acción de IA           [I2]
```

**Clave:** la IA jamás crea `EconomicEvent`/`JournalDraft`/movimientos. Llama al comando del kernel
correspondiente, que ya valida idempotencia, periodo, balance, etc. La IA es un *cliente más* del
dominio, sujeto a las mismas reglas — pero con auditoría y aprobación reforzadas.

---

## 5. Enganche con el substrato YA existente (no se reinventa nada)

| Necesidad de la espina | Pieza existente que se reutiliza | Path |
|---|---|---|
| Audit encadenada/firmada | `audit/writer.py` + `AuditEvent` (hash-chain HMAC) | `apps/modulos/audit/` |
| Eventos / disparo async-cron | `integration.OutboxEvent`/`InboxEvent` + `dispatch_outbox` | `apps/modulos/integration/` |
| Permisos por tool | `rbac.Permission/Role/RolePermission` + `rbac_permission()` scopeado | `common/permissions.py`, `rbac/selectors.py:11` |
| Seed de permisos nuevos | patrón `seed_v01.py` (dict de codes + asignación a `company_admin`) | `rbac/seed_v01.py:287` (ej. `documents.scan.*`) |
| Redacción PII | `audit/redaction.py` | `apps/modulos/audit/redaction.py` |
| Cadencia de workers | management commands `run_*_cycle` (no Celery) | varios `management/commands/` |

**Permisos nuevos (mismo patrón que `documents.scan.*`):** `ai.run.read`, `ai.observation.read`,
`ai.proposal.read`, `ai.proposal.create`, `ai.proposal.approve` (segregado), `ai.tool.invoke`,
`ai.admin` (gestionar `ToolDef`/`ToolPolicy`/`PromptVersion`). `ai.proposal.approve` **no** se da por
defecto a `company_admin` para acciones C1: se asigna a un rol aprobador explícito (segregación de
funciones, ya que el repo tiene SoD en accounting/payments).

---

## 6. Clasificación de riesgo (mapea a la severidad que el repo ya usa)
```
C1  dinero · stock · fiscal/billing · contabilidad/GL · permisos/IAM · tenant · CEC · audit
C2  confiabilidad · trazabilidad · API/eventos · validación · reporting
C3  estilo · ergonomía · baja exposición
```
La `ToolDef.risk_class` y la `AIActionProposal.risk_class` usan esta misma escala. El gate de
autonomía bloquea cualquier ejecución C1 sin `ApprovalRequest` granted.

---

## 7. Gates deterministas que custodian la espina (extienden la batería actual)

- **`ai-autonomy-guard`** (nuevo, gate estático + test): ninguna `ToolDef` con `risk_class=C1` puede
  tener `max_autonomy >= L4`; ningún path de ejecución llega a un domain command C1 sin pasar por
  `ApprovalRequest.GRANTED`. Falla el build si se viola.
- **`ai-tool-command-allowlist-guard`**: toda `ToolDef.domain_command` debe existir en el registro de
  comandos allowlisted; prohíbe que una tool referencie ORM/escritura directa.
- **Reuso `qa-audit-integrity`**: los `AuditEvent` de `module="AI"` entran en la misma verificación
  de cadena.
- **Reuso `qa-contract-guards` de vistas**: las vistas de `ai_platform` declaran `permission_classes`
  con `rbac_permission(...)` en forma plana (como ya exige el scanner AST).
- **Reuso `qa-static-scan`**: prohíbe `NotImplementedError`/TODO → los stubs del gateway usan
  excepciones tipadas (`AIProviderUnavailableError`), no placeholders.
- **Reuso `migration-safety` + `architecture-dependency`**: el módulo nuevo declara sus aristas
  (`ai_platform → common`, `ai_platform → audit`, `ai_platform → integration`, `ai_platform → rbac`)
  en el baseline.

---

## 8. Cómo se agrega una capacidad nueva SIN tocar la espina (punto de extensión)
1. Registrar una `ToolDef` (code, kind, `required_permission`, `risk_class`, `max_autonomy`,
   `domain_command`).
2. Registrar su `PromptVersion` (con `output_schema`).
3. Sembrar el permiso RBAC y asignarlo al rol que corresponda.
4. (Si toca dominio) asegurarse de que el `domain_command` ya existe y está allowlisted.
5. Listo: el gateway, el ciclo de vida, la auditoría, los gates y el HITL aplican **solos**.

Esto es lo que hace que las "120 formas" del documento sean *incrementales y seguras* en vez de un
mega-proyecto: cada una es una `ToolDef` + `PromptVersion`, no una plataforma nueva.

---

## 9. Fuera de alcance / PROHIBIDO por diseño
- Autonomía **L5/C1** (no existe ruta de código).
- Tool que invoque ORM o escriba en tablas core directamente (I4).
- IA en la **ruta crítica** de una operación de negocio (I6).
- SQL libre generado por modelo contra producción.
- Microservicio IA separado: la espina vive **dentro del monolito modular**.
- Voz-realtime / edge-LLM / streaming: incompatibles con offline-first hoy (ver factibilidad).

---

## 10. Contrato de verificación (tests que prueban los invariantes)
- **I1:** toda llamada al gateway crea exactamente un `AgentRun`; una llamada que falla deja
  `AgentRun.status=failed` (no se pierde).
- **I2:** cada acción ejecutada deja un `AuditEvent` con `prev_event_hash` válido (cadena intacta).
- **I3:** intentar ejecutar una `AIActionProposal` C1 sin `ApprovalRequest.GRANTED` → rechazo +
  `AuditEvent` de intento; con approval de un humano sin el permiso segregado → rechazo.
- **I4:** una `ToolDef` con `domain_command` no allowlisted no puede registrarse (guard).
- **I5:** una corrida en company A no puede leer/observar objetos de company B.
- **I6:** con el proveedor caído, la operación de negocio asociada completa igual (fallback sin IA).
- **I9:** excedido el `AIBudget`, la corrida falla cerrada.
- Transversal: suite pytest completa + batería de guards en el contenedor Docker canónico; restaurar
  `qa/reports/` tras correr guards.

---

## 11. Rollout (cuando se decida construir — aditivo y reversible)
1. Módulo `ai_platform` registrado en `config/settings/base.py` + `config/urls.py` (patrón
   `documents`).
2. Migración inicial de los 9 modelos + entrada en `migration_safety_baseline.json`.
3. Gateway con **un solo proveedor stub local** (eco/determinista) → permite probar TODO el ciclo,
   auditoría y gates **sin LLM real ni costo**.
4. Una primera `ToolDef` L0 read-only (p.ej. explicar un reporte ya computado) como prueba de extremo
   a extremo.
5. Recién entonces, conectar un proveedor real detrás del gateway, con `AIBudget` activo.
6. Todo detrás de un flag de módulo (la empresa lo activa como cualquier otro módulo en `org`).

**Nada C1, nada autónomo, nada en ruta crítica en el rollout inicial.** La robustez se prueba con el
stub antes de gastar un solo token.
