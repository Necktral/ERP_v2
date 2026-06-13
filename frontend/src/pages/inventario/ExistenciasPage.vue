<template>
  <q-page class="app-page">
    <PageHeader
      title="Existencias"
      subtitle="Lo que hay en cada bodega de la sucursal activa, con su costo promedio. Desde aquí se mueve el inventario."
      :loading="loading"
      @refresh="reload"
    >
      <template #actions>
        <q-btn
          v-if="puede('inventory.movement.receive')"
          unelevated
          no-caps
          color="primary"
          icon="archive"
          label="Recibir"
          @click="abrirMovimiento('RECIBIR')"
        />
        <q-btn
          v-if="puede('inventory.movement.issue')"
          outline
          no-caps
          color="primary"
          icon="unarchive"
          label="Despachar"
          @click="abrirMovimiento('DESPACHAR')"
        />
        <q-btn
          v-if="puede('inventory.movement.adjust')"
          flat
          no-caps
          icon="tune"
          label="Ajustar"
          @click="abrirMovimiento('AJUSTAR')"
        />
        <q-btn
          v-if="puede('inventory.transfer.create')"
          flat
          no-caps
          icon="swap_horiz"
          label="Transferir"
          @click="abrirMovimiento('TRANSFERIR')"
        />
      </template>
    </PageHeader>

    <div class="inv-filtros">
      <q-select
        v-model="filtroBodega"
        :options="opcionesBodega"
        dense
        outlined
        emit-value
        map-options
        clearable
        label="Bodega"
        class="inv-filtros__sel"
        @update:model-value="reload"
      />
      <q-select
        v-model="filtroItem"
        :options="opcionesItemFiltradas"
        dense
        outlined
        emit-value
        map-options
        clearable
        use-input
        input-debounce="200"
        label="Artículo"
        class="inv-filtros__sel-ancho"
        @filter="filtrarItems"
        @update:model-value="reload"
      />
      <q-toggle
        v-model="filtroReorden"
        label="Bajo punto de reorden"
        color="warning"
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
      no-data-label="Sin existencias con esos filtros. Usá «Recibir» para ingresar inventario."
    >
      <template #body-cell-disponible="props">
        <q-td :props="props" class="text-weight-bold">
          {{ formatQty(props.row.qty_available) }}
          {{ UOM_LABELS[props.row.item_uom] ?? props.row.item_uom }}
        </q-td>
      </template>
      <template #body-cell-costo="props">
        <q-td :props="props">{{ formatMoney(props.row.avg_cost) }}</q-td>
      </template>
      <template #body-cell-valor="props">
        <q-td :props="props">
          {{ formatMoney(Number(props.row.qty_on_hand) * Number(props.row.avg_cost)) }}
        </q-td>
      </template>
      <template #body-cell-acciones="props">
        <q-td :props="props" class="text-right">
          <q-btn
            v-if="esItemConLotes(props.row.item)"
            flat
            dense
            no-caps
            size="sm"
            icon="inventory_2"
            label="Lotes"
            @click="verLotes(props.row)"
          />
          <q-btn
            flat
            dense
            no-caps
            size="sm"
            icon="receipt_long"
            label="Kardex"
            :to="`/inventario/kardex?item_id=${props.row.item}`"
          />
        </q-td>
      </template>
    </q-table>

    <!-- Diálogo de movimiento (recibir/despachar/ajustar/transferir) -->
    <q-dialog v-model="dlgMov">
      <q-card class="app-dialog">
        <q-card-section class="text-h6">{{ TITULO_MOV[modo] }}</q-card-section>
        <q-card-section class="app-form">
          <q-select
            v-model="mov.item_id"
            :options="opcionesItemFiltradas"
            label="Artículo *"
            outlined
            dense
            emit-value
            map-options
            use-input
            input-debounce="200"
            @filter="filtrarItems"
          />
          <q-select
            v-if="modo !== 'TRANSFERIR'"
            v-model="mov.warehouse_id"
            :options="opcionesBodega"
            label="Bodega *"
            outlined
            dense
            emit-value
            map-options
          />
          <template v-if="modo === 'TRANSFERIR'">
            <q-select
              v-model="mov.from_warehouse_id"
              :options="opcionesBodega"
              label="Desde bodega *"
              outlined
              dense
              emit-value
              map-options
            />
            <q-select
              v-model="mov.to_warehouse_id"
              :options="opcionesBodega"
              label="Hacia bodega *"
              outlined
              dense
              emit-value
              map-options
            />
          </template>

          <q-input
            v-if="modo !== 'AJUSTAR'"
            v-model="mov.qty"
            outlined
            dense
            type="number"
            min="0"
            label="Cantidad *"
          />
          <q-input
            v-else
            v-model="mov.new_qty_on_hand"
            outlined
            dense
            type="number"
            min="0"
            label="Cantidad real contada *"
            hint="El sistema registra la diferencia contra lo que había."
          />
          <q-input
            v-if="modo === 'RECIBIR'"
            v-model="mov.unit_cost"
            outlined
            dense
            type="number"
            min="0"
            label="Costo unitario C$ *"
          />
          <template v-if="modo === 'RECIBIR' && esItemConLotes(mov.item_id)">
            <q-input v-model="mov.lot_number" outlined dense label="Número de lote" />
            <q-input
              v-model="mov.expiry_date"
              outlined
              dense
              type="date"
              label="Fecha de vencimiento"
            />
          </template>
          <q-input v-model="mov.note" outlined dense label="Nota" />
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat no-caps label="Cancelar" v-close-popup />
          <q-btn
            unelevated
            no-caps
            color="primary"
            :label="TITULO_MOV[modo]"
            :loading="posteando"
            :disable="!movValido"
            @click="postearMovimiento"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <!-- Diálogo de lotes por artículo -->
    <q-dialog v-model="dlgLotes">
      <q-card class="app-dialog inv-dlg-lotes">
        <q-card-section class="text-h6">
          Lotes de {{ lotesDe?.item_name }} en {{ lotesDe?.warehouse_name }}
        </q-card-section>
        <q-card-section>
          <q-list dense separator>
            <q-item v-for="l in lotes" :key="l.id">
              <q-item-section>
                <q-item-label>{{ l.lot_number }}</q-item-label>
                <q-item-label caption>
                  Vence: {{ formatDate(l.expiry_date) }} · {{ l.lot_status }}
                </q-item-label>
              </q-item-section>
              <q-item-section side>
                <q-item-label>{{ formatQty(l.qty_on_hand) }}</q-item-label>
              </q-item-section>
            </q-item>
            <q-item v-if="lotes.length === 0">
              <q-item-section class="text-caption text-muted">Sin lotes con saldo.</q-item-section>
            </q-item>
          </q-list>
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat no-caps label="Cerrar" v-close-popup />
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
import { formatDate, formatMoney, formatQty } from 'src/core/format';
import {
  adjustStock,
  getStock,
  getStockLots,
  issueStock,
  listItems,
  listWarehouses,
  receiveStock,
  transferStock,
  UOM_LABELS,
  type InventoryItem,
  type LotStockRow,
  type StockRow,
  type Warehouse,
} from 'src/features/inventory/inventory.api';
import { useAclStore } from 'src/stores/acl.store';
import { useContextStore } from 'src/stores/context.store';

