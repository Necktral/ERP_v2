<template>
  <q-page class="app-page">
    <PageHeader
      title="Facturación"
      subtitle="Facturas, notas de crédito y cotizaciones de la sucursal activa. Emitir asigna el número fiscal y puede bajar inventario."
      :loading="loading"
      @refresh="reload"
    >
      <template #actions>
        <q-btn
          v-if="puede('billing.fiscal.config.read')"
          flat
          no-caps
          icon="settings"
          label="Config fiscal"
          to="/facturacion/config-fiscal"
        />
        <q-btn
          v-if="puede('billing.doc.create')"
          unelevated
          no-caps
          color="primary"
          icon="post_add"
          label="Nuevo documento"
          @click="abrirCrear"
        />
      </template>
    </PageHeader>

    <div class="fac-filtros">
      <q-input
        v-model="filtroQ"
        dense
        outlined
        clearable
        placeholder="Buscar por cliente o número…"
        class="fac-filtros__buscar"
        :debounce="350"
        @update:model-value="reload"
      >
        <template #prepend><q-icon name="search" /></template>
      </q-input>
      <q-select
        v-model="filtroEstado"
        :options="opcionesEstado"
        dense
        outlined
        emit-value
        map-options
        clearable
        label="Estado"
        class="fac-filtros__sel"
        @update:model-value="reload"
      />
      <q-select
        v-model="filtroTipo"
        :options="opcionesTipo"
        dense
        outlined
        emit-value
        map-options
        clearable
        label="Tipo"
        class="fac-filtros__sel"
        @update:model-value="reload"
      />
    </div>

    <q-table
      class="app-table"
      :rows="rows"
      :columns="columns"
      row-key="id"
      flat
      :loading="loading"
      :pagination="{ rowsPerPage: 25 }"
      no-data-label="No hay documentos con esos filtros."
      @row-click="(_, row) => abrirDetalle(row as BillingDocRow)"
    >
      <template #body-cell-numero="props">
        <q-td :props="props">
          {{ props.row.number > 0 ? `${props.row.series}-${props.row.number}` : '—' }}
        </q-td>
      </template>
      <template #body-cell-tipo="props">
        <q-td :props="props">{{ BILLING_DOC_TYPE_LABELS[props.row.doc_type as BillingDocType] }}</q-td>
      </template>
      <template #body-cell-cliente="props">
        <q-td :props="props">
          {{ props.row.customer_party_display_name || props.row.customer_name || '—' }}
        </q-td>
      </template>
      <template #body-cell-total="props">
        <q-td :props="props">{{ formatMoney(props.row.total) }}</q-td>
      </template>
      <template #body-cell-fecha="props">
        <q-td :props="props">{{ formatDate(props.row.created_at) }}</q-td>
      </template>
      <template #body-cell-estado="props">
        <q-td :props="props">
          <EstadoChip :estado="props.row.status" />
          <EstadoChip
            v-if="props.row.is_fiscal && props.row.fiscal_status"
            :estado="props.row.fiscal_status"
            :map="MAPA_FISCAL"
          />
        </q-td>
      </template>
    </q-table>

    <!-- Diálogo: nuevo documento con líneas -->
    <q-dialog v-model="dlgCrear">
      <q-card class="app-dialog fac-dlg">
        <q-card-section class="text-h6">Nuevo documento de venta</q-card-section>
        <q-card-section class="app-form">
          <div class="fac-fila">
            <q-select
              v-model="form.doc_type"
              :options="opcionesTipo"
              label="Tipo *"
              outlined
              dense
              emit-value
              map-options
              class="col"
            />
            <q-select
              v-model="form.payment_method"
              :options="opcionesPago"
              label="Método de pago"
              outlined
              dense
              emit-value
              map-options
              clearable
              class="col"
            />
          </div>
          <PartySelect
            v-model="form.customer_party_id"
            role="CUSTOMER"
            label="Cliente (del directorio de Terceros)"
          />
          <q-input
            v-model="form.customer_name"
            outlined
            dense
            label="Cliente (texto libre si no está en Terceros)"
            :disable="form.customer_party_id != null"
          />
          <q-toggle v-model="form.is_fiscal" label="Documento fiscal (numera e imprime)" color="primary" />

          <q-separator spaced />
          <div class="text-subtitle2">Líneas</div>
          <div v-for="(linea, idx) in form.lines" :key="idx" class="fac-linea">
            <q-input v-model="linea.description" outlined dense label="Descripción *" class="fac-linea__desc" />
            <q-input v-model="linea.quantity" outlined dense type="number" min="0" label="Cant. *" class="fac-linea__num" />
            <q-input v-model="linea.unit_price" outlined dense type="number" min="0" label="Precio C$ *" class="fac-linea__num" />
            <q-input v-model="linea.tax_rate" outlined dense type="number" min="0" label="IVA %" class="fac-linea__num" />
            <q-btn flat dense round icon="delete" color="grey-7" @click="form.lines.splice(idx, 1)" />
          </div>
          <q-btn flat dense no-caps icon="add" label="Agregar línea" @click="agregarLinea" />
          <div class="text-right text-subtitle2">Total estimado: {{ formatMoney(totalEstimado) }}</div>
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat no-caps label="Cancelar" v-close-popup />
          <q-btn
            unelevated
            no-caps
            color="primary"
            label="Crear borrador"
            :loading="guardando"
            :disable="!formValido"
            @click="crear"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>
  </q-page>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from 'vue';
