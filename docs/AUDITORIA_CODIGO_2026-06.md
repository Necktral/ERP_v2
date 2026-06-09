# Auditoría de Código — Necktral ERP_v2 (2026-06)

> **Informe vivo.** Pasada de calidad línea-por-línea: huecos, bugs e inconsistencias.
> **Modo: informe primero** — aquí se registran los hallazgos; las correcciones van en una pasada posterior (con tests, verde, commits atómicos).
> **Suplanta** los análisis del 2026-05 (`ANALISIS_PROBLEMAS_CRITICOS_ALTOS.md`, `MATRIZ_PROBLEMAS_BLOQUES.md`, `REPORTE_FINAL_ANALISIS_PROFUNDO.md`, `INVENTARIO_ANALISIS_INICIAL.md`, `inventario_bloques_codigo.md`), enfocados en sync docs↔código.

## Metodología
Lectura de cada `.py` (services/models/views/serializers/urls/handlers/alerts) buscando:
- **Huecos:** validación faltante; casos no manejados (None/vacío/negativo/límite); idempotencia ausente donde hay efectos; falta `transaction.atomic`; auditoría/RBAC faltante; falta scope company/branch (fuga entre empresas, cada una con RUC propio); código muerto.
- **Bugs:** tipo equivocado (float en dinero, str vs Decimal, UUID vs PK entero); off-by-one; mapeo HTTP de error incorrecto; `except Exception` que traga fallos; orden de operaciones; carrera; recompute incorrecto.
- **Inconsistencias:** naming divergente; patrón distinto al vecino; contrato declarado-vs-usado (audit/RBAC/edges); doc↔código drift; serializer/migración vs modelo.

**Severidad:** `CRÍTICO` (dinero/seguridad/corrupción/scope-leak) · `ALTO` (bug real, impacto acotado) · `MEDIO` (inconsistencia/robustez) · `BAJO` (estilo/doc/deuda).

**Nota global positiva:** el backend está disciplinado — cero `TODO/FIXME/bare-except/print`; los `float()` son métricas de latencia (no dinero); sin `NotImplementedError`. Los defectos son **lógicos/sutiles**.

---

## ✅ Estado de corrección (2026-06-09) — TODOS RESUELTOS

Los 23 hallazgos fueron **corregidos con tests, verde, en commits atómicos**, cada uno en la rama de su módulo (pusheadas a `erp_v2`):

| Rama | Hallazgos resueltos |
|---|---|
| `fix/auditoria-mainline` (off master; **suite completo verde**) | **NM-01** (IR recalcula con flag `ir_manual`+migración), NM-02 (subsidio por tramos), NM-03 (other_income al neto), NM-04 (idempotencia posteo/aprobación), NM-05 (tope de pago), NM-06 (`abono_applied`+migración), NM-07 (costo desde devengado), **INV-01** (lote en salida + FEFO), INV-02 (avg en stock negativo), P-01 (lock obligación), P-02 (COMPOUND real), P-03 (base de interés), P-04 (comentario waterfall), P-05 (auditoría write-off/adjust), IAM-01/02/03 (scope multiempresa), RBAC-01 (`permission.is_active`). SUP-01 verificado (redaction ya cubre `*password*`). |
| `feat/finca-sync` | **F-01** (idempotency_key requerido), F-02 (idempotente por finca/season), F-03 (`_company_of`), F-04 (doc real_labor_cost), F-05 (FINCA_OK), F-06 (logging). F-07 nota perf. |
| `feat/comisariato-credito` | **C-01** (credit_limit NULL/0/>0 +migración), C-02 (saldo por moneda). |
| `feat/fleet-fase-b` | FL-01 (lectura decreciente), FL-02 (horómetro+umbrales), FL-03 (no resetea is_due), **N-01** (FCM HTTP v1 + OAuth2 SA), N-02 (cursor). |
| `feat/intercompany-ops` | I-01 (documentado posteo POSTED directo, decisión deliberada). |

