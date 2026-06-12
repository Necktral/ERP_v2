<template>
  <q-page class="app-page">
    <PageHeader
      title="Trabajadores"
      subtitle="Personas de la empresa. Creá nuevos o editá los existentes."
      :loading="loading"
      @refresh="reload"
    >
      <template #actions>
        <q-btn
          unelevated
          no-caps
          color="primary"
          icon="person_add"
          label="Nuevo trabajador"
          to="/recursos-humanos/trabajadores/nuevo"
        />
      </template>
    </PageHeader>

    <!-- Listado -->
    <q-table
      class="app-table"
      :rows="employees"
      :columns="columns"
      row-key="id"
      flat
      :loading="loading"
      :pagination="{ rowsPerPage: 25 }"
      no-data-label="Aún no hay trabajadores. Empieza con el alta rápida de arriba."
    >
      <template #body-cell-nombre="props">
        <q-td :props="props">
          <EmployeeAvatar
            :employee-id="props.row.id"
            :nombre="`${props.row.first_name} ${props.row.last_name}`"
            :has-photo="props.row.has_photo"
            :size="32"
            class="q-mr-sm"
          />
          <router-link :to="`/recursos-humanos/trabajadores/${props.row.id}`" class="hr-name-link">
            {{ props.row.first_name }} {{ props.row.last_name }}
          </router-link>
          <q-chip
            v-if="props.row.employment_status === 'SUSPENDIDO'"
            dense
            color="warning"
            text-color="white"
            label="Suspendido"
            class="q-ml-xs"
          />
          <q-chip
            v-else-if="props.row.employment_status === 'BAJA'"
            dense
            color="negative"
            text-color="white"
            label="Baja"
            class="q-ml-xs"
          />
        </q-td>
      </template>

      <template #body-cell-roles="props">
        <q-td :props="props">
          <div class="hr-roles-cell">
            <q-chip
              v-for="r in props.row.roles"
              :key="r.role_id"
              dense
              square
              color="primary"
              text-color="white"
              class="hr-role-chip"
            >
              {{ r.role_name }}
            </q-chip>
            <span v-if="props.row.roles.length > 0" class="hr-roles-count">
              {{ props.row.roles.length }}
            </span>
            <span v-else class="text-caption text-muted">sin roles</span>
          </div>
        </q-td>
      </template>

      <template #body-cell-estado="props">
        <q-td :props="props">
          <q-chip
            v-if="props.row.has_active_assignment"
            dense
            color="secondary"
            text-color="white"
            icon="badge"
          >
            {{ props.row.active_assignments[0]?.position_name }}
          </q-chip>
          <q-chip v-else dense outline color="grey-7" icon="badge">Sin asignar</q-chip>
          <q-chip
            v-if="props.row.linked_user_id"
            dense
            color="primary"
            text-color="white"
            icon="vpn_key"
          >
            {{ props.row.linked_username }}
          </q-chip>
        </q-td>
      </template>

      <template #body-cell-acciones="props">
        <q-td :props="props" class="text-right">
          <q-btn
            flat
            dense
            no-caps
            size="sm"
            icon="folder_shared"
            label="Perfil"
            :to="`/recursos-humanos/trabajadores/${props.row.id}`"
          />
          <q-btn flat dense no-caps size="sm" icon="edit" label="Editar" @click="openEdit(props.row)" />
          <q-btn
            flat
            dense
            no-caps
            size="sm"
            icon="admin_panel_settings"
            label="Roles"
            @click="openRoles(props.row)"
          />
          <q-btn flat dense no-caps size="sm" icon="badge" label="Asignar" @click="openAssign(props.row)" />
          <q-btn
            flat
            dense
            no-caps
            size="sm"
            icon="vpn_key"
            label="Acceso"
            :disable="!props.row.has_active_assignment || !!props.row.linked_user_id"
            @click="openProvision(props.row)"
          />
        </q-td>
      </template>
    </q-table>

    <!-- Diálogo: roles directos del trabajador -->
    <EmployeeRolesDialog
      v-model="rolesDialog"
      :employee-id="rolesEmployeeId"
      :employee-name="rolesEmployeeName"
      @saved="reload"
    />

    <!-- Diálogo: asignar puesto + sucursal -->
    <q-dialog v-model="assignDialog">
      <q-card class="app-dialog">
        <q-card-section class="text-h6">Asignar puesto</q-card-section>
        <q-card-section class="q-gutter-md">
          <div class="text-caption text-muted">
            {{ assignTarget?.first_name }} {{ assignTarget?.last_name }}
          </div>
          <q-select
            v-model="assignForm.position_id"
            :options="positionOptions"
            label="Puesto *"
            outlined
            dense
            emit-value
            map-options
          />
          <q-select
            v-model="assignForm.branch_id"
            :options="branchOptions"
            label="Sucursal"
            hint="Necesaria si el puesto otorga roles a nivel sucursal"
            outlined
            dense
            emit-value
            map-options
            clearable
          />
          <div v-if="currentPositionName" class="hr-assign-current">
            <div class="text-caption text-muted">
              Puesto actual: <strong>{{ currentPositionName }}</strong>
            </div>
            <q-toggle
              v-model="addAsExtra"
              dense
              label="Agregar como puesto adicional (mantener el actual)"
            />
            <div class="text-caption text-muted">
              {{ addAsExtra ? 'Tendrá ambos puestos.' : 'Se reemplaza el puesto actual.' }}
            </div>
          </div>
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat label="Cancelar" v-close-popup />
          <q-btn
            unelevated
            color="primary"
            label="Asignar"
            :loading="saving"
            :disable="!assignForm.position_id"
            @click="doAssign"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <!-- Diálogo: editar trabajador -->
    <q-dialog v-model="editDialog">
      <q-card class="app-dialog">
        <q-card-section class="text-h6">Editar trabajador</q-card-section>
        <q-card-section class="q-gutter-md">
          <div class="row q-col-gutter-md">
            <q-input
              v-model="editForm.first_name"
              label="Nombres *"
              outlined
              dense
              class="col-12 col-sm-6"
            />
            <q-input
              v-model="editForm.last_name"
              label="Apellidos"
              outlined
              dense
              class="col-12 col-sm-6"
            />
          </div>
          <q-input v-model="editForm.employee_code" label="Código" outlined dense />
          <q-input v-model="editForm.phone" label="Teléfono" outlined dense />
          <q-input v-model="editForm.email" label="Correo" type="email" outlined dense />
          <q-toggle v-model="editForm.is_active" label="Trabajador activo" />
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat label="Cancelar" v-close-popup />
          <q-btn
            unelevated
            color="primary"
            label="Guardar"
            :loading="saving"
            :disable="!editForm.first_name.trim()"
            @click="doEdit"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <!-- Diálogo: provisionar acceso -->
    <q-dialog v-model="provisionDialog">
      <q-card class="app-dialog">
        <q-card-section class="text-h6">Provisionar acceso</q-card-section>
        <q-card-section v-if="!provisionResult" class="q-gutter-md">
          <div class="text-caption text-muted">
            Se creará un usuario para {{ provTarget?.first_name }} con clave temporal.
          </div>
          <q-input v-model="provForm.username" label="Usuario *" outlined dense autofocus />
          <q-input v-model="provForm.email" label="Correo (opcional)" type="email" outlined dense />
        </q-card-section>
        <q-card-section v-else class="q-gutter-sm">
          <q-banner class="hr-dialog__ok" rounded>
            <template #avatar><q-icon name="check_circle" color="secondary" /></template>
            Usuario <strong>{{ provisionResult.username }}</strong> creado.
          </q-banner>
          <div class="text-caption text-muted">
            Clave temporal (cópiala ahora, no se vuelve a mostrar):
          </div>
          <q-input :model-value="provisionResult.temp_password" outlined dense readonly>
            <template #append>
              <q-btn flat dense round icon="content_copy" @click="copyTemp" />
            </template>
          </q-input>
        </q-card-section>
        <q-card-actions align="right">
          <q-btn v-if="!provisionResult" flat label="Cancelar" v-close-popup />
          <q-btn
            v-if="!provisionResult"
            unelevated
            color="primary"
            label="Crear acceso"
            :loading="saving"
            :disable="!provForm.username"
            @click="doProvision"
          />
          <q-btn v-else unelevated color="primary" label="Listo" v-close-popup />
        </q-card-actions>
      </q-card>
    </q-dialog>
  </q-page>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import { useQuasar, copyToClipboard, type QTableColumn } from 'quasar';
