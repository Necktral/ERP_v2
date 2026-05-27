# NECKTRAL_MASTER_ROADMAP

## 0. Control del documento

Documento: `NECKTRAL_MASTER_ROADMAP.md`
Proyecto: Necktral ERP/CRM/POS multiempresa
Estado: Roadmap Operating System vivo
Ultima actualizacion: 2026-05-27
Uso: direccion de plataforma, programas maestros, cortes ejecutables y gates de madurez
Regla superior: este roadmap no autoriza implementacion por si solo. Todo corte requiere Controller -> Auditor Agent -> Fixer Agent -> Reviewer Agent.

Fuentes rectoras:

- `docs/project/NECKTRAL_CONTEXT_CARD.md`
- `docs/project/CODEX_OPERATING_BRIEF.md`
- decisiones validadas sobre Party, HR, cartera, costos, contador, fincas, flota, nomina, work planning y CEC

GitHub es evidencia tecnica, no objetivo. El objetivo es construir una plataforma operacional robusta.

## 1. Tesis del roadmap

Necktral es una plataforma modular multiempresa, multidominio y multiplataforma para operar empresas correlacionadas con financiamiento, cartera, nomina, asistencia, planificacion de trabajo, inventario, flota, mantenimiento, ventas, pagos, verticales productivos, CEC, auditoria, Shadow Ledger y reportes utiles para contador certificado.

Este roadmap no es una lista de fases. Es un sistema de direccion para construir una plataforma operacional sin perder ownership, datos criticos, costos, cierres ni control.

Regla central:

```text
identidad -> operacion -> evidencia -> dinero/cartera/inventario/costo -> cierre -> contador -> Shadow Ledger
```

Cada capacidad nueva debe conectar con esa cadena o declarar por que no aplica. Una capacidad que no declara verdad dueña, evidencia, cierre, costos y reportes queda incompleta.

## 2. Que cuenta como avance real

Cuenta como avance real:

- cerrar un corte con owner de datos claro;
- crear contratos auditables y testeados;
- reducir texto suelto y reemplazarlo por FK fuerte cuando corresponde;
- producir evidencia revisable;
- conectar operacion con costo, cartera, inventario, pagos o cierre;
- pasar PostgreSQL real cuando hay persistencia critica;
- entregar reportes o paquetes utiles al contador;
- documentar decisiones y stop conditions;
- mantener scope acotado sin bajar calidad.

No cuenta como avance real:

- abrir modulos sin contratos;
- crear pantallas sin ownership de datos;
- usar GitHub/PRs como fin;
- crear fases sin DoD;
- meter todo en Accounting;
- dejar clientes/proveedores/personas como texto;
- aprobar persistencia critica solo con SQLite;
- abrir CxC/CxP/Creditos sin Party;
- abrir verticales productivos sin kernels base;
- crear microservicios sin senales objetivas.

## 3. Mapa maestro de plataforma

```text
Necktral Platform
├── Governance Layer
│   ├── Context Card
│   ├── Codex Brief
│   ├── Master Roadmap
│   ├── Decision Log
│   └── ADR Register
│
├── Identity & Scope Layer
│   ├── OrgUnit / Company / Branch
│   ├── Party / Counterparty
│   ├── RBAC / IAM
│   ├── Related Parties
│   └── Tax Profile / RUC
│
├── Financial Backbone
│   ├── CxC
│   ├── CxP
│   ├── Credits / Financing
│   ├── Payments / Cash / Bank
│   ├── Settlement
│   └── Accountant Review
│
├── Operational Backbone
│   ├── HR
│   ├── Payroll
│   ├── Attendance
│   ├── Work Planning
│   ├── Inventory
│   ├── Purchasing
│   ├── Fleet
│   └── Maintenance
│
├── Vertical Operations
│   ├── Hacienda / Fincas
│   ├── Ganaderia
│   ├── Agroquimicos
│   ├── Transporte
│   ├── Maquinaria
│   └── Comercio / Ventas
│
├── Control & Evidence Layer
│   ├── CEC
│   ├── CloseRun
│   ├── EvidencePackage
│   ├── AccountantPackage
│   └── Exception Management
│
├── Accounting Projection Layer
│   ├── EconomicEvent
│   ├── PostingRuleSet
│   ├── JournalDraft
│   └── JournalEntry futuro
│
└── Platform Reliability Layer
    ├── Audit
    ├── Outbox/Inbox
    ├── Sync
    ├── Security
    ├── Observability
    ├── QA Gates
    └── Release Stability
```

## 4. Mapa de verdades del sistema

| Verdad | Dueno | No debe poseerla |
| --- | --- | --- |
| Empresa/sucursal/scope | Org/IAM | HR, Billing, Inventory |
| Persona/contraparte | Party Kernel | OrgUnit, Billing textual |
| Empleado | HR | Party, Payroll |
| Saldo CxC/CxP | Financial Portfolio | Billing, Payments |
| Credito/financiamiento | Financing | Payments, Billing |
| Pago/cobro | Payments/Cash | Billing, Accounting |
| Documento/factura | Billing | Payments, Inventory |
| Stock/costo | Inventory/Cost | Billing, Work Planning |
| Asistencia/nomina | HR/Payroll | Payments, Accounting |
| Plan de trabajo | Work Planning | HR, Inventory |
| Vehiculo/mantenimiento | Fleet | Inventory, HR |
| Cierre/evidencia | CEC | Kernels primarios |
| Pre-asiento | Accounting/Shadow Ledger | Verticales |
| Contabilidad oficial | Contador certificado | Necktral |