type Modo = 'RECIBIR' | 'DESPACHAR' | 'AJUSTAR' | 'TRANSFERIR';

const TITULO_MOV: Record<Modo, string> = {
  RECIBIR: 'Recibir inventario',
  DESPACHAR: 'Despachar inventario',
  AJUSTAR: 'Ajustar existencia',
  TRANSFERIR: 'Transferir entre bodegas',
};

const ACCOUNTING_LABELS: Record<string, string> = {
  DISABLED: 'sin contabilizar (GL apagado)',
  POSTED: 'asiento contable posteado',
  DRAFT_VALIDATED: 'borrador contable generado',
  DRAFT_EXCEPTION: 'borrador contable con excepción',
  PENDING_RULESET: 'pendiente de reglas contables',
  PENDING_RULE: 'pendiente de regla contable',
  UNSUPPORTED: 'sin regla contable aplicable',
};

const $q = useQuasar();
const acl = useAclStore();
const ctx = useContextStore();

const filtroBodega = ref<number | null>(null);
const filtroItem = ref<number | null>(null);
const filtroReorden = ref(false);

const bodegas = ref<Warehouse[]>([]);
const items = ref<InventoryItem[]>([]);
const itemsPorId = computed(() => new Map(items.value.map((i) => [i.id, i])));

