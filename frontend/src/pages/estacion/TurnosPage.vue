<template>
  <q-page class="app-page">
    <PageHeader
      title="Turnos de la estación"
      subtitle="Historial de turnos con su reporte de cierre: totales por producto, tipo de venta y método de pago."
      :loading="loading"
      @refresh="reload"
    >
      <template #actions>
        <q-btn flat round dense icon="arrow_back" aria-label="Volver" to="/estacion" />
      </template>
    </PageHeader>

    <q-table
      class="app-table"
      :rows="rows"
      :columns="columns"
      row-key="id"
      flat
      :loading="loading"
      :pagination="{ rowsPerPage: 25 }"
      no-data-label="Aún no hay turnos."
    >
      <template #body-cell-estado="props">
        <q-td :props="props">
          <q-chip v-if="props.row.status === 'OPEN'" dense color="secondary" text-color="white" label="Abierto" />
          <q-chip v-else dense outline color="grey-7" label="Cerrado" />
        </q-td>
      </template>
      <template #body-cell-abierto="props">
        <q-td :props="props">{{ formatDateTime(props.row.opened_at) }}</q-td>
      </template>
      <template #body-cell-cerrado="props">
        <q-td :props="props">{{ formatDateTime(props.row.closed_at) }}</q-td>
      </template>
      <template #body-cell-acciones="props">
        <q-td :props="props" class="text-right">
          <q-btn
            v-if="puedeVerReportes && props.row.status === 'CLOSED'"
            flat
            dense
            no-caps
            size="sm"
            icon="summarize"
            label="Reporte"
            @click="verReporte(props.row)"
          />
        </q-td>
      </template>
    </q-table>

    <!-- Diálogo: reporte de cierre -->
    <q-dialog v-model="dlgReporte">
      <q-card class="app-dialog tur-reporte">
        <q-card-section class="text-h6">Reporte de cierre — turno #{{ turnoReporte?.id }}</q-card-section>
        <q-card-section>
          <pre class="tur-json">{{ reporteTexto }}</pre>
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat no-caps label="Cerrar" v-close-popup />
        </q-card-actions>
      </q-card>
    </q-dialog>
  </q-page>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import { useQuasar, type QTableColumn } from 'quasar';
import PageHeader from 'src/components/PageHeader.vue';
import { apiErrorMessage } from 'src/core/api';
import { useListado } from 'src/core/composables/useListado';
import { formatDateTime } from 'src/core/format';
import { getShiftCloseReport, listShifts, type FuelShift } from 'src/features/fuel/fuel.api';
import { useAclStore } from 'src/stores/acl.store';
import { useContextStore } from 'src/stores/context.store';

const $q = useQuasar();
const acl = useAclStore();
const ctx = useContextStore();

const { rows, loading, reload } = useListado<FuelShift>(() => listShifts(), {
  errorMessage: 'No se pudieron cargar los turnos.',
});

const puedeVerReportes = computed(() => {
  const companyId = ctx.activeCompanyId;
  return companyId ? acl.hasPermission(companyId, 'fuel.reports.view') : false;
});

const columns: QTableColumn<FuelShift>[] = [
  { name: 'id', label: '#', field: 'id', align: 'left' },
  { name: 'estado', label: 'Estado', field: 'status', align: 'left' },
  { name: 'abierto', label: 'Abierto', field: 'opened_at', align: 'left' },
  { name: 'cerrado', label: 'Cerrado', field: 'closed_at', align: 'left' },
  { name: 'acciones', label: '', field: 'id', align: 'right' },
];

const dlgReporte = ref(false);
const turnoReporte = ref<FuelShift | null>(null);
const reporteTexto = ref('');

async function verReporte(t: FuelShift) {
  turnoReporte.value = t;
  reporteTexto.value = 'Cargando…';
  dlgReporte.value = true;
  try {
    const r = await getShiftCloseReport(t.id);
    reporteTexto.value = JSON.stringify(r, null, 2);
  } catch (e) {
    reporteTexto.value = apiErrorMessage(e, 'No se pudo cargar el reporte.');
    $q.notify({ type: 'negative', message: reporteTexto.value });
  }
}
</script>

<style scoped>
.tur-reporte {
  width: 640px;
}

.tur-json {
  margin: 0;
  max-height: 60vh;
  overflow: auto;
  font-size: 0.78rem;
  color: var(--app-text);
  background: var(--app-surface);
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-sm);
  padding: var(--app-space-3);
  white-space: pre-wrap;
}
</style>