Regla: si un dominio intenta poseer una verdad que pertenece a otro, el corte debe detenerse y redisenarse.

## 5. Data Backbone

Los datos criticos que deben convertirse en columna vertebral son:

- `OrgUnit` / `Company` / `Branch`
- `Party` / `Counterparty`
- `CostCenter`
- `ProductionUnit`
- `WorkUnit` / `Zone` / `Labor`
- `Employee` / `Worker` / `Crew`
- `Obligation` / `Receivable` / `Payable` / `Credit`
- `Payment` / `Cash` / `Bank`
- `InventoryItem` / `StockMovement` / `CostLayer`
- `FleetAsset` / `MaintenanceOrder` / `TripLog`
- `Document` / `BillingDocument` / `Receipt`
- `AuditEvent` / `OutboxEvent`
- `EconomicEvent` / `JournalDraft`
- `CloseRun` / `EvidencePackage` / `AccountantPackage`

Regla: los snapshots textuales pueden existir como compatibilidad historica, pero no deben ser la base de nuevos saldos, cierres, costos ni reportes.

## 6. Cost Backbone

Necktral debe poder medir costos por objeto de costo. Sin costo asignable, no hay control operativo serio.

Cost objects:

- empresa;
- sucursal;
- finca;
- zona;
- labor;
- trabajador/cuadrilla;
- vehiculo/maquinaria;
- producto/insumo;
- proveedor;
- credito;
- venta;
- periodo.

Costos que debe medir:

- costo de mano de obra por finca/zona/labor;
- costo de insumos por finca/zona/labor;
- costo de flota por km/hora/labor;
- costo de mantenimiento por activo;
- costo de maquinaria por trabajo;
- costo de nomina por periodo/finca;
- costo financiero por credito/interes/mora;
- costo de inventario consumido;
- costo de produccion ganadera;
- costo de operacion por comprador/venta.

Regla: toda operacion relevante debe poder asignarse a un cost object. Si no se puede asignar, queda como excepcion CEC.

## 7. Mapa de cierre

No existe operacion seria sin cierre.

Cierre diario:

- caja;
- pagos;
- movimientos criticos;
- asistencia;
- tareas completadas;
- combustible;
- ventas/cobros.

Cierre semanal:

- avance de labores;
- nomina parcial;
- consumos de insumos;
- flota/mantenimiento;
- cartera vencida.

Cierre mensual:

- cartera;
- CxP;
- nomina;
- inventario;
- flota;
- work planning;
- documentos;
- paquete contador.

Cierre de ciclo:

- finca;
- cosecha;
- ganado;
- produccion;
- creditos asociados;
- costos acumulados.

Regla: cada programa debe declarar que CloseRun, EvidencePackage o AccountantPackage afecta.

## 8. Mapa de reportes del contador

El contador no debe reconstruir la operacion. Necktral debe entregarle paquetes listos para revisar.

Familias de reportes:

1. Reporte por RUC / declarante.
2. Reporte por empresa/sucursal.
3. CxC por antiguedad.
4. CxP por antiguedad.
5. Creditos otorgados.
6. Creditos recibidos.
7. Intereses y mora.
8. Pagos aplicados.
9. Pagos no aplicados.
10. Nomina y deducciones.
11. Inventario recibido/consumido.
12. Costos por finca/zona/labor.
13. Flota y mantenimiento.
14. Proveedores agroquimicos.
15. Ventas/cobros.
16. Operaciones sin evidencia.
17. Operaciones pendientes de revision.
18. Reclasificaciones del contador.
19. Cierres con excepcion.
20. Shadow Ledger summary.

Regla: cada reporte debe tener fuente, periodo, scope, evidencia y estado de revision.

## 9. Personalization gates

El roadmap define estructura, no sustituye validacion con expertos.

Contador define:

- reportes reales;
- limites;
- clasificacion fiscal;
- revision;
- reclasificaciones;
- formatos.

Ingenieros / agronomia definen:

- zonas;
- labores;
- calendarios;
- insumos tecnicos;
- rendimientos;
- calidad.

RRHH define:

- tipos de trabajador;
- jornadas;
- asistencia;
- calculo de nomina;
- deducciones;
- adelantos;
- temporales.

Flota define:

- planes de mantenimiento;
- odometro;
- horometro;
- combustible;
- repuestos;
- rutas;
- servicios.

Finanzas / microfinanciera define:

- tasas;
- mora;
- garantias;
- plazos;
- reestructuracion;
- castigos;
- aprobaciones.

Operacion / jefes define:

- jefes por zona;
- trabajadores por jefe;
- evidencia diaria;
- avance;
- productividad.

## 10. Plantilla obligatoria por programa

Cada programa maestro debe poder responder:

