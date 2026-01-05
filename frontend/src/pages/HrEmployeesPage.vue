<template>
  <q-page class="q-pa-md">
    <div class="row items-center justify-between">
      <div>
        <div class="text-h6">HR · Empleados</div>
        <div class="text-caption text-grey-7">
          GET /hr/employees/ devuelve lista con linked_user_id (para automatizar roles por puesto)
        </div>
      </div>

      <div class="row items-center q-gutter-sm">
        <q-btn flat label="Recargar" :disable="loading" @click="load" />
        <q-btn v-if="canCreate" color="primary" label="Nuevo empleado" @click="openCreate" />
      </div>
    </div>

    <q-card class="q-mt-md">
      <q-card-section>
        <q-table
          :rows="rows"
          :columns="columns"
          row-key="id"
          :loading="loading"
          :rows-per-page-options="[10, 20, 50, 0]"
        >
          <template #body-cell-actions="props">
            <q-td :props="props">
              <q-btn v-if="canUpdate" dense flat icon="edit" @click="openEdit(props.row)" />
              <q-btn
                v-if="canAssign"
                dense
                flat
                icon="assignment_ind"
                @click="openAssign(props.row)"
              >
                <q-tooltip>Crear asignación</q-tooltip>
              </q-btn>
              <q-btn
                v-if="canEndAssign"
                dense
                flat
                icon="assignment_turned_in"
                @click="openEnd(props.row)"
              >
                <q-tooltip>Finalizar asignación (por ID)</q-tooltip>
              </q-btn>
            </q-td>
          </template>
        </q-table>

        <q-banner v-if="errorMsg" class="q-mt-md" dense rounded>
          {{ errorMsg }}
        </q-banner>
      </q-card-section>
    </q-card>

    <!-- Create/Edit dialog -->
    <q-dialog v-model="editDialog">
      <q-card style="width: 640px; max-width: 96vw">
        <q-card-section class="row items-center justify-between">
          <div class="text-h6">{{ editingId ? 'Editar empleado' : 'Nuevo empleado' }}</div>
          <q-btn flat icon="close" v-close-popup />
        </q-card-section>

        <q-separator />

        <q-card-section>
          <q-form @submit.prevent="saveEmployee">
            <div class="row q-col-gutter-md">
              <div class="col-12 col-md-4">
                <q-input v-model="form.employee_code" label="Código (opcional)" outlined />
              </div>
              <div class="col-12 col-md-4">
                <q-input
                  v-model="form.first_name"
                  label="Nombres"
                  outlined
                  :rules="[(v) => !!v || 'Requerido']"
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

            <div class="row q-col-gutter-md q-mt-sm items-center">
              <div class="col-12 col-md-6">
                <q-input
                  v-model.number="form.linked_user_id"
                  label="linked_user_id (opcional, user real)"
                  type="number"
                  outlined
                  hint="Si lo llenas, el backend reconcilia roles POSITION en asignaciones."
                />
              </div>
              <div class="col-12 col-md-6">
                <q-toggle v-model="form.is_active" label="Activo" />
              </div>
            </div>

            <div class="q-mt-md">
              <q-btn color="primary" type="submit" :loading="saving" label="Guardar" />
              <q-btn
                v-if="editingId"
                flat
                color="negative"
                class="q-ml-sm"
                label="Desvincular user"
                :disable="saving"
                @click="unlinkUser"
              />
            </div>
          </q-form>
        </q-card-section>
      </q-card>
    </q-dialog>

    <!-- Assign dialog -->
    <q-dialog v-model="assignDialog">
      <q-card style="width: 640px; max-width: 96vw">
        <q-card-section class="row items-center justify-between">
          <div class="text-h6">Crear asignación</div>
          <q-btn flat icon="close" v-close-popup />
        </q-card-section>

        <q-separator />

        <q-card-section>
          <div class="text-caption text-grey-7 q-mb-sm">
            Empleado: <b>{{ assignTarget?.first_name }} {{ assignTarget?.last_name }}</b>
          </div>

          <q-banner class="q-mb-md" dense rounded>
            Si el Puesto tiene maps con scope <b>BRANCH</b>, necesitas <b>branch_id</b> para que se
            otorguen roles en esa sucursal (la reconciliación usa branch del assignment).
          </q-banner>

          <q-select
            v-model="assignForm.position_id"
            :options="positionOptions"
            label="Puesto"
            outlined
            emit-value
            map-options
            :disable="positionsLoading"
          />
          <div class="q-mt-sm" />
          <q-select
            v-model="assignForm.branch_id"
            :options="branchOptions"
            label="Sucursal (opcional)"
            outlined
            emit-value
            map-options
            clearable
            :disable="branchesLoading"
          />

          <div class="q-mt-md">
            <q-btn color="primary" label="Crear" :loading="assignSaving" @click="doAssign" />
          </div>

          <q-banner v-if="assignError" class="q-mt-md" dense rounded>
            {{ assignError }}
          </q-banner>
        </q-card-section>
      </q-card>
    </q-dialog>

    <!-- End assignment dialog -->
    <q-dialog v-model="endDialog">
      <q-card style="width: 520px; max-width: 92vw">
        <q-card-section class="row items-center justify-between">
          <div class="text-h6">Finalizar asignación</div>
          <q-btn flat icon="close" v-close-popup />
        </q-card-section>

        <q-separator />

        <q-card-section>
          <div class="text-caption text-grey-7 q-mb-sm">
            Empleado: <b>{{ endTarget?.first_name }} {{ endTarget?.last_name }}</b>
          </div>

          <q-input v-model.number="endAssignmentId" type="number" label="assignment_id" outlined />
          <div class="q-mt-md">
            <q-btn color="primary" label="Finalizar" :loading="endSaving" @click="doEnd" />
          </div>

          <q-banner v-if="endError" class="q-mt-md" dense rounded>
            {{ endError }}
          </q-banner>
        </q-card-section>
      </q-card>
    </q-dialog>
  </q-page>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import { useQuasar } from 'quasar';
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
  type EmployeeRow,
  type PositionRow,
} from 'src/services/hr.service';
import type { QTableColumn } from 'quasar';

