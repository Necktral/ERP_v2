<template>
  <AppContainer>
    <AppPageHeader
      title="HR · Empleados"
      subtitle="GET/POST /hr/employees/ · PATCH /hr/employees/{id}/ · POST /hr/employees/{id}/assignments/ · POST /.../end/ · POST /hr/employees/{id}/provision-user/"
    >
      <template #badges>
        <q-badge outline color="primary">Company: {{ companyLabel }}</q-badge>
        <q-badge outline>Read: hr.employee.read</q-badge>
        <q-badge outline v-if="canCreate">Create: hr.employee.create</q-badge>
        <q-badge outline v-if="canUpdate">Update: hr.employee.update</q-badge>
        <q-badge outline v-if="canAssign">Assign: hr.assignment.create</q-badge>
        <q-badge outline v-if="canEndAssign">End: hr.assignment.end</q-badge>
        <q-badge outline v-if="canProvision">Provision: iam.users.create</q-badge>
      </template>

      <template #actions>
        <q-btn flat label="Recargar" :disable="loading" @click="load" />
        <q-btn v-if="canCreate" color="primary" label="Nuevo empleado" @click="openCreate" />
      </template>
    </AppPageHeader>

    <div class="q-mt-md">
      <AppDataTable
        title="Listado"
        caption="Flujo PC-first: crear/editar empleado, asignar puesto/sucursal, provisionar acceso y terminar asignaciones."
        :rows="rows"
        :columns="columns"
        row-key="id"
        :loading="loading"
        :rows-per-page-options="[10, 20, 50, 0]"
        :filter="filter"
      >
        <template #toolbar>
          <q-input v-model="filter" dense outlined placeholder="Buscar…" style="width: 280px" />
        </template>

        <template #body-cell-is_active="props">
          <q-td :props="props">
            <q-badge v-if="props.row.is_active" outline>ACTIVO</q-badge>
            <q-badge v-else outline color="negative">INACTIVO</q-badge>
          </q-td>
        </template>

        <template #body-cell-assignment="props">
          <q-td :props="props">
            <template v-if="props.row.active_assignments?.length">
              <div class="row items-center q-gutter-xs">
                <q-badge outline color="primary">
                  {{ props.row.active_assignments[0].position_name }}
                </q-badge>
                <q-badge
                  v-if="props.row.active_assignments[0].branch_name"
                  outline
                  color="secondary"
                >
                  {{ props.row.active_assignments[0].branch_name }}
                </q-badge>
                <q-badge v-if="props.row.active_assignments.length > 1" outline>
                  +{{ props.row.active_assignments.length - 1 }}
                </q-badge>
              </div>
            </template>
            <q-badge v-else outline color="grey-7">SIN ASIGNACIÓN</q-badge>
          </q-td>
        </template>

        <template #body-cell-access="props">
          <q-td :props="props">
            <q-badge v-if="props.row.linked_user_id" outline color="positive">
              {{ props.row.linked_username || `user#${props.row.linked_user_id}` }}
            </q-badge>
            <q-badge v-else outline color="grey-7">SIN ACCESO</q-badge>
          </q-td>
        </template>

        <template #body-cell-actions="props">
          <q-td :props="props" class="text-right">
            <q-btn v-if="canUpdate" dense flat icon="edit" @click="openEdit(props.row)" />
            <q-btn v-if="canAssign" dense flat icon="work" @click="openAssign(props.row)" />
            <q-btn
              v-if="canEndAssign"
              dense
              flat
              icon="event_busy"
              :disable="!props.row.active_assignments?.length"
              @click="openEnd(props.row)"
            />
            <q-btn
              v-if="canProvision"
              dense
              flat
              icon="vpn_key"
              :disable="!!props.row.linked_user_id"
              @click="openProvision(props.row)"
            />
          </q-td>
        </template>
      </AppDataTable>

      <q-banner v-if="errorMsg" class="q-mt-md" dense rounded>
        {{ errorMsg }}
      </q-banner>
    </div>

    <!-- Create/Edit dialog -->
    <q-dialog v-model="editDialog">
      <q-card style="width: 760px; max-width: 96vw" class="app-card">
        <q-card-section class="row items-center justify-between">
          <div class="text-h6">{{ editingId ? 'Editar empleado' : 'Nuevo empleado' }}</div>
          <q-btn flat icon="close" v-close-popup />
        </q-card-section>

        <q-separator />

        <q-card-section>
          <q-form @submit.prevent="saveEmployee">
            <div class="row q-col-gutter-md">
              <div class="col-12 col-md-4">
                <q-input v-model="form.employee_code" label="Código" outlined />
              </div>
              <div class="col-12 col-md-4">
                <q-input
                  v-model="form.first_name"
                  label="Nombres"
                  outlined
                  :rules="[(v) => !!String(v || '').trim() || 'Requerido']"
                />
              </div>
              <div class="col-12 col-md-4">
                <q-input v-model="form.last_name" label="Apellidos" outlined />
              </div>
            </div>

            <div class="row q-col-gutter-md q-mt-sm">
              <div class="col-12 col-md-6">
                <q-input v-model="form.phone" label="Teléfono" outlined />
              </div>
              <div class="col-12 col-md-6">
                <q-input v-model="form.email" label="Email" outlined />
              </div>
            </div>

            <div class="q-mt-sm" v-if="editingId">
              <q-toggle v-model="form.is_active" label="Activo" />
            </div>

            <div class="q-mt-md">
              <q-btn color="primary" type="submit" :loading="saving" label="Guardar" />
            </div>
          </q-form>
        </q-card-section>
      </q-card>
    </q-dialog>

    <!-- Assign dialog -->
    <q-dialog v-model="assignDialog">
      <q-card style="width: 760px; max-width: 96vw" class="app-card">
        <q-card-section class="row items-center justify-between">
          <div class="text-h6">Asignar puesto</div>
          <q-btn flat icon="close" v-close-popup />
        </q-card-section>

        <q-separator />

        <q-card-section>
          <div class="text-caption text-grey-7">
            Empleado: {{ assignTarget?.first_name }} {{ assignTarget?.last_name }}
          </div>

          <q-form class="q-mt-sm" @submit.prevent="doAssign">
            <div class="row q-col-gutter-md">
              <div class="col-12 col-md-6">
                <q-select
                  v-model="assignForm.position_id"
                  :options="positionOptions"
                  label="Puesto"
                  outlined
                  emit-value
                  map-options
                  :loading="positionsLoading"
                />
              </div>

              <div class="col-12 col-md-6">
                <q-select
                  v-model="assignForm.branch_id"
                  :options="branchOptions"
                  label="Sucursal (opcional)"
                  outlined
                  emit-value
                  map-options
                  clearable
                  :loading="branchesLoading"
                />
              </div>
            </div>

            <q-banner v-if="assignError" class="q-mt-md" dense rounded>
              {{ assignError }}
            </q-banner>

            <div class="q-mt-md">
              <q-btn color="primary" type="submit" :loading="assignSaving" label="Asignar" />
            </div>
          </q-form>
        </q-card-section>
      </q-card>
    </q-dialog>

    <!-- End assignment dialog -->
    <q-dialog v-model="endDialog">
      <q-card style="width: 760px; max-width: 96vw" class="app-card">
        <q-card-section class="row items-center justify-between">
          <div class="text-h6">Terminar asignación</div>
          <q-btn flat icon="close" v-close-popup />
        </q-card-section>

        <q-separator />

        <q-card-section>
          <div class="text-caption text-grey-7">
            Empleado: {{ endTarget?.first_name }} {{ endTarget?.last_name }}
          </div>

          <q-form class="q-mt-sm" @submit.prevent="doEnd">
            <q-select
              v-model="endAssignmentId"
              :options="endAssignmentOptions"
              label="Assignment ID"
              outlined
              emit-value
              map-options
              :disable="!endAssignmentOptions.length"
            />

            <q-banner v-if="!endAssignmentOptions.length" class="q-mt-md" dense rounded>
              No hay asignaciones activas en el resumen (recarga si acabas de asignar).
            </q-banner>

            <q-banner v-if="endError" class="q-mt-md" dense rounded>
              {{ endError }}
            </q-banner>

            <div class="q-mt-md">
              <q-btn color="negative" type="submit" :loading="endSaving" label="Terminar" />
            </div>
          </q-form>
        </q-card-section>
      </q-card>
    </q-dialog>

    <!-- Provision user dialog -->
    <q-dialog v-model="provDialog">
      <q-card style="width: 760px; max-width: 96vw" class="app-card">
        <q-card-section class="row items-center justify-between">
          <div class="text-h6">Provisionar acceso</div>
          <q-btn flat icon="close" v-close-popup />
        </q-card-section>

        <q-separator />

        <q-card-section>
          <div class="text-caption text-grey-7">
            Empleado: {{ provTarget?.first_name }} {{ provTarget?.last_name }}
          </div>

          <q-form class="q-mt-sm" @submit.prevent="doProvision">
            <div class="row q-col-gutter-md">
              <div class="col-12 col-md-6">
                <q-input
                  v-model="provForm.username"
                  label="Username"
                  outlined
                  :rules="[(v) => !!String(v || '').trim() || 'Requerido']"
                />
              </div>
              <div class="col-12 col-md-6">
                <q-input v-model="provForm.email" label="Email (opcional)" outlined />
              </div>
            </div>

            <div class="q-mt-sm">
              <q-toggle v-model="provForm.manualPass" label="Definir contraseña manual" />
            </div>

            <div class="q-mt-sm" v-if="provForm.manualPass">
              <q-input
                v-model="provForm.temp_password"
                label="Contraseña provisional"
                outlined
                type="password"
              />
            </div>

            <q-banner v-if="provError" class="q-mt-md" dense rounded>
              {{ provError }}
            </q-banner>

            <div class="q-mt-md">
              <q-btn color="primary" type="submit" :loading="provSaving" label="Provisionar" />
            </div>
          </q-form>
        </q-card-section>
      </q-card>
    </q-dialog>

    <!-- Provision result dialog -->
    <q-dialog v-model="provResultDialog">
      <q-card style="width: 560px; max-width: 96vw" class="app-card">
        <q-card-section class="row items-center justify-between">
          <div class="text-h6">Credenciales provisionales</div>
          <q-btn flat icon="close" v-close-popup />
        </q-card-section>

        <q-separator />

        <q-card-section>
          <div class="row q-col-gutter-md">
            <div class="col-12">
              <q-input
                :model-value="provResult?.username || ''"
                label="Username"
                outlined
                readonly
              />
            </div>
            <div class="col-12">
              <q-input
                :model-value="provResult?.temp_password || ''"
                label="Contraseña provisional"
                outlined
                readonly
              />
            </div>
          </div>

          <div class="q-mt-md">
            <q-btn flat icon="content_copy" label="Copiar contraseña" @click="copyProvPass" />
          </div>

          <q-banner class="q-mt-md" dense rounded>
            Guarda esta contraseña ahora: no se volverá a mostrar.
          </q-banner>
        </q-card-section>
      </q-card>
    </q-dialog>
  </AppContainer>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import { copyToClipboard, useQuasar } from 'quasar';