- Proposito.
- Problema que resuelve.
- Por que importa.
- Dominios duenos.
- Dominios consumidores.
- Datos criticos.
- Estados principales.
- Eventos esperados.
- Integraciones.
- Impacto en auditoria.
- Impacto en Shadow Ledger.
- Impacto en CEC.
- Impacto en contador.
- Cost objects afectados.
- Riesgos C1/C2/C3.
- Gates.
- Metricas.
- Cortes ejecutables.
- Stop conditions.
- Que queda fuera.

Si un programa no puede responder esto, aun no esta listo para implementacion.

## 11. Programa 1 - Gobierno rector y continuidad

Proposito: evitar perdida de contexto, drift y tareas desconectadas.

Problema: Necktral es demasiado amplio para gobernarse por chats sueltos, PRs aislados o listas de features.

Dominios duenos: Governance, arquitectura, producto, Codex operating model.

Dominios consumidores: todos.

Datos criticos: Context Card, Operating Brief, Master Roadmap, Decision Log, ADR Register, Risk Register, Backlog Register.

Estados principales: `DRAFT`, `ACTIVE`, `SUPERSEDED`, `ARCHIVED`.

Eventos esperados: `governance.document.created`, `governance.decision.recorded`, `governance.roadmap.updated`.

Integraciones: docs, PRs, CI, handoffs, reviews.

Auditoria: cada cambio rector debe dejar commit/PR o decision log.

Shadow Ledger: no aplica directamente.

CEC: provee reglas de cierre para futuros programas.

Contador: recibe contexto de alcance, reportes y responsabilidades.

Cost objects: no aplica como costo operativo, pero define reglas de costeo.

Riesgos: C1 si Codex trabaja sin contexto; C2 si docs se vuelven decorativos.

Gates: no Codex sin leer Context Card y Operating Brief.

Metricas: tareas con scope correcto, PRs sin drift, decisiones registradas, stop conditions respetadas.

Cortes ejecutables:

- 1.1 Context Card.
- 1.2 Codex Operating Brief.
- 1.3 Master Roadmap.
- 1.4 Decision Log.
- 1.5 ADR/Risk/Backlog registers.

Stop conditions: roadmap contradictorio, decision sin owner, documento rector desactualizado.

Fuera de alcance: implementar modulos funcionales.

## 12. Programa 2 - Identity Backbone: Org + Party + Counterparty

Proposito: separar estructura interna de personas y contrapartes.

Problema: clientes, proveedores, empleados, declarantes y compradores no pueden vivir como texto ni como OrgUnit.

Dominios duenos: Org/IAM para scope; Party para identidad de negocio; RBAC para permisos.

Dominios consumidores: HR, Billing, Compras, Payments, Portfolio, CEC, Reporting.

Datos criticos: OrgUnit, CompanyProfile, BranchProfile, Party, CounterpartyRole, TaxProfile, PartyRelationship, NaturalPerson, LegalEntity.

Estados principales: `ACTIVE`, `INACTIVE`, `BLOCKED`, roles activos/inactivos.

Eventos esperados: `party.created.v1`, `party.updated.v1`, `party.role.assigned.v1`, `party.role.revoked.v1`, `hr.employee.linked_to_party.v1`.

Integraciones: HR Employee, Customer, Supplier, Producer, Declarant, ExternalBuyer, Accountant.

Auditoria: master data company-scoped, snapshots before/after, no eventos SYSTEM cuando hay company.

Shadow Ledger: no genera impacto economico por si mismo.

CEC: bloquea operaciones financieras sin contraparte cuando aplique.

Contador: reportes por RUC, persona, proveedor, cliente y declarante.

Cost objects: party, proveedor, cliente, trabajador, comprador externo.

Riesgos: C1 si OrgUnit se usa como Party; C1 si cartera se crea sobre texto.

Gates: PostgreSQL real, constraints por company, audit company-scoped, admin seguro, tests cross-company.

Metricas: % documentos con Party, % empleados vinculados a Party, duplicados por identificador.

Cortes ejecutables:

- 2.1 Auditoria repo.
- 2.2 Party base.
- 2.3 Counterparty roles.
- 2.4 Tax/RUC profile.
- 2.5 Employee -> Party.
- 2.6 Customer/Supplier compatibility.

Stop conditions: modelo equivalente no detectado, multiempresa ambigua, backfill destructivo.

Fuera de alcance: saldos, cartera, pagos, permisos RBAC.

## 13. Programa 3 - Financial Portfolio Kernel: CxC, CxP, Creditos

Proposito: controlar obligaciones, saldos, intereses, mora, vencimientos y revisiones.

Problema: financing sin cartera formal produce deuda tecnica financiera y reportes debiles.

Dominios duenos: Financial Portfolio, Financing.

Dominios consumidores: Billing, Payments, Compras, HR deductions, CEC, Accounting, Reporting.

Datos criticos: Obligation, Receivable, Payable, CreditFacility, CreditAgreement, Installment, InterestAccrual, Penalty, PaymentAllocation, Adjustment, Restructure, WriteOff, AccountantReview.

Estados principales: `DRAFT`, `OPEN`, `PARTIALLY_PAID`, `PAID`, `OVERDUE`, `RESTRUCTURED`, `WRITTEN_OFF`, `CANCELLED`.

