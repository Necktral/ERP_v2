<template>
  <q-page class="app-page">
    <PageHeader
      title="Créditos"
      subtitle="Créditos otorgados (agrícolas, de equipo, líneas). El desembolso activa el crédito y arranca el devengo de intereses."
      :loading="loading"
      @refresh="reload"
    >
      <template #actions>
        <q-btn flat round dense icon="arrow_back" aria-label="Volver" to="/cartera" />
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
      no-data-label="No hay créditos registrados."
    >
      <template #body-cell-parte="props">
        <q-td :props="props">{{ nombreParte(props.row.party) }}</q-td>
      </template>
      <template #body-cell-monto="props">
        <q-td :props="props">{{ formatMoney(props.row.principal_amount) }}</q-td>
      </template>
      <template #body-cell-saldo="props">
        <q-td :props="props" class="text-weight-bold">{{ formatMoney(props.row.outstanding_amount) }}</q-td>
      </template>
      <template #body-cell-estado="props">
        <q-td :props="props">
          {{ CREDIT_STATUS_LABELS[props.row.credit_status] ?? props.row.credit_status }}
        </q-td>
      </template>
      <template #body-cell-acciones="props">
        <q-td :props="props" class="text-right">
          <q-btn
            v-if="puedeDesembolsar && (props.row.credit_status === 'PENDING' || props.row.credit_status === 'APPROVED')"
            flat
            dense
            no-caps
            size="sm"
            color="primary"
            icon="payments"
            label="Desembolsar"
            @click="abrirDesembolso(props.row)"
          />
        </q-td>
      </template>
    </q-table>

    <!-- Diálogo: desembolsar -->
    <q-dialog v-model="dlgDesembolso">
      <q-card class="app-dialog">
        <q-card-section class="text-h6">Desembolsar crédito</q-card-section>
        <q-card-section class="app-form">
          <div class="text-caption text-muted">
            {{ objetivo ? `${nombreParte(objetivo.party)} · principal ${formatMoney(objetivo.principal_amount)}` : '' }}
          </div>
          <q-input v-model="formDes.monto" outlined dense type="number" min="0" label="Monto a desembolsar C$ *" />
          <q-input v-model="formDes.fecha" outlined dense type="date" label="Fecha de desembolso *" />
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat no-caps label="Cancelar" v-close-popup />
          <q-btn
            unelevated
            no-caps
            color="primary"
            label="Desembolsar"
            :loading="accionando"
            :disable="!formDes.monto || Number(formDes.monto) <= 0 || !formDes.fecha"
            @click="desembolsar"
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
import { useListado } from 'src/core/composables/useListado';
import { formatDate, formatMoney } from 'src/core/format';
import { listParties } from 'src/features/parties/parties.api';
import {
  CREDIT_STATUS_LABELS,
  disburseCredit,
  listCredits,
  type Credit,
} from 'src/features/portfolio/portfolio.api';
import { useAclStore } from 'src/stores/acl.store';
import { useContextStore } from 'src/stores/context.store';

const $q = useQuasar();
const acl = useAclStore();
const ctx = useContextStore();

const { rows, loading, reload } = useListado<Credit>(() => listCredits(), {
  errorMessage: 'No se pudieron cargar los créditos.',
});

const nombresParte = ref(new Map<number, string>());

const puedeDesembolsar = computed(() => {
  const companyId = ctx.activeCompanyId;
  return companyId ? acl.hasPermission(companyId, 'portfolio.credit.disburse') : false;
});

function nombreParte(partyId: number): string {
  return nombresParte.value.get(partyId) ?? `Tercero #${partyId}`;
}

const columns: QTableColumn<Credit>[] = [
  { name: 'contrato', label: 'Contrato', field: 'contract_number', align: 'left' },
  { name: 'parte', label: 'Deudor', field: 'party', align: 'left' },
  { name: 'tipo', label: 'Tipo', field: 'credit_type', align: 'left' },
  { name: 'monto', label: 'Principal', field: 'principal_amount', align: 'right' },
  { name: 'saldo', label: 'Saldo', field: 'outstanding_amount', align: 'right' },
  { name: 'tasa', label: 'Tasa %', field: 'interest_rate', align: 'right' },
  { name: 'vence', label: 'Vence', field: (r) => formatDate(r.maturity_date), align: 'left' },
  { name: 'estado', label: 'Estado', field: 'credit_status', align: 'left' },
  { name: 'acciones', label: '', field: 'id', align: 'right' },
];

// --- Desembolso ---
const dlgDesembolso = ref(false);
const accionando = ref(false);
const objetivo = ref<Credit | null>(null);
const formDes = reactive({ monto: '', fecha: new Date().toISOString().slice(0, 10) });

function abrirDesembolso(c: Credit) {
  objetivo.value = c;
  Object.assign(formDes, {
    monto: c.principal_amount,
    fecha: new Date().toISOString().slice(0, 10),
  });
  dlgDesembolso.value = true;
}

async function desembolsar() {
  if (!objetivo.value) return;
  accionando.value = true;
  try {
    await disburseCredit(objetivo.value.id, {
      disbursed_amount: Number(formDes.monto).toFixed(2),
      disbursement_date: formDes.fecha,
    });
    dlgDesembolso.value = false;
    $q.notify({ type: 'positive', message: 'Crédito desembolsado (ACTIVO).' });
    await reload();
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo desembolsar.') });
  } finally {
    accionando.value = false;
  }
}

onMounted(async () => {
  try {
    const ps = await listParties();
    nombresParte.value = new Map(ps.map((p) => [p.id, p.display_name]));
  } catch {
    /* nombres opcionales */
  }
});
</script>
