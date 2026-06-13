<template>
  <q-page class="app-page">
    <PageHeader
      title="Kardex"
      subtitle="Historial inmutable de movimientos por artículo: qué entró, qué salió, a qué costo y quién lo hizo."
      :loading="loading"
      @refresh="recargar"
    />

    <div class="kdx-filtros">
      <q-select
        v-model="itemId"
        :options="opcionesItemFiltradas"
        dense
        outlined
        emit-value
        map-options
        use-input
        input-debounce="200"
        label="Artículo *"
        class="kdx-filtros__item"
        @filter="filtrarItems"
        @update:model-value="recargar"
      />
      <q-select
        v-model="warehouseId"
        :options="opcionesBodega"
        dense
        outlined
        emit-value
        map-options
        clearable
        label="Bodega"
        class="kdx-filtros__sel"
        @update:model-value="recargar"
      />
      <q-select
        v-model="tipo"
        :options="opcionesTipo"
        dense
        outlined
        emit-value
        map-options
        clearable
        label="Tipo de movimiento"
        class="kdx-filtros__sel"
        @update:model-value="recargar"
      />
      <q-input
        v-model="desde"
        dense
        outlined
        type="date"
        label="Desde"
        class="kdx-filtros__fecha"
        @update:model-value="recargar"
      />
      <q-input
        v-model="hasta"
        dense
        outlined
        type="date"
        label="Hasta"
        class="kdx-filtros__fecha"
        @update:model-value="recargar"
      />
    </div>

    <q-banner v-if="itemId == null" class="kdx-aviso" rounded>
      <template #avatar><q-icon name="info" color="primary" /></template>
      Elegí un artículo para ver su kardex.
    </q-banner>

    <q-table
      v-else
      class="app-table"
      :rows="movimientos"
      :columns="columns"
      row-key="id"
      flat
      :loading="loading"
      :pagination="{ rowsPerPage: 50 }"
      no-data-label="Sin movimientos para esos filtros."
    >
      <template #body-cell-fecha="props">
        <q-td :props="props">{{ formatDateTime(props.row.created_at) }}</q-td>
      </template>
      <template #body-cell-tipo="props">
        <q-td :props="props">
          {{ MOVEMENT_TYPE_LABELS[props.row.movement_type] ?? props.row.movement_type }}
        </q-td>
      </template>
      <template #body-cell-cantidad="props">
        <q-td
          :props="props"
          :class="Number(props.row.qty_delta) >= 0 ? 'text-positive' : 'text-negative'"
        >
          {{ Number(props.row.qty_delta) >= 0 ? '+' : '' }}{{ formatQty(props.row.qty_delta) }}
        </q-td>
      </template>
      <template #body-cell-costo="props">
        <q-td :props="props">{{ formatMoney(props.row.unit_cost) }}</q-td>
      </template>
      <template #body-cell-total="props">
        <q-td :props="props">{{ formatMoney(props.row.total_cost) }}</q-td>
      </template>
    </q-table>
  </q-page>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useRoute } from 'vue-router';
import { useQuasar, type QTableColumn } from 'quasar';
import PageHeader from 'src/components/PageHeader.vue';
import { apiErrorMessage } from 'src/core/api';
import { formatDateTime, formatMoney, formatQty } from 'src/core/format';
import {
  getKardex,
  listItems,
  listWarehouses,
  MOVEMENT_TYPE_LABELS,
  type InventoryItem,
  type KardexRow,
  type Warehouse,
} from 'src/features/inventory/inventory.api';

const $q = useQuasar();
const route = useRoute();

const itemId = ref<number | null>(null);
const warehouseId = ref<number | null>(null);
const tipo = ref<string | null>(null);
const desde = ref('');
const hasta = ref('');

const loading = ref(false);
const movimientos = ref<KardexRow[]>([]);
const items = ref<InventoryItem[]>([]);
const bodegas = ref<Warehouse[]>([]);

const opcionesItem = computed(() =>
  items.value.map((i) => ({ value: i.id, label: `${i.sku} — ${i.name}` })),
);
const opcionesItemFiltradas = ref<{ value: number; label: string }[]>([]);
const opcionesBodega = computed(() => bodegas.value.map((w) => ({ value: w.id, label: w.name })));
const opcionesTipo = Object.entries(MOVEMENT_TYPE_LABELS).map(([value, label]) => ({
  value,
  label,
}));

function filtrarItems(input: string, update: (fn: () => void) => void) {
  update(() => {
    const q = input.trim().toLowerCase();
    opcionesItemFiltradas.value = q
      ? opcionesItem.value.filter((o) => o.label.toLowerCase().includes(q))
      : opcionesItem.value;
  });
}

const columns: QTableColumn<KardexRow>[] = [
  { name: 'fecha', label: 'Fecha', field: 'created_at', align: 'left' },
  { name: 'tipo', label: 'Movimiento', field: 'movement_type', align: 'left' },
  { name: 'warehouse_name', label: 'Bodega', field: 'warehouse_name', align: 'left' },
  { name: 'cantidad', label: 'Cantidad', field: 'qty_delta', align: 'right' },
  { name: 'costo', label: 'Costo unit.', field: 'unit_cost', align: 'right' },
  { name: 'total', label: 'Total', field: 'total_cost', align: 'right' },
  { name: 'lot_number', label: 'Lote', field: 'lot_number', align: 'left' },
  { name: 'note', label: 'Nota', field: 'note', align: 'left' },
];

async function recargar() {
  if (itemId.value == null) return;
  loading.value = true;
  try {
    movimientos.value = await getKardex({
      item_id: itemId.value,
      ...(warehouseId.value ? { warehouse_id: warehouseId.value } : {}),
      ...(tipo.value ? { movement_type: tipo.value } : {}),
      ...(desde.value ? { date_from: desde.value } : {}),
      ...(hasta.value ? { date_to: hasta.value } : {}),
    });
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo cargar el kardex.') });
  } finally {
    loading.value = false;
  }
}

onMounted(async () => {
  try {
    [items.value, bodegas.value] = await Promise.all([listItems({ is_active: true }), listWarehouses()]);
    opcionesItemFiltradas.value = opcionesItem.value;
  } catch {
    $q.notify({ type: 'negative', message: 'No se pudieron cargar artículos/bodegas.' });
  }
  const fromQuery = Number(route.query.item_id);
  if (Number.isFinite(fromQuery) && fromQuery > 0) {
    itemId.value = fromQuery;
    await recargar();
  }
});
</script>

<style scoped>
.kdx-filtros {
  display: flex;
  flex-wrap: wrap;
  gap: var(--app-space-3);
  margin-bottom: var(--app-space-4);
}

.kdx-filtros__item {
  width: 320px;
}

.kdx-filtros__sel {
  width: 210px;
}

.kdx-filtros__fecha {
  width: 160px;
}

.kdx-aviso {
  background: var(--app-surface);
  border: 1px solid var(--app-border);
  color: var(--app-text-muted);
}
</style>
