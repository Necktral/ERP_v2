<template>
  <q-layout view="hHh Lpr lff" class="app-shell">
    <q-header class="app-topbar">
      <q-toolbar class="app-toolbar">
        <q-btn flat dense round icon="menu" aria-label="Menú" @click="drawer = !drawer" />

        <div class="app-brand row items-center no-wrap q-ml-sm">
          <img v-if="brand.logoUrl" :src="brand.logoUrl" :alt="brand.name" class="app-brand__logo" />
          <span v-else class="app-brand__mark" aria-hidden="true">◆</span>
          <span class="app-brand__name gt-xs">{{ brand.name }}</span>
        </div>

        <q-space />

        <ConnectivityDot class="q-mr-sm" />

        <!-- Selector multi-empresa: cambia empresa/sucursal y recarga sesión/ACL -->
        <q-btn
          v-if="companyName"
          flat
          dense
          no-caps
          class="app-company"
          icon="business"
          icon-right="expand_more"
          :label="companyLabel"
          :loading="switching"
        >
          <q-tooltip>Cambiar de empresa o sucursal</q-tooltip>
          <q-menu anchor="bottom right" self="top right">
            <q-list class="app-company-menu" dense>
              <q-item-label header>Cambiar de empresa</q-item-label>
              <template v-for="c in acl.companies" :key="c.company_id">
                <q-item
                  clickable
                  v-close-popup
                  :active="esContextoActivo(c.company_id, null)"
                  active-class="app-company-menu--active"
                  @click="cambiarContexto(c.company_id, null)"
                >
                  <q-item-section avatar><q-icon name="business" size="18px" /></q-item-section>
                  <q-item-section>{{ c.company_name }}</q-item-section>
                </q-item>
                <q-item
                  v-for="b in c.branches"
                  :key="`${c.company_id}-${b.branch_id}`"
                  clickable
                  v-close-popup
                  class="app-company-menu__branch"
                  :active="esContextoActivo(c.company_id, b.branch_id)"
                  active-class="app-company-menu--active"
                  @click="cambiarContexto(c.company_id, b.branch_id)"
                >
                  <q-item-section avatar><q-icon name="subdirectory_arrow_right" size="16px" /></q-item-section>
                  <q-item-section>{{ b.branch_name }}</q-item-section>
                </q-item>
              </template>
            </q-list>
          </q-menu>
        </q-btn>

        <q-btn
          flat
          dense
          round
          :icon="isDark ? 'light_mode' : 'dark_mode'"
          :aria-label="isDark ? 'Tema claro' : 'Tema oscuro'"
          @click="toggleTheme"
        >
          <q-tooltip>{{ isDark ? 'Cambiar a claro' : 'Cambiar a oscuro' }}</q-tooltip>
        </q-btn>

        <q-btn flat dense round icon="account_circle" aria-label="Cuenta">
          <q-menu anchor="bottom right" self="top right">
            <div class="app-user-menu">
              <div class="app-user-menu__name">{{ user?.username ?? 'Usuario' }}</div>
              <q-separator spaced />
              <q-btn flat dense no-caps icon="logout" label="Cerrar sesión" @click="logout" />
            </div>
          </q-menu>
        </q-btn>
      </q-toolbar>
    </q-header>

    <q-drawer v-model="drawer" show-if-above bordered class="app-drawer" :width="248">
      <q-list padding>
        <template v-for="grupo in navAgrupado" :key="grupo.section">
          <q-item-label header class="app-drawer__header">{{ grupo.section }}</q-item-label>
          <q-item
            v-for="item in grupo.items"
            :key="item.to"
            clickable
            :to="item.to"
            active-class="app-nav--active"
            class="app-nav"
          >
            <q-item-section avatar>
              <q-icon :name="item.icon" />
            </q-item-section>
            <q-item-section>{{ item.label }}</q-item-section>
          </q-item>
        </template>

        <q-item v-if="navAgrupado.length === 0" class="app-nav">
          <q-item-section class="text-caption text-muted">
            Aún no hay módulos habilitados para tu usuario.
          </q-item-section>
        </q-item>
      </q-list>
    </q-drawer>

    <q-page-container>
      <!-- key por contexto: al cambiar de empresa/sucursal TODAS las páginas se remontan -->
      <router-view :key="`${ctx.activeCompanyId ?? ''}:${ctx.activeBranchId ?? ''}`" />
    </q-page-container>
  </q-layout>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import { useRouter } from 'vue-router';
