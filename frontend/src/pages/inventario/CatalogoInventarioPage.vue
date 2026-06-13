<template>
  <q-page class="app-page">
    <PageHeader
      title="Catálogo de inventario"
      subtitle="Artículos, bodegas y lotes. Se configura una vez y las existencias se mueven en la pantalla de Existencias."
      :loading="cargando"
      @refresh="recargarTodo"
    />

    <q-tabs
      v-model="tab"
      dense
      no-caps
      align="left"
      class="cat-tabs"
      active-color="primary"
      indicator-color="primary"
    >
      <q-tab name="articulos" icon="category" label="Artículos" />
      <q-tab name="bodegas" icon="warehouse" label="Bodegas" />
      <q-tab name="lotes" icon="inventory_2" label="Lotes" />
    </q-tabs>
    <q-separator class="q-mb-md" />

    <q-tab-panels v-model="tab" animated class="cat-panels">
      <!-- ============ ARTÍCULOS ============ -->
      <q-tab-panel name="articulos" class="q-pa-none">
        <div class="app-actions">
          <q-btn
            v-if="puede('inventory.item.create')"
            unelevated
            no-caps
            color="primary"
            icon="add"
            label="Nuevo artículo"
            @click="abrirCrearItem"
          />
          <span class="text-caption text-muted">
            SKU único por empresa. Si el artículo vence (agroquímicos, alimentos), activá lotes y
            vencimiento.
          </span>
        </div>
        <q-table
          class="app-table"
          :rows="items"
          :columns="columnasItem"
          row-key="id"
          flat
          :loading="cargando"
          :pagination="{ rowsPerPage: 25 }"
          no-data-label="Aún no hay artículos."
        >
          <template #body-cell-uom="props">
            <q-td :props="props">{{ UOM_LABELS[props.row.uom] ?? props.row.uom }}</q-td>
          </template>
          <template #body-cell-flags="props">
            <q-td :props="props">
              <q-chip v-if="props.row.track_lots" dense outline color="primary" label="Lotes" />
              <q-chip v-if="props.row.track_expiry" dense outline color="warning" label="Vence" />
              <q-chip v-if="props.row.is_controlled" dense outline color="negative" label="Controlado" />
            </q-td>
          </template>
        </q-table>
      </q-tab-panel>

      <!-- ============ BODEGAS ============ -->
      <q-tab-panel name="bodegas" class="q-pa-none">
        <div class="app-actions">
          <q-btn
            v-if="puede('inventory.warehouse.create')"
            unelevated
            no-caps
            color="primary"
            icon="add_home_work"
            label="Nueva bodega"
            :disable="!ctx.activeBranchId"
            @click="dlgBodega = true"
          />
          <span class="text-caption text-muted">
            {{
              ctx.activeBranchId
                ? 'Las bodegas pertenecen a la sucursal activa del selector de arriba.'
                : 'Elegí una SUCURSAL en el selector de arriba para crear bodegas.'
            }}
          </span>
        </div>
        <q-table
          class="app-table"
          :rows="bodegas"
          :columns="columnasBodega"
          row-key="id"
          flat
          :loading="cargando"
          :pagination="{ rowsPerPage: 25 }"
          no-data-label="Aún no hay bodegas en esta sucursal."
        >
          <template #body-cell-tipo="props">
            <q-td :props="props">
              {{ WAREHOUSE_TYPE_LABELS[props.row.warehouse_type] ?? props.row.warehouse_type }}
            </q-td>
          </template>
          <template #body-cell-default="props">
            <q-td :props="props">
              <q-icon v-if="props.row.is_default" name="star" color="amber" size="18px" />
            </q-td>
          </template>
        </q-table>
      </q-tab-panel>

      <!-- ============ LOTES ============ -->
      <q-tab-panel name="lotes" class="q-pa-none">
        <div class="app-actions">
          <q-select
            v-model="loteItemId"
            :options="opcionesItemLotes"
            dense
            outlined
            emit-value
            map-options
            label="Artículo con lotes"
            class="cat-lote-sel"
            @update:model-value="cargarLotes"
          />
          <q-btn
            v-if="puede('inventory.lot.create') && loteItemId != null"
            unelevated
            no-caps
            color="primary"
            icon="add"
            label="Nuevo lote"
            @click="dlgLote = true"
          />
        </div>
        <q-table
          class="app-table"
          :rows="lotes"
          :columns="columnasLote"
          row-key="id"
          flat
          :loading="cargandoLotes"
          :pagination="{ rowsPerPage: 25 }"
          :no-data-label="
            loteItemId == null ? 'Elegí un artículo con lotes.' : 'Este artículo no tiene lotes.'
          "
        >
          <template #body-cell-vence="props">
            <q-td :props="props" :class="props.row.is_expired ? 'text-negative' : ''">
              {{ formatDate(props.row.expiry_date) }}
              <span v-if="props.row.days_to_expiry != null" class="text-caption text-muted">
                ({{ props.row.days_to_expiry }} días)
              </span>
            </q-td>
          </template>
        </q-table>
      </q-tab-panel>
    </q-tab-panels>

    <!-- Diálogo: nuevo artículo -->
    <q-dialog v-model="dlgItem">
      <q-card class="app-dialog">
        <q-card-section class="text-h6">Nuevo artículo</q-card-section>
        <q-card-section class="app-form">
          <q-input v-model="formItem.sku" outlined dense label="SKU * (código único)" autofocus />
          <q-input v-model="formItem.name" outlined dense label="Nombre *" />
          <q-input v-model="formItem.category" outlined dense label="Categoría" />
          <q-select
            v-model="formItem.uom"
            :options="opcionesUom"
            label="Unidad de medida"
            outlined
            dense
            emit-value
            map-options
          />
          <q-input
            v-model="formItem.reorder_point"
            outlined
            dense
            type="number"
            min="0"
            label="Punto de reorden"
            hint="Cuando el saldo baje de aquí, aparece en la alerta de reorden."
          />
          <q-toggle v-model="formItem.track_lots" label="Maneja lotes" color="primary" />
          <q-toggle
            v-model="formItem.track_expiry"
            :disable="!formItem.track_lots"
            label="Controla vencimiento (requiere lotes)"
            color="warning"
          />
          <q-toggle
            v-model="formItem.is_controlled"
            label="Producto controlado (agroquímico)"
            color="negative"
          />
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat no-caps label="Cancelar" v-close-popup />
          <q-btn
            unelevated
            no-caps
            color="primary"
            label="Crear artículo"
            :loading="guardando"
            :disable="!formItem.sku.trim() || !formItem.name.trim()"
            @click="crearItemNuevo"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <!-- Diálogo: nueva bodega -->
    <q-dialog v-model="dlgBodega">
      <q-card class="app-dialog">
        <q-card-section class="text-h6">Nueva bodega</q-card-section>
        <q-card-section class="app-form">
          <q-input v-model="formBodega.name" outlined dense label="Nombre *" autofocus />
          <q-input v-model="formBodega.code" outlined dense label="Código (corto, opcional)" />
          <q-select
            v-model="formBodega.warehouse_type"
            :options="opcionesTipoBodega"
            label="Tipo"
            outlined
            dense
            emit-value
            map-options
          />
          <q-input v-model="formBodega.location_description" outlined dense label="Ubicación" />
          <q-toggle v-model="formBodega.is_default" label="Bodega por defecto" color="primary" />
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat no-caps label="Cancelar" v-close-popup />
          <q-btn
            unelevated
            no-caps
            color="primary"
            label="Crear bodega"
            :loading="guardando"
            :disable="!formBodega.name.trim()"
            @click="crearBodegaNueva"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <!-- Diálogo: nuevo lote -->
    <q-dialog v-model="dlgLote">
      <q-card class="app-dialog">
        <q-card-section class="text-h6">Nuevo lote</q-card-section>
        <q-card-section class="app-form">
          <q-input v-model="formLote.lot_number" outlined dense label="Número de lote *" autofocus />
          <q-input v-model="formLote.supplier_lot_ref" outlined dense label="Lote del proveedor" />
          <q-input v-model="formLote.production_date" outlined dense type="date" label="Fecha de producción" />
          <q-input v-model="formLote.expiry_date" outlined dense type="date" label="Fecha de vencimiento" />
          <q-input v-model="formLote.notes" outlined dense label="Notas" />
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat no-caps label="Cancelar" v-close-popup />
          <q-btn
            unelevated
            no-caps
            color="primary"
            label="Crear lote"
            :loading="guardando"
            :disable="!formLote.lot_number.trim()"
            @click="crearLoteNuevo"
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
import { formatDate, formatQty } from 'src/core/format';
import {
  createItem,
  createLot,
  createWarehouse,
  listItems,
  listLots,
  listWarehouses,
  UOM_LABELS,
  WAREHOUSE_TYPE_LABELS,
  type InventoryItem,
  type ItemLot,
  type Warehouse,
} from 'src/features/inventory/inventory.api';
import { useAclStore } from 'src/stores/acl.store';
import { useContextStore } from 'src/stores/context.store';