Eventos esperados: `obligation.created.v1`, `receivable.created.v1`, `payable.created.v1`, `credit.disbursement.recorded.v1`, `interest.accrued.v1`, `payment.applied.v1`.

Integraciones: Party, Billing, Payments, Compras, Accounting, CEC.

Auditoria: toda creacion, ajuste, reestructuracion, castigo y aplicacion requiere audit.

Shadow Ledger: genera `EconomicEvent` y puede generar `JournalDraft` cuando hay impacto economico.

CEC: gates de saldos vencidos, pagos no aplicados, operaciones sin evidencia y accountant review pending.

Contador: aging, saldos, intereses, mora, creditos otorgados/recibidos, ajustes y castigos.

Cost objects: party, credito, periodo, finca/labor cuando aplique.

Riesgos: C1 por saldos incorrectos; C1 por confundir tender CREDIT con credito financiero.

Gates: idempotencia, invariantes de saldo, PostgreSQL real, pruebas de aplicacion y reversa.

Metricas: aging, mora, saldo vencido, pagos no aplicados, obligaciones sin evidencia.

Cortes ejecutables:

- 3.1 Obligation core.
- 3.2 Receivable base.
- 3.3 Payable base.
- 3.4 Payment allocation.
- 3.5 Credit facility.
- 3.6 Interest/mora.
- 3.7 Accountant aging reports.

Stop conditions: Party incompleto, reglas de interes no definidas, contador no valida reportes.

Fuera de alcance: facturacion, movimientos bancarios, contabilidad oficial.

## 14. Programa 4 - Money Movement: Payments, Cash, Bank, Settlement

Proposito: controlar dinero, conciliacion y aplicacion a obligaciones.

Problema: pagos sin aplicacion y settlement sin cierre rompen cartera y caja.

Dominios duenos: Payments/Cash/Bank.

Dominios consumidores: Billing, Portfolio, CEC, Accounting, Reporting.

Datos criticos: PaymentIntent, CashSession, CashMovement, BankMovement, TransferSettlement, UnappliedPayment, Refund/Reversal, PaymentAllocation.

Estados principales: `CREATED`, `CAPTURED`, `REVERSED`, `APPLIED`, `UNAPPLIED`, `FAILED`, `RECONCILED`.

Eventos esperados: `payment.captured.v1`, `payment.reversed.v1`, `cash.movement.posted.v1`, `bank.movement.recorded.v1`, `payment.applied.v1`.

Integraciones: Portfolio, Billing, Bank, Accounting, CEC.

Auditoria: pagos, reversas, cierres de caja y cambios de aplicacion.

Shadow Ledger: pagos y reversas economicas generan `EconomicEvent` y `JournalDraft` segun reglas.

CEC: cierre diario de caja, transfer settlement, pagos no aplicados, failed outbox.

Contador: pagos aplicados, no aplicados, reversas, conciliacion y caja/banco.

Cost objects: party, obligacion, caja/banco, periodo.

Riesgos: C1 por doble aplicacion, reversas incorrectas o caja descuadrada.

Gates: idempotencia, settlement read-only cuando aplica, PostgreSQL real, pruebas de reversa.

Metricas: pagos capturados, aplicados, reversados, no aplicados, diferencias de cierre.

Cortes ejecutables:

- 4.1 Cash + Transfer close gate.
- 4.2 Payment allocation to obligations.
- 4.3 Unapplied payments.
- 4.4 Bank movement import/manual capture.
- 4.5 Reconciliation snapshot.

Stop conditions: cartera no existe, reglas bancarias ambiguas, reversas no idempotentes.

Fuera de alcance: emitir facturas, crear deuda, contabilidad formal.

## 15. Programa 5 - Documents: Billing, Receipts, Credit Notes, Reversals

Proposito: conectar documentos con cartera, pagos, evidencia y contador.

Problema: documentos con cliente textual no soportan CxC, RUC, declarantes ni reportes confiables.

Dominios duenos: Billing/Fiscal Documents.

Dominios consumidores: Portfolio, Payments, CEC, Accounting, Reporting.

Datos criticos: BillingDocument, Receipt, CreditNote, Void, DocumentReversal, PaymentTerms, CustomerCounterparty, DocumentEvidence.

Estados principales: `DRAFT`, `ISSUED`, `VOIDED`, `REVERSED`, `PAID`, `PARTIALLY_PAID`.

Eventos esperados: `billing.document.created.v1`, `billing.document.issued.v1`, `billing.document.voided.v1`, `receipt.issued.v1`.

Integraciones: Party customer, Portfolio receivable, Payments, fiscal adapter futuro.

Auditoria: emision, anulacion, reversa, contingencia, cambio de customer link.

Shadow Ledger: documentos emitidos pueden generar `EconomicEvent` y `JournalDraft`.

CEC: documentos sin contraparte, sin evidencia o con estado inconsistente bloquean cierre.

Contador: ventas, cobros, facturas, notas, RUC, comprador, pendientes.

Cost objects: cliente, venta, periodo, sucursal.

Riesgos: C1 por fiscalidad; C1 por confundir documento con saldo.

Gates: customer Party, idempotencia de documentos, reglas fiscales, pruebas de void/reversal.

Metricas: documentos emitidos/anulados, documentos sin Party, aging por documento.

