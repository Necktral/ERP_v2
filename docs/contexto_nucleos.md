## Estado de Ejecucion Backend (Staging First) — 2026-03-10

Este documento mantiene el estado operativo ejecutivo del proyecto.
El blueprint arquitectonico completo vive en:

- [ARQUITECTURA_DOMINIO_Y_CONTROL_v1.0.md](ARQUITECTURA_DOMINIO_Y_CONTROL_v1.0.md)

## Estado por fase (real)

- Fase 1 (Nucleo disciplinado): implementada en backend.
- Fase 2 (Contratos canonicos + event backbone): implementada en backend.
- Fase 3 (CEC operativo D+0): implementada en backend.
- Fase 4 (Shadow Ledger): cerrada con certificacion y gates.
- Fase 5 (Posting controlado): implementada con SoD, cierre de periodo y reversas.
- Fase 6 (Adapter B readiness): cerrada en staging.
- Fase 7A (GL formal + FX): cerrada en staging.
- Fase 7B (Intercompany + consolidacion): cerrada en staging.
- Fase 8 (Go-live controlado): cerrada con burn-in `14/14` y sign-off contador PASS.
- Fase 9 (Adapter B provider): cerrada en staging en carriles `EMULATED` y `HTTP`.
- Fase 10 (Procurement 4B): cerrada en staging con gate estricto.
- Fase 11 (Intercompany avanzado): cerrada en staging con gate estricto.
- Fase 12 (Cierre mensual continuo): cerrada en staging (`required_periods=3`, SLO PASS, gate PASS).

## Toolchain operativo activo (backend-only)

- Fase 8:
  - `verify_phase8_precutover`
  - `evaluate_phase8_rollback`
  - `run_phase8_go_live.sh`
- Fase 9:
  - `export_phase9_env_manifest`
  - `compare_phase9_env_manifests`
  - `certify_adapter_b_provider_run`
  - `verify_phase9_go_live`
  - `run_adapter_b_provider_cycle`
  - `qa/run_phase9_go_live.sh`
- Fase 10:
  - `export_phase10_env_manifest`
  - `certify_phase10_procurement_run`
  - `verify_phase10_go_live`
  - `run_phase10_procurement_cycle`
  - `qa/run_phase10_go_live.sh`
- Fase 11:
  - `export_phase11_env_manifest`
  - `compare_phase11_env_manifests`
  - `certify_phase11_intercompany_sla`
  - `verify_phase11_go_live`
  - `run_phase11_intercompany_cycle`
  - `qa/run_phase11_go_live.sh`
- Fase 12:
  - `export_phase12_env_manifest`
  - `compare_phase12_env_manifests`
  - `run_phase12_monthly_close`
  - `certify_phase12_monthly_determinism`
  - `verify_phase12_operational_slo`
  - `verify_phase12_go_live`
  - `qa/run_phase12_go_live.sh`

## Pendientes de roadmap (sin frontend)

- Promocion controlada de staging a produccion con gates estrictos.
- Integracion de provider fiscal externo real en productivo (credenciales/certificados reales).
- Operacion mensual consolidada continua con historico acumulado en produccion.

## Scope y decisiones vigentes

- Frontend fuera de alcance en este bloque.
- Politica de cambios: aditivos, sin breaking changes.
- Timezone operativa de referencia: `America/Managua`.

Este kernel es la base institucional del sistema.

Qué posee

usuarios, identidades y credenciales;

org units, company, branch, memberships;

roles, permisos, asignaciones;

políticas de SoD y matrices de aprobación;

contexto activo del request y selección de alcance;

excepciones de acceso y trazabilidad de autorización.

Submódulos internos

Identity

Organization Context

RBAC

SoD / Approval Policy

Session & Context

Machine / Device Identity si necesitas offline o dispositivos confiables

Qué exporta

contexto efectivo;

alcance permitido;

permisos efectivos;

requerimientos de aprobación;

eventos de seguridad y acceso denegado.

Qué tiene prohibido poseer

stock;

correlativos fiscales;

totales monetarios del negocio;

balances contables;

lógica específica de Fuel, Retail o Billing.

Contratos típicos

Comandos:

GrantMembership

AssignRole

SelectContext

ApproveSensitiveAction

Eventos:

MembershipGranted

RoleAssigned

ApprovalGranted

AccessDeniedAudited

5) Kernel 2 — Billing / Fiscal Document