import PageHeader from 'src/components/PageHeader.vue';
import {
  createAssignment,
  endAssignment,
  listBranches,
  listEmployees,
  listPositions,
  provisionUser,
  updateEmployee,
  type EmployeeRow,
  type ProvisionResult,
} from 'src/features/hr/hr.api';
import { apiErrorMessage } from 'src/core/api';
import EmployeeAvatar from 'src/features/hr/EmployeeAvatar.vue';
import EmployeeRolesDialog from 'src/features/hr/EmployeeRolesDialog.vue';

const $q = useQuasar();

const loading = ref(false);
const saving = ref(false);
const employees = ref<EmployeeRow[]>([]);

const columns: QTableColumn<EmployeeRow>[] = [
  { name: 'employee_code', label: 'Código', field: 'employee_code', align: 'left' },
  {
    name: 'nombre',
    label: 'Nombre',
    field: (r) => `${r.first_name} ${r.last_name}`.trim(),
    align: 'left',
  },
  { name: 'roles', label: 'Roles', field: 'id', align: 'left' },
  { name: 'phone', label: 'Teléfono', field: 'phone', align: 'left' },
  { name: 'email', label: 'Correo', field: 'email', align: 'left' },
  { name: 'estado', label: 'Estado', field: 'id', align: 'left' },
  { name: 'acciones', label: '', field: 'id', align: 'right' },
];

