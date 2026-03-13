<template>
  <AppDataTable
    title="Listado"
    caption="Flujo operativo: crear y editar empleados, asignar puestos y gestionar accesos."
    :rows="rows"
    :columns="columns"
    row-key="id"
    :loading="loading"
    :rows-per-page-options="[10, 20, 50, 0]"
    :filter="filterModel"
    :pagination="pagination"
    @request="onTableRequest"
  >
    <template #toolbar>
      <q-input
        v-model="filterModel"
        dense
        outlined
        placeholder="Buscar empleado..."
        style="width: 280px"
      />
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
        <q-badge v-else outline color="grey-7">SIN ASIGNACION</q-badge>
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
        <q-btn v-if="canUpdate" dense flat icon="edit" @click="emit('edit', props.row)" />
        <q-btn v-if="canAssign" dense flat icon="work" @click="emit('assign', props.row)" />
        <q-btn
          v-if="canEndAssign"
          dense
          flat
          icon="event_busy"
          :disable="!props.row.active_assignments?.length"
          @click="emit('end', props.row)"
        />
        <q-btn
          v-if="canProvisionUser"
          dense
          flat
          icon="vpn_key"
          :disable="!!props.row.linked_user_id || !props.row.active_assignments?.length"
          @click="emit('provision', props.row)"
        />

        <q-btn
          v-if="canProvisionUser"
          dense
          flat
          icon="person_off"
          :disable="!props.row.linked_user_id"
          @click="emit('revoke', props.row)"
        />

        <q-btn
          v-if="canProvisionUser"
          dense
          flat
          icon="lock_reset"
          :disable="!props.row.linked_user_id || !props.row.active_assignments?.length"
          @click="emit('reset', props.row)"
        />
      </q-td>
    </template>
  </AppDataTable>

  <q-banner v-if="errorMsg" class="q-mt-md" dense rounded>
    {{ errorMsg }}
  </q-banner>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import type { QTableColumn } from 'quasar';

import type { EmployeeRow } from 'src/services/hr.service';
import AppDataTable from 'src/ui/AppDataTable.vue';

type TablePagination = {
  page: number;
  rowsPerPage: number;
  rowsNumber: number;
};

type TableRequestPayload = {
  pagination: {
    page: number;
    rowsPerPage: number;
  };
};

const props = defineProps<{
  rows: EmployeeRow[];
  columns: QTableColumn[];
  loading: boolean;
  pagination: TablePagination;
  filter: string;
  errorMsg: string | null;
  canUpdate: boolean;
  canAssign: boolean;
  canEndAssign: boolean;
  canProvisionUser: boolean;
}>();

const emit = defineEmits<{
  (event: 'request', payload: TableRequestPayload): void;
  (event: 'update:filter', value: string): void;
  (event: 'edit', row: EmployeeRow): void;
  (event: 'assign', row: EmployeeRow): void;
  (event: 'end', row: EmployeeRow): void;
  (event: 'provision', row: EmployeeRow): void;
  (event: 'revoke', row: EmployeeRow): void;
  (event: 'reset', row: EmployeeRow): void;
}>();

const filterModel = computed({
  get: () => props.filter,
  set: (value: string) => emit('update:filter', value),
});

function onTableRequest(payload: TableRequestPayload): void {
  emit('request', payload);
}
</script>