Billing debe ser el source of truth documental y fiscal, no caja, no stock, no contabilidad final.

Qué posee

drafts, issue, void, credit notes;

series, correlativos y numeración;

lifecycle de documentos;

líneas, impuestos, breakdown fiscal;

relación entre documento comercial y documento fiscal;

vínculo a documento original en notas de crédito y anulaciones.

Submódulos internos

Commercial Document Lifecycle

Fiscal Numbering

Tax Calculation

Credit Notes / Void / Reversal

Fiscal Adapter Interface

Document Evidence Linkage

Qué exporta

DocumentDrafted

DocumentIssued

DocumentVoided

CreditNoteIssued

TaxCalculated

Qué tiene prohibido poseer

qty_on_hand, avg_cost, cost layers;

cash session balances;

journal entries finales;

lógica propia de reconciliación bancaria.

Regla central

Billing no “hace contabilidad”.
Billing emite hechos documentales y fiscales; Accounting interpreta esos hechos bajo reglas contables versionadas.

6) Kernel 3 — Inventory / Cost

Este kernel debe ser la verdad de existencias y costo.
Aquí no puede haber ambigüedad.

Qué posee

catálogo de ítems;

UOM y conversiones;

warehouses;

balances;

movimientos;

ajustes;

transferencias;

política de costo;

reservas futuras, si decides agregarlas.

Submódulos internos

Item Master

UOM & Conversion

Warehouse

Movement Engine

Cost Engine

Adjustment & Transfer

Availability / Reservation (futuro, si aplica)

Qué exporta

InventoryMovementPosted

InventoryAdjusted

TransferCompleted

CostValuationUpdated

StockExceptionRaised

Qué tiene prohibido poseer

correlativos fiscales;

lifecycle documental fiscal;

asientos contables posteados.

Decisión de arquitectura que debes congelar

El blueprint debe fijar explícitamente:

si el costo será promedio móvil, FIFO, u otra política;

si la política es por tenant, por empresa o por almacén;

cómo se comporta en transferencias;

qué ocurre con negativos temporales;

y cómo versionas esa política.

Sin eso, el kernel de inventario queda técnicamente abierto.

7) Kernel 4 — Accounting

Accounting debe nacer con una evolución clara:

Economic Events → Shadow Ledger → Posting Rules → Journal Entries → Close Governance

Qué posee

normalización de hechos económicos;

borradores contables;

reglas contables versionadas;

journal entries;

fiscal periods;

posting batches;

reversals;

FX / revaluation;

intercompany futuro;

close runs contables.

Submódulos internos

Economic Event Registry

Shadow Ledger

PostingRuleSet

Journaling

Period Close

Reversal & Revaluation

Intercompany (fase posterior)

Financial Reporting Canonical Layer

Qué exporta

EconomicEventRegistered

JournalDraftGenerated

JournalValidated

JournalPosted

JournalReversed

PeriodClosed

Qué tiene prohibido poseer

tickets, cash sessions, dispenses, facturas operativas, balances de inventario como verdad primaria.

Regla central

Accounting nunca inventa hechos.
Solo consume hechos operativos normalizados.

8) Payments & Cash Module

Este módulo no debe quedar difuso.
Tiene que existir como módulo de primer nivel porque su verdad no es fiscal ni contable final, pero sí es crítica.

Qué posee

payment intents;

authorized/captured/failed/refunded states;

conciliación con procesadores;

cash sessions;

arqueos;

diferencias de caja;

fondos de caja y movimientos de efectivo operativos.

Submódulos internos

Payment Intent / Capture

Provider Reconciliation

Cash Session

Cash Difference / Over-Short

Refund Handling

Settlement Linkage

Qué exporta

PaymentCaptured

PaymentFailed

RefundProcessed

CashSessionOpened

CashSessionClosed

CashDifferenceDetected

Qué tiene prohibido poseer

correlativos fiscales;

journal entries finales;

costo de inventario.

9) CEC como verdadero control plane

Aquí está una de las mejoras más importantes.

CEC no debe verse como “módulo de exportación”.
Debe ser el plano de control de integridad, evidencia, cierre y riesgo.

Qué posee

validaciones D+0;

reconciliaciones;

registry de soportes y hashes;

excepciones;

manifests de cierre;

KPI states;

gates de transición;

policy escalation;

paquete para contador;

historial de close runs.

Submódulos internos