const { rows, loading, reload } = useListado<StockRow>(
  () =>
    getStock({
      ...(filtroBodega.value ? { warehouse_id: filtroBodega.value } : {}),
      ...(filtroItem.value ? { item_id: filtroItem.value } : {}),
      ...(filtroReorden.value ? { below_reorder: true } : {}),
    }),
  { errorMessage: 'No se pudieron cargar las existencias.' },
);

function puede(code: string): boolean {
  const companyId = ctx.activeCompanyId;
  return companyId ? acl.hasPermission(companyId, code) : false;
}

const opcionesBodega = computed(() =>
  bodegas.value.map((w) => ({ value: w.id, label: w.code ? `${w.code} — ${w.name}` : w.name })),
);

const opcionesItem = computed(() =>
  items.value.map((i) => ({ value: i.id, label: `${i.sku} — ${i.name}` })),
);
const opcionesItemFiltradas = ref<{ value: number; label: string }[]>([]);

function filtrarItems(input: string, update: (fn: () => void) => void) {
  update(() => {
    const q = input.trim().toLowerCase();
    opcionesItemFiltradas.value = q
      ? opcionesItem.value.filter((o) => o.label.toLowerCase().includes(q))
      : opcionesItem.value;
  });
}

function esItemConLotes(itemId: number | null): boolean {
  return itemId != null && (itemsPorId.value.get(itemId)?.track_lots ?? false);
}

const columns: QTableColumn<StockRow>[] = [
  { name: 'item_sku', label: 'SKU', field: 'item_sku', align: 'left', sortable: true },
  { name: 'item_name', label: 'Artículo', field: 'item_name', align: 'left', sortable: true },
  { name: 'warehouse_name', label: 'Bodega', field: 'warehouse_name', align: 'left' },
  { name: 'disponible', label: 'Disponible', field: 'qty_available', align: 'right' },
  { name: 'costo', label: 'Costo prom.', field: 'avg_cost', align: 'right' },
  { name: 'valor', label: 'Valor', field: 'qty_on_hand', align: 'right' },
  { name: 'acciones', label: '', field: 'id', align: 'right' },
];

// --- Movimiento ---
const dlgMov = ref(false);
const modo = ref<Modo>('RECIBIR');
const posteando = ref(false);
const mov = reactive<{
  item_id: number | null;
  warehouse_id: number | null;
  from_warehouse_id: number | null;
  to_warehouse_id: number | null;
  qty: string;
  unit_cost: string;
  new_qty_on_hand: string;
  lot_number: string;
  expiry_date: string;
  note: string;
}>({
  item_id: null,
  warehouse_id: null,
  from_warehouse_id: null,
  to_warehouse_id: null,
  qty: '',
  unit_cost: '',
  new_qty_on_hand: '',
  lot_number: '',
  expiry_date: '',
  note: '',
});

function abrirMovimiento(m: Modo) {
  modo.value = m;
  Object.assign(mov, {
    item_id: filtroItem.value,
    warehouse_id: filtroBodega.value,
    from_warehouse_id: filtroBodega.value,
    to_warehouse_id: null,
    qty: '',
    unit_cost: '',
    new_qty_on_hand: '',
    lot_number: '',
    expiry_date: '',
    note: '',
  });
  dlgMov.value = true;
}