Cortes ejecutables:

- 5.1 Customer counterparty link.
- 5.2 Document -> receivable.
- 5.3 Credit note / reversal.
- 5.4 Receipt package.
- 5.5 Fiscal adapter readiness.

Stop conditions: cliente fuerte inexistente, reglas fiscales no definidas, cartera no lista.

Fuera de alcance: cash movement, saldo canonico, contabilidad oficial.

## 16. Programa 6 - Supply Chain: Inventory, Purchasing, Suppliers, Cost

Proposito: controlar stock, compras, insumos, proveedores y costo.

Problema: compras/proveedores sin Party ni CxP no soportan deuda, credito agroquimico ni costeo.

Dominios duenos: Inventory/Cost, Purchasing.

Dominios consumidores: Work Planning, Fleet, Portfolio, Accounting, CEC, Reporting.

Datos criticos: Supplier, PurchaseOrder, SupplierInvoice, GoodsReceipt, Warehouse, StockMovement, StockBalance, InternalTransfer, Consumption, CostAllocation, CostPolicy.

Estados principales: `REQUESTED`, `ORDERED`, `RECEIVED`, `INVOICED`, `CONSUMED`, `TRANSFERRED`, `ADJUSTED`.

Eventos esperados: `purchase.created.v1`, `goods.received.v1`, `supplier.invoice.recorded.v1`, `stock.moved.v1`, `inventory.consumed.v1`.

Integraciones: Party supplier, Portfolio payable, Work Planning, Fleet, Accounting.

Auditoria: recepcion, ajustes, transferencias, consumos, factura proveedor.

Shadow Ledger: facturas proveedor y consumo/costo pueden generar hechos economicos.

CEC: stock negativo, documentos sin proveedor, consumos sin cost object, CxP sin evidencia.

Contador: inventario recibido/consumido, proveedores, CxP, costos.

Cost objects: finca, zona, labor, insumo, proveedor, bodega, periodo.

Riesgos: C1 por stock/costo incorrecto; C1 por CxP sin proveedor.

Gates: supplier Party, constraints stock, cost policy, tests de consumo y transferencia.

Metricas: stock, consumo por labor, costo promedio/capa, proveedores sin Party.

Cortes ejecutables:

- 6.1 Supplier role.
- 6.2 Purchase/receipt base.
- 6.3 Supplier invoice -> payable.
- 6.4 Consumption by cost object.
- 6.5 Internal transfers.
- 6.6 Cost policy.

Stop conditions: cost object no definido, proveedor debil, reglas de costo no definidas.

Fuera de alcance: pagos, cartera canonica, contabilidad formal.

## 17. Programa 7 - Workforce: HR, Payroll, Attendance, Crews

Proposito: controlar personal, asistencia, asignaciones y costos laborales.

Problema: sin workforce backbone no se puede costear finca/zona/labor ni cerrar nomina.

Dominios duenos: HR, Payroll, Attendance.

Dominios consumidores: Work Planning, Costing, Payments, Portfolio, CEC, Reporting.

Datos criticos: Employee, EmploymentAssignment, Attendance, Shift, Crew, Supervisor, WorkerAssignment, PayrollRun, PayrollLine, Deduction, Advance, EmployeeLoan.

Estados principales: `ACTIVE`, `INACTIVE`, `ASSIGNED`, `PRESENT`, `ABSENT`, `APPROVED`, `PAID`, `CLOSED`.

Eventos esperados: `hr.employee.created.v1`, `hr.employee.linked_to_party.v1`, `attendance.recorded.v1`, `payroll.run.closed.v1`, `deduction.applied.v1`.

Integraciones: Party, RBAC, Work Planning, Payments, Portfolio, CEC.

Auditoria: employee changes, attendance, payroll close, deductions, advances.

Shadow Ledger: payroll closed and paid can create economic facts.

CEC: asistencia incompleta, nomina sin aprobacion, deducciones sin evidencia.

Contador: nomina, deducciones, adelantos, pagos, costos laborales.

Cost objects: empleado, cuadrilla, finca, zona, labor, periodo.

Riesgos: C1 por nomina; C2 por HR operacional.

Gates: Employee -> Party, no RBAC drift, attendance policy, payroll approval.

Metricas: asistencia, costo laboral, productividad por cuadrilla, deducciones pendientes.

Cortes ejecutables:

- 7.1 Employee -> Party.
- 7.2 Assignment by org/cost object.
- 7.3 Attendance base.
- 7.4 Payroll base.
- 7.5 Deductions/advances.
- 7.6 Crews and supervisors.

Stop conditions: RRHH no define jornadas, Party no aprobado, payroll formulas ambiguas.

Fuera de alcance: cartera general, contabilidad oficial, Work Planning tecnico.

## 18. Programa 8 - Work Planning: Annual Plans, Zones, Labor Tasks

Proposito: planificar, ejecutar y medir labores por finca/zona/labor.

Problema: sin plan de trabajo no hay control de avance, insumos, personal ni costo real.

Dominios duenos: Work Planning.

Dominios consumidores: HR, Inventory, Fleet, Costing, CEC, Reporting.