import type { QTableColumn } from 'quasar';
import { useAclStore } from 'src/stores/acl.store';
import { useContextStore } from 'src/stores/context.store';
import { extractErrorMessage } from 'src/core/http/errors';
import { listBranches } from 'src/services/org.service';
import {
  createAssignment,
  createEmployee,
  endAssignment,
  listEmployees,
  listPositions,
  patchEmployee,
  provisionEmployeeUser,
  type EmployeeRow,
  type PositionRow,
} from 'src/services/hr.service';
import AppContainer from 'src/ui/AppContainer.vue';
import AppDataTable from 'src/ui/AppDataTable.vue';
import AppPageHeader from 'src/ui/AppPageHeader.vue';

const $q = useQuasar();
const acl = useAclStore();
const ctx = useContextStore();

const companyLabel = computed(
  () => acl.companyName(ctx.activeCompanyId) ?? ctx.activeCompanyId ?? '—',
);

const loading = ref(false);
const saving = ref(false);
const errorMsg = ref<string | null>(null);
const rows = ref<EmployeeRow[]>([]);

const filter = ref('');

const columns: QTableColumn[] = [
  { name: 'employee_code', label: 'Código', field: 'employee_code', align: 'left', sortable: true },
  { name: 'first_name', label: 'Nombres', field: 'first_name', align: 'left', sortable: true },
  { name: 'last_name', label: 'Apellidos', field: 'last_name', align: 'left', sortable: true },
  { name: 'phone', label: 'Teléfono', field: 'phone', align: 'left' },
  { name: 'email', label: 'Email', field: 'email', align: 'left' },
  { name: 'assignment', label: 'Asignación', field: 'has_active_assignment', align: 'left' },
  { name: 'is_active', label: 'Activo', field: 'is_active', align: 'left', sortable: true },
  { name: 'access', label: 'Acceso', field: 'access', align: 'left' },
  { name: 'actions', label: 'Acciones', field: 'actions', align: 'right' },
];

