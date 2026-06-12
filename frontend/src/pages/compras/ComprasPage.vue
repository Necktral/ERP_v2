<template>
  <q-page class="app-page">
    <PageHeader
      title="Compras"
      subtitle="Documentos de proveedor de la sucursal activa: recepciones, facturas, notas de crédito y pagos. El posteo asigna número y alimenta la cuenta por pagar."
      :loading="loading"
      @refresh="reload"
    >
      <template #actions>
        <q-btn
          v-if="puedeCrear"
          unelevated
          no-caps
          color="primary"
          icon="post_add"
          label="Nuevo documento"
          @click="abrirCrear"
        />
      </template>
    </PageHeader>

    <div class="cmp-filtros">
      <q-input
        v-model="filtroQ"
        dense
        outlined
        clearable
        placeholder="Buscar por proveedor, referencia o número…"
        class="cmp-filtros__buscar"
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
        class="cmp-filtros__sel"
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
        class="cmp-filtros__sel-ancho"
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
      no-data-label="No hay documentos de compra con esos filtros."
      @row-click="(_, row) => abrirDetalle(row as PurchaseDocRow)"
    >
      <template #body-cell-numero="props">
        <q-td :props="props">
          {{ props.row.number > 0 ? `${props.row.series}-${props.row.number}` : '—' }}
        </q-td>
      </template>
      <template #body-cell-tipo="props">
        <q-td :props="props">{{ PURCHASE_DOC_TYPE_LABELS[props.row.doc_type as PurchaseDocType] }}</q-td>
      </template>
      <template #body-cell-proveedor="props">
        <q-td :props="props">
          {{ props.row.supplier_party_display_name || props.row.supplier_name || '—' }}
        </q-td>
      </template>
      <template #body-cell-total="props">
        <q-td :props="props">{{ formatMoney(props.row.total) }}</q-td>
      </template>
      <template #body-cell-fecha="props">
        <q-td :props="props">{{ formatDate(props.row.created_at) }}</q-td>
      </template>
      <template #body-cell-estado="props">
        <q-td :props="props"><EstadoChip :estado="props.row.status" /></q-td>
      </template>
    </q-table>

    <!-- Diálogo: nuevo documento -->
    <q-dialog v-model="dlgCrear">
      <q-card class="app-dialog">
        <q-card-section class="text-h6">Nuevo documento de compra</q-card-section>
        <q-card-section class="app-form">
          <q-select
            v-model="form.doc_type"
            :options="opcionesTipo"
            label="Tipo de documento *"
            outlined
            dense
            emit-value
            map-options
          />
          <PartySelect
            v-model="form.supplier_party_id"
            role="SUPPLIER"
            label="Proveedor (del directorio de Terceros)"
          />
          <q-input
            v-model="form.supplier_name"
            outlined
            dense
            label="Proveedor (texto libre si no está en Terceros)"
            :disable="form.supplier_party_id != null"
          />
          <q-input v-model="form.supplier_ref" outlined dense label="Referencia del proveedor (Nº factura física)" />
          <q-input
            v-model="form.subtotal"
            outlined
            dense
            type="number"
            min="0"
            label="Subtotal C$ *"
          />
          <q-input
            v-model="form.tax_total"
            outlined
            dense
            type="number"
            min="0"
            label="Impuesto C$"
          />
          <q-input
            :model-value="formatMoney(totalCalculado)"
            outlined
            dense
            readonly
            label="Total (subtotal + impuesto)"
          />
          <q-input v-model="form.notes" outlined dense label="Notas" />
          <div class="text-caption text-muted">
            Se crea como BORRADOR (sin número). Al postearlo toma número y queda en firme.
          </div>
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
import { useQuasar } from 'quasar';
import type { QTableColumn } from 'quasar';
import PageHeader from 'src/components/PageHeader.vue';
import EstadoChip from 'src/components/EstadoChip.vue';
import { apiErrorMessage } from 'src/core/api';
import { useListado } from 'src/core/composables/useListado';
import { formatDate, formatMoney } from 'src/core/format';
import PartySelect from 'src/features/parties/PartySelect.vue';
import {
  createPurchaseDoc,
  listPurchaseDocs,
  PURCHASE_DOC_TYPE_LABELS,
  type PurchaseDocRow,
  type PurchaseDocStatus,
  type PurchaseDocType,
} from 'src/features/procurement/procurement.api';
import { useAclStore } from 'src/stores/acl.store';
import { useContextStore } from 'src/stores/context.store';