**Observacionales documentados (decisión, no bug):** AC-01 (auto-post operacional con SoD en la capa de origen, espejado por I-01), RBAC-02 (superuser sin auto-grant en la ruta scoped, por aislamiento por tenant), AUD-01 (contención del head de cadena, aceptable a la escala actual).

Verificación: cada rama corre verde su suite (mainline = **suite completo**; batch-1 = full-suite de las 4 ramas, 100%). Las correcciones añadieron tests que reproducen cada bug.

---

## Matriz resumen (parcial — batch 1: módulos frescos)

| Módulo | CRÍTICO | ALTO | MEDIO | BAJO |
|---|:---:|:---:|:---:|:---:|
| finca | 0 | 2 | 2 | 3 |
| comisariato | 0 | 1 | 1 | 0 |
| fleet | 0 | 0 | 2 | 1 |
| notifications | 0 | 1 | 1 | 0 |
| intercompany | 0 | 0 | 1 | 0 |

---

## finca (`apps/modulos/finca`)

| ID | Sev | Ubicación | Tipo | Descripción | Fix sugerido |
|---|---|---|---|---|---|
| F-01 | **ALTO** | `inventory_link.py:32,41` | bug/hueco | `issue_insumo_from_stock` tiene `idempotency_key=""` por defecto; si el caller no lo pasa, `post_issue` NO es idempotente → **doble descuento de stock + `InsumoApplication` duplicada** al reintentar. | Exigir `idempotency_key` no vacío o derivarlo de `work_order.id+item_id` / `command_id`. |
| F-02 | **ALTO** | `accounting_link.py:22` | hueco | `post_finca_cost_to_accounting` **no es idempotente**: re-ejecutarlo para la misma finca/temporada emite otro `FincaCostAccrued` → **doble asiento de reclasificación** del costo por finca. | Idempotencia por `(finca, season)`/reference; o verificar outbox existente. |
| F-03 | MEDIO | `accounting_link.py:26` | inconsistencia | `company = getattr(finca,"parent",None)` sin validar `unit_type==COMPANY`; `field_link._company_of` SÍ valida. Si la jerarquía difiere, postea con company equivocada. | Reusar `_company_of(finca)`. |
| F-04 | MEDIO | `field_link.py:104` | inconsistencia | `real_labor_cost = jornales × labor.default_rate` (tarifa de **catálogo**, no el salario real de planilla); el nombre "real" induce a error y es la base del asiento de reclasificación. | Renombrar/documentar ("asistencia real valuada a tarifa estándar"); evaluar si debe usar costo de planilla real. |
| F-05 | BAJO | `services.py` + links (pervasivo) | inconsistencia | Todos los `write_event` de finca usan `reason_code="OK"` (legacy/compat) en vez de un código por módulo (`FINCA_OK`), distinto del patrón de los módulos nuevos. | Estandarizar a `FINCA_OK`. |
| F-06 | BAJO | `accounting_link.py:75` | robustez | El `except` best-effort no loguea (solo `link_status=FAILED` en metadata); fallos de posting quedan poco visibles. | `logger.exception(...)` como en billing/intercompany. |
| F-07 | BAJO | `field_link.py:206`, `services.py:236` | performance | `company_real_cost_summary`/`company_cost_summary` hacen O(N) queries por finca (aceptable para pocas fincas). | Agregar en query si crece el nº de fincas. |

---

## comisariato (`apps/modulos/comisariato`)

| ID | Sev | Ubicación | Tipo | Descripción | Fix sugerido |
|---|---|---|---|---|---|
| C-01 | **ALTO** | `services.py` `available_credit` | hueco/política | `credit_limit==0` se trata como **"sin tope" (crédito ilimitado)**. Un cliente PUBLIC/sin límite asignado (default 0) obtiene crédito **ilimitado** → riesgo operativo real. | Distinguir "sin límite" (None explícito) de `0`="sin crédito"; o política/segmento con default seguro. |
| C-02 | MEDIO | `services.py` `outstanding_balance` | bug | Suma `outstanding_amount` de TODAS las CxC abiertas **sin filtrar moneda**; mezcla NIO+USD si las hubiera. | Filtrar/normalizar por `currency` (o por la moneda de la venta). |

