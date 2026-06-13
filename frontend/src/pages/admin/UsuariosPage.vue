<template>
  <q-page class="app-page">
    <PageHeader
      title="Usuarios y acceso"
      :subtitle="`Quién entra a ${companyName} y con qué roles. Un rol da permisos en toda la empresa o solo en una sucursal.`"
      :loading="loading"
      @refresh="reload"
    />

    <div class="usr-actions">
      <q-input
        v-model="busqueda"
        dense
        outlined
        clearable
        placeholder="Buscar por usuario o correo…"
        class="usr-search"
        :debounce="350"
        @update:model-value="reload"
      >
        <template #prepend><q-icon name="search" /></template>
      </q-input>
    </div>

    <q-table
      class="app-table"
      :rows="usuarios"
      :columns="columns"
      row-key="id"
      flat
      :loading="loading"
      :pagination="{ rowsPerPage: 25 }"
      no-data-label="No hay usuarios con acceso en esta empresa."
    >
      <template #body-cell-estado="props">
        <q-td :props="props">
          <q-chip v-if="props.row.is_active" dense color="secondary" text-color="white">
            Activo
          </q-chip>
          <q-chip v-else dense outline color="grey-7">Inactivo</q-chip>
        </q-td>
      </template>

      <template #body-cell-roles="props">
        <q-td :props="props">
          <div class="usr-chips">
            <q-chip
              v-for="r in props.row.roles"
              :key="r.assignment_id"
              dense
              outline
              color="primary"
              :removable="puedeGestionar"
              @remove="confirmarRevocar(props.row, r)"
            >
              {{ r.role_name }}
              <q-tooltip>
                {{ r.org_unit_type === 'BRANCH' ? 'Sucursal' : 'Empresa' }}:
                {{ r.org_unit_name }}
              </q-tooltip>
            </q-chip>
            <span v-if="props.row.roles.length === 0" class="text-caption text-muted">
              Sin roles en esta empresa
            </span>
          </div>
        </q-td>
      </template>

      <template #body-cell-acciones="props">
        <q-td :props="props" class="text-right usr-acciones">
          <q-btn
            v-if="puedeGestionar"
            flat
            dense
            no-caps
            size="sm"
            icon="person_add"
            label="Asignar rol"
            @click="abrirAsignar(props.row)"
          />
          <q-btn
            flat
            dense
            no-caps
            size="sm"
            icon="key"
            label="Permisos"
            @click="verPermisos(props.row)"
          />
        </q-td>
      </template>
    </q-table>

    <!-- Diálogo: asignar rol -->
    <q-dialog v-model="dlgAsignar">
      <q-card class="app-dialog">
        <q-card-section class="text-h6">
          Asignar rol a {{ usuarioObjetivo?.username }}
        </q-card-section>
        <q-card-section class="app-form">
          <q-select
            v-model="formAsignar.role_id"
            :options="opcionesRol"
            label="Rol"
            outlined
            dense
            emit-value
            map-options
            :loading="cargandoRoles"
          >
            <template #option="scope">
              <q-item v-bind="scope.itemProps">
                <q-item-section>
                  <q-item-label>{{ scope.opt.label }}</q-item-label>
                  <q-item-label caption lines="2">{{ scope.opt.description }}</q-item-label>
                </q-item-section>
              </q-item>
            </template>
          </q-select>
          <q-select
            v-model="formAsignar.org_unit_id"
            :options="opcionesAlcance"
            label="Alcance"
            outlined
            dense
            emit-value
            map-options
            hint="Empresa = aplica en toda la empresa; sucursal = solo ahí."
          />
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat no-caps label="Cancelar" v-close-popup />
          <q-btn
            unelevated
            no-caps
            color="primary"
            label="Asignar"
            :loading="guardando"
            :disable="formAsignar.role_id == null || formAsignar.org_unit_id == null"
            @click="asignar"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <!-- Diálogo: permisos efectivos -->
    <q-dialog v-model="dlgPermisos">
      <q-card class="app-dialog">
        <q-card-section class="text-h6">
          Permisos efectivos de {{ usuarioObjetivo?.username }}
        </q-card-section>
        <q-card-section>
          <div class="text-caption text-muted q-mb-sm">
            Lo que este usuario puede hacer HOY en {{ companyName }} (suma de todos sus roles).
          </div>
          <q-spinner v-if="cargandoPermisos" color="primary" size="24px" />
          <template v-else>
            <div class="usr-permcount q-mb-sm">
              {{ permisosEfectivos.length }}
              {{ permisosEfectivos.length === 1 ? 'permiso' : 'permisos' }}
            </div>
            <div class="usr-permlist">
              <code v-for="p in permisosEfectivos" :key="p" class="usr-perm">{{ p }}</code>
              <span v-if="permisosEfectivos.length === 0" class="text-caption text-muted">
                Sin permisos en este contexto.
              </span>
            </div>
          </template>
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat no-caps label="Cerrar" v-close-popup />
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
import { listRoles, type Role } from 'src/features/hr/hr.api';
import { listBranches, type BranchRow } from 'src/features/org/org.api';
import {
  assignRole,
  getUserEffectivePermissions,
  listScopeUsers,
  revokeAssignment,
  type ScopeUserRow,
  type UserRoleRow,
} from 'src/features/rbac/rbac.api';
import { useAclStore } from 'src/stores/acl.store';
import { useContextStore } from 'src/stores/context.store';

const $q = useQuasar();
const acl = useAclStore();
const ctx = useContextStore();

const loading = ref(false);
const guardando = ref(false);
const busqueda = ref('');
const usuarios = ref<ScopeUserRow[]>([]);

