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

## Tracker de progreso

- [x] **Batch 1 — Módulos frescos**: finca, comisariato, fleet, notifications, intercompany. *(arriba)*
- [ ] Batch 2 — Kernels económicos: nomina, portfolio, accounting, facturacion, inventarios, payments, reporting.
- [ ] Batch 3 — Plataforma/soporte: iam, rbac, audit, integration, sync_engine, sync, common, org, accounts, parties, hr, cec, compras, dashboard, estacion_servicios, retail_pos, activity.
- [ ] Barridos cross-cutting: cobertura de contratos (audit/RBAC/edges) declarada vs real; dinero=Decimal en todo $; fronteras de transacción; revisar los ~116 `except Exception`.
- [ ] Frontend (Vue/Quasar) — evaluación aparte.

> Tras tu revisión, la pasada de **corrección** ataca por severidad (ALTO/CRÍTICO primero), con test que reproduce el bug + verde.