const $q = useQuasar();
const router = useRouter();
const acl = useAclStore();
const ctx = useContextStore();

const filtroQ = ref('');
const filtroEstado = ref<PurchaseDocStatus | null>(null);
const filtroTipo = ref<PurchaseDocType | null>(null);

const { rows, loading, reload } = useListado<PurchaseDocRow>(
  () =>
    listPurchaseDocs({
      q: filtroQ.value?.trim() ?? '',
      status: filtroEstado.value ?? '',
      doc_type: filtroTipo.value ?? '',
    }),
  { errorMessage: 'No se pudieron cargar los documentos de compra.' },
);

const puedeCrear = computed(() => {
  const companyId = ctx.activeCompanyId;
  return companyId ? acl.hasPermission(companyId, 'procurement.doc.create') : false;
});

const opcionesEstado = [
  { value: 'DRAFT', label: 'Borrador' },
  { value: 'POSTED', label: 'Posteado' },
  { value: 'VOIDED', label: 'Anulado' },
];
const opcionesTipo = Object.entries(PURCHASE_DOC_TYPE_LABELS).map(([value, label]) => ({
  value,
  label,
}));

const columns: QTableColumn<PurchaseDocRow>[] = [
  { name: 'numero', label: 'Número', field: 'number', align: 'left' },
  { name: 'tipo', label: 'Tipo', field: 'doc_type', align: 'left' },
  { name: 'proveedor', label: 'Proveedor', field: 'supplier_name', align: 'left' },
  { name: 'total', label: 'Total', field: 'total', align: 'right' },
  { name: 'fecha', label: 'Fecha', field: 'created_at', align: 'left' },
  { name: 'estado', label: 'Estado', field: 'status', align: 'left' },
];

function abrirDetalle(row: PurchaseDocRow) {
  void router.push(`/compras/${row.id}`);
}

// --- Crear ---
const dlgCrear = ref(false);
const guardando = ref(false);
const form = reactive<{
  doc_type: PurchaseDocType;
  supplier_party_id: number | null;
  supplier_name: string;
  supplier_ref: string;
  subtotal: string;
  tax_total: string;
  notes: string;
}>({
  doc_type: 'SUPPLIER_INVOICE',
  supplier_party_id: null,
  supplier_name: '',
  supplier_ref: '',
  subtotal: '',
  tax_total: '0',
  notes: '',
});

const totalCalculado = computed(() => Number(form.subtotal || 0) + Number(form.tax_total || 0));
const formValido = computed(
  () => form.subtotal !== '' && Number(form.subtotal) >= 0 && Number(form.tax_total || 0) >= 0,
);

function abrirCrear() {
  Object.assign(form, {
    doc_type: 'SUPPLIER_INVOICE',
    supplier_party_id: null,
    supplier_name: '',
    supplier_ref: '',
    subtotal: '',
    tax_total: '0',
    notes: '',
  });
  dlgCrear.value = true;
}

async function crear() {
  if (!formValido.value) return;
  guardando.value = true;
  try {
    const id = await createPurchaseDoc({
      doc_type: form.doc_type,
      ...(form.supplier_party_id != null
        ? { supplier_party_id: form.supplier_party_id }
        : { supplier_name: form.supplier_name }),
      ...(form.supplier_ref ? { supplier_ref: form.supplier_ref } : {}),
      subtotal: Number(form.subtotal).toFixed(2),
      tax_total: Number(form.tax_total || 0).toFixed(2),
      total: totalCalculado.value.toFixed(2),
      ...(form.notes ? { notes: form.notes } : {}),
    });
    dlgCrear.value = false;
    $q.notify({ type: 'positive', message: 'Borrador creado.' });
    await router.push(`/compras/${id}`);
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo crear el documento.') });
  } finally {
    guardando.value = false;
  }
}
</script>

<style scoped>
.cmp-filtros {
  display: flex;
  flex-wrap: wrap;
  gap: var(--app-space-3);
  margin-bottom: var(--app-space-4);
}

.cmp-filtros__buscar {
  width: 320px;
  max-width: 100%;
}

.cmp-filtros__sel {
  width: 170px;
}

.cmp-filtros__sel-ancho {
  width: 240px;
}
</style>