import { useRouter } from 'vue-router';
import { useQuasar, type QTableColumn } from 'quasar';
import PageHeader from 'src/components/PageHeader.vue';
import EstadoChip, { type EstadoEstilo } from 'src/components/EstadoChip.vue';
import { apiErrorMessage } from 'src/core/api';
import { useListado } from 'src/core/composables/useListado';
import { formatDate, formatMoney } from 'src/core/format';
import PartySelect from 'src/features/parties/PartySelect.vue';
import {
  BILLING_DOC_TYPE_LABELS,
  createBillingDoc,
  FISCAL_STATUS_LABELS,
  listBillingDocs,
  PAYMENT_METHOD_LABELS,
  type BillingDocRow,
  type BillingDocStatus,
  type BillingDocType,
  type BillingLineInput,
} from 'src/features/billing/billing.api';
import { useAclStore } from 'src/stores/acl.store';
import { useContextStore } from 'src/stores/context.store';

const $q = useQuasar();
const router = useRouter();
const acl = useAclStore();
const ctx = useContextStore();

const MAPA_FISCAL: Record<string, EstadoEstilo> = Object.fromEntries(
  Object.entries(FISCAL_STATUS_LABELS).map(([code, label]) => [
    code,
    {
      label,
      color: code === 'PRINTED' || code === 'ISSUED' ? 'secondary' : code === 'NUMBER_RESERVED' ? 'grey-7' : 'warning',
      outline: true,
    },
  ]),
);

const filtroQ = ref('');
const filtroEstado = ref<BillingDocStatus | null>(null);
const filtroTipo = ref<BillingDocType | null>(null);

const { rows, loading, reload } = useListado<BillingDocRow>(
  () =>
    listBillingDocs({
      q: filtroQ.value?.trim() ?? '',
      status: filtroEstado.value ?? '',
      doc_type: filtroTipo.value ?? '',
    }),
  { errorMessage: 'No se pudieron cargar los documentos.' },
);

function puede(code: string): boolean {
  const companyId = ctx.activeCompanyId;
  return companyId ? acl.hasPermission(companyId, code) : false;
}

const opcionesEstado = [
  { value: 'DRAFT', label: 'Borrador' },
  { value: 'ISSUED', label: 'Emitido' },
  { value: 'VOIDED', label: 'Anulado' },
];
const opcionesTipo = Object.entries(BILLING_DOC_TYPE_LABELS).map(([value, label]) => ({ value, label }));
const opcionesPago = Object.entries(PAYMENT_METHOD_LABELS).map(([value, label]) => ({ value, label }));