const canCreate = computed(
  () => !!ctx.activeCompanyId && acl.hasPermission(ctx.activeCompanyId, 'hr.employee.create'),
);
const canUpdate = computed(
  () => !!ctx.activeCompanyId && acl.hasPermission(ctx.activeCompanyId, 'hr.employee.update'),
);
const canAssign = computed(
  () => !!ctx.activeCompanyId && acl.hasPermission(ctx.activeCompanyId, 'hr.assignment.create'),
);
const canEndAssign = computed(
  () => !!ctx.activeCompanyId && acl.hasPermission(ctx.activeCompanyId, 'hr.assignment.end'),
);
const canProvision = computed(
  () => !!ctx.activeCompanyId && acl.hasPermission(ctx.activeCompanyId, 'iam.users.create'),
);

async function load() {
  loading.value = true;
  errorMsg.value = null;
  try {
    rows.value = await listEmployees();
  } catch (e: unknown) {
    errorMsg.value = extractErrorMessage(e);
  } finally {
    loading.value = false;
  }
}
onMounted(load);

// Create/Edit
const editDialog = ref(false);
const editingId = ref<number | null>(null);

const form = reactive<{
  employee_code: string;
  first_name: string;
  last_name: string;
  phone: string;
  email: string;
  is_active: boolean;
}>({
  employee_code: '',
  first_name: '',
  last_name: '',
  phone: '',
  email: '',
  is_active: true,
});