import { useQuasar } from 'quasar';
import ConnectivityDot from 'src/components/ConnectivityDot.vue';
import { BRAND } from 'src/config/brand';
import { useAuthStore } from 'src/stores/auth.store';
import { useAclStore } from 'src/stores/acl.store';
import { useContextStore } from 'src/stores/context.store';
import { useSessionBootstrapStore } from 'src/stores/session-bootstrap.store';
import { useUiStore } from 'src/stores/ui.store';

type NavSection = 'Operación' | 'Finanzas' | 'Verticales' | 'Administración';

interface NavItem {
  module: string | null; // null = transversal (no depende de módulos de la empresa)
  label: string;
  icon: string;
  to: string;
  perm: string;
  section: NavSection;
  mobile?: boolean; // visible en la experiencia LIMITADA del cel
}

// Catálogo de navegación. Cada ítem se muestra solo si la empresa tiene el módulo
// habilitado (effective_modules) Y el usuario tiene el permiso → "módulos sin dueño".
// Los ítems con module: null son del núcleo (p. ej. Dispositivos) y solo exigen permiso.
// En el CEL solo se muestran los ítems mobile:true (la operación de campo);
// el resto del sistema es de PC.
const NAV: NavItem[] = [
  {
    module: 'payroll',
    label: 'Asistencia',
    icon: 'fact_check',
    to: '/asistencia',
    perm: 'nomina.field.read',
    section: 'Operación',
    mobile: true,
  },
  {
    module: 'human_resources',
    label: 'Recursos Humanos',
    icon: 'groups',
    to: '/recursos-humanos',
    perm: 'hr.employee.read',
    section: 'Operación',
  },
  {
    module: 'parties',
    label: 'Terceros',
    icon: 'contacts',
    to: '/terceros',
    perm: 'parties.party.read',
    section: 'Operación',
  },
  {
    module: 'inventory',
    label: 'Inventario',
    icon: 'inventory',
    to: '/inventario',
    perm: 'inventory.balance.read',
    section: 'Operación',
  },
  {
    module: 'inventory',
    label: 'Catálogo de inventario',
    icon: 'category',
    to: '/inventario/catalogo',
    perm: 'inventory.item.read',
    section: 'Operación',
  },
  {
    module: 'procurement',
    label: 'Compras',
    icon: 'shopping_cart',
    to: '/compras',
    perm: 'procurement.doc.read',
    section: 'Operación',
  },
  {
    module: 'payroll',
    label: 'Nómina',
    icon: 'payments',
    to: '/nomina',
    perm: 'nomina.period.read',
    section: 'Operación',
  },
  {
    module: 'accounting',
    label: 'Contabilidad',
    icon: 'account_balance',
    to: '/contabilidad',
    perm: 'accounting.report.read',
    section: 'Finanzas',
  },
  {
    module: 'billing',
    label: 'Facturación',
    icon: 'receipt',
    to: '/facturacion',
    perm: 'billing.doc.read',
    section: 'Finanzas',
  },
  {
    module: 'payments',
    label: 'Caja y Pagos',
    icon: 'point_of_sale',
    to: '/caja',
    perm: 'payments.cash_session.read',
    section: 'Finanzas',
  },
  {
    module: 'portfolio',
    label: 'Cartera',
    icon: 'account_balance_wallet',
    to: '/cartera',
    perm: 'portfolio.receivable.read',
    section: 'Finanzas',
  },
  {
    module: 'comisariato',
    label: 'Comisariato',
    icon: 'storefront',
    to: '/comisariato',
    perm: 'comisariato.read',
    section: 'Verticales',
  },
  {
    module: 'fuel',
    label: 'Estación de Servicio',
    icon: 'local_gas_station',
    to: '/estacion',
    perm: 'fuel.shift.read',
    section: 'Verticales',
  },
  {
    module: 'retail_pos',
    label: 'Punto de Venta',
    icon: 'shopping_cart_checkout',
    to: '/pos',
    perm: 'retail.pos.session.read',
    section: 'Verticales',
  },
  {
    module: 'finca',
    label: 'Finca',
    icon: 'agriculture',
    to: '/finca',
    perm: 'finca.finca.read',
    section: 'Verticales',
  },
  {
    module: 'fleet',
    label: 'Flota',
    icon: 'local_shipping',
    to: '/flota',
    perm: 'fleet.asset.read',
    section: 'Verticales',
  },
  {
    module: 'cec',
    label: 'Cierre contable (CEC)',
    icon: 'all_inclusive',
    to: '/cec',
    perm: 'cec.close_run.read',
    section: 'Finanzas',
  },
  {
    module: 'analytics',
    label: 'Analítica',
    icon: 'insights',
    to: '/analitica',
    perm: 'report.dashboard.read',
    section: 'Finanzas',
  },
  {
    module: 'audit',
    label: 'Auditoría',
    icon: 'history_edu',
    to: '/auditoria',
    perm: 'audit.read',
    section: 'Administración',
  },
  {
    module: 'controls',
    label: 'Controles',
    icon: 'gpp_maybe',
    to: '/controles',
    perm: 'controls.sod.read',
    section: 'Administración',
  },
  {
    module: 'documents',
    label: 'Documentos',
    icon: 'document_scanner',
    to: '/documentos',
    perm: 'documents.scan.read',
    section: 'Administración',
  },
  {
    module: 'knowledge',
    label: 'Conocimiento',
    icon: 'menu_book',
    to: '/conocimiento',
    perm: 'knowledge.docs.read',
    section: 'Administración',
  },
  {
    module: 'diagnostics',
    label: 'Diagnóstico',
    icon: 'monitor_heart',
    to: '/diagnostico',
    perm: 'diagnostics.error.read',
    section: 'Administración',
  },
  {
    module: 'synchronization',
    label: 'Dispositivos',
    icon: 'devices',
    to: '/dispositivos',
    perm: 'sync.device.enroll',
    section: 'Administración',
  },
  {
    module: 'organization',
    label: 'Organización',
    icon: 'corporate_fare',
    to: '/organizacion',
    perm: 'org.company.read',
    section: 'Administración',
  },
  {
    module: 'organization',
    label: 'Usuarios y acceso',
    icon: 'admin_panel_settings',
    to: '/usuarios',
    perm: 'rbac.assignments.read',
    section: 'Administración',
  },
];