const companyName = computed(() => acl.companyName(ctx.activeCompanyId) ?? 'la empresa activa');

const puedeGestionar = computed(() => {
  const companyId = ctx.activeCompanyId;
  return companyId ? acl.hasPermission(companyId, 'rbac.assignments.update') : false;
});

const puedeVerSucursales = computed(() => {
  const companyId = ctx.activeCompanyId;
  return companyId ? acl.hasPermission(companyId, 'org.branch.read') : false;
});

const columns: QTableColumn<ScopeUserRow>[] = [
  { name: 'username', label: 'Usuario', field: 'username', align: 'left' },
  { name: 'email', label: 'Correo', field: 'email', align: 'left' },
  { name: 'estado', label: 'Estado', field: 'is_active', align: 'left' },
  { name: 'roles', label: 'Roles', field: 'id', align: 'left' },
  { name: 'acciones', label: '', field: 'id', align: 'right' },
];

async function reload() {
  loading.value = true;
  try {
    usuarios.value = await listScopeUsers(busqueda.value?.trim() ?? '');
  } catch {
    $q.notify({ type: 'negative', message: 'No se pudieron cargar los usuarios.' });
  } finally {
    loading.value = false;
  }
}

// --- Asignar rol ---
const dlgAsignar = ref(false);
const usuarioObjetivo = ref<ScopeUserRow | null>(null);
const roles = ref<Role[]>([]);
const sucursales = ref<BranchRow[]>([]);
const cargandoRoles = ref(false);
const formAsignar = reactive<{ role_id: number | null; org_unit_id: number | null }>({
  role_id: null,
  org_unit_id: null,
});

const opcionesRol = computed(() =>
  roles.value.map((r) => ({ label: r.name, value: r.id, description: r.description })),
);

const opcionesAlcance = computed(() => {
  const companyId = Number(ctx.activeCompanyId);
  const out: { label: string; value: number }[] = [
    { label: `Toda la empresa (${companyName.value})`, value: companyId },
  ];
  for (const b of sucursales.value) {
    out.push({ label: `Sucursal: ${b.name}`, value: b.id });
  }
  return out;
});

async function abrirAsignar(u: ScopeUserRow) {
  usuarioObjetivo.value = u;
  formAsignar.role_id = null;
  formAsignar.org_unit_id = Number(ctx.activeCompanyId);
  dlgAsignar.value = true;
  if (roles.value.length === 0) {
    cargandoRoles.value = true;
    try {
      roles.value = await listRoles();
    } catch {
      $q.notify({ type: 'negative', message: 'No se pudo cargar el catálogo de roles.' });
    } finally {
      cargandoRoles.value = false;
    }
  }
  if (puedeVerSucursales.value && sucursales.value.length === 0) {
    try {
      sucursales.value = await listBranches();
    } catch {
      /* sin sucursales: solo alcance empresa */
    }
  }
}

async function asignar() {
  if (!usuarioObjetivo.value || formAsignar.role_id == null || formAsignar.org_unit_id == null) {
    return;
  }
  guardando.value = true;
  try {
    await assignRole({
      user_id: usuarioObjetivo.value.id,
      role_id: formAsignar.role_id,
      org_unit_id: formAsignar.org_unit_id,
    });
    dlgAsignar.value = false;
    $q.notify({ type: 'positive', message: 'Rol asignado.' });
    await reload();
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e) || 'No se pudo asignar el rol.' });
  } finally {
    guardando.value = false;
  }
}

// --- Revocar ---
function confirmarRevocar(u: ScopeUserRow, r: UserRoleRow) {
  $q.dialog({
    title: 'Quitar rol',
    message: `¿Quitar el rol "${r.role_name}" (${r.org_unit_name}) a ${u.username}? Deja de tener esos permisos al instante.`,
    cancel: { flat: true, noCaps: true, label: 'Cancelar' },
    ok: { unelevated: true, noCaps: true, color: 'negative', label: 'Quitar rol' },
    persistent: true,
  }).onOk(() => {
    void revocar(r.assignment_id);
  });
}

async function revocar(assignmentId: number) {
  try {
    await revokeAssignment(assignmentId);
    $q.notify({ type: 'positive', message: 'Rol revocado.' });
    await reload();
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e) || 'No se pudo revocar el rol.' });
  }
}

// --- Permisos efectivos ---
const dlgPermisos = ref(false);
const cargandoPermisos = ref(false);
const permisosEfectivos = ref<string[]>([]);

async function verPermisos(u: ScopeUserRow) {
  usuarioObjetivo.value = u;
  permisosEfectivos.value = [];
  dlgPermisos.value = true;
  cargandoPermisos.value = true;
  try {
    permisosEfectivos.value = (await getUserEffectivePermissions(u.id)).sort();
  } catch {
    $q.notify({ type: 'negative', message: 'No se pudieron cargar los permisos.' });
  } finally {
    cargandoPermisos.value = false;
  }
}


onMounted(reload);
</script>

<style scoped>




.usr-actions {
  display: flex;
  align-items: center;
  gap: var(--app-space-3);
  margin-bottom: var(--app-space-4);
}

.usr-search {
  width: 320px;
  max-width: 100%;
}


.usr-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.usr-acciones {
  white-space: nowrap;
}



.usr-permcount {
  font-weight: 700;
  font-size: 0.8rem;
  color: var(--app-text);
}

.usr-permlist {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  max-height: 50vh;
  overflow: auto;
}

.usr-perm {
  font-size: 0.72rem;
  padding: 2px 6px;
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-sm);
  background: var(--app-surface);
  color: var(--app-text-muted);
}

</style>
