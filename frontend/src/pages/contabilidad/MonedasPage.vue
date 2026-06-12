<template>
  <q-page class="app-page">
    <PageHeader
      title="Tipo de cambio"
      subtitle="Tasas de cambio por fecha y la corrida de revaluación de cuentas en moneda extranjera."
      :loading="loading"
      @refresh="reload"
    >
      <template #actions>
        <q-btn
          v-if="puede('accounting.fx_rate.update')"
          unelevated
          no-caps
          color="primary"
          icon="add"
          label="Registrar tasa"
          @click="abrirTasa"
        />
        <q-btn
          v-if="puede('accounting.revaluation.run')"
          outline
          no-caps
          color="primary"
          icon="currency_exchange"
          label="Correr revaluación"
          @click="correrRevaluacion"
        />
      </template>
    </PageHeader>

    <q-table
      class="app-table"
      :rows="rows"
      :columns="columns"
      row-key="rate_date"
      flat
      :loading="loading"
      :pagination="{ rowsPerPage: 25 }"
      no-data-label="Sin tasas registradas."
    >
      <template #body-cell-fecha="props">
        <q-td :props="props">{{ formatDate(props.row.rate_date) }}</q-td>
      </template>
    </q-table>

    <q-dialog v-model="dlgTasa">
      <q-card class="app-dialog">
        <q-card-section class="text-h6">Registrar tasa de cambio</q-card-section>
        <q-card-section class="app-form">
          <q-input v-model="form.rate_date" outlined dense type="date" label="Fecha *" />
          <div class="row q-gutter-sm">
            <q-input v-model="form.from_currency" outlined dense label="De *" class="col" />
            <q-input v-model="form.to_currency" outlined dense label="A *" class="col" />
          </div>
          <q-input v-model="form.rate" outlined dense type="number" min="0" step="0.0001" label="Tasa *" />
          <q-select
            v-model="form.rate_type"
            :options="[
              { value: 'CLOSING', label: 'Cierre' },
              { value: 'SPOT', label: 'Spot' },
              { value: 'AVERAGE', label: 'Promedio' },
            ]"
            label="Tipo"
            outlined
            dense
            emit-value
            map-options
          />
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat no-caps label="Cancelar" v-close-popup />
          <q-btn
            unelevated
            no-caps
            color="primary"
            label="Guardar"
            :loading="guardando"
            :disable="!form.rate_date || !form.rate || !form.from_currency || !form.to_currency"
            @click="guardarTasa"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>
  </q-page>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue';
import { useQuasar, type QTableColumn } from 'quasar';
import PageHeader from 'src/components/PageHeader.vue';
import { apiErrorMessage } from 'src/core/api';
import { useListado } from 'src/core/composables/useListado';
import { formatDate } from 'src/core/format';
import {
  listFxRates,
  runRevaluation,
  upsertFxRate,
  type FxRateRow,
} from 'src/features/accounting/accounting.api';
import { useAclStore } from 'src/stores/acl.store';
import { useContextStore } from 'src/stores/context.store';

const $q = useQuasar();
const acl = useAclStore();
const ctx = useContextStore();

const { rows, loading, reload } = useListado<FxRateRow>(() => listFxRates(), {
  errorMessage: 'No se pudieron cargar las tasas.',
});

function puede(code: string): boolean {
  const companyId = ctx.activeCompanyId;
  return companyId ? acl.hasPermission(companyId, code) : false;
}

const columns: QTableColumn<FxRateRow>[] = [
  { name: 'fecha', label: 'Fecha', field: 'rate_date', align: 'left', sortable: true },
  { name: 'from_currency', label: 'De', field: 'from_currency', align: 'left' },
  { name: 'to_currency', label: 'A', field: 'to_currency', align: 'left' },
  { name: 'rate', label: 'Tasa', field: 'rate', align: 'right' },
  { name: 'rate_type', label: 'Tipo', field: 'rate_type', align: 'left' },
];

const dlgTasa = ref(false);
const guardando = ref(false);
const form = reactive<FxRateRow>({
  rate_date: new Date().toISOString().slice(0, 10),
  from_currency: 'USD',
  to_currency: 'NIO',
  rate_type: 'CLOSING',
  rate: '',
});

function abrirTasa() {
  Object.assign(form, {
    rate_date: new Date().toISOString().slice(0, 10),
    from_currency: 'USD',
    to_currency: 'NIO',
    rate_type: 'CLOSING',
    rate: '',
  });
  dlgTasa.value = true;
}

async function guardarTasa() {
  guardando.value = true;
  try {
    await upsertFxRate({
      ...form,
      from_currency: form.from_currency.toUpperCase(),
      to_currency: form.to_currency.toUpperCase(),
    });
    dlgTasa.value = false;
    $q.notify({ type: 'positive', message: 'Tasa registrada.' });
    await reload();
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo guardar la tasa.') });
  } finally {
    guardando.value = false;
  }
}

function correrRevaluacion() {
  const hoy = new Date();
  $q.dialog({
    title: 'Correr revaluación',
    message: 'Período a revaluar (AAAA-MM):',
    prompt: {
      model: `${hoy.getFullYear()}-${String(hoy.getMonth() + 1).padStart(2, '0')}`,
      type: 'text',
      isValid: (v: string) => /^\d{4}-\d{2}$/.test(v),
    },
    cancel: { flat: true, noCaps: true, label: 'Cancelar' },
    ok: { unelevated: true, noCaps: true, color: 'primary', label: 'Correr' },
  }).onOk((valor: string) => {
    const [y, m] = valor.split('-').map(Number);
    void (async () => {
      try {
        await runRevaluation({ year: y!, month: m! });
        $q.notify({ type: 'positive', message: 'Revaluación corrida (borradores en el diario).' });
      } catch (e) {
        $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo correr la revaluación.') });
      }
    })();
  });
}
</script>
