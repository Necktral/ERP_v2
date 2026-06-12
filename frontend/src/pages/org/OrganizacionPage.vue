<template>
  <q-page class="app-page">
    <PageHeader
      title="Organización"
      subtitle="Empresas del grupo, sucursales y qué módulos usa cada empresa. Todo lo que ves aquí aplica a la empresa activa del selector de arriba."
      :loading="loading"
      @refresh="reload"
    />

    <q-tabs
      v-model="tab"
      dense
      no-caps
      align="left"
      class="org-tabs"
      active-color="primary"
      indicator-color="primary"
    >
      <q-tab name="empresas" icon="business" label="Empresas" />
      <q-tab name="perfil" icon="badge" label="Perfil de la empresa" />
      <q-tab v-if="puedeVerSucursales" name="sucursales" icon="store" label="Sucursales" />
      <q-tab v-if="puedeVerModulos" name="modulos" icon="tune" label="Módulos" />
    </q-tabs>
    <q-separator class="q-mb-md" />

    <q-tab-panels v-model="tab" animated class="org-panels">
      <!-- ============ EMPRESAS ============ -->
      <q-tab-panel name="empresas" class="q-pa-none">
        <div class="app-actions">
          <q-btn
            v-if="puedeCrearEmpresa"
            unelevated
            no-caps
            color="primary"
            icon="add_business"
            label="Nueva empresa"
            @click="abrirCrearEmpresa"
          />
          <span class="text-caption text-muted">
            Cada empresa tiene su propio RUC y sus propios módulos. Los cruces entre empresas se
            facturan como intercompany.
          </span>
        </div>

        <q-table
          class="app-table"
          :rows="companies"
          :columns="companyColumns"
          row-key="id"
          flat
          :loading="loading"
          :pagination="{ rowsPerPage: 25 }"
          no-data-label="No hay empresas visibles para tu usuario."
        >
          <template #body-cell-estado="props">
            <q-td :props="props">
              <q-chip v-if="props.row.is_active" dense color="secondary" text-color="white">
                Activa
              </q-chip>
              <q-chip v-else dense outline color="grey-7">Inactiva</q-chip>
            </q-td>
          </template>
        </q-table>
      </q-tab-panel>

      <!-- ============ PERFIL EMPRESA ACTIVA ============ -->
      <q-tab-panel name="perfil" class="q-pa-none">
        <div class="org-card">
          <div class="org-card__title">{{ companyName }}</div>
          <div class="text-caption text-muted q-mb-md">
            Datos legales de la empresa activa. Aparecen en planillas, facturas y reportes.
          </div>
          <div class="app-form">
            <q-input
              v-model="perfil.legal_name"
              outlined
              dense
              label="Razón social"
              :readonly="!puedeEditarEmpresa"
            />
            <q-input
              v-model="perfil.tax_id"
              outlined
              dense
              label="RUC"
              :readonly="!puedeEditarEmpresa"
            />
            <q-input
              v-model="perfil.address"
              outlined
              dense
              label="Dirección"
              :readonly="!puedeEditarEmpresa"
            />
            <q-input
              v-model="perfil.phone"
              outlined
              dense
              label="Teléfono"
              :readonly="!puedeEditarEmpresa"
            />
            <q-input
              v-model="perfil.email"
              outlined
              dense
              label="Correo"
              type="email"
              :readonly="!puedeEditarEmpresa"
            />
          </div>
          <div v-if="puedeEditarEmpresa" class="q-mt-md">
            <q-btn
              unelevated
              no-caps
              color="primary"
              icon="save"
              label="Guardar perfil"
              :loading="savingPerfil"
              @click="guardarPerfil"
            />
          </div>
          <div v-else class="text-caption text-muted q-mt-md">
            Solo lectura: no tenés permiso para editar el perfil.
          </div>
        </div>
      </q-tab-panel>

      <!-- ============ SUCURSALES ============ -->
      <q-tab-panel name="sucursales" class="q-pa-none">
        <div class="app-actions">
          <q-btn
            v-if="puedeCrearSucursal"
            unelevated
            no-caps
            color="primary"
            icon="add_location_alt"
            label="Nueva sucursal"
            @click="abrirCrearSucursal"
          />
          <span class="text-caption text-muted">
            Sucursales de {{ companyName }}. Los roles se pueden limitar a una sucursal.
          </span>
        </div>

        <q-table
          class="app-table"
          :rows="branches"
          :columns="branchColumns"
          row-key="id"
          flat
          :loading="loading"
          :pagination="{ rowsPerPage: 25 }"
          no-data-label="Esta empresa aún no tiene sucursales."
        >
          <template #body-cell-estado="props">
            <q-td :props="props">
              <q-chip v-if="props.row.is_active" dense color="secondary" text-color="white">
                Activa
              </q-chip>
              <q-chip v-else dense outline color="grey-7">Inactiva</q-chip>
            </q-td>
          </template>
          <template #body-cell-acciones="props">
            <q-td :props="props" class="text-right">
              <q-btn
                v-if="puedeEditarSucursal"
                flat
                dense
                no-caps
                size="sm"
                icon="edit"
                label="Editar"
                @click="abrirEditarSucursal(props.row)"
              />
            </q-td>
          </template>
        </q-table>
      </q-tab-panel>

      <!-- ============ MÓDULOS POR EMPRESA ============ -->
      <q-tab-panel name="modulos" class="q-pa-none">
        <div class="text-caption text-muted q-mb-md org-modulos-intro">
          Qué módulos usa <strong>{{ companyName }}</strong
          >. Apagar un módulo lo quita del menú para todos los usuarios de esta empresa (los
          permisos RBAC siguen aparte). Los del núcleo no se pueden apagar.
        </div>

        <div v-for="grupo in gruposModulos" :key="grupo.categoria" class="org-modgroup">
          <div class="org-modgroup__title">{{ grupo.titulo }}</div>
          <div class="org-modgrid">
            <div v-for="m in grupo.modulos" :key="m.code" class="org-modcard">
              <div class="org-modcard__info">
                <div class="org-modcard__label">{{ m.label }}</div>
                <div class="org-modcard__code">{{ m.code }}</div>
              </div>
              <q-toggle
                :model-value="m.is_enabled"
                :disable="m.core || !puedeManejarModulos || togglingCode === m.code"
                color="primary"
                @update:model-value="(v: boolean) => toggleModulo(m, v)"
              >
                <q-tooltip v-if="m.core">Módulo del núcleo: siempre encendido.</q-tooltip>
                <q-tooltip v-else-if="!puedeManejarModulos">
                  No tenés permiso para cambiar módulos.
                </q-tooltip>
              </q-toggle>
            </div>
          </div>
        </div>
      </q-tab-panel>
    </q-tab-panels>

    <!-- Diálogo: nueva empresa -->
    <q-dialog v-model="dlgEmpresa">
      <q-card class="app-dialog">
        <q-card-section class="text-h6">Nueva empresa</q-card-section>
        <q-card-section class="app-form">
          <q-input
            v-model="nuevaEmpresa.name"
            outlined
            dense
            label="Nombre *"
            autofocus
            :rules="[(v) => !!String(v).trim() || 'El nombre es obligatorio']"
          />
          <q-input v-model="nuevaEmpresa.code" outlined dense label="Código (corto, opcional)" />
          <q-input v-model="nuevaEmpresa.legal_name" outlined dense label="Razón social" />
          <q-input v-model="nuevaEmpresa.tax_id" outlined dense label="RUC" />
          <q-input v-model="nuevaEmpresa.address" outlined dense label="Dirección" />
          <q-input v-model="nuevaEmpresa.phone" outlined dense label="Teléfono" />
          <q-input v-model="nuevaEmpresa.email" outlined dense label="Correo" type="email" />
          <div class="text-caption text-muted">
            Quedás con acceso inmediato a la empresa nueva con tus mismos roles.
          </div>
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat no-caps label="Cancelar" v-close-popup />
          <q-btn
            unelevated
            no-caps
            color="primary"
            label="Crear empresa"
            :loading="savingEmpresa"
            :disable="!nuevaEmpresa.name.trim()"
            @click="crearEmpresa"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <!-- Diálogo: crear/editar sucursal -->
    <q-dialog v-model="dlgSucursal">
      <q-card class="app-dialog">
        <q-card-section class="text-h6">
          {{ sucursalEnEdicion ? `Editar "${sucursalEnEdicion.name}"` : 'Nueva sucursal' }}
        </q-card-section>
        <q-card-section class="app-form">
          <q-input
            v-model="formSucursal.name"
            outlined
            dense
            label="Nombre *"
            autofocus
            :rules="[(v) => !!String(v).trim() || 'El nombre es obligatorio']"
          />
          <q-input v-model="formSucursal.code" outlined dense label="Código (corto, opcional)" />
          <q-input v-model="formSucursal.address" outlined dense label="Dirección" />
          <q-input v-model="formSucursal.phone" outlined dense label="Teléfono" />
          <q-input v-model="formSucursal.email" outlined dense label="Correo" type="email" />
          <q-toggle
            v-if="sucursalEnEdicion"
            v-model="formSucursal.is_active"
            label="Sucursal activa"
            color="primary"
          />
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat no-caps label="Cancelar" v-close-popup />
          <q-btn
            unelevated
            no-caps
            color="primary"
            :label="sucursalEnEdicion ? 'Guardar cambios' : 'Crear sucursal'"
            :loading="savingSucursal"
            :disable="!formSucursal.name.trim()"
            @click="guardarSucursal"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>
  </q-page>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import { useQuasar, type QTableColumn } from 'quasar';
