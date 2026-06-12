<template>
  <q-page class="app-page">
    <PageHeader
      title="Plan de cuentas"
      subtitle="Catálogo contable de la empresa. Las cuentas posteables reciben asientos; las demás agrupan."
      :loading="loading"
      @refresh="cargar"
    >
      <template #actions>
        <q-btn
          v-if="puedeEditar"
          unelevated
          no-caps
          color="primary"
          icon="add"
          label="Nueva cuenta"
          @click="abrirCuenta"
        />
      </template>
    </PageHeader>

    <div v-if="config" class="coa-config">
      Moneda funcional: <strong>{{ config.functional_currency }}</strong>
      <span v-if="config.fx_gain_account_code">
        · Ganancia cambiaria: {{ config.fx_gain_account_code }} · Pérdida: {{ config.fx_loss_account_code }}
      </span>
    </div>

    <q-table
      class="app-table"
      :rows="cuentas"
      :columns="columns"
      row-key="id"
      flat
      :loading="loading"
      :pagination="{ rowsPerPage: 50 }"
      no-data-label="Sin cuentas. Creá la primera."
    >
      <template #body-cell-tipo="props">
        <q-td :props="props">{{ ACCOUNT_TYPE_LABELS[props.row.account_type] ?? props.row.account_type }}</q-td>
      </template>
      <template #body-cell-flags="props">
        <q-td :props="props">
          <q-chip v-if="props.row.is_postable" dense outline color="primary" label="Posteable" />
          <q-chip v-if="props.row.is_revaluable" dense outline color="warning" label="Revaluable" />
          <q-chip v-if="!props.row.is_active" dense outline color="grey-7" label="Inactiva" />
        </q-td>
      </template>
    </q-table>

    <q-dialog v-model="dlgCuenta">
      <q-card class="app-dialog">
        <q-card-section class="text-h6">Nueva cuenta</q-card-section>
        <q-card-section class="app-form">
          <q-input v-model="form.code" outlined dense label="Código * (ej. 1101)" autofocus />
          <q-input v-model="form.name" outlined dense label="Nombre *" />
          <q-select
            v-model="form.account_type"
            :options="opcionesTipo"
            label="Tipo *"
            outlined
            dense
            emit-value
            map-options
          />
          <q-input v-model="form.parent_code" outlined dense label="Cuenta padre (código)" />
          <q-toggle v-model="form.is_postable" label="Posteable (recibe asientos)" color="primary" />
          <q-toggle v-model="form.is_revaluable" label="Revaluable (moneda extranjera)" color="warning" />
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat no-caps label="Cancelar" v-close-popup />
          <q-btn
            unelevated
            no-caps
            color="primary"
            label="Guardar cuenta"
            :loading="guardando"
            :disable="!form.code.trim() || !form.name.trim()"
            @click="guardar"
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
  ACCOUNT_TYPE_LABELS,
  getChartOfAccounts,
  upsertChartOfAccounts,
  type CoAResponse,
  type CoARow,
} from 'src/features/accounting/accounting.api';
import { useAclStore } from 'src/stores/acl.store';
import { useContextStore } from 'src/stores/context.store';

const $q = useQuasar();
const acl = useAclStore();
const ctx = useContextStore();

const loading = ref(false);
const guardando = ref(false);
const cuentas = ref<CoARow[]>([]);
const config = ref<CoAResponse['config'] | null>(null);

const puedeEditar = computed(() => {
  const companyId = ctx.activeCompanyId;
  return companyId ? acl.hasPermission(companyId, 'accounting.coa.update') : false;
});

const opcionesTipo = Object.entries(ACCOUNT_TYPE_LABELS).map(([value, label]) => ({ value, label }));

const columns: QTableColumn<CoARow>[] = [
  { name: 'code', label: 'Código', field: 'code', align: 'left', sortable: true },
  { name: 'name', label: 'Cuenta', field: 'name', align: 'left' },
  { name: 'tipo', label: 'Tipo', field: 'account_type', align: 'left' },
  { name: 'parent_code', label: 'Padre', field: 'parent_code', align: 'left' },
  { name: 'flags', label: 'Atributos', field: 'id', align: 'left' },
];

async function cargar() {
  loading.value = true;
  try {
    const r = await getChartOfAccounts();
    cuentas.value = r.results;
    config.value = r.config;
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo cargar el plan de cuentas.') });
  } finally {
    loading.value = false;
  }
}

const dlgCuenta = ref(false);
const form = reactive({
  code: '',
  name: '',
  account_type: 'ASSET',
  parent_code: '',
  is_postable: true,
  is_revaluable: false,
});

function abrirCuenta() {
  Object.assign(form, {
    code: '',
    name: '',
    account_type: 'ASSET',
    parent_code: '',
    is_postable: true,
    is_revaluable: false,
  });
  dlgCuenta.value = true;
}

async function guardar() {
  guardando.value = true;
  try {
    await upsertChartOfAccounts([
      {
        code: form.code.trim(),
        name: form.name.trim(),
        account_type: form.account_type,
        ...(form.parent_code ? { parent_code: form.parent_code.trim() } : {}),
        is_postable: form.is_postable,
        is_revaluable: form.is_revaluable,
      },
    ]);
    dlgCuenta.value = false;
    $q.notify({ type: 'positive', message: 'Cuenta guardada.' });
    await cargar();
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo guardar la cuenta.') });
  } finally {
    guardando.value = false;
  }
}

onMounted(cargar);
</script>

<style scoped>
.coa-config {
  margin-bottom: var(--app-space-3);
  font-size: 0.85rem;
  color: var(--app-text-muted);
}
</style>
