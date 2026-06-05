# Necktral ERP_v2 — Paquete económico para Codex (corregido contra el código real)

> **Estado de este documento.** Reescritura del “Paquete avanzado para Codex” después de
> **verificar cada premisa contra el código** (no contra la documentación). Varias premisas del
> borrador original estaban desactualizadas y, de seguirse literalmente, habrían hecho que Codex
> construyera justo lo que el propio brief prohíbe (kernels duplicados, nombres de evento
> inventados). Las correcciones están abajo con evidencia `archivo:línea`.
>
> Complementa —no reemplaza— `docs/project/CODEX_OPERATING_BRIEF.md`,
> `NECKTRAL_CONTEXT_CARD.md`, `NECKTRAL_DECISION_LOG.md` y `NECKTRAL_MASTER_ROADMAP.md`.

---

## 0. Corrección de hechos (lo que el borrador asumía vs. lo que hay en el repo)

| Premisa del borrador | Realidad verificada | Evidencia | Consecuencia |
|---|---|---|---|
| Billing depende de `customer_name/customer_ref`; falta cliente fuerte Party | `BillingDocument.customer_party` (FK a `parties.Party`) **ya existe** con validación de company e índice; el service ya resuelve/valida la party | `apps/kernels/facturacion/models.py:292,407-409`; `services.py:192-205,301` | PR-1 se reduce a **enforcement + payload**, no “migrar a Party” |
| Falta proveedor fuerte basado en Party | `PurchaseDocument.supplier_party` (FK a `parties.Party`) **ya existe** con validación de company | `apps/modulos/compras/models.py:53-54,98-99` | PR-2 se reduce a **enforcement + payload** |
| Crear `kernels/receivables/` y `kernels/payables/` | **`kernels/portfolio/` ya es ese kernel**: `Obligation`→`Receivable`+`Payable`, `PaymentAllocation`; services `create_receivable`, `create_payable`, `allocate_payment_to_obligation`, `auto_allocate_payment`, crédito e interés; **ya emite outbox** | `apps/kernels/portfolio/models.py:49,334,415,796`; `services.py:47,225,492,637` | **Crítico**: crear nuevos kernels duplicaría portfolio (viola anti-patrón #7). PR-3/4/5 = **endurecer + cablear portfolio** |
| “Counterparty” como identidad canónica | Existe `Party` + `PartyRole`; **no hay clase `Counterparty`** | `apps/modulos/parties/models.py:19,94` | No inventar `Counterparty`; usar `Party`/`PartyRole` |
| Eventos `BILLING.DocumentIssued`, `PROCUREMENT.ProcurementDocumentPosted`, `PAYMENTS.PaymentCaptured`, `RECEIVABLE.*` | Convención real **mixta y sin esos prefijos**: billing core `DocumentDrafted/DocumentIssued/DocumentVoided`; fiscal `BILLING.Fiscal*`; compras `ProcurementDocumentDrafted/Posted/Voided`; payments `PaymentCaptured/PaymentRefunded/...`; portfolio ya tiene sus tipos | grep `event_type=` en cada `services.py` | Descubrir y **reusar los `event_type` reales**; no inventar prefijos |
| `make qa-run-profile PROFILE=pr`, `qa-ci-fresh` | ✅ Correcto (target existe, default `PROFILE:-pr`) | `Makefile:299-300,130` | Único bloque de QA del borrador que estaba bien |
| (No mencionado) | Ya existen guards de gobernanza: `qa-codex-governance-guard`, `qa-pr-blast-radius-guard`, `qa-architecture-dependency-guard`, `qa-route-contract-guard`, `qa-kernel-compat-strict`, `qa-audit-integrity`, `qa-makemigrations-check`, `qa-migration-safety-guard` | `Makefile:6` | Exigirlos por PR |
| (No mencionado) | Ya existe primitiva SoD `iam.ApprovalRequest` + `iam/approvals.py`, helper de auditoría `audit/service_audit.py::emit_service_event`, seed `rbac/seed_v01.py`, outbox `integration/services.py::publish_outbox_event`, inbox/handlers en `sync_engine` | — | **Reusar**; prohibido reimplementar audit/outbox/SoD |

**Regla derivada:** el gap real de la “columna vertebral económica” **no es “no existe”**, sino que
`portfolio` tiene **audit=0 y rbac=0** y **no está cableado por inbox** a billing/compras/payments; y
que billing/compras **no exigen** la Party fuerte que su modelo ya soporta.

---

## 1. Decisión de ejecución (sin cambios respecto al borrador: PRs secuenciales)

Mantener PRs cerrados, blast-radius controlado, **de menor a mayor**:

```text
PR-0  Auditoría real del economic spine (mapa de gaps, sin tocar código)
PR-1  Enforcement de customer_party en Billing (FK ya existe) + payload + snapshot
PR-2  Enforcement de supplier_party en Compras (FK ya existe) + payload + snapshot
PR-3  Endurecer portfolio CxC (audit+rbac) y cablear Billing -> portfolio (inbox)
PR-4  Endurecer portfolio CxP (audit+rbac) y cablear Compras -> portfolio (inbox)
PR-5  Payments allocation/settlement contra portfolio (reusar allocate_payment_to_obligation)
PR-6  CEC financial gates (cartera/pagos/drafts incompletos)
PR-7  Shadow Ledger completeness + reporting contador (trazabilidad documento->evento->draft)
```

> Diferencia clave con el borrador: **PR-3/4/5 NO crean kernels**. Endurecen y cablean `portfolio`,
> que ya posee `Receivable/Payable/PaymentAllocation` y servicios de aplicación de pagos.

---

## 2. Prompt maestro para Codex (endurecido)

Pegar como instrucción principal. Es el del borrador **más** las reglas que faltaban:

```text
Trabajá en el repositorio Necktral/ERP_v2. El remoto activo es `erp_v2`
(git@github.com:Necktral/ERP_v2.git); la rama de trabajo es `master` (la trackea).
El remoto `origin` (Necktral/Necktral) está ABANDONADO: no pushees ahí.

Rol:
Principal Engineer/Auditor de un ERP financiero-operativo modular. No improvisás
arquitectura, no hacés cambios cosméticos, no abrís dominios nuevos. Primero leés
código real, migraciones y tests. La documentación ORIENTA; el código, migraciones,
tests y CI MANDAN.

REGLA DE EPISTEMOLOGÍA (la más importante):
- Las afirmaciones de este brief son HIPÓTESIS, no hechos. Si el código las
  contradice, gana el código y lo reportás en PR-0 ANTES de implementar.
- Antes de crear cualquier modelo, kernel, servicio o evento, PROBÁ con grep que no
  exista ya. En particular: `portfolio` (Receivable/Payable/PaymentAllocation),
  `parties` (Party/PartyRole), `customer_party`, `supplier_party`, y el `event_type`
  exacto que pensás emitir.

REUTILIZACIÓN OBLIGATORIA (no reimplementar):
- SoD/maker-checker: apps/modulos/iam/approvals.py (+ iam.ApprovalRequest).
- Auditoría de servicio: apps/modulos/audit/service_audit.py::emit_service_event y
  apps/modulos/audit/writer.py::write_event; tipos nuevos en
  apps/modulos/audit/contracts.py::ALLOWED_EVENT_TYPES (+ subjects).
- RBAC: apps/modulos/rbac/seed_v01.py + common/permissions.py::rbac_permission.
- Outbox/inbox: apps/modulos/integration/services.py::publish_outbox_event y los
  handlers/registry de apps/modulos/sync_engine.
- Cartera: apps/kernels/portfolio (NO crear receivables/payables paralelos).

Objetivo activo (cerrar el circuito económico base):
Party fuerte -> Billing/Compras -> portfolio CxC/CxP -> Payments allocation/settlement
-> CEC financial gates -> Shadow Ledger -> Reporting contador.

Reglas no negociables:
1. No microservicios. No kernels duplicados (portfolio ya es cartera).
2. OrgUnit NO es cliente/proveedor/persona/empleado. Identidad de negocio = Party/PartyRole.
3. Billing emite documento; no posee cartera. Payments captura dinero; no inventa deuda.
   Inventory mueve stock/costo; no crea deuda. Compras genera obligación; portfolio (CxP)
   posee saldo. portfolio (CxC/CxP) posee saldos, movimientos y allocations.
4. CEC no corrige datos primarios; bloquea, evidencia y gobierna cierre.
5. Accounting no inventa hechos; consume eventos operativos (EconomicEvent->JournalDraft).
6. Todo C1 requiere AuditEvent, OutboxEvent, idempotencia, scope company/branch,
   transaction boundary, y path a EconomicEvent/JournalDraft o excepción explícita.
7. Eventos nuevos: registralos en ALLOWED_EVENT_TYPES y seguí la convención REAL ya
   presente (source_module + event_type, sin inventar prefijos). No rompas contratos
   sin compatibilidad/migración documentada.
8. No tocar UI salvo necesidad contractual. No features fuera del núcleo económico.
9. Cada PR incluye tests y los QA commands ejecutados (o por qué no).

Stop conditions (detenete y reportá ANTES de modificar):
- un modelo/servicio existente ya resuelve el objetivo (p.ej. portfolio.allocate_payment_to_obligation);
- migraciones divergentes/peligrosas; uso de OrgUnit como Party; eventos económicos
  duplicados; endpoints sin RBAC/scope; deuda que exige decisión arquitectónica;
  tests existentes que contradicen este brief.

Formato de respuesta obligatorio:
1. Files inspected  2. Current behavior proven from code  3. Gaps found
4. Proposed implementation  5. Files to change  6. Files forbidden to change
7. Migration strategy  8. Event/API contract impact  9. Shadow Ledger/Audit impact
10. Tests to add/update  11. QA commands  12. Residual risks  13. Definition of done
```

---

## 3. PR-0 — Auditoría real del economic spine (sin tocar código)

**Objetivo.** Producir el mapa de estado real. Las afirmaciones de §0 son el punto de partida, pero
Codex debe **confirmarlas o refutarlas** leyendo el código.

**Inspeccionar:** `parties/`, `iam/`, `rbac/`, `audit/`, `integration/`, `sync_engine/`,
`kernels/accounting/`, `kernels/facturacion/`, `kernels/payments/`, `kernels/portfolio/`,
`modulos/compras/`, `modulos/cec/`, `backend/src/tests/`, `qa/`, `Makefile`,
`docs/project/CODEX_OPERATING_BRIEF.md`.

**Búsquedas obligatorias:** `Party PartyRole customer_party supplier_party Obligation Receivable
Payable PaymentAllocation allocate_payment_to_obligation PaymentIntent PaymentCaptured CashSession
EconomicEvent JournalDraft OutboxEvent AuditEvent ALLOWED_EVENT_TYPES CloseRun CECException
idempotency company branch`.

**Entregable:** `docs/project/ECONOMIC_SPINE_AUDIT.md` (solo reporte) con:

| Área | Estado real | Gap real | Severidad | PR |
|---|---|---|---|---|
| Party/PartyRole | existe | ¿roles cliente/proveedor poblados? | C1 | PR-1/2 |
| Billing | `customer_party` FK existe; opcional | exigir en productivo + payload + snapshot | C1 | PR-1 |
| Compras | `supplier_party` FK existe; opcional | exigir + payload + snapshot | C1 | PR-2 |
| portfolio CxC | `Receivable` + outbox existen | **audit=0, rbac=0**, sin inbox desde Billing | C1 | PR-3 |
| portfolio CxP | `Payable` + outbox existen | **audit=0, rbac=0**, sin inbox desde Compras | C1 | PR-4 |
| Payments allocation | `portfolio.allocate_payment_to_obligation` existe | sin puente captura->allocation; estados settlement | C1 | PR-5 |
| CEC | `CloseRun`/`CECException` existen | sin gates de cartera/pago/draft | C1 | PR-6 |
| Accounting | EconomicEvent/JournalDraft/RuleSet existen | rule sets por evento nuevo | C1/C2 | PR-7 |

**Acceptance:** no cambia modelos/migraciones/lógica; evidencia por `archivo:función`; marca campos
opcionales que deben volverse obligatorios; identifica tests reusables y riesgos de migración.

---

## 4. PR-1 / PR-2 — Enforcement de Party fuerte (el FK ya existe)

**PR-1 Billing.** El modelo y el service ya soportan `customer_party`
(`facturacion/services.py::_load_customer_party`). Trabajo real:
- Exigir `customer_party` en documentos **productivos** (hoy es opcional/`None`); legacy textual solo
  permitido en import/migración controlada.
- Añadir snapshot fiscal (`customer_tax_id_snapshot`) y `customer_party_id` + snapshot al **payload**
  de los eventos reales `DocumentIssued`/`DocumentVoided` (no inventar prefijo).
- Invariante: `customer_party.company_id == doc.company_id` (ya validado en `models.py:407-409`); no
  cross-company; `customer_name` queda como snapshot, no verdad foránea.

**PR-2 Compras.** Idéntico recorte con `supplier_party` (ya en `compras/models.py:53-54`): enforcement
+ snapshot + `supplier_party_id` en el payload de `ProcurementDocumentPosted`/`...Voided`.

**Tests (ejemplos):** `requires_customer_party_for_new_document`, `rejects_party_from_other_company`,
`keeps_snapshot_after_party_rename`, `outbox_payload_includes_customer_party_id`,
`duplicate_retry_does_not_duplicate_economic_event`; análogos para supplier en Compras.

---

## 5. PR-3 / PR-4 — Endurecer y cablear `portfolio` (NO crear kernels)

**Estado:** `portfolio` ya tiene `Receivable`, `Payable`, `PaymentAllocation` y servicios
(`create_receivable`, `create_payable`, `allocate_payment_to_obligation`, `auto_allocate_payment`,
crédito/interés) que **ya emiten outbox**. Falta **audit, rbac y wiring por inbox**.

**PR-3 (CxC):**
- Auditoría: emitir `write_event`/`emit_service_event` en create/adjust/write-off/allocate de
  `Receivable` (tipos nuevos `PORTFOLIO_*` en `audit/contracts.py`; ya existe el reason_code
  `PORTFOLIO_OK`).
- RBAC: permisos `portfolio.receivable.*` en `rbac/seed_v01.py` + `rbac_permission` en endpoints.
- Wiring: handler de inbox que consuma el `DocumentIssued` real de Billing (venta a crédito/saldo) y
  llame `create_receivable` de portfolio, **idempotente por `source_event_id`** (reusar patrón
  `sync_engine`/`integration`). Sin mini-CxC en Billing.

**PR-4 (CxP):** análogo con `Payable`, consumiendo `ProcurementDocumentPosted` de Compras ->
`create_payable`; permisos `portfolio.payable.*`; auditoría idem.

**Invariantes C1:** no duplicar por reintento; no CxC/CxP sin `Party`; party/company coherentes;
`open_amount` no negativo; no aplicar pago > saldo salvo regla de overpayment explícita; no borrar
movimientos (reversar/compensar).

**Tests:** `billing_issued_creates_receivable`, `retry_does_not_duplicate`, `rejects_missing_party`,
`rejects_cross_company_party`, `partial_payment_updates_open_amount`, `full_payment_marks_paid`,
`void_with_payment_blocked_or_compensated`, `outbox_event_created`,
`audit_event_emitted_on_receivable_open`; análogos CxP.

---

## 6. PR-5 — Payments allocation/settlement (reusar portfolio)

Payments ya tiene `PaymentIntent`/`CashSession`/`CashMovement` con **auditoría, máquinas de estado y
SoD** (Unidad #3 hardening). Falta el puente captura→cartera y los estados de settlement.

- Al capturar un pago aplicable a cartera, aplicar contra obligaciones vía
  `portfolio.allocate_payment_to_obligation` (reusar `AllocationStatus`), respetando ownership:
  **payments captura, portfolio posee saldo**. Reversa de captura ⇒ compensar la allocation.
- Estados a distinguir: `CAPTURED` (operacional) vs aplicado (`UNAPPLIED/PARTIALLY_APPLIED/APPLIED`)
  vs conciliado (`RECONCILED`/`SETTLEMENT_*`). `TRANSFER` conserva su tratamiento contable específico;
  `CREDIT` (tender) **no** es dinero recibido ni financiamiento.
- Invariantes: no aplicar pago de un cliente a deuda de otro; respetar company/branch/party/currency;
  intercompany solo por flujo explícito.

**Tests:** `capture_creates_unapplied_state`, `apply_to_receivable_partial/full`,
`apply_rejects_cross_company/wrong_party`, `reversal_reverses_allocation`,
`transfer_capture_not_auto_reconciled`, `credit_tender_not_treated_as_cash`,
`allocation_idempotent_on_retry`, `allocation_outbox_created`,
`allocation_economic_event_or_exception_created`.

---

## 7. PR-6 — CEC financial gates

`CloseRun`/`CECException` existen (fingerprint por run/code/object). Falta que CEC **bloquee** cierre si
hay: documento Billing/Compras sin party; `Receivable/Payable` inconsistente; pago `CAPTURED` pero
`UNAPPLIED`; reversa de pago con allocation activa; `OutboxEvent` C1 fallido/no despachado;
`EconomicEvent`/`JournalDraft` faltante o en `EXCEPTION`; `CashSession` abierta; movimiento de
inventario económico sin linkage. Cada bloqueo crea/actualiza `CECException` idempotente (no muta
documentos primarios).

**Tests:** `blocks_close_when_*` (missing_party, payment_unapplied, receivable/payable_inconsistent,
economic_event_missing, journal_draft_exception), `does_not_mutate_primary_documents`,
`exception_fingerprint_idempotent`, `clean_close_passes`.

---

## 8. PR-7 — Shadow Ledger completeness + reporting contador

Accounting ya crea/recupera `EconomicEvent` desde `OutboxEvent`, elige `PostingRuleSet`, genera
`JournalDraft` y actualiza el payload del outbox (`accounting_status`, `economic_event_id`,
`journal_draft_id`, `journal_entry_id`). Trabajo: completar rule sets para los **event_type reales**
(`DocumentIssued/Voided`, `ProcurementDocumentPosted/Voided`, eventos `portfolio.*` de receivable/
payable/allocation, `PaymentCaptured/PaymentRefunded/PaymentCaptureReversed`, eventos de inventario) y
los reportes contador (ventas/cobros/pagos del período, aging CxC/CxP, pagos no aplicados, diferencias
caja/banco, drafts/excepciones, trazabilidad documento→outbox→economic_event→draft→evidencia).
Reporting **no** posee verdad primaria: consume kernels.

**Tests:** `sales_trace_to_billing_and_economic_event`, `receivables/payables_aging_matches_documents`,
`unapplied_payments_list`, `journal_drafts_exceptions_list`,
`traceability_document_to_outbox_to_economic_event_to_draft`, `cross_company_isolation`.

---

## 9. QA por PR (comandos reales)

```text
# Suite + gates estáticos (perfil PR):
make qa-run-profile PROFILE=pr
make qa-ci-fresh

# Gates que deben quedar verdes en lo tocado (existen en el Makefile):
make qa-backend-ruff qa-backend-mypy qa-makemigrations-check qa-migration-safety-guard \
     qa-architecture-dependency-guard qa-route-contract-guard qa-kernel-compat-strict \
     qa-audit-integrity qa-pr-blast-radius-guard qa-codex-governance-guard

# Tests dentro de Docker (rápido, reusando slot):
docker compose -f compose.yaml exec -T backend bash -lc \
 "cd /app/backend && export DJANGO_SETTINGS_MODULE=config.settings.test \
  PYTEST_DB_BASE_NAME=test_erp_db PYTEST_DB_SLOT=devloop; pytest --reuse-db -p no:cacheprovider"
# (usar --create-db la primera corrida tras una migración nueva)

# Cuando toque migraciones, además:
make qa-run-profile PROFILE=release
```

Higiene de git: `git add` con rutas explícitas + `git diff --cached --stat` antes de commitear; push
`git push erp_v2 master`.

---

## 10. Definition of Done global (corregida)

```text
1. BillingDocument productivo nuevo exige customer_party (FK ya existe); legacy = snapshot.
2. Documento de compra nuevo exige supplier_party (FK ya existe); legacy = snapshot.
3. portfolio (CxC/CxP) endurecido: audit + rbac, y cableado por inbox desde Billing/Compras.
   NO se crearon kernels receivables/payables nuevos.
4. Payments aplica capturas contra portfolio (allocate_payment_to_obligation) con estados
   CAPTURED/UNAPPLIED/APPLIED/REVERSED/RECONCILED; CREDIT no es dinero; TRANSFER conserva su trato.
5. Todo movimiento de cartera/pago: OutboxEvent + AuditEvent + idempotencia + scope.
6. Todo evento económico C1: EconomicEvent + JournalDraft o excepción CEC explícita.
7. CEC bloquea cierres con cartera/pagos/drafts incompletos sin mutar datos primarios.
8. Reporting explica cada cifra con trazabilidad documento->evento->draft->evidencia.
9. QA PR/release verde; eventos nuevos en ALLOWED_EVENT_TYPES con la convención real.
10. Cero uso de OrgUnit como Party. Cero kernels duplicados.
```

---

## 11. Errores del borrador a NO repetir (resumen para el revisor humano)

1. Afirmar gaps como hechos sin verificar → degradar a hipótesis (PR-0 manda).
2. “Crear receivables/payables” → **endurecer/cablear `portfolio`** (ya existe con allocation).
3. Inventar `Counterparty` y prefijos de evento (`BILLING.`, `RECEIVABLE.`) → usar `Party`/`PartyRole`
   y los `event_type` reales.
4. Ignorar la infra ya construida (iam.approvals, audit.service_audit, rbac.seed_v01, sync_engine,
   y los guards `qa-codex-governance-guard`/`qa-pr-blast-radius-guard`) → exigir su reutilización.
5. Tratar PR-1/PR-2 como migración de identidad → es **enforcement + payload** (el FK ya está).