import PageHeader from 'src/components/PageHeader.vue';
import { apiErrorMessage } from 'src/core/api';
import {
  createBranch,
  createCompany,
  getCompanyProfile,
  listBranches,
  listCompanies,
  listCompanyModules,
  updateBranch,
  updateCompanyModules,
  updateCompanyProfile,
  type BranchRow,
  type CompanyRow,
  type ModuleState,
} from 'src/features/org/org.api';
import { useAclStore } from 'src/stores/acl.store';
import { useContextStore } from 'src/stores/context.store';
import { useSessionBootstrapStore } from 'src/stores/session-bootstrap.store';

const $q = useQuasar();
const acl = useAclStore();
const ctx = useContextStore();
const sessionBootstrap = useSessionBootstrapStore();

const tab = ref('empresas');
const loading = ref(false);

const companies = ref<CompanyRow[]>([]);
const branches = ref<BranchRow[]>([]);
const modulos = ref<ModuleState[]>([]);

const companyName = computed(() => acl.companyName(ctx.activeCompanyId) ?? 'Empresa activa');

function tienePermiso(code: string): boolean {
  const companyId = ctx.activeCompanyId;
  return companyId ? acl.hasPermission(companyId, code) : false;
}

const puedeCrearEmpresa = computed(() => tienePermiso('org.company.create'));
const puedeEditarEmpresa = computed(() => tienePermiso('org.company.update'));
const puedeVerSucursales = computed(() => tienePermiso('org.branch.read'));
const puedeCrearSucursal = computed(() => tienePermiso('org.branch.create'));
const puedeEditarSucursal = computed(() => tienePermiso('org.branch.update'));
const puedeVerModulos = computed(() => tienePermiso('org.module.read'));
const puedeManejarModulos = computed(() => tienePermiso('org.module.manage'));