// Selectores para diálogos
const positionOptions = ref<{ label: string; value: number }[]>([]);
const branchOptions = ref<{ label: string; value: number }[]>([]);

async function reload() {
  loading.value = true;
  try {
    employees.value = await listEmployees();
  } catch {
    $q.notify({ type: 'negative', message: 'No se pudieron cargar los trabajadores.' });
  } finally {
    loading.value = false;
  }
}

async function loadSelectors() {
  try {
    const [positions, branches] = await Promise.all([listPositions(), listBranches()]);
    positionOptions.value = positions.map((p) => ({ label: p.name, value: p.id }));
    branchOptions.value = branches.map((b) => ({ label: b.name, value: b.id }));
  } catch {
    /* selectores opcionales: si fallan, los diálogos quedan vacíos */
  }
}

// --- Roles directos del trabajador ---
const rolesDialog = ref(false);
const rolesEmployeeId = ref<number | null>(null);
const rolesEmployeeName = ref('');

function openRoles(emp: EmployeeRow) {
  rolesEmployeeId.value = emp.id;
  rolesEmployeeName.value = `${emp.first_name} ${emp.last_name}`.trim();
  rolesDialog.value = true;
}

// --- Editar trabajador ---
const editDialog = ref(false);
const editTarget = ref<EmployeeRow | null>(null);
const editForm = reactive({
  first_name: '',
  last_name: '',
  employee_code: '',
  phone: '',
  email: '',
  is_active: true,
});

function openEdit(emp: EmployeeRow) {
  editTarget.value = emp;
  editForm.first_name = emp.first_name;
  editForm.last_name = emp.last_name;
  editForm.employee_code = emp.employee_code;
  editForm.phone = emp.phone;
  editForm.email = emp.email;
  editForm.is_active = emp.is_active;
  editDialog.value = true;
}

async function doEdit() {
  if (!editTarget.value || !editForm.first_name.trim()) return;
  saving.value = true;
  try {
    await updateEmployee(editTarget.value.id, {
      first_name: editForm.first_name.trim(),
      last_name: editForm.last_name.trim(),
      employee_code: editForm.employee_code.trim(),
      phone: editForm.phone.trim(),
      email: editForm.email.trim(),
      is_active: editForm.is_active,
    });
    $q.notify({ type: 'positive', message: 'Trabajador actualizado.' });
    editDialog.value = false;
    await reload();
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e) || 'No se pudo actualizar el trabajador.' });
  } finally {
    saving.value = false;
  }
}