---

## fleet (`apps/modulos/fleet`)

| ID | Sev | Ubicación | Tipo | Descripción | Fix sugerido |
|---|---|---|---|---|---|
| FL-01 | MEDIO | `services.py` `record_meter_reading` | hueco | Una lectura **decreciente** (odómetro/horómetro < actual) se descarta en silencio con `verified=True`; no se marca sospechosa. | `verified=False` y/o registrar la lectura rechazada. |
| FL-02 | BAJO | `services.py` `record_meter_reading` | inconsistencia | La guarda de salto `>500` aplica solo a odómetro, no a horómetro; umbral hardcodeado. | Guardar también horómetro; umbral configurable por settings/activo. |
| FL-03 | MEDIO | `services.py` `apply_plan_to_asset` | bug | `update_or_create(defaults={"is_due":False,...})` **resetea** el flag: re-aplicar un plan **oculta un mantenimiento ya marcado vencido**. | No tocar `is_due/last_flagged_at` si el estado ya existe. |

---

## notifications (`apps/modulos/notifications`)

| ID | Sev | Ubicación | Tipo | Descripción | Fix sugerido |
|---|---|---|---|---|---|
| N-01 | **ALTO** (al activar) | `senders.py` `_fcm_post` | bug | Usa la **API FCM legacy** (`/fcm/send`, `Authorization: key=`), **descontinuada por Google (2024)**. Al activar FCM (Fase B.2) NO funcionará. | Migrar a **FCM HTTP v1** (`/v1/projects/{id}/messages:send`) con OAuth2 de service account. |
| N-02 | MEDIO | `services.py` `dispatch_fleet_notifications` | performance | Escanea **todos** los `OutboxEvent` FLEET en cada corrida (sin cota por cursor/tiempo). Idempotente (vía `InboxEvent`) pero O(n) creciente. | Filtrar los aún sin `InboxEvent(consumer="notifications")`, o cursor por id/tiempo. |

---

## intercompany (`apps/modulos/intercompany`)

| ID | Sev | Ubicación | Tipo | Descripción | Fix sugerido |
|---|---|---|---|---|---|
| I-01 | MEDIO | `services.py` `_post_balanced_entry` | inconsistencia | Crea `JournalEntry` directamente en estado **POSTED**, sin pasar por el poster con SoD (`post_journal_drafts`). Es intencional (espeja el test probado) pero inconsistente con el camino normal de posteo. | Documentar la excepción; evaluar si debe pasar por el flujo SoD/draft. |

---

## Matriz resumen (batch 2: kernels económicos)

| Kernel | CRÍTICO | ALTO | MEDIO | BAJO | Nota |
|---|:---:|:---:|:---:|:---:|---|
| nomina | 0 | 1 | 5 | 1 | recompute de IR + idempotencia/conciliación |
| portfolio | 0 | 0 | 5 | 0 | concurrencia + interés COMPOUND + auditoría write-off |
| accounting | 0 | 0 | 1 | 0 | **el kernel más robusto**: idempotente por `outbox_event_id`, `select_for_update` + SoD en approve/post/close/reverse |
| facturacion | 0 | 0 | 0 | 0 | maduro: `idempotency_key` + lock + idempotencia por línea; issue en una sola txn |
| inventarios | 0 | 1 | 0 | 1 | trazabilidad de lote rota en salida |
| payments | 0 | 0 | 0 | 0 | maduro: idempotente en create/capture/reverse con detección de conflicto |
| reporting | 0 | 0 | 0 | 0 | read-only/observabilidad; `float()` = métricas de latencia, no dinero |

---

## nomina (`apps/kernels/nomina`)