Validation Engine
correlativos, gaps con estado, duplicados, integridad documental, SoD, completitud de soporte.

Reconciliation Engine
ventas ↔ pagos, pagos ↔ caja, billing ↔ inventory, operación ↔ Shadow Ledger, documento ↔ soporte.

Evidence Registry
SoporteID, sha256, mime, retención, referencia causal, manifiesto del paquete.

Close Orchestrator
cierre diario, cierre mensual, paquetes reproducibles, rerun controlado.

Exception Manager
aperturas, clasificación, severidad, asignación, resolución, cierre evidenciado.

KPI / Gate Engine
disciplina de caja, integridad documental, correlativos, devoluciones, anomalías de inventario.

Stabilization Policy Engine
si cae la disciplina, endurece controles, escalamiento o bloqueo.

Qué tiene prohibido hacer

no reescribe tickets;

no corrige stock;

no re-numera documentos;

no postea contabilidad por su cuenta;

no reemplaza kernels.

Regla maestra

CEC controla, verifica, evidencia y empaqueta; no sustituye la verdad primaria.

10) Integration / Event Backbone

Esto debe existir como plataforma explícita y no quedar implícito.

Componentes

outbox_event

inbox_event

schema registry

replay service

dedupe service

retry / dead-letter strategy

contract tests

correlation / causation chain

Regla

Toda integración entre kernels debe seguir este criterio:

consistencia fuerte dentro del agregado;

consistencia eventual entre bounded contexts;

eventos versionados;

replay seguro;

consumidores idempotentes.

11) Adaptadores fiscales A y B

Aquí hay que endurecer una idea clave:

A y B no son dos sistemas; son dos adaptadores fiscales sobre un mismo núcleo.

Adapter A

liga ticket/venta a documento manual o preimpreso;

controla rangos manuales y evidencia;

exige vinculación, soporte y conciliación;

emite los mismos eventos canónicos al resto del sistema.

Adapter B

reserva correlativo transaccionalmente;

emite documento computarizado;

controla impresión, fallo de impresión, contingencia y anulación;

emite los mismos eventos canónicos al resto del sistema.

Interfaz común que ambos deben cumplir

attach_or_reserve_reference()

issue_document()

void_document()

issue_credit_note()

record_contingency()

produce_fiscal_evidence()

validate_range_integrity()

Regla de oro

A y B cambian:

evidencia,

numeración,

cumplimiento,

disciplina operativa.

A y B no cambian:

Billing como source of truth documental;

Inventory como source of truth de stock/costo;

Payments/Cash como source of truth de cobro/caja;

Accounting como truth financiera final.

12) Shadow Ledger bien formalizado

Este punto debe quedar impecable.

Definición correcta

El Shadow Ledger es la capa que convierte hechos operativos normalizados en proyecciones contables reproducibles, antes del posting formal.

Objetos del Shadow Ledger

EconomicEvent

JournalDraft

PostingRuleSet

CloseRun

DraftValidationResult

ExceptionLink

Reglas duras

todo EconomicEvent deriva de eventos operativos canónicos;

todo JournalDraft debe ser reproducible;

no se editan drafts manualmente como si fueran fuente primaria;

si hay excepción, se registra excepción, no “se arregla el Excel”;

cada draft guarda:

rule_set_version

contract_version

close_run_id

input_manifest_hash

Estado sugerido del draft

GENERATED -> VALIDATED -> EXCEPTION -> APPROVED_FOR_POSTING -> POSTED -> SUPERSEDED

Regla maestra

Shadow Ledger ≠ GL
Shadow Ledger = proyección validable y gobernada.

13) PostingRuleSet: el motor que evita el caos futuro

Este es uno de los componentes más importantes del blueprint.

Qué es

Un catálogo versionado de reglas que traduce:

EconomicEvent -> JournalDraft -> JournalEntry

Qué debe parametrizar

tenant / empresa;

jurisdicción / país;

modo fiscal A/B;

doc type;

tax regime;

payment method;

inventory valuation policy;

FX policy;

intercompany policy futura.

Qué debe guardar

versión;

estado (DRAFT, ACTIVE, DEPRECATED);

fecha/criterio de activación;

pruebas de contrato asociadas;

cuenta(s) destino;

lógica de reversión;

validaciones previas.

Regla de diseño

No dejes que las reglas contables vivan enterradas en código disperso de módulos verticales.
Deben vivir en un motor gobernado y versionado.

