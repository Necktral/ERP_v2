<template>
  <q-page class="app-page">
    <PageHeader
      title="Órdenes de trabajo"
      subtitle="Qué labor se hace en qué lote: planificada → en ejecución → terminada, con jornales e insumos (manuales o desde bodega)."
      :loading="loading"
      @refresh="reload"
    >
      <template #actions>
        <q-btn flat round dense icon="arrow_back" aria-label="Volver" to="/finca" />
        <q-btn
          v-if="puede('finca.work.capture')"
          unelevated
          no-caps
          color="primary"
          icon="add_task"
          label="Nueva orden"
          @click="abrirCrear"
        />
      </template>
    </PageHeader>

    <div class="ord-filtros">
      <q-select
        v-model="filtroEstado"
        :options="opcionesEstado"
        dense
        outlined
        emit-value
        map-options
        clearable
        label="Estado"
        class="ord-filtros__sel"
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
      no-data-label="Sin órdenes de trabajo."
    >
      <template #body-cell-lote="props">
        <q-td :props="props">{{ nombreLote(props.row.plot) }}</q-td>
      </template>
      <template #body-cell-labor="props">
        <q-td :props="props">{{ nombreLabor(props.row.labor) }}</q-td>
      </template>
      <template #body-cell-estado="props">
        <q-td :props="props">
          {{ WORK_ORDER_STATUS_LABELS[props.row.status] ?? props.row.status }}
        </q-td>
      </template>
      <template #body-cell-acciones="props">
        <q-td :props="props" class="text-right ord-acciones">
          <template v-if="puede('finca.work.capture')">
            <q-btn
              v-if="props.row.status === 'PLANNED'"
              flat
              dense
              no-caps
              size="sm"
              label="Iniciar"
              @click="cambiarEstado(props.row, 'IN_PROGRESS')"
            />
            <q-btn
              v-if="props.row.status === 'IN_PROGRESS'"
              flat
              dense
              no-caps
              size="sm"
              color="primary"
              label="Terminar"
              @click="terminar(props.row)"
            />
            <q-btn
              v-if="props.row.status !== 'CANCELLED' && props.row.status !== 'DONE'"
              flat
              dense
              no-caps
              size="sm"
              icon="science"
              label="Insumos"
              @click="abrirInsumo(props.row)"
            />
          </template>
        </q-td>
      </template>
    </q-table>

    <!-- Diálogo: nueva orden -->
    <q-dialog v-model="dlgCrear">
      <q-card class="app-dialog">
        <q-card-section class="text-h6">Nueva orden de trabajo</q-card-section>
        <q-card-section class="app-form">
          <q-select
            v-model="form.plot_id"
            :options="opcionesLote"
            label="Lote *"
            outlined
            dense
            emit-value
            map-options
          />
          <q-select
            v-model="form.labor_id"
            :options="opcionesLabor"
            label="Labor *"
            outlined
            dense
            emit-value
            map-options
          />
          <q-input v-model="form.season_label" outlined dense label="Temporada (ej. 2026-2027)" />
          <q-input v-model="form.planned_date" outlined dense type="date" label="Fecha planificada" />
          <q-input v-model="form.target_quantity" outlined dense type="number" min="0" label="Meta (en la unidad de la labor)" />
          <q-input v-model="form.notes" outlined dense label="Notas" />
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat no-caps label="Cancelar" v-close-popup />
          <q-btn
            unelevated
            no-caps
            color="primary"
            label="Crear orden"
            :loading="accionando"
            :disable="form.plot_id == null || form.labor_id == null"
            @click="crear"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <!-- Diálogo: insumos -->
    <q-dialog v-model="dlgInsumo">
      <q-card class="app-dialog">
        <q-card-section class="text-h6">Insumos de la orden #{{ ordenInsumo?.id }}</q-card-section>
        <q-card-section class="app-form">
          <q-btn-toggle
            v-model="modoInsumo"
            no-caps
            unelevated
            :options="[
              { label: 'Desde bodega (descuenta stock)', value: 'STOCK' },
              { label: 'Manual (sin inventario)', value: 'MANUAL' },
            ]"
          />
          <template v-if="modoInsumo === 'STOCK'">
            <q-select
              v-model="formInsumo.warehouse_id"
              :options="opcionesBodega"
              label="Bodega *"
              outlined
              dense
              emit-value
              map-options
            />
            <q-select
              v-model="formInsumo.item_id"
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
          </template>
          <template v-else>
            <q-input v-model="formInsumo.item_name" outlined dense label="Insumo *" />
            <q-input v-model="formInsumo.unit" outlined dense label="Unidad (ej. litro, kg)" />
            <q-input v-model="formInsumo.unit_cost" outlined dense type="number" min="0" label="Costo unitario C$" />
          </template>
          <q-input v-model="formInsumo.quantity" outlined dense type="number" min="0" label="Cantidad *" />
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat no-caps label="Cerrar" v-close-popup />
          <q-btn
            unelevated
            no-caps
            color="primary"
            label="Aplicar insumo"
            :loading="accionando"
            :disable="!insumoValido"
            @click="aplicarInsumo"
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
import { formatDate, formatQty } from 'src/core/format';
import {
  addInsumoManual,
  createWorkOrder,
  issueInsumoFromStock,
  listLabors,
  listPlots,
  listWorkOrders,
  updateWorkOrder,
  WORK_ORDER_STATUS_LABELS,
  type Labor,
  type Plot,
  type WorkOrder,
} from 'src/features/finca/finca.api';
import {
  listItems,
  listWarehouses,
  type InventoryItem,
  type Warehouse,
} from 'src/features/inventory/inventory.api';
import { useAclStore } from 'src/stores/acl.store';
import { useContextStore } from 'src/stores/context.store';

