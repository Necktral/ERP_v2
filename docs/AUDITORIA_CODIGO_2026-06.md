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

## Tracker de progreso

- [x] **Batch 1 — Módulos frescos**: finca, comisariato, fleet, notifications, intercompany. *(arriba)*
- [x] **Batch 2 — Kernels económicos**: nomina, portfolio, accounting, facturacion, inventarios, payments, reporting. *(arriba)*
- [ ] Batch 3 — Plataforma/soporte: iam, rbac, audit, integration, sync_engine, sync, common, org, accounts, parties, hr, cec, compras, dashboard, estacion_servicios, retail_pos, activity.
- [ ] Barridos cross-cutting: cobertura de contratos (audit/RBAC/edges) declarada vs real; dinero=Decimal en todo $; fronteras de transacción; revisar los ~116 `except Exception`.
- [ ] Frontend (Vue/Quasar) — evaluación aparte.

> Tras tu revisión, la pasada de **corrección** ataca por severidad (ALTO/CRÍTICO primero), con test que reproduce el bug + verde.