const $q = useQuasar();
const acl = useAclStore();
const ctx = useContextStore();

const tab = ref('articulos');
const cargando = ref(false);
const guardando = ref(false);

const items = ref<InventoryItem[]>([]);
const bodegas = ref<Warehouse[]>([]);

function puede(code: string): boolean {
  const companyId = ctx.activeCompanyId;
  return companyId ? acl.hasPermission(companyId, code) : false;
}

const opcionesUom = Object.entries(UOM_LABELS).map(([value, label]) => ({ value, label }));
const opcionesTipoBodega = Object.entries(WAREHOUSE_TYPE_LABELS).map(([value, label]) => ({
  value,
  label,
}));

const columnasItem: QTableColumn<InventoryItem>[] = [
  { name: 'sku', label: 'SKU', field: 'sku', align: 'left', sortable: true },
  { name: 'name', label: 'Nombre', field: 'name', align: 'left', sortable: true },
  { name: 'category', label: 'Categoría', field: 'category', align: 'left' },
  { name: 'uom', label: 'Unidad', field: 'uom', align: 'left' },
  {
    name: 'reorder',
    label: 'Reorden',
    field: (r) => formatQty(r.reorder_point),
    align: 'right',
  },
  { name: 'flags', label: 'Controles', field: 'id', align: 'left' },
];