const $q = useQuasar();
const acl = useAclStore();
const ctx = useContextStore();

const filtroEstado = ref<string | null>(null);

const { rows, loading, reload } = useListado<WorkOrder>(
  () => listWorkOrders({ ...(filtroEstado.value ? { status: filtroEstado.value } : {}) }),
  { errorMessage: 'No se pudieron cargar las órdenes.' },
);

const lotes = ref<Plot[]>([]);
const labores = ref<Labor[]>([]);
const bodegas = ref<Warehouse[]>([]);
const items = ref<InventoryItem[]>([]);
const accionando = ref(false);

function puede(code: string): boolean {
  const companyId = ctx.activeCompanyId;
  return companyId ? acl.hasPermission(companyId, code) : false;
}

function nombreLote(id: number): string {
  const l = lotes.value.find((x) => x.id === id);
  return l ? `${l.code}${l.name ? ` — ${l.name}` : ''}` : `Lote #${id}`;
}

function nombreLabor(id: number): string {
  return labores.value.find((x) => x.id === id)?.name ?? `Labor #${id}`;
}

const opcionesEstado = Object.entries(WORK_ORDER_STATUS_LABELS).map(([value, label]) => ({ value, label }));
const opcionesLote = computed(() =>
  lotes.value.filter((l) => l.is_active).map((l) => ({ value: l.id, label: `${l.code} — ${l.name || l.crop}` })),
);
const opcionesLabor = computed(() =>
  labores.value.filter((l) => l.is_active).map((l) => ({ value: l.id, label: l.name })),
);
const opcionesBodega = computed(() => bodegas.value.map((w) => ({ value: w.id, label: w.name })));
const opcionesItem = computed(() => items.value.map((i) => ({ value: i.id, label: `${i.sku} — ${i.name}` })));
const opcionesItemFiltradas = ref<{ value: number; label: string }[]>([]);

function filtrarItems(input: string, update: (fn: () => void) => void) {
  update(() => {
    const q = input.trim().toLowerCase();
    opcionesItemFiltradas.value = q
      ? opcionesItem.value.filter((o) => o.label.toLowerCase().includes(q))
      : opcionesItem.value;
  });
}

const columns: QTableColumn<WorkOrder>[] = [
  { name: 'id', label: '#', field: 'id', align: 'left' },
  { name: 'lote', label: 'Lote', field: 'plot', align: 'left' },
  { name: 'labor', label: 'Labor', field: 'labor', align: 'left' },
  { name: 'fecha', label: 'Planificada', field: (r) => formatDate(r.planned_date), align: 'left' },
  { name: 'meta', label: 'Meta', field: (r) => (r.target_quantity ? formatQty(r.target_quantity) : '—'), align: 'right' },
  { name: 'jornales', label: 'Jornales', field: (r) => formatQty(r.jornales), align: 'right' },
  { name: 'estado', label: 'Estado', field: 'status', align: 'left' },
  { name: 'acciones', label: '', field: 'id', align: 'right' },
];

// --- Crear ---
const dlgCrear = ref(false);
const form = reactive<{
  plot_id: number | null;
  labor_id: number | null;
  season_label: string;
  planned_date: string;
  target_quantity: string;
  notes: string;
}>({ plot_id: null, labor_id: null, season_label: '', planned_date: '', target_quantity: '', notes: '' });

function abrirCrear() {
  Object.assign(form, {
    plot_id: null,
    labor_id: null,
    season_label: '',
    planned_date: new Date().toISOString().slice(0, 10),
    target_quantity: '',
    notes: '',
  });
  dlgCrear.value = true;
}