const companyColumns: QTableColumn<CompanyRow>[] = [
  { name: 'name', label: 'Empresa', field: 'name', align: 'left' },
  { name: 'code', label: 'Código', field: 'code', align: 'left' },
  { name: 'legal_name', label: 'Razón social', field: 'legal_name', align: 'left' },
  { name: 'tax_id', label: 'RUC', field: 'tax_id', align: 'left' },
  { name: 'estado', label: 'Estado', field: 'is_active', align: 'left' },
];

const branchColumns: QTableColumn<BranchRow>[] = [
  { name: 'name', label: 'Sucursal', field: 'name', align: 'left' },
  { name: 'code', label: 'Código', field: 'code', align: 'left' },
  { name: 'address', label: 'Dirección', field: 'address', align: 'left' },
  { name: 'phone', label: 'Teléfono', field: 'phone', align: 'left' },
  { name: 'estado', label: 'Estado', field: 'is_active', align: 'left' },
  { name: 'acciones', label: '', field: 'id', align: 'right' },
];

// --- Perfil de la empresa activa ---
const perfil = reactive({ legal_name: '', tax_id: '', address: '', phone: '', email: '' });
const savingPerfil = ref(false);

async function guardarPerfil() {
  savingPerfil.value = true;
  try {
    await updateCompanyProfile({ ...perfil });
    $q.notify({ type: 'positive', message: 'Perfil de la empresa guardado.' });
    await reload();
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e) || 'No se pudo guardar el perfil.' });
  } finally {
    savingPerfil.value = false;
  }
}