const NAV_SECTIONS: NavSection[] = ['Operación', 'Finanzas', 'Verticales', 'Administración'];

const brand = BRAND;
const $q = useQuasar();
const router = useRouter();
const auth = useAuthStore();
const acl = useAclStore();
const ctx = useContextStore();
const sessionBootstrap = useSessionBootstrapStore();
const ui = useUiStore();

const drawer = ref(true);
const switching = ref(false);

const user = computed(() => auth.user);
const companyName = computed(() => acl.companyName(ctx.activeCompanyId));
const isDark = computed(() => ui.theme === 'dark');

const companyLabel = computed(() => {
  const company = acl.companies.find((c) => String(c.company_id) === ctx.activeCompanyId);
  if (!company) return companyName.value ?? '';
  const branch = ctx.activeBranchId
    ? company.branches.find((b) => String(b.branch_id) === ctx.activeBranchId)
    : null;
  return branch ? `${company.company_name} · ${branch.branch_name}` : company.company_name;
});

// Gating multi-empresa: effective = (permisos del usuario) ∩ (módulos que la
// empresa tiene encendidos). allowed_modules queda solo como fallback legacy.
const effectiveModules = computed(
  () =>
    new Set(
      sessionBootstrap.payload?.effective_modules ?? sessionBootstrap.payload?.allowed_modules ?? [],
    ),
);