const columnasBodega: QTableColumn<Warehouse>[] = [
  { name: 'name', label: 'Bodega', field: 'name', align: 'left', sortable: true },
  { name: 'code', label: 'Código', field: 'code', align: 'left' },
  { name: 'tipo', label: 'Tipo', field: 'warehouse_type', align: 'left' },
  { name: 'location', label: 'Ubicación', field: 'location_description', align: 'left' },
  { name: 'default', label: 'Defecto', field: 'is_default', align: 'center' },
];

const columnasLote: QTableColumn<ItemLot>[] = [
  { name: 'lot_number', label: 'Lote', field: 'lot_number', align: 'left' },
  { name: 'supplier_lot_ref', label: 'Ref. proveedor', field: 'supplier_lot_ref', align: 'left' },
  { name: 'production', label: 'Producción', field: (r) => formatDate(r.production_date), align: 'left' },
  { name: 'vence', label: 'Vence', field: 'expiry_date', align: 'left' },
  { name: 'status', label: 'Estado', field: 'status', align: 'left' },
  { name: 'qty', label: 'Recibido', field: (r) => formatQty(r.qty_received), align: 'right' },
];

async function recargarTodo() {
  cargando.value = true;
  try {
    [items.value, bodegas.value] = await Promise.all([listItems(), listWarehouses()]);
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo cargar el catálogo.') });
  } finally {
    cargando.value = false;
  }
}

