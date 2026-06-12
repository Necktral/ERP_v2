<template>
  <q-page class="app-page">
    <PageHeader
      title="Períodos fiscales"
      subtitle="Cerrar un período bloquea nuevos asientos en ese mes; reabrir exige motivo y queda auditado."
      :loading="loading"
      @refresh="reload"
    >
      <template #actions>
        <q-btn
          v-if="puedeCerrar"
          unelevated
          no-caps
          color="primary"
          icon="event_busy"
          label="Cerrar período"
          @click="abrirCerrar"
        />
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
      no-data-label="Aún no hay períodos (se crean al postear asientos o cerrarlos)."
    >
      <template #body-cell-periodo="props">
        <q-td :props="props">{{ String(props.row.month).padStart(2, '0') }}/{{ props.row.year }}</q-td>
      </template>
      <template #body-cell-estado="props">
        <q-td :props="props">
          <q-chip v-if="props.row.status === 'OPEN'" dense color="secondary" text-color="white" label="Abierto" />
          <q-chip v-else dense outline color="grey-7" label="Cerrado" />
        </q-td>
      </template>
      <template #body-cell-acciones="props">
        <q-td :props="props" class="text-right">
          <q-btn
            v-if="puedeCerrar && props.row.status === 'OPEN'"
            flat
            dense
            no-caps
            size="sm"
            color="negative"
            label="Cerrar"
            @click="cerrar(props.row)"
          />
          <q-btn
            v-if="puedeReabrir && props.row.status === 'CLOSED'"
            flat
            dense
            no-caps
            size="sm"
            color="warning"
            label="Reabrir"
            @click="reabrir(props.row)"
          />
        </q-td>
      </template>
    </q-table>
  </q-page>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useQuasar, type QTableColumn } from 'quasar';
import PageHeader from 'src/components/PageHeader.vue';
import { apiErrorMessage } from 'src/core/api';
import { useListado } from 'src/core/composables/useListado';
import {
  closePeriod,
  listPeriods,
  reopenPeriod,
  type FiscalPeriodRow,
} from 'src/features/accounting/accounting.api';
import { useAclStore } from 'src/stores/acl.store';
import { useContextStore } from 'src/stores/context.store';

const $q = useQuasar();
const acl = useAclStore();
const ctx = useContextStore();

const { rows, loading, reload } = useListado<FiscalPeriodRow>(() => listPeriods(), {
  errorMessage: 'No se pudieron cargar los períodos.',
});

function tienePermiso(code: string): boolean {
  const companyId = ctx.activeCompanyId;
  return companyId ? acl.hasPermission(companyId, code) : false;
}

const puedeCerrar = computed(() => tienePermiso('accounting.period.close'));
const puedeReabrir = computed(() => tienePermiso('accounting.period.reopen'));

const columns: QTableColumn<FiscalPeriodRow>[] = [
  { name: 'periodo', label: 'Período', field: 'year', align: 'left' },
  { name: 'estado', label: 'Estado', field: 'status', align: 'left' },
  { name: 'acciones', label: '', field: 'id', align: 'right' },
];

function abrirCerrar() {
  const hoy = new Date();
  $q.dialog({
    title: 'Cerrar período',
    message: 'Mes a cerrar (AAAA-MM):',
    prompt: {
      model: `${hoy.getFullYear()}-${String(hoy.getMonth() + 1).padStart(2, '0')}`,
      type: 'text',
      isValid: (v: string) => /^\d{4}-\d{2}$/.test(v),
    },
    cancel: { flat: true, noCaps: true, label: 'Cancelar' },
    ok: { unelevated: true, noCaps: true, color: 'negative', label: 'Cerrar período' },
  }).onOk((valor: string) => {
    const [y, m] = valor.split('-').map(Number);
    void ejecutarCierre(y!, m!);
  });
}

function cerrar(p: FiscalPeriodRow) {
  $q.dialog({
    title: 'Cerrar período',
    message: `¿Cerrar ${String(p.month).padStart(2, '0')}/${p.year}? No se podrán postear más asientos en ese mes.`,
    cancel: { flat: true, noCaps: true, label: 'Cancelar' },
    ok: { unelevated: true, noCaps: true, color: 'negative', label: 'Cerrar' },
  }).onOk(() => {
    void ejecutarCierre(p.year, p.month);
  });
}

async function ejecutarCierre(year: number, month: number) {
  try {
    await closePeriod(year, month);
    $q.notify({ type: 'positive', message: `Período ${String(month).padStart(2, '0')}/${year} cerrado.` });
    await reload();
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo cerrar el período.') });
  }
}

function reabrir(p: FiscalPeriodRow) {
  $q.dialog({
    title: 'Reabrir período',
    message: 'Motivo de la reapertura (queda en auditoría):',
    prompt: { model: '', type: 'text', isValid: (v: string) => v.trim().length >= 5 },
    cancel: { flat: true, noCaps: true, label: 'Cancelar' },
    ok: { unelevated: true, noCaps: true, color: 'warning', label: 'Reabrir' },
    persistent: true,
  }).onOk((motivo: string) => {
    void (async () => {
      try {
        await reopenPeriod(p.year, p.month, motivo.trim());
        $q.notify({ type: 'positive', message: 'Período reabierto.' });
        await reload();
      } catch (e) {
        $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo reabrir.') });
      }
    })();
  });
}
</script>
