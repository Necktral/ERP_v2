from __future__ import annotations

from dataclasses import dataclass

from django.db import transaction

from apps.modulos.rbac.models import Permission, Role, RolePermission


@dataclass(frozen=True)
class SeedResult:
    roles_created: int
    roles_updated: int
    perms_created: int
    perms_updated: int
    roleperms_created: int


def seed_rbac_v01() -> SeedResult:
    """
    Catálogo estándar v0.1 (robusto, modular, extensible).
    - Idempotente (get_or_create + updates)
    - No borra cosas existentes.
    """

    roles = {
        "company_admin": "Administrador global dentro de la empresa (RBAC + ORG + HR + reportes).",
        "branch_manager": "Administrador de sucursal.",
        "hr_manager": "Gestión completa de RRHH.",
        "hr_clerk": "Operación RRHH (altas/bajas/edición), sin RBAC.",
        "auditor": "Lectura de auditoría y reportes.",
        "controls_officer": "Oficial de control interno: reglas SoD y hallazgos anti-fraude.",
        "warehouse_manager": "Gestión de inventario (placeholder).",
        "warehouse_operator": "Operación inventario (placeholder).",
        "sales_manager": "Gestión comercial (placeholder).",
        "sales_rep": "Operación ventas (placeholder).",
        "cashier": "Caja (placeholder).",
        "billing_manager": "Gestión de facturación (kernel).",
        "procurement_manager": "Gestión de compras/procurement (kernel).",
        "payroll_manager": "Planillero: opera planilla y asistencia de campo con SoD anti autoaprobación.",
        "sync_admin": "Administración de Sync (enroll/revoke) (placeholder).",

        # FUEL (Estación de Servicios)
        "fuel_admin": "Administrador del módulo Estación de Servicios (todo dentro de la empresa).",
        "fuel_supervisor": "Supervisor Estación (cierres, precios, recibos, conciliaciones).",
        "fuel_cashier": "Cajero/operador Estación (ventas/dispenses; sin precios ni ajustes).",
        "fuel_auditor": "Auditor Estación (solo lectura de operación y reportes).",

        # NOMINA / Asistencia de campo
        "field_supervisor": "Supervisor de campo: revisa/aprueba asistencia de cuadrillas con segregación de funciones.",

        # FLEET / Mantenimiento
        "fleet_driver": "Conductor: checklists y reportes de campo (app).",
        "fleet_mechanic": "Mecánico: ejecuta mantenimiento y atiende defectos.",
        "fleet_supervisor": "Supervisor de flota: recibe alertas, gestiona planes y documentos.",
        "fleet_manager": "Gerente de flota: configuración y análisis.",
        "fleet_clerk": "Bodega/registro de flota.",

        # FINCA / Manejo de fincas (agrícola)
        "finca_mandador": "Mandador / Administrador de Finca: coordina finca, personal, labores, insumos y bitácora agrícola.",
        "finca_capataz": "Capataz: supervisa cuadrillas, registra labores ejecutadas, asistencia e insumos en campo.",
        "finca_tecnico": "Ingeniero/Técnico Agrónomo: asesor técnico — ve todo y define el plan de labores (fertilización/plagas); NO captura ejecución diaria ni postea costos.",
    }

    permissions = {
        # ORG
        "org.company.create": "Crear empresas (COMPANY) bajo el holding",
        "org.company.read": "Ver datos de empresa.",
        "org.company.update": "Actualizar datos de empresa.",
        "org.branch.read": "Ver sucursales.",
        "org.branch.create": "Crear sucursales.",
        "org.branch.update": "Actualizar sucursales.",
        "org.module.read": "Ver módulos habilitados de la empresa.",
        "org.module.manage": "Habilitar/deshabilitar módulos de la empresa.",
        # IAM
        "iam.users.create": "Crear usuarios del sistema (provisionar acceso a empleados).",
        # HR
        "hr.position.read": "Ver puestos.",
        "hr.position.create": "Crear puestos.",
        "hr.position.update": "Actualizar puestos.",
        "hr.position.roles.update": "Actualizar mapeo Puesto->Roles.",
        "hr.employee.read": "Ver empleados.",
        "hr.employee.create": "Crear empleados.",
        "hr.employee.update": "Actualizar empleados.",
        "hr.assignment.read": "Ver asignaciones laborales.",
        "hr.assignment.create": "Crear asignaciones laborales.",
        "hr.assignment.end": "Finalizar asignaciones laborales.",
        # NOMINA (planilla) — los views ya los exigían; faltaban en el seed
        "nomina.config.read": "Ver configuración de nómina (tasas/IR).",
        "nomina.config.manage": "Crear/actualizar configuración de nómina y tabla IR.",
        "nomina.period.read": "Ver períodos de planilla.",
        "nomina.period.create": "Crear períodos de planilla.",
        "nomina.sheet.read": "Ver planillas/sub-planillas.",
        "nomina.sheet.create": "Crear planillas/sub-planillas.",
        "nomina.sheet.manage": "Enviar/aprobar planillas.",
        "nomina.entry.read": "Ver líneas de planilla.",
        "nomina.entry.create": "Crear/calcular líneas de planilla.",
        "nomina.inss.read": "Ver régimen/elección INSS.",
        "nomina.inss.manage": "Gestionar afiliación y elección INSS por período.",
        "nomina.period.approve.request": "Solicitar aprobación de período (maker, SoD).",
        "nomina.period.approve": "Aprobar período de planilla (checker, SoD).",
        # NOMINA — Asistencia de campo (Field Attendance)
        "nomina.field.read": "Ver asistencia de campo (días, cuadrillas, consolidación).",
        "nomina.field.capture": "Capturar asistencia de campo (lista, cuadrilla, reporte, evento, traslado).",
        "nomina.field.consolidate": "Consolidar la asistencia de campo del día.",
        "nomina.field.approve.request": "Solicitar aprobación de asistencia de campo (maker, SoD).",
        "nomina.field.approve": "Aprobar asistencia de campo (checker, SoD).",
        "nomina.field.apply": "Aplicar asistencia aprobada a la planilla.",
        # RBAC (para UI admin futura)
        "rbac.roles.read": "Ver roles.",
        "rbac.roles.update": "Actualizar roles.",
        "rbac.permissions.read": "Ver permisos.",
        "rbac.permissions.update": "Actualizar permisos.",
        "rbac.assignments.read": "Ver asignaciones de roles.",
        "rbac.assignments.update": "Actualizar asignaciones de roles.",
        # Auditoría
        "audit.read": "Leer auditoría.",
        "audit.export": "Exportar auditoría.",
        # Controls (Capa 3: anti-fraude / SoD)
        "controls.sod.read": "Ver matriz SoD y violaciones por concesión.",
        "controls.sod.manage": "Gestionar reglas de segregación de funciones.",
        "controls.findings.read": "Ver hallazgos de control.",
        "controls.findings.manage": "Correr detectores y resolver hallazgos.",
        # Finca (manejo de fincas)
        "finca.finca.read": "Ver fincas y su geografía.",
        "finca.finca.manage": "Gestionar perfil/geografía de fincas.",
        "finca.plot.read": "Ver lotes.",
        "finca.plot.manage": "Crear/actualizar lotes.",
        "finca.labor.read": "Ver catálogo de labores.",
        "finca.labor.manage": "Gestionar catálogo de labores.",
        "finca.work.read": "Ver órdenes de trabajo / bitácora.",
        "finca.work.capture": "Registrar labores ejecutadas e insumos.",
        "finca.report.read": "Ver costeo de fincas/lotes.",
        "finca.field.read": "Ver costeo real desde asistencia de campo y reconciliación.",
        "finca.cost.post": "Postear (reclasificar) el costo real de la finca al GL.",
        # Sync (placeholder)
        "sync.device.enroll": "Enrolar dispositivos.",
        "sync.device.revoke": "Revocar dispositivos.",
        "sync.batch.receive": "Recibir lotes de sync.",
        # --- Inventario (kernels) ---
        "inventory.item.read": "Ver items del inventario.",
        "inventory.item.create": "Crear items del inventario.",
        "inventory.item.update": "Actualizar items del inventario.",
        "inventory.warehouse.read": "Ver almacenes/bodegas.",
        "inventory.warehouse.create": "Crear almacenes/bodegas.",
        "inventory.lot.read": "Ver lotes de inventario.",
        "inventory.lot.create": "Crear lotes de inventario.",
        "inventory.balance.read": "Ver existencias y costo promedio.",
        "inventory.movement.read": "Ver movimientos de inventario.",
        "inventory.movement.receive": "Registrar entradas/recepciones de inventario.",
        "inventory.movement.issue": "Registrar salidas/consumos de inventario.",
        "inventory.movement.adjust": "Registrar ajustes de inventario.",
        "inventory.transfer.create": "Registrar transferencias entre almacenes.",
        "inventory.movement.post": "Registrar/mayorizar movimientos de inventario.",
        "inventory.adjustment.create": "Crear ajustes de inventario.",

        # --- Facturación (kernels) ---
        "billing.customer.read": "Ver clientes.",
        "billing.customer.create": "Crear clientes.",
        "billing.customer.update": "Actualizar clientes.",
        "billing.invoice.read": "Ver facturas.",
        "billing.invoice.create": "Crear facturas (draft).",
        "billing.invoice.issue": "Emitir facturas.",
        "billing.invoice.void": "Anular facturas.",
        "billing.doc.read": "Ver documentos de facturación (kernel).",
        "billing.doc.create": "Crear documentos de facturación (kernel).",
        "billing.doc.issue": "Emitir documentos de facturación (kernel).",
        "billing.doc.void": "Anular documentos de facturación (kernel).",
        "billing.fiscal.config.read": "Ver configuración fiscal por sucursal.",
        "billing.fiscal.config.update": "Actualizar configuración fiscal por sucursal.",
        "billing.doc.print": "Solicitar impresión fiscal de documento.",
        "billing.doc.contingency": "Registrar contingencia fiscal sobre documento.",
        "billing.doc.contingency.resolve": "Resolver contingencia fiscal por reintento o anulación.",
        # --- Payments & Cash (core module) ---
        "payments.intent.read": "Ver intents de pago.",
        "payments.intent.create": "Crear intents de pago.",
        "payments.cash_session.read": "Ver sesiones de caja.",
        "payments.cash_session.open": "Abrir sesión de caja.",
        "payments.cash_session.close": "Cerrar sesión de caja.",
        "payments.cash_movement.create": "Registrar movimiento de caja.",
        # --- CEC Control Plane (core module) ---
        "cec.close_run.read": "Ver cierres CEC.",
        "cec.close_run.create": "Crear corridas de cierre CEC.",
        "cec.close_run.update": "Actualizar estado de corridas de cierre CEC.",
        "cec.exception.read": "Ver excepciones CEC.",
        "cec.exception.create": "Crear excepciones CEC.",
        "cec.exception.resolve": "Resolver excepciones CEC.",
        "cec.evidence.create": "Registrar evidencia en CEC.",
        # --- Integration Backbone (core module) ---
        "integration.outbox.read": "Ver outbox canónico.",
        "integration.outbox.publish": "Marcar/publish outbox canónico.",
        "integration.inbox.read": "Ver inbox canónico.",
        "integration.inbox.process": "Procesar/ack inbox canónico.",
        # --- Accounting kernel ---
        "accounting.journal_draft.read": "Ver journal drafts contables.",
        "accounting.journal_draft.approve": "Aprobar journal drafts validados para posting.",
        "accounting.journal_draft.post": "Ejecutar posting de journal drafts a journal entries.",
        "accounting.journal_entry.read": "Ver journal entries posteados.",
        "accounting.journal_entry.reverse": "Generar reversa contable de journal entry.",
        "accounting.journal_entry.reverse_batch": "Ejecutar reversa contable masiva.",
        "accounting.period.read": "Ver periodos fiscales contables.",
        "accounting.period.close": "Cerrar periodo fiscal contable.",
        "accounting.period.reopen": "Reabrir periodo fiscal contable cerrado (CLOSED -> OPEN).",
        "accounting.sod.override": "Override excepcional de segregación de funciones en contabilidad.",
        "accounting.coa.read": "Ver catálogo contable (Chart of Accounts).",
        "accounting.coa.update": "Actualizar catálogo contable y configuración GL por compañía.",
        "accounting.fx_rate.read": "Ver tasas FX contables.",
        "accounting.fx_rate.update": "Crear/actualizar tasas FX contables.",
        "accounting.report.read": "Ver reportes financieros formales (Trial Balance, GL, PnL, Balance Sheet).",
        "accounting.revaluation.run": "Ejecutar corrida de revaluación FX.",
        "accounting.intercompany.read": "Ver ciclo intercompany transaccional.",
        "accounting.intercompany.write": "Crear/confirmar/cerrar transacciones intercompany.",
        "accounting.intercompany.reconcile": "Conciliar transacciones intercompany (matching/diferencias/disputa).",
        "accounting.intercompany.dispute": "Abrir disputa formal intercompany.",
        "accounting.intercompany.settle": "Resolver disputa y liquidar/cerrar transacción intercompany.",
        "accounting.consolidation.read": "Ver corridas y reportes de consolidación multi-compañía.",
        "accounting.consolidation.run": "Ejecutar cierre y consolidación financiera multi-compañía.",
        # --- Reporting kernel ---
        "report.catalog.read": "Ver catálogo de datasets certificados.",
        "report.dataset.read": "Ejecutar datasets del reporting kernel.",
        "report.dataset.export": "Exportar resultados de datasets.",
        "report.run.read": "Ver historial de ejecuciones de reporting.",
        "report.snapshot.generate": "Generar snapshots manuales de reporting.",
        "report.definition.manage": "Gestionar definiciones y metadatos de datasets.",
        "report.dashboard.read": "Ver dashboards y vistas guardadas de reporting.",
        "report.dashboard.compose": "Crear y gestionar vistas guardadas para dashboards.",
        # --- Nómina field capture / AttendanceReport ---
        "nomina.field.manage": "Gestionar cuadrillas de campo.",
        "nomina.attendance.read": "Ver reportes de asistencia derivados.",
        "nomina.attendance.review": "Solicitar revisión/aprobación de asistencia de campo.",
        "nomina.attendance.approve": "Aprobar asistencia de campo como checker SoD.",
        "nomina.attendance.build": "Materializar AttendanceReport desde captura aprobada.",

        # --- Compat / legacy (tests + transición) ---
        # Nota: se conservan porque varios tests usan estos códigos como canary de RBAC.
        "inventory.read": "Lectura inventario (legacy/compat).",
        "inventory.write": "Escritura inventario (legacy/compat).",
        "clients.read": "Lectura clientes (legacy/compat).",
        "clients.write": "Escritura clientes (legacy/compat).",
        "reports.view": "Ver reportes (legacy/compat).",
        "reports.export": "Exportar reportes (legacy/compat).",

        # FUEL (Estación de Servicios)
        "fuel.config.read": "Leer configuración de estación.",
        "fuel.config.update": "Actualizar configuración de estación.",
        "fuel.shift.open": "Abrir turno.",
        "fuel.shift.close": "Cerrar turno.",
        "fuel.shift.read": "Ver turnos.",
        "fuel.dispense.create": "Registrar despacho (evento físico).",
        "fuel.dispense.read": "Ver despachos (evento físico).",
        "fuel.dispense.void": "Anular despacho.",
        "fuel.sale.create": "Crear venta.",
        "fuel.sale.read": "Ver ventas.",
        "fuel.sale.void": "Anular venta.",
        "fuel.price.read": "Ver precios.",
        "fuel.price.update": "Actualizar precios.",
        "fuel.tank.read": "Ver tanques.",
        "fuel.tank.receive": "Registrar recepción/descarga a tanque.",
        "fuel.tank.adjust": "Registrar ajustes de tanque (merma/derrame/calibración).",
        "fuel.reconcile.view": "Ver conciliaciones y variaciones.",
        "fuel.reconcile.post": "Registrar conciliación.",
        "fuel.outbox.read": "Ver outbox intercompany.",
        "fuel.outbox.reprocess": "Reprocesar outbox intercompany.",
        "fuel.reports.view": "Ver reportes del módulo Estación.",
        "fuel.reports.export": "Exportar reportes del módulo Estación.",
        "fuel.uom_preferences.manage": "Gestionar preferencias UOM de combustible.",
        # RETAIL POS
        "retail.pos.session.open": "Abrir sesión POS por sucursal.",
        "retail.pos.session.read": "Ver sesión POS activa y estado de caja.",
        "retail.pos.session.close": "Cerrar sesión POS y arqueo.",
        "retail.pos.ticket.open": "Crear ticket POS.",
        "retail.pos.ticket.read": "Ver tickets POS.",
        "retail.pos.ticket.checkout": "Ejecutar checkout POS.",
        "retail.pos.ticket.void": "Anular ticket POS.",
        "retail.pos.peripherals.read": "Ver estado de periféricos POS.",
        "retail.pos.peripherals.manage": "Registrar/actualizar estado de periféricos POS.",
        # FLEET / Mantenimiento
        "fleet.asset.read": "Ver activos de flota.",
        "fleet.asset.manage": "Crear/editar activos de flota.",
        "fleet.driver.read": "Ver conductores.",
        "fleet.driver.manage": "Crear/editar conductores y asignaciones.",
        "fleet.document.read": "Ver documentos de flota.",
        "fleet.document.manage": "Registrar/editar documentos de flota.",
        "fleet.maintenance.read": "Ver catálogo y planes de mantenimiento.",
        "fleet.maintenance.manage": "Configurar tipos/planes/reglas y correr alertas.",
        "fleet.meter.record": "Registrar lecturas de odómetro/horómetro.",
        "notifications.device.register": "Registrar token de dispositivo para notificaciones.",
        "documents.scan.create": "Subir/capturar documentos para procesamiento (IDP).",
        "documents.scan.read": "Ver documentos escaneados y su texto/campos extraídos.",
        "documents.scan.review": "Revisar y confirmar el resultado de OCR/extracción.",
        "diagnostics.error.read": "Ver el ledger de errores de runtime (observabilidad/diagnóstico).",
        "diagnostics.finding.read": "Ver el ledger de hallazgos de seguridad (SCA/SAST).",
        "diagnostics.ai_control.read": "Ver el estado del botón de apagado de la IA.",
        "diagnostics.ai_control.manage": "Encender/apagar la IA (kill switch runtime).",
        "diagnostics.diagnose.read": "Ver diagnósticos de causa raíz de fallos.",
        "diagnostics.diagnose.run": "Disparar el diagnóstico de causa raíz de un fallo.",
    }

    permissions.update(
        {
            # INVENTORY kernel (granular)
            "inventory.item.create": "Crear ítems de inventario.",
            "inventory.warehouse.create": "Crear almacenes.",
            "inventory.movement.receive": "Registrar entradas.",
            "inventory.movement.issue": "Registrar salidas.",
            "inventory.movement.adjust": "Registrar ajustes.",
            "inventory.transfer.create": "Registrar transferencias.",
            "inventory.balance.read": "Ver balances.",
            # BILLING kernel
            "billing.doc.create": "Crear documentos (draft).",
            "billing.doc.read": "Ver documentos.",
            "billing.doc.issue": "Emitir documentos.",
            "billing.doc.void": "Anular documentos.",
            # PROCUREMENT kernel
            "procurement.doc.create": "Crear documentos de compra (draft).",
            "procurement.doc.read": "Ver documentos de compra.",
            "procurement.doc.post": "Postear documentos de compra.",
            "procurement.doc.void": "Anular documentos de compra.",
            # COMISARIATO (tienda de la empresa a crédito)
            "comisariato.read": "Ver cuentas/saldos del comisariato.",
            "comisariato.account.manage": "Crear/editar cuentas de crédito del comisariato (límite, segmento).",
            "comisariato.sell": "Vender mercadería a crédito en el comisariato.",
            "comisariato.payroll.apply": "Aplicar el crédito del comisariato a la planilla (descuento + abono).",
            # SoD (maker-checker) para anulación de documentos de facturación
            "billing.doc.void.request": "Solicitar anulación de documento (maker).",
            "billing.doc.void.approve": "Aprobar anulación de documento (checker, SoD).",
            # SoD (maker-checker) en payments: reembolso de intent y reapertura de caja
            "payments.refund.request": "Solicitar reembolso de pago (maker).",
            "payments.refund.approve": "Aprobar reembolso de pago (checker, SoD).",
            "payments.cash.reopen.request": "Solicitar reapertura de sesión de caja (maker).",
            "payments.cash.reopen.approve": "Aprobar reapertura de sesión de caja (checker, SoD).",
            # Portfolio (cartera CxC/CxP/crédito) — cierra rbac=0; ops sensibles con permiso propio
            "portfolio.receivable.read": "Ver cuentas por cobrar (CxC).",
            "portfolio.receivable.write": "Crear/editar cuentas por cobrar.",
            "portfolio.receivable.adjust": "Ajustar monto de una CxC (sensible).",
            "portfolio.receivable.writeoff": "Castigar/write-off una CxC (sensible).",
            "portfolio.payable.read": "Ver cuentas por pagar (CxP).",
            "portfolio.payable.write": "Crear/editar cuentas por pagar.",
            "portfolio.credit.read": "Ver créditos.",
            "portfolio.credit.write": "Crear/editar créditos.",
            "portfolio.credit.disburse": "Desembolsar un crédito (sensible).",
            "portfolio.allocation.read": "Ver aplicaciones de pago (allocations).",
            "portfolio.allocation.write": "Crear/editar aplicaciones de pago.",
            "portfolio.interest.read": "Ver devengo de intereses.",
            "portfolio.settings.read": "Ver configuración de cartera.",
            "portfolio.settings.write": "Editar configuración de cartera.",
        }
    )

    role_to_perms = {
        "company_admin": [
            "org.company.create",
            "org.company.read",
            "org.company.update",
            "org.branch.read",
            "org.branch.create",
            "org.branch.update",
            "org.module.read",
            "org.module.manage",
            "iam.users.create",
            "documents.scan.create",
            "documents.scan.read",
            "documents.scan.review",
            "diagnostics.error.read",
            "diagnostics.finding.read",
            "diagnostics.ai_control.read",
            "diagnostics.ai_control.manage",
            "diagnostics.diagnose.read",
            "diagnostics.diagnose.run",
            "hr.position.read",
            "hr.position.create",
            "hr.position.update",
            "hr.position.roles.update",
            "hr.employee.read",
            "hr.employee.create",
            "hr.employee.update",
            "hr.assignment.read",
            "hr.assignment.create",
            "hr.assignment.end",
            "rbac.roles.read",
            "rbac.roles.update",
            "rbac.permissions.read",
            "rbac.permissions.update",
            "rbac.assignments.read",
            "rbac.assignments.update",
            "audit.read",
            "audit.export",
            # Reporting / dashboards: company_admin se describe como "...+ reportes". El dueño
            # del bootstrap (que recibe este rol) debe poder VER dashboards y datasets; sin esto,
            # /dashboard (que exige report.dashboard.read) le daba 403 al recién creado.
            "report.catalog.read",
            "report.dataset.read",
            "report.dataset.export",
            "report.run.read",
            "report.snapshot.generate",
            "report.definition.manage",
            "report.dashboard.read",
            "report.dashboard.compose",
            "accounting.report.read",
            "controls.sod.read",
            "controls.sod.manage",
            "controls.findings.read",
            "controls.findings.manage",
            "finca.finca.read",
            "finca.finca.manage",
            "finca.plot.read",
            "finca.plot.manage",
            "finca.labor.read",
            "finca.labor.manage",
            "finca.work.read",
            "finca.work.capture",
            "finca.report.read",
            "finca.field.read",
            "finca.cost.post",
            "sync.device.enroll",
            "sync.device.revoke",
            "sync.batch.receive",
            # Inventario (granular)
            "inventory.item.read",
            "inventory.item.create",
            "inventory.item.update",
            "inventory.warehouse.read",
            "inventory.warehouse.create",
            "inventory.lot.read",
            "inventory.lot.create",
            "inventory.balance.read",
            "inventory.movement.read",
            "inventory.movement.receive",
            "inventory.movement.issue",
            "inventory.movement.adjust",
            "inventory.transfer.create",
            "inventory.movement.post",
            "inventory.adjustment.create",
            # Facturación (granular)
            "billing.customer.read",
            "billing.customer.create",
            "billing.customer.update",
            "billing.invoice.read",
            "billing.invoice.create",
            "billing.invoice.issue",
            "billing.invoice.void",
            "billing.doc.read",
            "billing.doc.create",
            "billing.doc.issue",
            "billing.doc.void",
            "billing.fiscal.config.read",
            "billing.fiscal.config.update",
            "billing.doc.print",
            "billing.doc.contingency",
            "billing.doc.contingency.resolve",
            # Payments/Cash
            "payments.intent.read",
            "payments.intent.create",
            "payments.cash_session.read",
            "payments.cash_session.open",
            "payments.cash_session.close",
            "payments.cash_movement.create",
            # CEC
            "cec.close_run.read",
            "cec.close_run.create",
            "cec.close_run.update",
            "cec.exception.read",
            "cec.exception.create",
            "cec.exception.resolve",
            "cec.evidence.create",
            # Integration backbone
            "integration.outbox.read",
            "integration.outbox.publish",
            "integration.inbox.read",
            "integration.inbox.process",
            # Accounting
            "accounting.journal_draft.read",
            "accounting.journal_draft.approve",
            "accounting.journal_draft.post",
            "accounting.journal_entry.read",
            "accounting.journal_entry.reverse",
            "accounting.journal_entry.reverse_batch",
            "accounting.period.read",
            "accounting.period.close",
            "accounting.period.reopen",
            "accounting.sod.override",
            "accounting.coa.read",
            "accounting.coa.update",
            "accounting.fx_rate.read",
            "accounting.fx_rate.update",
            "accounting.report.read",
            "accounting.revaluation.run",
            "accounting.intercompany.read",
            "accounting.intercompany.write",
            "accounting.intercompany.reconcile",
            "accounting.intercompany.dispute",
            "accounting.intercompany.settle",
            "accounting.consolidation.read",
            "accounting.consolidation.run",
            # Reporting kernel
            "report.catalog.read",
            "report.dataset.read",
            "report.dataset.export",
            "report.run.read",
            "report.snapshot.generate",
            "report.definition.manage",
            "report.dashboard.read",
            "report.dashboard.compose",
            # Nómina
            "nomina.config.read",
            "nomina.config.manage",
            "nomina.period.read",
            "nomina.period.create",
            "nomina.sheet.read",
            "nomina.sheet.create",
            "nomina.sheet.manage",
            "nomina.entry.read",
            "nomina.entry.create",
            "nomina.field.read",
            "nomina.field.manage",
            "nomina.field.capture",
            "nomina.attendance.read",
            "nomina.attendance.review",
            "nomina.attendance.approve",
            "nomina.attendance.build",
            # Portfolio (cartera CxC/CxP/crédito)
            "portfolio.receivable.read",
            "portfolio.receivable.write",
            "portfolio.receivable.adjust",
            "portfolio.receivable.writeoff",
            "portfolio.payable.read",
            "portfolio.payable.write",
            "portfolio.credit.read",
            "portfolio.credit.write",
            "portfolio.credit.disburse",
            "portfolio.allocation.read",
            "portfolio.allocation.write",
            "portfolio.interest.read",
            "portfolio.settings.read",
            "portfolio.settings.write",
            # Compat
            "inventory.read",
            "inventory.write",
            "clients.read",
            "clients.write",
            "reports.view",
            "reports.export",
        ],
        "branch_manager": [
            "org.branch.read",
            "org.branch.update",
            "hr.employee.read",
            "hr.employee.update",
            "hr.assignment.read",
            # Inventario (granular)
            "inventory.item.read",
            "inventory.item.create",
            "inventory.item.update",
            "inventory.warehouse.read",
            "inventory.warehouse.create",
            "inventory.lot.read",
            "inventory.lot.create",
            "inventory.balance.read",
            "inventory.movement.read",
            "inventory.movement.receive",
            "inventory.movement.issue",
            "inventory.movement.adjust",
            "inventory.transfer.create",
            "inventory.movement.post",
            "inventory.adjustment.create",
            # Facturación (lectura + draft)
            "billing.customer.read",
            "billing.invoice.read",
            "billing.invoice.create",
            "billing.doc.read",
            "billing.doc.create",
            "billing.doc.issue",
            "billing.doc.void",
            "billing.fiscal.config.read",
            "billing.doc.print",
            "billing.doc.contingency",
            "billing.doc.contingency.resolve",
            # Payments/Cash
            "payments.intent.read",
            "payments.intent.create",
            "payments.cash_session.read",
            "payments.cash_session.open",
            "payments.cash_session.close",
            "payments.cash_movement.create",
            # CEC control plane
            "cec.close_run.read",
            "cec.close_run.create",
            "cec.close_run.update",
            "cec.exception.read",
            "cec.exception.create",
            "cec.exception.resolve",
            "cec.evidence.create",
            # Integration backbone (read)
            "integration.outbox.read",
            "integration.inbox.read",
            # Accounting
            "accounting.journal_draft.read",
            "accounting.journal_draft.approve",
            "accounting.journal_draft.post",
            "accounting.journal_entry.read",
            "accounting.journal_entry.reverse",
            "accounting.journal_entry.reverse_batch",
            "accounting.period.read",
            "accounting.coa.read",
            "accounting.fx_rate.read",
            "accounting.report.read",
            "accounting.revaluation.run",
            "accounting.intercompany.read",
            "accounting.intercompany.write",
            "accounting.intercompany.reconcile",
            "accounting.intercompany.dispute",
            "accounting.intercompany.settle",
            "accounting.consolidation.read",
            # Reporting kernel
            "report.catalog.read",
            "report.dataset.read",
            "report.dataset.export",
            "report.run.read",
            "report.snapshot.generate",
            "report.dashboard.read",
            "report.dashboard.compose",
            # Nómina operativa de sucursal
            "nomina.period.read",
            "nomina.sheet.read",
            "nomina.sheet.create",
            "nomina.sheet.manage",
            "nomina.entry.read",
            "nomina.entry.create",
            "nomina.field.read",
            "nomina.field.manage",
            "nomina.field.capture",
            "nomina.attendance.read",
            "nomina.attendance.review",
            # Compat
            "inventory.read",
            "inventory.write",
            "clients.read",
            "clients.write",
            "reports.view",
        ],
        "hr_manager": [
            "org.company.read",
            "org.branch.read",
            "iam.users.create",
            "hr.position.read",
            "hr.position.create",
            "hr.position.update",
            "hr.position.roles.update",
            "hr.employee.read",
            "hr.employee.create",
            "hr.employee.update",
            "hr.assignment.read",
            "hr.assignment.create",
            "hr.assignment.end",
        ],
        "hr_clerk": [
            "org.branch.read",
            "hr.position.read",
            "hr.employee.read",
            "hr.employee.create",
            "hr.employee.update",
            "hr.assignment.read",
            "hr.assignment.create",
            "hr.assignment.end",
        ],
        "auditor": [
            "audit.read",
            "reports.view",
            "cec.close_run.read",
            "cec.exception.read",
            "integration.outbox.read",
            "integration.inbox.read",
            "accounting.journal_draft.read",
            "accounting.journal_entry.read",
            "accounting.period.read",
            "accounting.coa.read",
            "accounting.fx_rate.read",
            "accounting.report.read",
            "accounting.intercompany.read",
            "accounting.consolidation.read",
            # Reporting kernel
            "report.catalog.read",
            "report.dataset.read",
            "report.run.read",
            "report.dashboard.read",
            # Controls (lectura)
            "controls.sod.read",
            "controls.findings.read",
        ],
        "controls_officer": [
            "controls.sod.read",
            "controls.sod.manage",
            "controls.findings.read",
            "controls.findings.manage",
            "audit.read",
        ],
        "warehouse_manager": [
            "inventory.item.read",
            "inventory.item.create",
            "inventory.item.update",
            "inventory.warehouse.read",
            "inventory.lot.read",
            "inventory.lot.create",
            "inventory.movement.read",
            "inventory.movement.post",
            "inventory.adjustment.create",
            # Compat
            "inventory.read",
            "inventory.write",
        ],
        "warehouse_operator": [
            "inventory.item.read",
            "inventory.warehouse.read",
            "inventory.lot.read",
            "inventory.movement.read",
            "inventory.movement.post",
            # Compat
            "inventory.read",
        ],
        "sales_manager": [
            "billing.customer.read",
            "billing.customer.create",
            "billing.customer.update",
            "billing.invoice.read",
            "billing.invoice.create",
            "billing.invoice.issue",
            "billing.invoice.void",
            # Compat
            "clients.read",
            "clients.write",
            "reports.view",
        ],
        "sales_rep": [
            "billing.customer.read",
            "billing.invoice.read",
            "billing.invoice.create",
            # Compat
            "clients.read",
        ],
        "cashier": [
            "billing.invoice.read",
            "billing.invoice.issue",
            # Compat
            "reports.view",
        ],
        "sync_admin": ["sync.device.enroll", "sync.device.revoke"],
        "payroll_manager": [
            "nomina.config.read",
            "nomina.config.manage",
            "nomina.period.read",
            "nomina.period.create",
            "nomina.sheet.read",
            "nomina.sheet.create",
            "nomina.sheet.manage",
            "nomina.entry.read",
            "nomina.entry.create",
            "nomina.field.read",
            "nomina.field.manage",
            "nomina.field.capture",
            "nomina.attendance.read",
            "nomina.attendance.review",
            "nomina.attendance.approve",
            "nomina.attendance.build",
        ],

        # FUEL
        "fuel_admin": [
            "fuel.config.read",
            "fuel.config.update",
            "fuel.shift.open",
            "fuel.shift.close",
            "fuel.shift.read",
            "fuel.dispense.create",
            "fuel.dispense.read",
            "fuel.dispense.void",
            "fuel.sale.create",
            "fuel.sale.read",
            "fuel.sale.void",
            "fuel.price.read",
            "fuel.price.update",
            "fuel.tank.read",
            "fuel.tank.receive",
            "fuel.tank.adjust",
            "fuel.reconcile.view",
            "fuel.reconcile.post",
            "fuel.outbox.read",
            "fuel.outbox.reprocess",
            "fuel.reports.view",
            "fuel.reports.export",
            "fuel.uom_preferences.manage",
            "report.dashboard.read",
        ],
        "fuel_supervisor": [
            "fuel.config.read",
            "fuel.shift.open",
            "fuel.shift.close",
            "fuel.shift.read",
            "fuel.dispense.read",
            "fuel.dispense.void",
            "fuel.sale.read",
            "fuel.sale.void",
            "fuel.price.read",
            "fuel.price.update",
            "fuel.tank.read",
            "fuel.tank.receive",
            "fuel.tank.adjust",
            "fuel.reconcile.view",
            "fuel.reconcile.post",
            "fuel.outbox.read",
            "fuel.outbox.reprocess",
            "fuel.reports.view",
            "fuel.reports.export",
            "fuel.uom_preferences.manage",
            "report.dashboard.read",
        ],
        "fuel_cashier": [
            "fuel.shift.open",
            "fuel.shift.read",
            "fuel.dispense.create",
            "fuel.dispense.read",
            "fuel.sale.create",
            "fuel.sale.read",
            "fuel.reports.view",
            "fuel.uom_preferences.manage",
        ],
        "fuel_auditor": [
            "fuel.shift.read",
            "fuel.dispense.read",
            "fuel.sale.read",
            "fuel.price.read",
            "fuel.tank.read",
            "fuel.reconcile.view",
            "fuel.outbox.read",
            "fuel.reports.view",
        ],
    }

    role_to_perms.update(
        {
            "warehouse_manager": [
                "inventory.item.create",
                "inventory.warehouse.read",
                "inventory.warehouse.create",
                "inventory.lot.read",
                "inventory.lot.create",
                "inventory.movement.read",
                "inventory.movement.receive",
                "inventory.movement.issue",
                "inventory.movement.adjust",
                "inventory.transfer.create",
                "inventory.balance.read",
            ],
            "procurement_manager": [
                "procurement.doc.create",
                "procurement.doc.read",
                "procurement.doc.post",
                "procurement.doc.void",
                "accounting.journal_draft.read",
                "accounting.journal_draft.approve",
                "accounting.journal_draft.post",
                "accounting.journal_entry.read",
                "accounting.report.read",
                "cec.close_run.read",
                "cec.close_run.create",
                "cec.close_run.update",
                "cec.exception.read",
                "cec.exception.resolve",
            ],
            "cashier": [
                "billing.doc.create",
                "billing.doc.read",
                "billing.doc.issue",
                "billing.doc.print",
                "payments.intent.read",
                "payments.intent.create",
                "payments.cash_session.read",
                "payments.cash_session.open",
                "payments.cash_session.close",
                "payments.cash_movement.create",
            ],
            "billing_manager": [
                "billing.doc.create",
                "billing.doc.read",
                "billing.doc.issue",
                "billing.doc.void",
                "billing.fiscal.config.read",
                "billing.fiscal.config.update",
                "billing.doc.print",
                "billing.doc.contingency",
                "billing.doc.contingency.resolve",
                "payments.intent.read",
                "cec.close_run.read",
                "cec.close_run.create",
                "cec.close_run.update",
                "cec.exception.read",
                "cec.exception.resolve",
                "cec.evidence.create",
                "integration.outbox.read",
                "accounting.journal_draft.read",
                "accounting.journal_draft.approve",
                "accounting.journal_draft.post",
                "accounting.journal_entry.read",
                "accounting.journal_entry.reverse",
                "accounting.journal_entry.reverse_batch",
                "accounting.period.read",
                "accounting.sod.override",
                "accounting.coa.read",
                "accounting.coa.update",
                "accounting.fx_rate.read",
                "accounting.fx_rate.update",
                "accounting.report.read",
                "accounting.revaluation.run",
                "accounting.intercompany.read",
                "accounting.intercompany.write",
                "accounting.intercompany.reconcile",
                "accounting.intercompany.dispute",
                "accounting.intercompany.settle",
                "accounting.consolidation.read",
                "procurement.doc.create",
                "procurement.doc.read",
                "procurement.doc.post",
                "procurement.doc.void",
            ],
        }
    )

    for role_name in ("company_admin",):
        codes = role_to_perms.get(role_name, [])
        for code in (
            "procurement.doc.create",
            "procurement.doc.read",
            "procurement.doc.post",
            "procurement.doc.void",
        ):
            if code not in codes:
                codes.append(code)

    # NOMINA / Asistencia de campo — mapeo de roles (SoD: planillero captura/consolida, jefe aprueba)
    _nomina_field_maker_perms = [
        "nomina.config.read",
        "nomina.config.manage",
        "nomina.period.read",
        "nomina.period.create",
        "nomina.sheet.read",
        "nomina.sheet.create",
        "nomina.sheet.manage",
        "nomina.entry.read",
        "nomina.entry.create",
        "nomina.field.read",
        "nomina.field.manage",
        "nomina.field.capture",
        "nomina.field.consolidate",
        "nomina.field.approve.request",
        "nomina.field.apply",
        "nomina.attendance.read",
        "nomina.attendance.review",
        "nomina.attendance.approve",
        "nomina.attendance.build",
        "nomina.inss.read",
        "nomina.inss.manage",
        "nomina.period.approve.request",
    ]
    role_to_perms["payroll_manager"] = list(_nomina_field_maker_perms)
    role_to_perms["field_supervisor"] = [
        "nomina.field.read",
        "nomina.field.approve",
        "nomina.attendance.read",
        "nomina.attendance.approve",
        "nomina.period.read",
        "nomina.period.approve",
    ]
    role_to_perms["finca_mandador"] = [
        "finca.finca.read",
        "finca.finca.manage",
        "finca.plot.read",
        "finca.plot.manage",
        "finca.labor.read",
        "finca.labor.manage",
        "finca.work.read",
        "finca.work.capture",
        "finca.report.read",
        "finca.field.read",
        "finca.cost.post",
    ]
    role_to_perms["finca_capataz"] = [
        "finca.finca.read",
        "finca.plot.read",
        "finca.labor.read",
        "finca.work.read",
        "finca.work.capture",
        "finca.field.read",
    ]
    # Agrónomo (asesor técnico): ve todo y DEFINE el plan de labores (finca.labor.manage),
    # pero NO captura la ejecución diaria (work.capture, eso es del capataz) ni postea costos
    # (cost.post, eso es del mandador). SoD: distinto de capataz y de mandador.
    role_to_perms["finca_tecnico"] = [
        "finca.finca.read",
        "finca.plot.read",
        "finca.labor.read",
        "finca.labor.manage",
        "finca.work.read",
        "finca.report.read",
        "finca.field.read",
    ]
    _admin_codes = role_to_perms.get("company_admin", [])
    for code in (*_nomina_field_maker_perms, "nomina.field.approve", "nomina.period.approve"):
        if code not in _admin_codes:
            _admin_codes.append(code)

    retail_perms_full = [
        "retail.pos.session.open",
        "retail.pos.session.read",
        "retail.pos.session.close",
        "retail.pos.ticket.open",
        "retail.pos.ticket.read",
        "retail.pos.ticket.checkout",
        "retail.pos.ticket.void",
        "retail.pos.peripherals.read",
        "retail.pos.peripherals.manage",
    ]
    retail_perms_operator = [
        "retail.pos.session.open",
        "retail.pos.session.read",
        "retail.pos.ticket.open",
        "retail.pos.ticket.read",
        "retail.pos.ticket.checkout",
        "retail.pos.ticket.void",
        "retail.pos.peripherals.read",
    ]
    retail_perms_auditor = [
        "retail.pos.session.read",
        "retail.pos.ticket.read",
        "retail.pos.peripherals.read",
    ]

    role_retail_matrix = {
        "company_admin": retail_perms_full,
        "branch_manager": retail_perms_full,
        "cashier": retail_perms_operator,
        "fuel_admin": retail_perms_full,
        "fuel_supervisor": retail_perms_full,
        "fuel_cashier": retail_perms_operator,
        "fuel_auditor": retail_perms_auditor,
    }
    for role_name, codes_to_add in role_retail_matrix.items():
        current = role_to_perms.get(role_name, [])
        for code in codes_to_add:
            if code not in current:
                current.append(code)

    comisariato_perms_full = [
        "comisariato.read",
        "comisariato.account.manage",
        "comisariato.sell",
        "comisariato.payroll.apply",
    ]
    comisariato_perms_cashier = ["comisariato.read", "comisariato.sell"]
    role_comisariato_matrix = {
        "company_admin": comisariato_perms_full,
        "branch_manager": comisariato_perms_full,
        "cashier": comisariato_perms_cashier,
    }
    for role_name, codes_to_add in role_comisariato_matrix.items():
        current = role_to_perms.setdefault(role_name, [])
        for code in codes_to_add:
            if code not in current:
                current.append(code)

    fleet_perms_full = [
        "fleet.asset.read", "fleet.asset.manage", "fleet.driver.read", "fleet.driver.manage",
        "fleet.document.read", "fleet.document.manage", "fleet.maintenance.read",
        "fleet.maintenance.manage", "fleet.meter.record", "notifications.device.register",
    ]
    fleet_perms_supervisor = [
        "fleet.asset.read", "fleet.driver.read", "fleet.driver.manage", "fleet.document.read",
        "fleet.document.manage", "fleet.maintenance.read", "fleet.maintenance.manage",
        "fleet.meter.record", "notifications.device.register",
    ]
    fleet_perms_mechanic = [
        "fleet.asset.read", "fleet.maintenance.read", "fleet.document.read", "notifications.device.register",
    ]
    fleet_perms_driver = ["fleet.asset.read", "fleet.meter.record", "notifications.device.register"]
    fleet_perms_clerk = [
        "fleet.asset.read", "fleet.document.read", "fleet.document.manage", "notifications.device.register",
    ]
    role_fleet_matrix = {
        "company_admin": fleet_perms_full,
        "branch_manager": fleet_perms_full,
        "fleet_manager": fleet_perms_full,
        "fleet_supervisor": fleet_perms_supervisor,
        "fleet_mechanic": fleet_perms_mechanic,
        "fleet_driver": fleet_perms_driver,
        "fleet_clerk": fleet_perms_clerk,
    }
    for role_name, codes_to_add in role_fleet_matrix.items():
        current = role_to_perms.setdefault(role_name, [])
        for code in codes_to_add:
            if code not in current:
                current.append(code)

    roles_created = roles_updated = perms_created = perms_updated = roleperms_created = 0

    with transaction.atomic():
        role_objs: dict[str, Role] = {}
        for name, desc in roles.items():
            role_obj, created = Role.objects.get_or_create(
                name=name,
                defaults={"description": desc, "is_active": True},
            )
            if created:
                roles_created += 1
            else:
                role_update_fields: list[str] = []
                if role_obj.description != desc:
                    role_obj.description = desc
                    role_update_fields.append("description")
                if not role_obj.is_active:
                    role_obj.is_active = True
                    role_update_fields.append("is_active")
                if role_update_fields:
                    role_obj.save(update_fields=role_update_fields)
                    roles_updated += 1
            role_objs[name] = role_obj

        perm_objs: dict[str, Permission] = {}
        for code, desc in permissions.items():
            perm_obj, created = Permission.objects.get_or_create(
                code=code, defaults={"description": desc, "is_active": True}
            )
            if created:
                perms_created += 1
            else:
                perm_update_fields: list[str] = []
                if perm_obj.description != desc:
                    perm_obj.description = desc
                    perm_update_fields.append("description")
                if not perm_obj.is_active:
                    perm_obj.is_active = True
                    perm_update_fields.append("is_active")
                if perm_update_fields:
                    perm_obj.save(update_fields=perm_update_fields)
                    perms_updated += 1
            perm_objs[code] = perm_obj

        for role_name, perm_codes in role_to_perms.items():
            role = role_objs[role_name]
            for code in perm_codes:
                perm = perm_objs.get(code)
                if perm is None:
                    # Catálogo inconsistente => fallo duro
                    raise ValueError(f"Permiso no existe en seed permissions: {code}")
                _, rp_created = RolePermission.objects.get_or_create(role=role, permission=perm)
                if rp_created:
                    roleperms_created += 1
    return SeedResult(
        roles_created=roles_created,
        roles_updated=roles_updated,
        perms_created=perms_created,
        perms_updated=perms_updated,
        roleperms_created=roleperms_created,
    )