function openCreate() {
  editingId.value = null;
  Object.assign(form, {
    employee_code: '',
    first_name: '',
    last_name: '',
    phone: '',
    email: '',
    is_active: true,
  });
  editDialog.value = true;
}

function openEdit(e: EmployeeRow) {
  editingId.value = e.id;
  Object.assign(form, {
    employee_code: e.employee_code ?? '',
    first_name: e.first_name ?? '',
    last_name: e.last_name ?? '',
    phone: e.phone ?? '',
    email: e.email ?? '',
    is_active: e.is_active,
  });
  editDialog.value = true;
}

async function saveEmployee() {
  saving.value = true;
  try {
    if (!form.first_name.trim()) return;

    if (!editingId.value) {
      await createEmployee({
        employee_code: form.employee_code ?? '',
        first_name: form.first_name.trim(),
        last_name: form.last_name ?? '',
        phone: form.phone ?? '',
        email: form.email ?? '',
      });
      $q.notify({ type: 'positive', message: 'Empleado creado' });
    } else {
      await patchEmployee(editingId.value, {
        employee_code: form.employee_code ?? '',
        first_name: form.first_name.trim(),
        last_name: form.last_name ?? '',
        phone: form.phone ?? '',
        email: form.email ?? '',
        is_active: form.is_active,
      });
      $q.notify({ type: 'positive', message: 'Empleado actualizado' });
    }

    editDialog.value = false;
    await load();
  } catch (e: unknown) {
    $q.notify({ type: 'negative', message: extractErrorMessage(e) });
  } finally {
    saving.value = false;
  }
}

// Assign
const assignDialog = ref(false);
const assignTarget = ref<EmployeeRow | null>(null);
const assignSaving = ref(false);
const assignError = ref<string | null>(null);

const positionsLoading = ref(false);
const branchesLoading = ref(false);

const positionOptions = ref<{ label: string; value: number }[]>([]);
const branchOptions = ref<{ label: string; value: number }[]>([]);

const assignForm = reactive<{ position_id: number | null; branch_id: number | null }>({
  position_id: null,
  branch_id: null,
});

async function openAssign(e: EmployeeRow) {
  assignTarget.value = e;
  assignForm.position_id = null;
  assignForm.branch_id = null;
  assignError.value = null;
  assignDialog.value = true;

  positionsLoading.value = true;
  branchesLoading.value = true;

  try {
    const positions: PositionRow[] = await listPositions();
    positionOptions.value = positions.map((p) => ({
      label: `${p.name} (${p.code || '-'})`,
      value: p.id,
    }));
  } catch (err: unknown) {
    assignError.value = `No pude cargar puestos: ${extractErrorMessage(err)}`;
  } finally {
    positionsLoading.value = false;
  }

  try {
    const branches = await listBranches();
    branchOptions.value = branches.map((b) => ({ label: `${b.name} (${b.code})`, value: b.id }));
  } catch (err: unknown) {
    // Si no tienes org.branch.read, igual puedes asignar sin branch_id o ingresarlo manual (más adelante si lo quieres)
    // Aquí solo informamos.
    const msg = extractErrorMessage(err);
    assignError.value = assignError.value
      ? `${assignError.value} | Branches: ${msg}`
      : `Branches: ${msg}`;
  } finally {
    branchesLoading.value = false;
  }
}