Datos criticos: ProductionUnit, Zone, AnnualWorkPlan, MonthlyWorkCalendar, LaborType, WorkTask, RequiredInputs, RequiredWorkforce, RequiredEquipment, TaskExecution, ProgressReport, CostVariance.

Estados principales: `PLANNED`, `SCHEDULED`, `IN_PROGRESS`, `COMPLETED`, `BLOCKED`, `CANCELLED`, `REWORK_REQUIRED`.

Eventos esperados: `work.plan.created.v1`, `work.task.scheduled.v1`, `work.task.completed.v1`, `work.cost.allocated.v1`.

Integraciones: HR/Attendance, Inventory consumption, Fleet, Cost Backbone, CEC.

Auditoria: cambios de plan, ejecucion, aprobaciones, evidencia de avance.

Shadow Ledger: no directo salvo consumo/costo o obligaciones asociadas.

CEC: tareas sin evidencia, consumo sin tarea, avance no aprobado.

Contador: costos por finca/zona/labor, productividad, variaciones.

Cost objects: finca, zona, labor, cuadrilla, insumo, equipo, periodo.

Riesgos: C1 si costos quedan sin asignacion; C2 si catalogo tecnico no validado.

Gates: personalization con ingenieros, catalogo de labores, cost objects.

Metricas: avance, costo plan vs real, productividad, tareas bloqueadas.

Cortes ejecutables:

- 8.1 ProductionUnit/Zone.
- 8.2 Labor catalog.
- 8.3 Annual plan.
- 8.4 Monthly calendar.
- 8.5 Task execution.
- 8.6 Input/workforce/equipment consumption.
- 8.7 Cost actualization.

Stop conditions: agronomia no valida labores, cost object ausente, inventario/HR no integrables.

Fuera de alcance: inventario maestro, pagos, contabilidad formal.

## 19. Programa 9 - Asset Operations: Fleet, Maintenance, Machinery

Proposito: medir activos, mantenimiento, combustible, viajes y costos.

Problema: flota y maquinaria sin control rompen costos por finca/labor y mantenimiento preventivo.

Dominios duenos: Fleet/Maintenance.

Dominios consumidores: Work Planning, Inventory, Payments, Costing, CEC, Reporting.

Datos criticos: FleetAsset, Vehicle, Machine, MaintenancePlan, MaintenanceOrder, FuelConsumption, TripLog, DriverAssignment, SparePartUsage, InsuranceDocument, ServiceProvider, CostAllocation.

Estados principales: `ACTIVE`, `IN_SERVICE`, `MAINTENANCE_DUE`, `IN_MAINTENANCE`, `OUT_OF_SERVICE`, `RETIRED`.

Eventos esperados: `fleet.asset.created.v1`, `fleet.maintenance.scheduled.v1`, `fleet.maintenance.completed.v1`, `fleet.fuel.consumed.v1`, `fleet.trip.completed.v1`.

Integraciones: Party service provider, Inventory spare parts, Payments, Work Planning.

Auditoria: mantenimiento, combustible, viajes, cambios de activo.

Shadow Ledger: costos y obligaciones asociadas pueden generar hechos economicos via compras/pagos.

CEC: mantenimiento vencido, combustible sin evidencia, costo sin asignacion.

Contador: flota, mantenimiento, combustible, proveedores, costos por activo.

Cost objects: vehiculo, maquinaria, finca, labor, viaje, periodo.

Riesgos: C1 por costos sin evidencia; C2 por mantenimiento incompleto.

Gates: asset registry, odometro/horometro, evidence policy, supplier Party.

Metricas: costo/km, costo/hora, mantenimientos vencidos, consumo combustible.

Cortes ejecutables:

- 9.1 Fleet asset registry.
- 9.2 Maintenance plan.
- 9.3 Maintenance order.
- 9.4 Fuel consumption.
- 9.5 Trip logs.
- 9.6 Spare part usage.
- 9.7 Cost allocation.

Stop conditions: flota no define metrica base, repuestos sin inventory, proveedor debil.

Fuera de alcance: inventario maestro, pagos, nomina conductor.

## 20. Programa 10 - Productive Verticals: Hacienda, Ganado, Agro, Transporte

Proposito: modelar verticales sin romper kernels.

Problema: verticales productivos pueden capturar operacion real, pero si poseen cartera, pagos, inventario o contabilidad generan deuda estructural.

Dominios duenos: cada vertical posee hechos productivos; los kernels poseen identidad, dinero, stock, costos, cierre y contabilidad auxiliar.

Dominios consumidores: Work Planning, Inventory, HR, Fleet, Portfolio, CEC, Reporting.

Datos criticos: Hacienda operations, Cattle operations, Agrochemical operations, Transport services, Machinery services, Production cycles, Quality records, Operational KPIs.

Estados principales: `ACTIVE`, `IN_PROGRESS`, `COMPLETED`, `CLOSED`, `BLOCKED`.

Eventos esperados: `production.cycle.started.v1`, `cattle.lot.updated.v1`, `agrochemical.applied.v1`, `transport.service.completed.v1`, `quality.recorded.v1`.

Integraciones: Party, HR, Inventory, Fleet, Work Planning, CxC/CxP, CEC, Accounting projection.

Auditoria: operaciones productivas, calidad, evidencia, aprobaciones.