// --- Nueva empresa ---
const dlgEmpresa = ref(false);
const savingEmpresa = ref(false);
const nuevaEmpresa = reactive({
  name: '',
  code: '',
  legal_name: '',
  tax_id: '',
  address: '',
  phone: '',
  email: '',
});

function abrirCrearEmpresa() {
  Object.assign(nuevaEmpresa, {
    name: '',
    code: '',
    legal_name: '',
    tax_id: '',
    address: '',
    phone: '',
    email: '',
  });
  dlgEmpresa.value = true;
}

async function crearEmpresa() {
  savingEmpresa.value = true;
  try {
    await createCompany({ ...nuevaEmpresa, name: nuevaEmpresa.name.trim() });
    dlgEmpresa.value = false;
    $q.notify({ type: 'positive', message: `Empresa "${nuevaEmpresa.name.trim()}" creada.` });
    // La sesión trae el selector de empresas: recargarla para que aparezca la nueva.
    await sessionBootstrap.loadSession({ force: true });
    await reload();
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e) || 'No se pudo crear la empresa.' });
  } finally {
    savingEmpresa.value = false;
  }
}

// --- Sucursales ---
const dlgSucursal = ref(false);
const savingSucursal = ref(false);
const sucursalEnEdicion = ref<BranchRow | null>(null);
const formSucursal = reactive({
  name: '',
  code: '',
  address: '',
  phone: '',
  email: '',
  is_active: true,
});

function abrirCrearSucursal() {
  sucursalEnEdicion.value = null;
  Object.assign(formSucursal, {
    name: '',
    code: '',
    address: '',
    phone: '',
    email: '',
    is_active: true,
  });
  dlgSucursal.value = true;
}

function abrirEditarSucursal(b: BranchRow) {
  sucursalEnEdicion.value = b;
  Object.assign(formSucursal, {
    name: b.name,
    code: b.code,
    address: b.address,
    phone: b.phone,
    email: b.email,
    is_active: b.is_active,
  });
  dlgSucursal.value = true;
}