14) Modelos de estados que deben quedar fijos
Venta / ticket

DRAFT -> OPEN -> PAID -> CLOSED -> VOIDED

Documento fiscal A

PENDING_LINK -> LINKED_MANUAL -> VERIFIED -> VOIDED

Documento fiscal B

NUMBER_RESERVED -> ISSUED -> PRINTED -> FAILED_PRINT -> CONTINGENCY -> VOIDED

Pago

INTENDED -> AUTHORIZED -> CAPTURED -> REFUNDED / FAILED

Cash Session

OPEN -> COUNT_PENDING -> REVIEW_PENDING -> CLOSED -> REOPENED_FOR_INVESTIGATION

Movimiento inventario

PROPOSED -> POSTED -> REVERSED

Journal Draft

GENERATED -> VALIDATED -> EXCEPTION -> APPROVED_FOR_POSTING -> POSTED

Close Run

CREATED -> GATHERED -> VALIDATED -> PACKAGED -> DELIVERED -> REOPENED_EXCEPTION

Con esto evitas ambigüedad y reduces errores de orquestación.

15) Verticales: cómo deben vivir encima de los kernels

Este punto es clave para Fuel y cualquier módulo futuro.

Regla estructural

Un vertical puede tener:

workflow propio;

estados propios;

UI propia;

reglas operativas propias;

vistas locales;

métricas locales.

Pero no puede apropiarse de:

verdad fiscal,

verdad de stock/costo,

verdad de caja,

ni verdad financiera posteada.

Contrato de un vertical

Un vertical debe:

consumir IAM/contexto;

orquestar Billing, Inventory y Payments/Cash;

emitir eventos operativos locales;

recibir feedback de CEC y Accounting;

conservar solo sus vistas y estados locales.

Ejemplo: Fuel

Fuel debe poseer:

shift,

dispense,

bomba/nozzle,

lectura de medidor,

flujo operativo de estación.

Fuel no debe poseer:

costo maestro del inventario,

numeración fiscal primaria,

asientos finales.

En el repo ya se ve a Fuel separado de inventory y billing, lo cual es una buena base para mantenerlo como vertical y no como kernel.

16) Cierres como máquina de disciplina
Cierre diario

Debe cerrar:

ventas,

pagos,

caja,

diferencias,

eventos sensibles,

soportes mínimos del día.

Output:

reconciliación operativa,

excepciones abiertas,

paquete de evidencia diaria,

borradores contables del día o del turno, según diseño.

Cierre de periodo

Debe cerrar:

documentos emitidos/voided/credit notes;

pagos y cash sessions;

inventario y ajustes;

paquete contable;

manifiesto de soportes;

Shadow Ledger del periodo;

validación de posting readiness.

Regla crítica

El cierre no es solo “generar Excel”.
El cierre es una corrida controlada, reproducible y auditable.

17) KPIs y gates, pero mejor estructurados

Mantén tus KPIs, pero agrúpalos por familias para que el blueprint sea más limpio.

Familia 1 — Disciplina documental y fiscal

duplicados,

huecos sin estado,

correlativos inválidos,

soporte documental incompleto.

Familia 2 — Disciplina de caja y pagos

diferencias de caja,

conciliación pagos ↔ caja,

cierres aprobados correctamente.

Familia 3 — Disciplina de devoluciones y anulaciones

frecuencia,

monto,

autorización,

soporte.

Familia 4 — Disciplina de inventario

mermas,

ajustes,

diferencias no justificadas,

reversas.

Familia 5 — Calidad de cierre y entrega

paquete reproducible,

soportes íntegros,

consistency score,

exception backlog.

Regla de gobierno

Si cae una familia crítica, el sistema puede:

endurecer autorizaciones,

bloquear transición fiscal,

impedir cierre sin supervisor,

abrir plan de estabilización.

18) Fases de madurez, sin fechas

No usaría meses.
Usaría fases de capacidad.

Fase 1 — Núcleo disciplinado

IAM, Billing, Inventory y Payments/Cash con invariantes fijos.

Fase 2 — Contratos canónicos y event backbone

Eventos, outbox/inbox, correlation, idempotencia, versionado.

Fase 3 — CEC operativo

Validaciones D+0, evidencia, cierres reproducibles, excepciones.

Fase 4 — Shadow Ledger

EconomicEvent, JournalDraft, RuleSet v1, paquete contable consistente.

Fase 5 — Posting controlado