const $q = useQuasar();
const acl = useAclStore();
const ctx = useContextStore();

const loading = ref(false);
const saving = ref(false);
const errorMsg = ref<string | null>(null);
const rows = ref<EmployeeRow[]>([]);

const columns: QTableColumn[] = [
  { name: 'employee_code', label: 'Código', field: 'employee_code', align: 'left', sortable: true },
  { name: 'first_name', label: 'Nombres', field: 'first_name', align: 'left', sortable: true },
  { name: 'last_name', label: 'Apellidos', field: 'last_name', align: 'left', sortable: true },
  { name: 'phone', label: 'Teléfono', field: 'phone', align: 'left' },
  { name: 'email', label: 'Email', field: 'email', align: 'left' },
  { name: 'is_active', label: 'Activo', field: 'is_active', align: 'left', sortable: true },
  { name: 'linked_user_id', label: 'linked_user_id', field: 'linked_user_id', align: 'left' },
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
  linked_user_id: number | null;
}>({
  employee_code: '',
  first_name: '',
  last_name: '',
  phone: '',
  email: '',
  is_active: true,
  linked_user_id: null,
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
    linked_user_id: null,
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
    linked_user_id: e.linked_user_id,
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
        ...(form.linked_user_id ? { linked_user_id: form.linked_user_id } : {}),
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
        linked_user_id: form.linked_user_id,
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

async function unlinkUser() {
  if (!editingId.value) return;
  saving.value = true;
  try {
    await patchEmployee(editingId.value, { linked_user_id: null });
    $q.notify({ type: 'positive', message: 'User desvinculado' });
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
  endAssignmentId.value = null;
  endError.value = null;
  endDialog.value = true;
}

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
  } catch (e: unknown) {
    endError.value = extractErrorMessage(e);
  } finally {
    endSaving.value = false;
  }
}
</script>