async function guardarSucursal() {
  const nombre = formSucursal.name.trim();
  if (!nombre) return;
  savingSucursal.value = true;
  try {
    if (sucursalEnEdicion.value) {
      await updateBranch(sucursalEnEdicion.value.id, { ...formSucursal, name: nombre });
      $q.notify({ type: 'positive', message: 'Sucursal actualizada.' });
    } else {
      await createBranch({
        name: nombre,
        code: formSucursal.code,
        address: formSucursal.address,
        phone: formSucursal.phone,
        email: formSucursal.email,
      });
      $q.notify({ type: 'positive', message: `Sucursal "${nombre}" creada.` });
    }
    dlgSucursal.value = false;
    // Las sucursales también alimentan el selector del topbar.
    await sessionBootstrap.loadSession({ force: true });
    await reload();
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e) || 'No se pudo guardar la sucursal.' });
  } finally {
    savingSucursal.value = false;
  }
}

// --- Módulos por empresa ---
const togglingCode = ref<string | null>(null);

const TITULOS_CATEGORIA: Record<string, string> = {
  CORE: 'Núcleo (siempre encendidos)',
  OPERATIONS: 'Operación',
  FINANCE: 'Finanzas',
  VERTICAL: 'Verticales (según el giro de la empresa)',
};

const gruposModulos = computed(() => {
  const orden = ['CORE', 'OPERATIONS', 'FINANCE', 'VERTICAL'];
  return orden
    .map((categoria) => ({
      categoria,
      titulo: TITULOS_CATEGORIA[categoria] ?? categoria,
      modulos: modulos.value.filter((m) => m.category === categoria),
    }))
    .filter((g) => g.modulos.length > 0);
});

async function toggleModulo(m: ModuleState, habilitar: boolean) {
  togglingCode.value = m.code;
  try {
    modulos.value = await updateCompanyModules([{ code: m.code, is_enabled: habilitar }]);
    $q.notify({
      type: 'positive',
      message: `${m.label} ${habilitar ? 'encendido' : 'apagado'} para ${companyName.value}.`,
    });
    // Refrescar effective_modules para que el menú reaccione al instante.
    await sessionBootstrap.loadSession({ force: true });
  } catch (e) {
    // 409 = dependencia entre módulos; el backend explica cuál falta.
    $q.notify({ type: 'negative', message: apiErrorMessage(e) || 'No se pudo cambiar el módulo.' });
  } finally {
    togglingCode.value = null;
  }
}

// --- Carga ---
async function reload() {
  loading.value = true;
  try {
    const tareas: Promise<void>[] = [
      listCompanies().then((rows) => {
        companies.value = rows;
      }),
      getCompanyProfile().then((p) => {
        Object.assign(perfil, p);
      }),
    ];
    if (puedeVerSucursales.value) {
      tareas.push(
        listBranches().then((rows) => {
          branches.value = rows;
        }),
      );
    }
    if (puedeVerModulos.value) {
      tareas.push(
        listCompanyModules().then((rows) => {
          modulos.value = rows;
        }),
      );
    }
    await Promise.all(tareas);
  } catch {
    $q.notify({ type: 'negative', message: 'No se pudo cargar la organización.' });
  } finally {
    loading.value = false;
  }
}

onMounted(reload);
</script>

<style scoped>




.org-tabs {
  color: var(--app-text-muted);
}

.org-panels {
  background: transparent;
}



.org-card {
  max-width: 560px;
  padding: var(--app-space-5);
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-lg);
  background: var(--app-surface);
}

.org-card__title {
  font-weight: 800;
  font-size: 1.1rem;
  color: var(--app-text);
}


.org-modulos-intro {
  max-width: 640px;
}

.org-modgroup {
  margin-bottom: var(--app-space-5);
}

.org-modgroup__title {
  font-weight: 700;
  font-size: 0.78rem;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--app-text-muted);
  margin-bottom: var(--app-space-3);
}

.org-modgrid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: var(--app-space-3);
}

.org-modcard {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--app-space-2);
  padding: var(--app-space-3) var(--app-space-4);
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-md);
  background: var(--app-surface);
}

.org-modcard__label {
  font-weight: 600;
  color: var(--app-text);
}

.org-modcard__code {
  font-size: 0.72rem;
  color: var(--app-text-muted);
}


</style>