// --- Artículos ---
const dlgItem = ref(false);
const formItem = reactive({
  sku: '',
  name: '',
  category: '',
  uom: 'UNIT',
  reorder_point: '0',
  track_lots: false,
  track_expiry: false,
  is_controlled: false,
});

function abrirCrearItem() {
  Object.assign(formItem, {
    sku: '',
    name: '',
    category: '',
    uom: 'UNIT',
    reorder_point: '0',
    track_lots: false,
    track_expiry: false,
    is_controlled: false,
  });
  dlgItem.value = true;
}

async function crearItemNuevo() {
  guardando.value = true;
  try {
    await createItem({
      sku: formItem.sku.trim(),
      name: formItem.name.trim(),
      category: formItem.category,
      uom: formItem.uom,
      reorder_point: formItem.reorder_point || '0',
      track_lots: formItem.track_lots,
      track_expiry: formItem.track_lots && formItem.track_expiry,
      is_controlled: formItem.is_controlled,
    });
    dlgItem.value = false;
    $q.notify({ type: 'positive', message: `Artículo "${formItem.name.trim()}" creado.` });
    await recargarTodo();
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo crear el artículo.') });
  } finally {
    guardando.value = false;
  }
}

// --- Bodegas ---
const dlgBodega = ref(false);
const formBodega = reactive({
  name: '',
  code: '',
  warehouse_type: 'GENERAL',
  location_description: '',
  is_default: false,
});

async function crearBodegaNueva() {
  guardando.value = true;
  try {
    await createWarehouse({ ...formBodega, name: formBodega.name.trim() });
    dlgBodega.value = false;
    $q.notify({ type: 'positive', message: `Bodega "${formBodega.name.trim()}" creada.` });
    Object.assign(formBodega, {
      name: '',
      code: '',
      warehouse_type: 'GENERAL',
      location_description: '',
      is_default: false,
    });
    await recargarTodo();
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo crear la bodega.') });
  } finally {
    guardando.value = false;
  }
}

// --- Lotes ---
const loteItemId = ref<number | null>(null);
const lotes = ref<ItemLot[]>([]);
const cargandoLotes = ref(false);
const dlgLote = ref(false);
const formLote = reactive({
  lot_number: '',
  supplier_lot_ref: '',
  production_date: '',
  expiry_date: '',
  notes: '',
});

const opcionesItemLotes = computed(() =>
  items.value.filter((i) => i.track_lots).map((i) => ({ value: i.id, label: `${i.sku} — ${i.name}` })),
);

async function cargarLotes() {
  if (loteItemId.value == null) {
    lotes.value = [];
    return;
  }
  cargandoLotes.value = true;
  try {
    lotes.value = await listLots(loteItemId.value);
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudieron cargar los lotes.') });
  } finally {
    cargandoLotes.value = false;
  }
}

async function crearLoteNuevo() {
  if (loteItemId.value == null) return;
  guardando.value = true;
  try {
    await createLot({
      item_id: loteItemId.value,
      lot_number: formLote.lot_number.trim(),
      ...(formLote.supplier_lot_ref ? { supplier_lot_ref: formLote.supplier_lot_ref } : {}),
      ...(formLote.production_date ? { production_date: formLote.production_date } : {}),
      ...(formLote.expiry_date ? { expiry_date: formLote.expiry_date } : {}),
      ...(formLote.notes ? { notes: formLote.notes } : {}),
    });
    dlgLote.value = false;
    $q.notify({ type: 'positive', message: 'Lote creado.' });
    Object.assign(formLote, {
      lot_number: '',
      supplier_lot_ref: '',
      production_date: '',
      expiry_date: '',
      notes: '',
    });
    await cargarLotes();
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo crear el lote.') });
  } finally {
    guardando.value = false;
  }
}

onMounted(recargarTodo);
</script>

<style scoped>
.cat-tabs {
  color: var(--app-text-muted);
}

.cat-panels {
  background: transparent;
}

.cat-lote-sel {
  width: 320px;
}
</style>
