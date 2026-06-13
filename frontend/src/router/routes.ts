import { Platform } from 'quasar';
import type { RouteRecordRaw } from 'vue-router';

// Frontend en reconstrucción alrededor del modelo multi-empresa.
// Auth (público) + app gated (AppLayout) con Recursos Humanos como primer módulo.
const routes: RouteRecordRaw[] = [
  {
    path: '/bootstrap',
    component: () => import('layouts/AuthLayout.vue'),
    children: [
      {
        path: '',
        component: () => import('pages/BootstrapWizardPage.vue'),
        meta: { requiresAuth: false },
      },
    ],
  },
  {
    path: '/password-change',
    component: () => import('layouts/AuthLayout.vue'),
    children: [
      {
        path: '',
        component: () => import('pages/ForcePasswordChangePage.vue'),
        meta: { requiresAuth: true },
      },
    ],
  },
  {
    path: '/enrolar',
    component: () => import('layouts/AuthLayout.vue'),
    children: [
      {
        path: '',
        component: () => import('pages/devices/EnrolarDispositivoPage.vue'),
        meta: { requiresAuth: false },
      },
    ],
  },
  {
    path: '/select-context',
    component: () => import('layouts/AuthLayout.vue'),
    children: [
      {
        path: '',
        component: () => import('pages/SelectContextPage.vue'),
        meta: { requiresAuth: true },
      },
    ],
  },
  {
    path: '/403',
    component: () => import('layouts/AuthLayout.vue'),
    children: [
      {
        path: '',
        component: () => import('pages/ForbiddenPage.vue'),
        meta: { requiresAuth: true },
      },
    ],
  },
  {
    path: '/login',
    component: () => import('layouts/AuthLayout.vue'),
    children: [
      {
        path: '',
        component: () => import('pages/LoginPage.vue'),
        meta: { requiresAuth: false },
      },
      {
        path: '2fa',
        component: () => import('pages/TwoFactorPage.vue'),
        meta: { requiresAuth: false },
      },
    ],
  },
  {
    path: '/',
    component: () => import('layouts/AppLayout.vue'),
    meta: { requiresAuth: true, requiresContext: true },
    children: [
      // En el cel la experiencia es LIMITADA: entra directo a Asistencia.
      { path: '', redirect: () => (Platform.is.mobile ? '/asistencia' : '/recursos-humanos') },
      {
        path: 'asistencia',
        name: 'asistencia',
        component: () => import('pages/asistencia/AsistenciaPage.vue'),
        // read = entrar a ver (supervisor); marcar exige nomina.field.capture (la página lo controla)
        meta: { requiresAuth: true, requiresContext: true, requiredPermissions: ['nomina.field.read'] },
      },
      {
        path: 'recursos-humanos',
        name: 'rrhh-home',
        component: () => import('pages/hr/HrHomePage.vue'),
        meta: { requiresAuth: true, requiresContext: true, requiredPermissions: ['hr.employee.read'] },
      },
      {
        path: 'recursos-humanos/puestos',
        name: 'rrhh-puestos',
        component: () => import('pages/hr/PuestosPage.vue'),
        meta: { requiresAuth: true, requiresContext: true, requiredPermissions: ['hr.position.read'] },
      },
      {
        path: 'recursos-humanos/trabajadores',
        name: 'rrhh-trabajadores',
        component: () => import('pages/hr/TrabajadoresPage.vue'),
        meta: { requiresAuth: true, requiresContext: true, requiredPermissions: ['hr.employee.read'] },
      },
      {
        path: 'recursos-humanos/trabajadores/nuevo',
        name: 'rrhh-trabajadores-nuevo',
        component: () => import('pages/hr/NuevoTrabajadorPage.vue'),
        meta: { requiresAuth: true, requiresContext: true, requiredPermissions: ['hr.employee.create'] },
      },
      {
        path: 'recursos-humanos/trabajadores/:id(\\d+)',
        name: 'rrhh-trabajador-perfil',
        component: () => import('pages/hr/TrabajadorPerfilPage.vue'),
        meta: { requiresAuth: true, requiresContext: true, requiredPermissions: ['hr.employee.read'] },
      },
      {
        path: 'nomina',
        name: 'nomina',
        component: () => import('pages/nomina/NominaPage.vue'),
        meta: { requiresAuth: true, requiresContext: true, requiredPermissions: ['nomina.period.read'] },
      },
      {
        path: 'nomina/periodos/:id(\\d+)',
        name: 'nomina-periodo',
        component: () => import('pages/nomina/PeriodoDetallePage.vue'),
        meta: { requiresAuth: true, requiresContext: true, requiredPermissions: ['nomina.period.read'] },
      },
      {
        path: 'dispositivos',
        name: 'dispositivos',
        component: () => import('pages/devices/DispositivosPage.vue'),
        meta: { requiresAuth: true, requiresContext: true, requiredPermissions: ['sync.device.enroll'] },
      },
      {
        path: 'inventario',
        name: 'inventario',
        component: () => import('pages/inventario/ExistenciasPage.vue'),
        meta: { requiresAuth: true, requiresContext: true, requiredPermissions: ['inventory.balance.read'] },
      },
      {
        path: 'inventario/kardex',
        name: 'inventario-kardex',
        component: () => import('pages/inventario/KardexPage.vue'),
        meta: { requiresAuth: true, requiresContext: true, requiredPermissions: ['inventory.movement.read'] },
      },
      {
        path: 'inventario/catalogo',
        name: 'inventario-catalogo',
        component: () => import('pages/inventario/CatalogoInventarioPage.vue'),
        meta: { requiresAuth: true, requiresContext: true, requiredPermissions: ['inventory.item.read'] },
      },
      {
        path: 'compras',
        name: 'compras',
        component: () => import('pages/compras/ComprasPage.vue'),
        meta: { requiresAuth: true, requiresContext: true, requiredPermissions: ['procurement.doc.read'] },
      },
      {
        path: 'compras/:id(\\d+)',
        name: 'compra-detalle',
        component: () => import('pages/compras/CompraDetallePage.vue'),
        meta: { requiresAuth: true, requiresContext: true, requiredPermissions: ['procurement.doc.read'] },
      },
      {
        path: 'facturacion',
        name: 'facturacion',
        component: () => import('pages/facturacion/FacturacionPage.vue'),
        meta: { requiresAuth: true, requiresContext: true, requiredPermissions: ['billing.doc.read'] },
      },
      {
        path: 'facturacion/config-fiscal',
        name: 'facturacion-config-fiscal',
        component: () => import('pages/facturacion/ConfigFiscalPage.vue'),
        meta: { requiresAuth: true, requiresContext: true, requiredPermissions: ['billing.fiscal.config.read'] },
      },
      {
        path: 'facturacion/:id(\\d+)',
        name: 'factura-detalle',
        component: () => import('pages/facturacion/FacturaDetallePage.vue'),
        meta: { requiresAuth: true, requiresContext: true, requiredPermissions: ['billing.doc.read'] },
      },
      {
        path: 'caja',
        name: 'caja',
        component: () => import('pages/caja/CajaPage.vue'),
        meta: { requiresAuth: true, requiresContext: true, requiredPermissions: ['payments.cash_session.read'] },
      },
      {
        path: 'caja/sesiones',
        name: 'caja-sesiones',
        component: () => import('pages/caja/SesionesCajaPage.vue'),
        meta: { requiresAuth: true, requiresContext: true, requiredPermissions: ['payments.cash_session.read'] },
      },
      {
        path: 'caja/pagos',
        name: 'caja-pagos',
        component: () => import('pages/caja/IntentosPagoPage.vue'),
        meta: { requiresAuth: true, requiresContext: true, requiredPermissions: ['payments.intent.read'] },
      },
      {
        path: 'cartera',
        name: 'cartera',
        component: () => import('pages/cartera/CarteraPage.vue'),
        meta: { requiresAuth: true, requiresContext: true, requiredPermissions: ['portfolio.receivable.read'] },
      },
      {
        path: 'cartera/creditos',
        name: 'cartera-creditos',
        component: () => import('pages/cartera/CreditosPage.vue'),
        meta: { requiresAuth: true, requiresContext: true, requiredPermissions: ['portfolio.credit.read'] },
      },
      {
        path: 'comisariato',
        name: 'comisariato',
        component: () => import('pages/comisariato/ComisariatoPage.vue'),
        meta: { requiresAuth: true, requiresContext: true, requiredPermissions: ['comisariato.read'] },
      },
      {
        path: 'comisariato/venta',
        name: 'comisariato-venta',
        component: () => import('pages/comisariato/VentaComisariatoPage.vue'),
        meta: { requiresAuth: true, requiresContext: true, requiredPermissions: ['comisariato.sell'] },
      },
      {
        path: 'estacion',
        name: 'estacion',
        component: () => import('pages/estacion/EstacionPage.vue'),
        meta: { requiresAuth: true, requiresContext: true, requiredPermissions: ['fuel.shift.read'] },
      },
      {
        path: 'estacion/turnos',
        name: 'estacion-turnos',
        component: () => import('pages/estacion/TurnosPage.vue'),
        meta: { requiresAuth: true, requiresContext: true, requiredPermissions: ['fuel.shift.read'] },
      },
      {
        path: 'estacion/reportes',
        name: 'estacion-reportes',
        component: () => import('pages/estacion/ReportesEstacionPage.vue'),
        meta: { requiresAuth: true, requiresContext: true, requiredPermissions: ['fuel.reports.view'] },
      },
      {
        path: 'estacion/tanques',
        name: 'estacion-tanques',
        component: () => import('pages/estacion/TanquesPage.vue'),
        meta: { requiresAuth: true, requiresContext: true, requiredPermissions: ['fuel.tank.read'] },
      },
      {
        path: 'pos',
        name: 'pos',
        component: () => import('pages/pos/PosPage.vue'),
        meta: { requiresAuth: true, requiresContext: true, requiredPermissions: ['retail.pos.session.read'] },
      },
      {
        path: 'pos/tickets',
        name: 'pos-tickets',
        component: () => import('pages/pos/TicketsPage.vue'),
        meta: { requiresAuth: true, requiresContext: true, requiredPermissions: ['retail.pos.ticket.read'] },
      },
      {
        path: 'finca',
        name: 'finca',
        component: () => import('pages/finca/FincaPage.vue'),
        meta: { requiresAuth: true, requiresContext: true, requiredPermissions: ['finca.finca.read'] },
      },
      {
        path: 'finca/ordenes',
        name: 'finca-ordenes',
        component: () => import('pages/finca/OrdenesTrabajoPage.vue'),
        meta: { requiresAuth: true, requiresContext: true, requiredPermissions: ['finca.work.read'] },
      },
      {
        path: 'finca/costos',
        name: 'finca-costos',
        component: () => import('pages/finca/CostosFincaPage.vue'),
        meta: { requiresAuth: true, requiresContext: true, requiredPermissions: ['finca.field.read'] },
      },
      {
        path: 'finca/presupuesto',
        name: 'finca-presupuesto',
        component: () => import('pages/finca/PresupuestoFincaPage.vue'),
        meta: { requiresAuth: true, requiresContext: true, requiredPermissions: ['finca.budget.read'] },
      },
      {
        path: 'flota',
        name: 'flota',
        component: () => import('pages/flota/FlotaPage.vue'),
        meta: { requiresAuth: true, requiresContext: true, requiredPermissions: ['fleet.asset.read'] },
      },
      {
        path: 'flota/conductores',
        name: 'flota-conductores',
        component: () => import('pages/flota/ConductoresPage.vue'),
        meta: { requiresAuth: true, requiresContext: true, requiredPermissions: ['fleet.driver.read'] },
      },
      {
        path: 'flota/mantenimiento',
        name: 'flota-mantenimiento',
        component: () => import('pages/flota/MantenimientoPage.vue'),
        meta: { requiresAuth: true, requiresContext: true, requiredPermissions: ['fleet.maintenance.read'] },
      },
      {
        path: 'flota/costos',
        name: 'flota-costos',
        component: () => import('pages/flota/CostosFlotaPage.vue'),
        meta: { requiresAuth: true, requiresContext: true, requiredPermissions: ['fleet.cost.read'] },
      },
      {
        path: 'contabilidad',
        name: 'contabilidad',
        component: () => import('pages/contabilidad/ContabilidadHomePage.vue'),
        meta: { requiresAuth: true, requiresContext: true, requiredPermissions: ['accounting.report.read'] },
      },
      {
        path: 'contabilidad/diario',
        name: 'contabilidad-diario',
        component: () => import('pages/contabilidad/DiarioPage.vue'),
        meta: { requiresAuth: true, requiresContext: true, requiredPermissions: ['accounting.journal_draft.read'] },
      },
      {
        path: 'contabilidad/plan-cuentas',
        name: 'contabilidad-plan',
        component: () => import('pages/contabilidad/PlanCuentasPage.vue'),
        meta: { requiresAuth: true, requiresContext: true, requiredPermissions: ['accounting.coa.read'] },
      },
      {
        path: 'contabilidad/periodos',
        name: 'contabilidad-periodos',
        component: () => import('pages/contabilidad/PeriodosPage.vue'),
        meta: { requiresAuth: true, requiresContext: true, requiredPermissions: ['accounting.period.read'] },
      },
      {
        path: 'contabilidad/reportes',
        name: 'contabilidad-reportes',
        component: () => import('pages/contabilidad/ReportesContablesPage.vue'),
        meta: { requiresAuth: true, requiresContext: true, requiredPermissions: ['accounting.report.read'] },
      },
      {
        path: 'contabilidad/monedas',
        name: 'contabilidad-monedas',
        component: () => import('pages/contabilidad/MonedasPage.vue'),
        meta: { requiresAuth: true, requiresContext: true, requiredPermissions: ['accounting.fx_rate.read'] },
      },
      {
        path: 'contabilidad/intercompania',
        name: 'contabilidad-intercompania',
        component: () => import('pages/contabilidad/IntercompaniaPage.vue'),
        meta: { requiresAuth: true, requiresContext: true, requiredPermissions: ['accounting.intercompany.read'] },
      },
      {
        path: 'cec',
        name: 'cec',
        component: () => import('pages/cec/CecPage.vue'),
        meta: { requiresAuth: true, requiresContext: true, requiredPermissions: ['cec.close_run.read'] },
      },
      {
        path: 'auditoria',
        name: 'auditoria',
        component: () => import('pages/auditoria/BitacoraPage.vue'),
        meta: { requiresAuth: true, requiresContext: true, requiredPermissions: ['audit.read'] },
      },
      {
        path: 'controles',
        name: 'controles',
        component: () => import('pages/controles/ControlesPage.vue'),
        meta: { requiresAuth: true, requiresContext: true, requiredPermissions: ['controls.sod.read'] },
      },
      {
        path: 'analitica',
        name: 'analitica',
        component: () => import('pages/dashboard/AnaliticaPage.vue'),
        meta: { requiresAuth: true, requiresContext: true, requiredPermissions: ['report.dashboard.read'] },
      },
      {
        path: 'documentos',
        name: 'documentos',
        component: () => import('pages/documentos/EscaneosPage.vue'),
        meta: { requiresAuth: true, requiresContext: true, requiredPermissions: ['documents.scan.read'] },
      },
      {
        path: 'conocimiento',
        name: 'conocimiento',
        component: () => import('pages/conocimiento/ConocimientoPage.vue'),
        meta: { requiresAuth: true, requiresContext: true, requiredPermissions: ['knowledge.docs.read'] },
      },
      {
        path: 'diagnostico',
        name: 'diagnostico',
        component: () => import('pages/diagnostico/DiagnosticoPage.vue'),
        meta: { requiresAuth: true, requiresContext: true, requiredPermissions: ['diagnostics.error.read'] },
      },
      {
        path: 'terceros',
        name: 'terceros',
        component: () => import('pages/parties/TercerosPage.vue'),
        meta: { requiresAuth: true, requiresContext: true, requiredPermissions: ['parties.party.read'] },
      },
      {
        path: 'organizacion',
        name: 'organizacion',
        component: () => import('pages/org/OrganizacionPage.vue'),
        meta: { requiresAuth: true, requiresContext: true, requiredPermissions: ['org.company.read'] },
      },
      {
        path: 'usuarios',
        name: 'usuarios',
        component: () => import('pages/admin/UsuariosPage.vue'),
        meta: { requiresAuth: true, requiresContext: true, requiredPermissions: ['rbac.assignments.read'] },
      },
    ],
  },
  {
    path: '/:catchAll(.*)*',
    component: () => import('pages/ErrorNotFound.vue'),
  },
];

export default routes;