GL formal parcial para procesos ya maduros.

Estado de ejecución (2026-03-08): implementado en backend con `post_journal_drafts` (idempotencia 1:1 draft→entry, bloqueo en período cerrado, eventos `ACCOUNTING.JournalPosted`).
También quedó habilitado el control de aprobación (`approve_journal_drafts`) y cierre formal de período (`close_fiscal_period`) con bloqueo por drafts pendientes.
Actualización (2026-03-08): Fase 5 reforzada con segregación de funciones (SoD) operativa en API:
- aprobador de `JournalDraft` no puede postear el mismo draft sin override explícito;
- quien posteó asientos del período no puede cerrar ese mismo período sin override explícito;
- trazabilidad de actor en `JournalDraft.approved_by/approved_at` y `JournalEntry.posted_by`.
Actualización (2026-03-08): reversa contable formal habilitada (`reverse_journal_entry` + `POST /api/accounting/journal-entries/{entry_id}/reverse/`) con:
- creación de `EconomicEvent` + `JournalDraft` de reversa (sin editar histórico);
- idempotencia por `JournalEntry.reversed_entry`;
- evento canónico `ACCOUNTING.JournalReversed`.
Actualización (2026-03-08): reversa masiva operativa (sin frontend) para integración futura:
- `POST /api/accounting/journal-entries/reverse-batch/` (scope por `run_id`, por `year/month` o por `entry_ids`);
- comando `reverse_journal_entries_batch`;
- modo `strict` y override SoD controlado por `accounting.sod.override`.

Fase 6 — Adapter B readiness

Numeración computarizada, contingencia, impresión, control reforzado.

Fase 7 — GL pleno e intercompany

Revaluación, consolidación, intercompany, reporting financiero formal.
Estado de ejecución (2026-03-08): iniciado en backend con Fase 7A (GL Core formal) incluyendo:
- `ChartOfAccount`, `CompanyAccountingConfig`, `JournalEntryLine`, `FxRate`, `RevaluationRun`, `RevaluationEntryLink`;
- APIs aditivas `/api/accounting/chart-of-accounts/`, `/api/accounting/reports/*`, `/api/accounting/fx-rates/`, `/api/accounting/revaluation/run/`;
- comandos operativos `run_fx_revaluation`, `export_gl_report` y toolchain de certificación/go-live Fase 7A.
Pendiente para Fase 7B: intercompany transaccional y consolidación multi-compañía.

19) Anti-patrones que debes prohibir desde el blueprint

CEC como mega-módulo ambiguo que intenta ser a la vez auditor, ERP, exportador y contabilidad.

Shadow Ledger como segunda contabilidad viva.

Billing calculando balances contables finales.

Inventory “inventando” políticas de costo por caso sin rule versioning.

Excel usado como fuente primaria.

Adaptadores fiscales con lógica de negocio metida adentro.

Verticales con sus propios “mini stocks” o “mini ledgers”.

Correcciones por edición directa de histórico.

reapertura de periodos sin cadena de auditoría.

credenciales compartidas o bypass de SoD.

20) Decisiones que yo congelaría ya

Si quieres que el blueprint quede realmente profesional, estas decisiones deben quedar fijas pronto:

Política de costo de Inventory.

Modelo de estados de documentos, pagos, caja, drafts y cierres.

Envelope canónico de eventos.

RuleSet v1 para Shadow Ledger.

Objeto de evidencia y manifest hashado.

Exception model del CEC.

interfaz común de Adaptador Fiscal A/B.

Payments/Cash como módulo de primer nivel y no apéndice de billing.

Resultado final del blueprint fusionado

La formulación más fuerte de tu arquitectura sería esta:

Necktral es una plataforma modular con kernels de verdad operativa y financiera, módulos core de cobro/caja y control transversal, adaptadores fiscales intercambiables y verticales de negocio que orquestan el núcleo sin apropiarse de la verdad. El CEC actúa como plano de control, evidencia y cierre; el Shadow Ledger es una proyección contable reproducible; y el GL formal es la única verdad financiera posteada.

Ese enunciado ya es blueprint de nivel serio.

Si quieres, en el siguiente paso te lo convierto en documento arquitectónico final, ya pulido como entregable profesional, con formato de especificación:
Propósito, Principios, Núcleos, Módulos, Contratos, Estados, Eventos, CEC, Shadow Ledger, Gates y Anti-patrones.