const columns: QTableColumn<BillingDocRow>[] = [
  { name: 'numero', label: 'Número', field: 'number', align: 'left' },
  { name: 'tipo', label: 'Tipo', field: 'doc_type', align: 'left' },
  { name: 'cliente', label: 'Cliente', field: 'customer_name', align: 'left' },
  { name: 'total', label: 'Total', field: 'total', align: 'right' },
  { name: 'fecha', label: 'Fecha', field: 'created_at', align: 'left' },
  { name: 'estado', label: 'Estado', field: 'status', align: 'left' },
];

function abrirDetalle(row: BillingDocRow) {
  void router.push(`/facturacion/${row.id}`);
}

// --- Crear ---
const dlgCrear = ref(false);
const guardando = ref(false);
const form = reactive<{
  doc_type: BillingDocType;
  customer_party_id: number | null;
  customer_name: string;
  is_fiscal: boolean;
  payment_method: string | null;
  lines: BillingLineInput[];
}>({
  doc_type: 'INVOICE',
  customer_party_id: null,
  customer_name: '',
  is_fiscal: false,
  payment_method: 'CASH',
  lines: [],
});

function agregarLinea() {
  form.lines.push({ description: '', quantity: '1', unit_price: '', tax_rate: '0' });
}

function abrirCrear() {
  Object.assign(form, {
    doc_type: 'INVOICE',
    customer_party_id: null,
    customer_name: '',
    is_fiscal: false,
    payment_method: 'CASH',
    lines: [],
  });
  agregarLinea();
  dlgCrear.value = true;
}

const totalEstimado = computed(() =>
  form.lines.reduce((acc, l) => {
    const sub = Number(l.quantity || 0) * Number(l.unit_price || 0);
    return acc + sub * (1 + Number(l.tax_rate || 0) / 100);
  }, 0),
);

const formValido = computed(
  () =>
    form.lines.length > 0 &&
    form.lines.every(
      (l) => l.description.trim() && Number(l.quantity) > 0 && l.unit_price !== '' && Number(l.unit_price) >= 0,
    ),
);

async function crear() {
  if (!formValido.value) return;
  guardando.value = true;
  try {
    const id = await createBillingDoc({
      doc_type: form.doc_type,
      ...(form.customer_party_id != null
        ? { customer_party_id: form.customer_party_id }
        : { customer_name: form.customer_name }),
      is_fiscal: form.is_fiscal,
      ...(form.payment_method ? { payment_method: form.payment_method } : {}),
      lines: form.lines.map((l) => ({
        description: l.description.trim(),
        quantity: String(l.quantity),
        unit_price: String(l.unit_price),
        // el backend espera tasa como fracción decimal (0.15 = 15%)
        tax_rate: String(Number(l.tax_rate || 0) / 100),
      })),
    });
    dlgCrear.value = false;
    $q.notify({ type: 'positive', message: 'Borrador creado.' });
    await router.push(`/facturacion/${id}`);
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo crear el documento.') });
  } finally {
    guardando.value = false;
  }
}
</script>

<style scoped>
.fac-filtros {
  display: flex;
  flex-wrap: wrap;
  gap: var(--app-space-3);
  margin-bottom: var(--app-space-4);
}

.fac-filtros__buscar {
  width: 320px;
  max-width: 100%;
}

.fac-filtros__sel {
  width: 180px;
}

.fac-dlg {
  width: 720px;
}

.fac-fila {
  display: flex;
  gap: var(--app-space-3);
}

.fac-fila .col {
  flex: 1;
}

.fac-linea {
  display: flex;
  align-items: center;
  gap: var(--app-space-2);
}

.fac-linea__desc {
  flex: 1;
}

.fac-linea__num {
  width: 110px;
}
</style>