| ID | Sev | Ubicación | Tipo | Descripción | Fix sugerido |
|---|---|---|---|---|---|
| NM-01 | **ALTO** | `models.py:735` | bug | `compute_all`: `if config and not self.ir_amount:` → el IR **solo se calcula si está en 0**. En cualquier recompute (`apply_field_attendance_to_entry`, `classify_entries_by_inss` al mover CON/SIN INSS, cambio de días/salario) el IR **queda obsoleto** con el valor viejo, aunque la base gravable cambió → `total_deductions`/`net_to_pay` mal. Confunde "ya calculado" con "override manual" (no hay flag de override). | Recalcular siempre IR; si se quiere permitir override manual, usar un flag explícito `ir_manual`. |
| NM-02 | MEDIO | `models.py:693-700` | hueco | Subsidio INSS: el comentario dice "empresa paga 100% días 1-N, INSS 60% desde N+1", pero `subsidy_amount = rate·días·subsidy_inss_rate` aplica **60% a TODOS los días**; `DEFAULT_SUBSIDY_EMPLOYER_DAYS`/`subsidy_employer_days` **no se usa** en `compute_all`. Subestima el subsidio de los primeros días. | Implementar el tramo patronal (primeros N días al 100%) o eliminar el campo/parámetro si no aplica. |
| NM-03 | MEDIO | `models.py:726-759` | bug/semántica | `other_income` entra a `total_income` (línea 726) pero **no** a `total_devengado` (755) ni a `net_to_pay` → si "otros ingresos" es efectivo (bono/viático), **no se le paga al trabajador**. | Definir si `other_income` es efectivo; si lo es, sumarlo a `total_devengado`. |
| NM-04 | MEDIO | `accounting_link.py:23` + `period_sod.py:47` | hueco | `post_payroll_period_to_accounting` **no es idempotente** (emite outbox nuevo cada vez) y `approve_period` **no re-valida** `period.status ∈ _APPROVABLE_STATES` antes de postear. Una 2ª `ApprovalRequest` del mismo período (permitido en DRAFT) ⇒ **doble asiento/outbox** de planilla. *(El kernel de contabilidad es idempotente por `outbox_event_id`, así que el control debe estar AQUÍ.)* | Guardar el estado (rechazar si ya APPROVED/posteado) e idempotencia por `(period_id)` antes de emitir. |
| NM-05 | MEDIO | `payroll_payments.py:36` | hueco | `register_payroll_payment` no topa el monto contra el **neto restante** ni es idempotente → puede registrar pagos que **exceden** `net_to_pay` o un pago duplicado por reintento. | Validar `amount ≤ neto - pagado`; idempotencia por `reference`/clave. |
| NM-06 | MEDIO | `portfolio_link.py:76-80` | inconsistencia | El abono a portfolio es best-effort **fuera de la txn**: si falla, el `PayrollLoanDeduction` queda registrado (al trabajador **ya se le descontó**) pero el crédito **no se abona** → brecha de conciliación silenciosa (devuelve `applied=None`, fácil de ignorar). | Cola de reintento / marcar la deducción como "abono pendiente" y reconciliar. |
| NM-07 | BAJO | `models.py:775` | inconsistencia | `total_payroll_cost = net_to_pay + total_employer_cost`: las **retenciones de ley** (INSS laboral + IR) que la empresa remite a terceros no entran al costo → **subestima** el costo patronal real (debería partir de `total_devengado`, no del neto). | Revisar la fórmula del costo patronal total. |

---

## portfolio (`apps/kernels/portfolio`)