Shadow Ledger: indirecto por costos, ventas, consumos y obligaciones.

CEC: cierre por finca, cosecha, ganado, produccion y excepciones.

Contador: paquetes por finca, produccion, costo, proveedor, comprador y periodo.

Cost objects: finca, hato/lote, labor, insumo, activo, comprador, periodo.

Riesgos: C1 si vertical sustituye kernels; C2 si se implementa sin contador/ingenieros.

Gates: kernels base, personalization, cost objects, evidence policy.

Metricas: productividad, costo/ciclo, calidad, merma, margen operativo.

Cortes ejecutables:

- 10.1 Hacienda vertical shell.
- 10.2 Ganado by herd/lot.
- 10.3 Agrochemical operational flow.
- 10.4 Transport service flow.
- 10.5 Quality/production records.

Stop conditions: contador/ingenieros no validan flujo, kernels base faltan.

Fuera de alcance: cartera, pagos, inventario maestro, contabilidad final.

## 21. Programa 11 - Control Plane: CEC, Accountant Package, Reporting

Proposito: cerrar, evidenciar y reportar todo.

Problema: sin control plane, los datos operativos no se convierten en cierre revisable ni soporte para contador.

Dominios duenos: CEC, Reporting, Accountant Package.

Dominios consumidores: todos los dominios operativos y financieros.

Datos criticos: CloseRun, CloseGate, EvidencePackage, AccountantPackage, ExceptionCase, ReviewStatus, OperationalSnapshot, FinancialSnapshot, ReportExport.

Estados principales: `OPEN`, `PENDING_EVIDENCE`, `PENDING_ACCOUNTANT_REVIEW`, `APPROVED`, `RECLASSIFICATION_REQUIRED`, `BLOCKED`, `CLOSED`.

Eventos esperados: `cec.close.started.v1`, `cec.exception.raised.v1`, `cec.evidence.attached.v1`, `accountant.review.requested.v1`, `accountant.package.closed.v1`.

Integraciones: Portfolio, Payments, Billing, Inventory, HR, Fleet, Work Planning, Accounting.

Auditoria: todo gate, excepcion, evidencia, revision y cierre.

Shadow Ledger: valida drafts, exceptions, economic events and summaries.

CEC: es el programa dueno.

Contador: paquete mensual/ciclo, reportes por RUC/persona/proveedor/cliente/finca.

Cost objects: todos los objetos de costo consolidados.

Riesgos: C1 si cierre aprueba datos incompletos; C1 si contador reconstruye manualmente.

Gates: evidence required, no Party block, draft exception block, accountant review status.

Metricas: excepciones abiertas, cierres a tiempo, operaciones sin evidencia, drafts exception.

Cortes ejecutables:

- 11.1 Accountant package v1.
- 11.2 Close gates by domain.
- 11.3 Exception management.
- 11.4 Evidence registry.
- 11.5 Report exports.
- 11.6 Consolidated group dashboard.

Stop conditions: dominios no emiten evidencia, datos sin Party/cost object, contador no valida reportes.

Fuera de alcance: corregir datos primarios, crear hechos economicos.

## 22. Programa 12 - Platform Hardening: Security, Sync, Frontend, Observability, IA

Proposito: hacer Necktral confiable, seguro, observable y escalable.

Problema: una plataforma operacional critica no puede depender de QA manual, contratos fragiles o sincronizacion insegura.

Dominios duenos: Platform Reliability, Security, Sync, Observability, Release.

Dominios consumidores: todos.

Datos criticos: Audit chain, SoD, Sync commands, Device identity, Outbox/Inbox contracts, OpenAPI/TypeScript drift, health metrics, backups, AI tool registry futuro.

Estados principales: `HEALTHY`, `DEGRADED`, `BLOCKED`, `RELEASE_READY`, `ROLLBACK_REQUIRED`.

Eventos esperados: `security.finding.recorded.v1`, `sync.batch.received.v1`, `outbox.failed.v1`, `release.gate.passed.v1`, `ai.tool.invoked.v1`.

Integraciones: CI, QA gates, release, device enrollment, observability.

Auditoria: security changes, sync commands, release gates, privileged actions.

Shadow Ledger: sync/offline must preserve economic invariants.

CEC: puede bloquear cierres por outbox failed, sync lag, missing evidence.

Contador: recibe datos confiables solo si la plataforma sostiene integridad.

Cost objects: no aplica directo, salvo costos de operacion tecnica.

Riesgos: C1 por seguridad, sync, datos offline, supply chain.

Gates: security CI, dependency checks, sync invariant tests, backup/recovery, observability.

Metricas: CI pass rate, drift, failed outbox, sync lag, audit integrity, recovery time.

Cortes ejecutables:

- 12.1 Security baseline.
- 12.2 Sync/offline economic invariants.
- 12.3 Observability/health metrics.
- 12.4 Backup/recovery.
- 12.5 Frontend contract tests.
- 12.6 AI tool guardrails.
- 12.7 Microservice readiness gates.

Stop conditions: secrets leak, sync breaks economic invariants, audit chain failure, CI blocking.

Fuera de alcance: reemplazar dominios funcionales.

## 23. Dependencias entre programas