async function doAssign() {
  if (!assignTarget.value) return;
  if (!assignForm.position_id) {
    assignError.value = 'Selecciona un puesto';
    return;
  }
  assignSaving.value = true;
  assignError.value = null;

  try {
    const id = await createAssignment(assignTarget.value.id, {
      position_id: assignForm.position_id,
      branch_id: assignForm.branch_id,
    });
    $q.notify({ type: 'positive', message: `Asignación creada (id=${id})` });
    assignDialog.value = false;
    await load();
  } catch (e: unknown) {
    assignError.value = extractErrorMessage(e);
  } finally {
    assignSaving.value = false;
  }
}

// End assignment
const endDialog = ref(false);
const endTarget = ref<EmployeeRow | null>(null);
const endAssignmentId = ref<number | null>(null);
const endSaving = ref(false);
const endError = ref<string | null>(null);

function openEnd(e: EmployeeRow) {
  endTarget.value = e;
  endAssignmentId.value = e.active_assignments?.[0]?.id ?? null;
  endError.value = null;
  endDialog.value = true;
}

const endAssignmentOptions = computed(() =>
  (endTarget.value?.active_assignments ?? []).map((a) => ({
    label: `${a.id} · ${a.position_name}${a.branch_name ? ` · ${a.branch_name}` : ''}`,
    value: a.id,
  })),
);

async function doEnd() {
  if (!endTarget.value) return;
  if (!endAssignmentId.value) {
    endError.value = 'Ingresa assignment_id';
    return;
  }
  endSaving.value = true;
  endError.value = null;

  try {
    await endAssignment(endTarget.value.id, endAssignmentId.value);
    $q.notify({ type: 'positive', message: 'Asignación finalizada' });
    endDialog.value = false;
    await load();
  } catch (e: unknown) {
    endError.value = extractErrorMessage(e);
  } finally {
    endSaving.value = false;
  }
}

// Provision user
const provDialog = ref(false);
const provTarget = ref<EmployeeRow | null>(null);
const provSaving = ref(false);
const provError = ref<string | null>(null);

const provResultDialog = ref(false);
const provResult = ref<{ username: string; temp_password: string } | null>(null);

const provForm = reactive<{
  username: string;
  email: string;
  manualPass: boolean;
  temp_password: string;
}>({
  username: '',
  email: '',
  manualPass: false,
  temp_password: '',
});

function openProvision(e: EmployeeRow) {
  provTarget.value = e;
  provError.value = null;
  provResult.value = null;

  provForm.username = '';
  provForm.email = e.email ?? '';
  provForm.manualPass = false;
  provForm.temp_password = '';

  provDialog.value = true;
}

async function doProvision() {
  if (!provTarget.value) return;
  if (!provForm.username.trim()) {
    provError.value = 'Username es requerido';
    return;
  }

  provSaving.value = true;
  provError.value = null;
  try {
    const payload: { username: string; email?: string; temp_password?: string } = {
      username: provForm.username.trim(),
    };
    if (provForm.email.trim()) payload.email = provForm.email.trim();
    if (provForm.manualPass && provForm.temp_password) {
      payload.temp_password = provForm.temp_password;
    }

    const data = await provisionEmployeeUser(provTarget.value.id, payload);

    provDialog.value = false;
    provResult.value = { username: data.username, temp_password: data.temp_password };
    provResultDialog.value = true;
    $q.notify({ type: 'positive', message: 'Acceso provisionado' });
    await load();
  } catch (e: unknown) {
    provError.value = extractErrorMessage(e);
  } finally {
    provSaving.value = false;
  }
}

async function copyProvPass() {
  const pass = provResult.value?.temp_password;
  if (!pass) return;
  try {
    await copyToClipboard(pass);
    $q.notify({ type: 'positive', message: 'Contraseña copiada' });
  } catch {
    $q.notify({ type: 'negative', message: 'No pude copiar al portapapeles' });
  }
}
</script>