// --- Asignar ---
const assignDialog = ref(false);
const assignTarget = ref<EmployeeRow | null>(null);
const addAsExtra = ref(false);
const assignForm = reactive<{ position_id: number | null; branch_id: number | null }>({
  position_id: null,
  branch_id: null,
});

const currentPositionName = computed(
  () => assignTarget.value?.active_assignments?.[0]?.position_name ?? '',
);

function openAssign(emp: EmployeeRow) {
  assignTarget.value = emp;
  assignForm.position_id = null;
  assignForm.branch_id = null;
  addAsExtra.value = false;
  assignDialog.value = true;
}

async function doAssign() {
  if (!assignTarget.value || !assignForm.position_id) return;
  saving.value = true;
  try {
    // Por defecto, un trabajador tiene UN puesto: reemplazamos el actual.
    // Multi-puesto solo si se pide explícitamente (caso poco frecuente).
    const current = assignTarget.value.active_assignments ?? [];
    if (!addAsExtra.value && current.length > 0) {
      for (const a of current) {
        await endAssignment(assignTarget.value.id, a.id);
      }
    }
    await createAssignment(assignTarget.value.id, {
      position_id: assignForm.position_id,
      branch_id: assignForm.branch_id,
    });
    $q.notify({ type: 'positive', message: 'Puesto asignado.' });
    assignDialog.value = false;
    await reload();
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e) || 'No se pudo asignar.' });
  } finally {
    saving.value = false;
  }
}

// --- Provisionar ---
const provisionDialog = ref(false);
const provTarget = ref<EmployeeRow | null>(null);
const provForm = reactive({ username: '', email: '' });
const provisionResult = ref<ProvisionResult | null>(null);

function openProvision(emp: EmployeeRow) {
  provTarget.value = emp;
  provForm.username = (emp.first_name + emp.last_name).toLowerCase().replace(/\s+/g, '') || '';
  provForm.email = emp.email || '';
  provisionResult.value = null;
  provisionDialog.value = true;
}

async function doProvision() {
  if (!provTarget.value || !provForm.username) return;
  saving.value = true;
  try {
    provisionResult.value = await provisionUser(provTarget.value.id, {
      username: provForm.username.trim(),
      email: provForm.email.trim(),
    });
    await reload();
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e) || 'No se pudo provisionar el acceso.' });
  } finally {
    saving.value = false;
  }
}

function copyTemp() {
  if (provisionResult.value) {
    void copyToClipboard(provisionResult.value.temp_password);
    $q.notify({ type: 'info', message: 'Clave temporal copiada.' });
  }
}


onMounted(async () => {
  await Promise.all([reload(), loadSelectors()]);
});
</script>

<style scoped>




kbd {
  background: var(--app-surface-strong);
  border: 1px solid var(--app-border-strong);
  border-radius: 6px;
  padding: 0 6px;
  font-size: 0.78rem;
}

.hr-quickadd {
  padding: var(--app-space-4);
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-lg);
  background: var(--app-surface);
  box-shadow: var(--app-shadow-soft);
  margin-bottom: var(--app-space-5);
}

.hr-quickadd__grid {
  display: grid;
  grid-template-columns: 1.2fr 1.2fr 0.9fr 1fr 1.4fr auto;
  gap: var(--app-space-3);
  align-items: start;
}

@media (max-width: 900px) {
  .hr-quickadd__grid {
    grid-template-columns: 1fr 1fr;
  }
}

.hr-quickadd__hint {
  margin-top: var(--app-space-3);
  font-size: 0.78rem;
  color: var(--app-text-muted);
}


.hr-name-link {
  color: var(--app-text);
  font-weight: 600;
  text-decoration: none;
}

.hr-name-link:hover {
  color: var(--app-primary);
  text-decoration: underline;
}

.hr-roles-cell {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 3px;
  max-width: 340px;
}

.hr-role-chip {
  font-size: 0.68rem;
}

.hr-roles-count {
  font-size: 0.7rem;
  font-weight: 700;
  color: var(--app-text-muted);
}


.hr-dialog__ok {
  border: 1px solid var(--app-border-strong);
  background: var(--app-surface);
}

</style>