Dependencias duras:

- Portfolio depende de Party.
- Billing -> CxC depende de Party y Portfolio.
- Compras -> CxP depende de Party y Portfolio.
- Payroll depende de HR/Attendance.
- Work Planning depende de ProductionUnit/Zone, HR, Inventory y Cost Backbone.
- Fleet cost allocation depende de FleetAsset, cost objects e Inventory/Payments cuando aplique.
- Verticales productivos dependen de Identity, Work Planning, Inventory, HR, Fleet, Portfolio y CEC.
- Accountant Package depende de CEC, evidence, Portfolio, Payments, Billing, Inventory, HR y Accounting projection.

Regla: si una dependencia dura falta, el corte debe ser ASK ONLY o preparatorio, no implementacion completa.

## 24. Oleadas de construccion

No son fechas. Son niveles de madurez.

Oleada 1 - Columna vertebral:

- Context + Codex Brief + Master Roadmap.
- Party/Counterparty.
- Cartera obligations.
- Employee -> Party.
- Supplier/Customer roles.

Oleada 2 - Dinero y documentos:

- CxC/CxP base.
- Payments allocation.
- Billing -> CxC.
- Supplier invoice -> CxP.
- Cash + Transfer close.

Oleada 3 - Operacion laboral y costos:

- Attendance.
- Payroll base.
- Work planning base.
- Inventory consumption.
- Cost objects.

Oleada 4 - Activos y verticales:

- Fleet registry.
- Maintenance plans.
- Trip/fuel logs.
- Hacienda vertical.
- Ganado vertical.
- Agrochemical flow.

Oleada 5 - Cierre y contador:

- CEC close gates.
- Accountant package.
- Evidence package.
- Reports.
- Exception management.

Oleada 6 - Plataforma avanzada:

- Sync/offline.
- Security hardening.
- Observability.
- Frontend readiness.
- AI tool governance.
- Microservice gates.

## 25. Gates transversales

Gates de datos:

- owner de verdad definido;
- FK fuerte donde corresponde;
- multiempresa probado;
- backfill aprobado si aplica.

Gates economicos:

- `AuditEvent`;
- `OutboxEvent`;
- `EconomicEvent`;
- `JournalDraft`;
- idempotencia;
- rollback;
- evidencia.

Gates de cierre:

- CloseRun impactado;
- CEC gate definido;
- exception policy;
- accountant review status.

Gates de QA:

- tests unitarios/servicios/API;
- PostgreSQL real para persistencia;
- `makemigrations --check`;
- `migrate --plan`;
- `git diff --check`;
- Reviewer Agent.

Gates de producto:

- personalization gate cuando el dominio dependa de contador, ingenieros, RRHH, flota, finanzas u operacion;
- no-goals declarados;
- stop conditions declaradas.

## 26. Metricas de madurez

Madurez 0 - Texto y operacion manual:

- datos clave en texto;
- sin cierre;
- sin evidencia consistente.

Madurez 1 - Identidad y scope:

- company/branch correctos;
- Party/Counterparty;
- roles de negocio.

Madurez 2 - Operacion transaccional:

- servicios auditados;
- constraints DB;
- tests PostgreSQL;
- APIs company-scoped.

Madurez 3 - Backbone financiero/costos:

- obligaciones;
- pagos aplicados;
- costos por objeto;
- inventario/nomina/flota conectados.

Madurez 4 - Cierre y contador:

- CEC gates;
- AccountantPackage;
- EvidencePackage;
- reportes revisables.

Madurez 5 - Plataforma avanzada:

- sync/offline confiable;
- observabilidad;
- seguridad madura;
- release gates;
- readiness para separacion de servicios si aplica.

## 27. Reglas para Codex

Codex debe:

- leer Context Card, Operating Brief y este roadmap;
- verificar repo/worktree;
- declarar programa afectado;
- declarar owner de verdad;
- declarar contratos e invariantes;
- usar ASK ONLY si el dominio no esta claro;
- implementar solo cortes aprobados;
- reportar QA real;
- detenerse ante stop condition.

Codex no debe:

- convertir este roadmap en permiso para implementar todo;
- crear microfrentes;
- saltar personalization gates;
- usar GitHub como objetivo;
- tocar dominios prohibidos;
- mezclar ramas tecnicas con docs rectores;
- aprobar C1 sin PostgreSQL real cuando hay persistencia.

## 28. Parking lot

Temas reconocidos pero no listos para ejecucion:

- fiscalidad final por RUC/persona/declarante;
- estrategia de microfinanciera completa;
- reglas exactas de interes, mora, garantias y castigos;
- catalogo tecnico agricola definitivo;
- modelo de calidad/beneficiado de cafe;
- calculo completo de nomina;
- formulas de productividad por finca/zona/labor;
- reglas de costo contable vs costo operativo;
- integracion bancaria automatica;
- Sync economico offline completo;
- AI tool registry y governance futura;
- microservices readiness.

## 29. Estado operativo

Este roadmap es direccion. No crea modelos, APIs, migraciones ni permisos. Cada programa debe convertirse en cortes ejecutables pequenos, revisables y probados.

Siguiente documento rector recomendado: `docs/project/NECKTRAL_DECISION_LOG.md`.