const visibleNav = computed(() =>
  NAV.filter((item) => {
    const companyId = ctx.activeCompanyId;
    if (!companyId) return false;
    if ($q.platform.is.mobile && !item.mobile) return false; // cel = solo campo
    if (!acl.hasPermission(companyId, item.perm)) return false;
    return item.module === null || effectiveModules.value.has(item.module);
  }),
);

// Drawer agrupado por sección (las secciones sin ítems visibles no se muestran).
const navAgrupado = computed(() =>
  NAV_SECTIONS.map((section) => ({
    section,
    items: visibleNav.value.filter((i) => i.section === section),
  })).filter((g) => g.items.length > 0),
);

function esContextoActivo(companyId: string | number, branchId: string | number | null): boolean {
  if (String(companyId) !== ctx.activeCompanyId) return false;
  return branchId === null ? !ctx.activeBranchId : String(branchId) === ctx.activeBranchId;
}

async function cambiarContexto(companyId: string | number, branchId: string | number | null) {
  if (esContextoActivo(companyId, branchId)) return;
  switching.value = true;
  try {
    ctx.setContext(companyId, branchId);
    // Recarga sesión: ACL + módulos efectivos de la empresa nueva.
    await sessionBootstrap.loadSession({ force: true });
    // A la raíz: la ruta actual puede no existir/permitirse en la otra empresa.
    await router.replace('/');
    $q.notify({ type: 'positive', message: `Ahora estás en ${companyLabel.value}.` });
  } catch {
    $q.notify({ type: 'negative', message: 'No se pudo cambiar de empresa.' });
  } finally {
    switching.value = false;
  }
}

function toggleTheme() {
  ui.setTheme(ui.theme === 'dark' ? 'light' : 'dark');
}

async function logout() {
  await auth.logout();
  await router.replace('/login');
}
</script>

<style scoped>
.app-shell {
  background: var(--app-bg-gradient);
  background-color: var(--app-bg);
}

.app-topbar {
  background: var(--app-surface-strong);
  color: var(--app-text);
  border-bottom: 1px solid var(--app-border);
}

.app-toolbar {
  min-height: 56px;
}

.app-brand__logo {
  height: 28px;
  width: auto;
  max-width: 120px;
  object-fit: contain;
}

.app-brand__mark {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border-radius: var(--app-radius-sm);
  color: #fff;
  font-size: 0.95rem;
  background: linear-gradient(135deg, var(--app-primary), var(--app-secondary));
}

.app-brand__name {
  margin-left: var(--app-space-3);
  font-family: 'Manrope', 'IBM Plex Sans', sans-serif;
  font-weight: 800;
  letter-spacing: 0.03em;
  font-size: 1.02rem;
}

.app-company {
  color: var(--app-text-muted);
  border-color: var(--app-border-strong);
}

.app-company-menu {
  min-width: 240px;
}

.app-company-menu__branch {
  padding-left: var(--app-space-5);
}

.app-company-menu--active {
  color: var(--app-primary);
  font-weight: 600;
}

.app-drawer {
  background: var(--app-surface);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
}

.app-drawer__header {
  color: var(--app-text-muted);
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  font-size: 0.7rem;
}

.app-nav {
  border-radius: var(--app-radius-sm);
  margin: 2px var(--app-space-2);
  color: var(--app-text);
}

.app-nav--active {
  background: var(--app-surface-strong);
  color: var(--app-primary);
  font-weight: 600;
}

.app-user-menu {
  display: flex;
  flex-direction: column;
  padding: var(--app-space-3);
  min-width: 180px;
}

.app-user-menu__name {
  font-weight: 700;
  color: var(--app-text);
  padding: 0 var(--app-space-2) var(--app-space-1);
}

.text-muted {
  color: var(--app-text-muted);
}
</style>