const movValido = computed(() => {
  if (mov.item_id == null) return false;
  if (modo.value === 'TRANSFERIR') {
    return (
      mov.from_warehouse_id != null &&
      mov.to_warehouse_id != null &&
      mov.from_warehouse_id !== mov.to_warehouse_id &&
      Number(mov.qty) > 0
    );
  }
  if (mov.warehouse_id == null) return false;
  if (modo.value === 'AJUSTAR') return mov.new_qty_on_hand !== '' && Number(mov.new_qty_on_hand) >= 0;
  if (modo.value === 'RECIBIR') return Number(mov.qty) > 0 && Number(mov.unit_cost) >= 0 && mov.unit_cost !== '';
  return Number(mov.qty) > 0;
});

async function postearMovimiento() {
  if (!movValido.value || mov.item_id == null) return;
  posteando.value = true;
  try {
    let accounting = '';
    if (modo.value === 'RECIBIR') {
      const r = await receiveStock({
        warehouse_id: mov.warehouse_id!,
        item_id: mov.item_id,
        qty: mov.qty,
        unit_cost: mov.unit_cost,
        ...(mov.lot_number ? { lot_number: mov.lot_number } : {}),
        ...(mov.expiry_date ? { expiry_date: mov.expiry_date } : {}),
        ...(mov.note ? { note: mov.note } : {}),
      });
      accounting = r.accounting_status;
    } else if (modo.value === 'DESPACHAR') {
      const r = await issueStock({
        warehouse_id: mov.warehouse_id!,
        item_id: mov.item_id,
        qty: mov.qty,
        ...(mov.note ? { note: mov.note } : {}),
      });
      accounting = r.accounting_status;
    } else if (modo.value === 'AJUSTAR') {
      const r = await adjustStock({
        warehouse_id: mov.warehouse_id!,
        item_id: mov.item_id,
        new_qty_on_hand: mov.new_qty_on_hand,
        ...(mov.note ? { note: mov.note } : {}),
      });
      accounting = r.accounting_status;
    } else {
      const r = await transferStock({
        from_warehouse_id: mov.from_warehouse_id!,
        to_warehouse_id: mov.to_warehouse_id!,
        item_id: mov.item_id,
        qty: mov.qty,
        ...(mov.note ? { note: mov.note } : {}),
      });
      accounting = r.to_movement.accounting_status;
    }
    dlgMov.value = false;
    const detalle = ACCOUNTING_LABELS[accounting] ? ` (${ACCOUNTING_LABELS[accounting]})` : '';
    $q.notify({ type: 'positive', message: `${TITULO_MOV[modo.value]}: listo${detalle}.` });
    await reload();
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo registrar el movimiento.') });
  } finally {
    posteando.value = false;
  }
}

// --- Lotes ---
const dlgLotes = ref(false);
const lotes = ref<LotStockRow[]>([]);
const lotesDe = ref<StockRow | null>(null);

async function verLotes(row: StockRow) {
  lotesDe.value = row;
  lotes.value = [];
  dlgLotes.value = true;
  try {
    lotes.value = await getStockLots(row.item, row.warehouse);
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudieron cargar los lotes.') });
  }
}

onMounted(async () => {
  try {
    [bodegas.value, items.value] = await Promise.all([listWarehouses(), listItems({ is_active: true })]);
    opcionesItemFiltradas.value = opcionesItem.value;
  } catch {
    $q.notify({ type: 'negative', message: 'No se pudieron cargar bodegas/artículos.' });
  }
});
</script>

<style scoped>
.inv-filtros {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--app-space-3);
  margin-bottom: var(--app-space-4);
}

.inv-filtros__sel {
  width: 220px;
}

.inv-filtros__sel-ancho {
  width: 320px;
}

.inv-dlg-lotes {
  width: 560px;
}
</style>