async function crear() {
  if (form.plot_id == null || form.labor_id == null) return;
  accionando.value = true;
  try {
    await createWorkOrder({
      plot_id: form.plot_id,
      labor_id: form.labor_id,
      ...(form.season_label ? { season_label: form.season_label } : {}),
      ...(form.planned_date ? { planned_date: form.planned_date } : {}),
      ...(form.target_quantity ? { target_quantity: Number(form.target_quantity).toFixed(2) } : {}),
      ...(form.notes ? { notes: form.notes } : {}),
    });
    dlgCrear.value = false;
    $q.notify({ type: 'positive', message: 'Orden creada.' });
    await reload();
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo crear la orden.') });
  } finally {
    accionando.value = false;
  }
}

async function cambiarEstado(wo: WorkOrder, estado: string) {
  try {
    await updateWorkOrder(wo.id, { status: estado });
    $q.notify({ type: 'positive', message: 'Estado actualizado.' });
    await reload();
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo actualizar.') });
  }
}

function terminar(wo: WorkOrder) {
  $q.dialog({
    title: 'Terminar orden',
    message: 'Cantidad real ejecutada (en la unidad de la labor):',
    prompt: { model: wo.target_quantity ?? '0', type: 'number', isValid: (v) => Number(v) >= 0 },
    cancel: { flat: true, noCaps: true, label: 'Cancelar' },
    ok: { unelevated: true, noCaps: true, color: 'primary', label: 'Terminar' },
  }).onOk((cantidad: string) => {
    void (async () => {
      try {
        await updateWorkOrder(wo.id, {
          status: 'DONE',
          done_date: new Date().toISOString().slice(0, 10),
          actual_quantity: Number(cantidad).toFixed(2),
        });
        $q.notify({ type: 'positive', message: 'Orden terminada.' });
        await reload();
      } catch (e) {
        $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo terminar.') });
      }
    })();
  });
}

// --- Insumos ---
const dlgInsumo = ref(false);
const ordenInsumo = ref<WorkOrder | null>(null);
const modoInsumo = ref<'STOCK' | 'MANUAL'>('STOCK');
const formInsumo = reactive<{
  warehouse_id: number | null;
  item_id: number | null;
  item_name: string;
  unit: string;
  unit_cost: string;
  quantity: string;
}>({ warehouse_id: null, item_id: null, item_name: '', unit: '', unit_cost: '', quantity: '' });

const insumoValido = computed(() => {
  if (!formInsumo.quantity || Number(formInsumo.quantity) <= 0) return false;
  if (modoInsumo.value === 'STOCK') return formInsumo.warehouse_id != null && formInsumo.item_id != null;
  return formInsumo.item_name.trim().length > 0;
});

async function abrirInsumo(wo: WorkOrder) {
  ordenInsumo.value = wo;
  modoInsumo.value = 'STOCK';
  Object.assign(formInsumo, {
    warehouse_id: null,
    item_id: null,
    item_name: '',
    unit: '',
    unit_cost: '',
    quantity: '',
  });
  if (bodegas.value.length === 0) {
    try {
      [bodegas.value, items.value] = await Promise.all([listWarehouses(), listItems({ is_active: true })]);
      opcionesItemFiltradas.value = opcionesItem.value;
    } catch {
      /* modo manual sigue disponible */
    }
  }
  dlgInsumo.value = true;
}

async function aplicarInsumo() {
  if (!ordenInsumo.value || !insumoValido.value) return;
  accionando.value = true;
  try {
    if (modoInsumo.value === 'STOCK') {
      await issueInsumoFromStock(ordenInsumo.value.id, {
        warehouse_id: formInsumo.warehouse_id!,
        item_id: formInsumo.item_id!,
        quantity: Number(formInsumo.quantity).toFixed(2),
      });
      $q.notify({ type: 'positive', message: 'Insumo descontado de bodega y aplicado.' });
    } else {
      await addInsumoManual(ordenInsumo.value.id, {
        item_name: formInsumo.item_name.trim(),
        quantity: Number(formInsumo.quantity).toFixed(2),
        ...(formInsumo.unit ? { unit: formInsumo.unit } : {}),
        ...(formInsumo.unit_cost ? { unit_cost: Number(formInsumo.unit_cost).toFixed(2) } : {}),
      });
      $q.notify({ type: 'positive', message: 'Insumo manual registrado.' });
    }
    dlgInsumo.value = false;
    await reload();
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo aplicar el insumo.') });
  } finally {
    accionando.value = false;
  }
}

onMounted(async () => {
  try {
    [lotes.value, labores.value] = await Promise.all([listPlots(), listLabors()]);
  } catch {
    /* nombres opcionales */
  }
});
</script>

<style scoped>
.ord-filtros {
  margin-bottom: var(--app-space-4);
}

.ord-filtros__sel {
  width: 220px;
}

.ord-acciones {
  white-space: nowrap;
}
</style>