| ID | Sev | Ubicación | Tipo | Descripción | Fix sugerido |
|---|---|---|---|---|---|
| P-01 | MEDIO | `services.py:738,792-806`; `851-877` | bug/carrera | `allocate_payment_to_obligation` y `apply_payroll_abono` leen `outstanding_amount`, luego hacen `obligation.allocated_amount += …; obligation.save()` **sin `select_for_update()`** sobre la obligación. Dos aplicaciones concurrentes (auto + manual) ⇒ **lost update / over-allocation** (saldo aplicado > total). | `Obligation.objects.select_for_update()` dentro de la txn antes de actualizar el saldo. |
| P-02 | MEDIO | `services.py:998-1002` | bug | `accrue_interest_for_credit`: la rama **COMPOUND** calcula `P·daily_rate·días` (interés **simple/lineal**), idéntica a SIMPLE; el comentario promete `P·((1+r)^t−1)`. **Subcobra** interés en créditos COMPOUND. | Implementar el compuesto real o documentar que solo se soporta SIMPLE. |
| P-03 | MEDIO | `services.py:987` | bug | `principal_balance = disbursed_amount − allocated_amount`: `allocated_amount` incluye lo aplicado a **interés/fees/penalty**, no solo a principal → la **base del interés queda subestimada**. | Usar `disbursed − Σprincipal_applied` (componente principal). |
| P-04 | MEDIO | `services.py:758-767` | inconsistencia | El comentario del waterfall dice "aplicar a **principal primero**, luego interés…", pero el código aplica **penalty → interés → fee → principal** (orden inverso, que es el contable correcto). Comentario **engañoso** sobre el orden de aplicación del dinero. | Corregir el comentario (el código es el correcto). |
| P-05 | MEDIO | `services.py:248-342` | hueco | `write_off_receivable` y `adjust_receivable` **no escriben evento de auditoría** (`write_event`), a diferencia de `create_receivable`/`allocate` (que sí cumplen la invariante #4). El **write-off** (declarar incobrable) es una acción sensible sin rastro de auditoría de servicio. | Añadir `_write_portfolio_audit_event` a write-off y adjust. |

---

## accounting (`apps/kernels/accounting`)

| ID | Sev | Ubicación | Tipo | Descripción | Fix sugerido |
|---|---|---|---|---|---|
| AC-01 | MEDIO (obs.) | `services.py:2255-2312`, `714-721` | inconsistencia | Dos caminos saltan el maker-checker del GL **por diseño**: (1) `post_journal_drafts` con el default `require_approved=False` postea drafts `VALIDATED` sin paso de aprobación (el SoD aprobador≠posteador queda **vacío** porque `approved_by` es None) y, sin `run_id`, sin gate `PACKAGED`; (2) `link_operational_event_to_accounting` con `auto_post_on_write` postea directo. Es intencional (el control SoD vive en la capa operativa: factura emitida, período de nómina aprobado), pero conviene **documentar** la frontera para que un endpoint no exponga `post_journal_drafts(require_approved=False)` sin control. Conecta con **I-01** (intercompany postea POSTED directo). | Documentar el contrato de auto-post; en endpoints exigir `require_approved=True`/`run` PACKAGED. |

> **Nota positiva (accounting):** es el kernel mejor blindado del repo — idempotente por `EconomicEvent.source_outbox_event_id` (re-procesar el mismo outbox **no** duplica draft/asiento), `select_for_update` + chequeo de balance + SoD en `approve_journal_drafts`/`post_journal_drafts`/cierre de período/reversa, y guarda de período CERRADO. Sin hallazgos de corrección.

---

## facturacion (`apps/kernels/facturacion`)

> **Sin hallazgos bloqueantes.** Kernel maduro: `create_draft` idempotente por `idempotency_key`; `issue_doc` usa `select_for_update`, retorna temprano si `already_issued`, y ejecuta **fiscal + inventario + CxC dentro de una sola `transaction.atomic`** con idempotencia por línea (`bill:{doc}:ln:{ln}`). La selección de lote en el auto-despacho respeta la clase del producto (FEFO/FIFO/AVERAGE). *(El problema de lote es del lado de inventarios — ver INV-01 — no de facturación.)*

---

## inventarios (`apps/kernels/inventarios`)

| ID | Sev | Ubicación | Tipo | Descripción | Fix sugerido |
|---|---|---|---|---|---|
| INV-01 | **ALTO** | `services.py:720-853` | bug | `post_issue` **recibe `lot_id` pero NUNCA lo usa**: la salida (a) **no** decrementa `LotBalance` y (b) **no** registra `lot=` en el `StockMovement`. (Compárese con `post_receipt`, que sí trackea lote, líneas 663-668.) Consecuencias: los balances por lote **solo crecen** → el selector FEFO/FIFO de facturación (`LotBalance.filter(qty_on_hand__gt=0).order_by(expiry)`) **sigue eligiendo lotes ya agotados/vencidos**, y se **pierde la trazabilidad** del lote consumido. El `StockBalance` agregado y el costo promedio **sí** quedan bien (el COGS financiero es correcto), pero la gestión por lote/vencimiento está rota. | En `post_issue`: resolver el lote, decrementar `LotBalance` (con consumo FEFO/FIFO si no se especifica lote) y setear `lot=` en el movimiento. |
| INV-02 | BAJO | `services.py:776-805` | robustez | Con `allow_negative=True`, una salida lleva `qty_on_hand` a negativo manteniendo `avg_cost`; un receipt posterior recalcula el promedio ponderado sobre **base negativa**, lo que puede **distorsionar el costo** al volver a positivo. Es opt-in (default `False`; facturación pasa `False`). | Política explícita de costeo en stock negativo (o bloquear el promedio mientras qty<0). |

---

## payments (`apps/kernels/payments`)

> **Sin hallazgos.** Kernel maduro: `create_payment_intent` idempotente por `idempotency_key`; `capture_payment_intent` con `select_for_update`, retorno temprano si ya `CAPTURED`, y `can_transition_to` (state machine); `reverse_captured_payment_intent` exige `idempotency_key` y **detecta conflicto** de clave reutilizada con payload distinto.

---

## reporting (`apps/kernels/reporting`)

> **Sin hallazgos (pasada ligera).** Read-only/observabilidad (selectors, materialización, exports, lineage). Los `float()` de `observability.py` son **métricas de latencia/percentiles** (p95 ms, error-rate %), no dinero. Sin `except Exception`/bare-except ni divisiones de dinero en flotante.

---

## Matriz resumen (batch 3: plataforma/soporte)

| Módulo | CRÍTICO | ALTO | MEDIO | BAJO | Nota |
|---|:---:|:---:|:---:|:---:|---|
| iam | 0 | 0 | 3 | 0 | semántica de scope (branch-only, data-company, doble camino) |
| rbac | 0 | 0 | 1 | 1 | `permission.is_active` no filtrado en la ruta scoped |
| audit | 0 | 0 | 0 | 1 | hash-chain HMAC fail-closed; lock del head serializa |
| integration | 0 | 0 | 0 | 0 | outbox retry/backoff + inbox idempotente |
| sync_engine | 0 | 0 | 0 | 0 | firma Ed25519 default-on + dedup `AppliedCommand` |
| compras | 0 | 0 | 0 | 0 | idempotente + best-effort **logueado**; CEC reconcilia |
| estacion_servicios | 0 | 0 | 0 | 0 | conversión US-gallon consistente/documentada |
| retail_pos | 0 | 0 | 0 | 0 | once-publishers + compensación/retry |
| cec | 0 | 0 | 0 | 0 | **aporta los controles de reconciliación** (red de seguridad) |
| accounts/hr | 0 | 0 | 0 | 1 | `temp_password` en claro en el result |
| org/parties/dashboard/activity/common | 0 | 0 | 0 | 0 | scoped por company; sin hallazgos |

> **Hallazgo arquitectónico positivo:** la capa **CEC** (`_collect_procurement_supplier_payment_mismatch_issues`, `_collect_billing_cash_mismatch_issues`, `_collect_cash_difference_issues`, `_collect_negative_stock_issues`, gaps de numeración) es la **red de seguridad** de los enlaces best-effort: detecta en el cierre la deriva que dejan los puentes que "nunca bloquean" (NM-06, F-02, compras→CxP). Esto **modera** —no elimina— esos hallazgos: el dinero descuadrado se *detecta*, aunque la corrección siga siendo manual.

---

## iam (`apps/modulos/iam`)

> **Nota positiva:** `approvals.py` (SoD/maker-checker) es sólido — `select_for_update` en decide/approve/reject/cancel/mark_executed, guarda de estado PENDING, anti-autoaprobación (`approver != requested_by`), permiso validado en scope, auditoría completa.

| ID | Sev | Ubicación | Tipo | Descripción | Fix sugerido |
|---|---|---|---|---|---|
| IAM-01 | MEDIO | `authentication.py:105-110`, `context_middleware.py:80-90` | hueco/scope | Un miembro **solo de sucursal** (sin membresía a la empresa) pasa el gate de empresa vía `has_branch_under_company`; si **omite** `X-Branch-Id`, opera con `request.company` y `branch=None` → **scope de empresa completo** (todas las sucursales). El sistema asume que el usuario branch-only siempre manda su header de sucursal, pero nada lo obliga. | Si no hay `has_company_membership` y no se envía branch, forzar la(s) sucursal(es) de su membresía (no caer a scope empresa). |
| IAM-02 | MEDIO | `authentication.py:147-185` + `common/permissions.py:96-123` | hueco/scope | `X-Data-Company-Id` abre lectura **intercompany** a otra empresa: la capa de auth fija `request.data_company` **sin** verificar membresía/grant ahí; el grant se valida **solo dentro de `rbac_permission`** (opt-in por vista, modo READ). Cualquier endpoint que no use `rbac_permission`, o un selector que filtre por `data_company` sin pasar por él, **omite el grant** → fuga cross-tenant. Es defensa-en-profundidad delegada a disciplina por vista. | Guard centralizado de data-scope (middleware/base view) que exija el grant antes de exponer `data_company`. |
| IAM-03 | MEDIO | `authentication.py` vs `context_middleware.py` | inconsistencia | **Dos caminos** casi duplicados de inyección de contexto org. Listas `EXEMPT` **divergentes** (auth exime `/2fa/verify/` y `/password/`; el middleware no) y **capacidades distintas** (el data-scope intercompany solo existe en el camino JWT). Mantener ambos invita a drift de seguridad. | Unificar en una sola capa (o derivar la lista EXEMPT de una constante compartida). |

---

## rbac (`apps/modulos/rbac`)

| ID | Sev | Ubicación | Tipo | Descripción | Fix sugerido |
|---|---|---|---|---|---|
| RBAC-01 | MEDIO | `selectors.py:52-57` | bug | `get_effective_permissions_for_scope` (la ruta de enforcement **principal**, usada por `rbac_permission` y `approvals`) **no filtra `permission__is_active`**; `get_effective_permissions` (línea 69) **sí**. Un permiso **desactivado** globalmente **sigue concediendo acceso** en la ruta scoped. | Añadir `permission__is_active=True` al filtro de `RolePermission`. |
| RBAC-02 | BAJO | `selectors.py:60-70` vs `11-57` | inconsistencia | Semántica de **superusuario divergente**: `get_effective_permissions` devuelve `["*"]`, pero `get_effective_permissions_for_scope` **ignora** `is_superuser` (un superuser sin `RoleAssignment` queda sin permisos en la ruta scoped). Puede ser intencional (aislamiento por tenant), pero conviene documentarlo. | Documentar la decisión o unificar la semántica. |

---

## audit (`apps/modulos/audit`)

> **Nota positiva:** `writer.py` es una **cadena de hash a prueba de manipulación** (payload canónico → SHA256 `event_hash` → HMAC `signature` con keyring → encadenado por `prev_event_hash` y partición por tenant, con `select_for_update` en el head). `contracts.py` es **fail-closed**: `validate_event_type`/`validate_subject` **lanzan** ante catálogos no registrados → un evento no contratado **bloquea** la operación (ratchet de contrato).

| ID | Sev | Ubicación | Tipo | Descripción | Fix sugerido |
|---|---|---|---|---|---|
| AUD-01 | BAJO | `writer.py:145-207` | performance | El `AuditChainHeadV2` se bloquea con `select_for_update` durante **toda la transacción de negocio externa** (no solo el write de auditoría) → **todas** las operaciones auditadas de una empresa se **serializan** en esa fila; bajo carga, contención y posible deadlock (orden de locks recurso↔head). Aceptable a la escala actual (finca de un dueño). | Si crece la concurrencia, acortar la sección crítica del head o particionar la cadena más fino. |

---

## integration / sync_engine / compras / estacion_servicios / retail_pos / cec

> **Sin hallazgos de corrección.** Capa de mensajería e idempotencia madura:
> - **integration**: outbox con `retry`/backoff exponencial/`FAILED` tras N intentos, `select_for_update` en dispatch; inbox idempotente por `(event_id, consumer)` con `ignore_conflicts`. El `except Exception` del dispatcher es correcto (aísla el fallo por evento y reintenta).
> - **sync_engine**: firma **Ed25519 obligatoria por defecto** (`enforce_command_signature=True`), dedup `AppliedCommand` por `command_id` con `select_for_update`, y rechazo por payload-hash distinto al mismo `command_id`.
> - **compras**: `post_purchase_document` idempotente (`already_posted`) + lock; el enlace best-effort a CxP **sí se loguea** con `logger.exception` (el patrón correcto que a finca le faltaba — ver F-06).
> - **estacion_servicios**: las conversiones de combustible son consistentes (`GALLON_TO_LITER = GALLON_US_TO_LITER`; `PER_GALLON`/`PER_GALLON_US` son el **mismo** galón US por contrato documentado, no un bug).
> - **retail_pos**: once-publishers (`_publish_pos_outbox_event_once`), claves de idempotencia por venta/pago/movimiento de caja, y compensación con reintento.
> - **cec**: el motor de cierre con `select_for_update` + `fingerprint` de excepciones; aporta los **controles de reconciliación** descritos arriba.

---

## accounts / hr / parties / org / dashboard / activity / common

| ID | Sev | Ubicación | Tipo | Descripción | Fix sugerido |
|---|---|---|---|---|---|
| SUP-01 | BAJO | `hr/services.py:427,431-456` | seguridad | `provision_user_for_employee`/`reset_temp_password_for_employee` devuelven el `temp_password` **en claro** en el dict resultado (patrón "mostrar una vez" al admin). Verificar que la capa de `redaction` lo excluya de **audit/logs** y que no termine en un `OutboxEvent`/metadata. | Confirmar redaction de `*password*`; nunca persistir el valor. |

> **Resto sin hallazgos.** `accounts` usa `password_validation` de Django + `set_password` (hash) + `must_change_password`; los servicios de `hr`/`parties`/`org` están scopeados por company con helpers `_request_company`/`_same_company` y auditoría; los `except Exception` de `common/pagination.py` y `dashboard` son parseos defensivos de parámetros/observabilidad.

---

## Tracker de progreso

- [x] **Batch 1 — Módulos frescos**: finca, comisariato, fleet, notifications, intercompany. *(arriba)*
- [x] **Batch 2 — Kernels económicos**: nomina, portfolio, accounting, facturacion, inventarios, payments, reporting. *(arriba)*
- [x] **Batch 3 — Plataforma/soporte**: iam, rbac, audit, integration, sync_engine, sync *(retirado/vacío)*, common, org, accounts, parties, hr, cec, compras, dashboard, estacion_servicios, retail_pos, activity. *(arriba)*
- [ ] Barridos cross-cutting: cobertura de contratos (audit/RBAC/edges) declarada vs real; dinero=Decimal en todo $; fronteras de transacción; revisar los ~116 `except Exception`.
- [ ] Frontend (Vue/Quasar) — evaluación aparte.

> Tras tu revisión, la pasada de **corrección** ataca por severidad (ALTO/CRÍTICO primero), con test que reproduce el bug + verde.
