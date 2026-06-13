<template>
  <q-page class="app-page">
    <PageHeader
      title="Costos de flota"
      subtitle="Combustible, mantenimiento y gastos por vehículo, con costo por km/hora y rendimiento."
      :loading="cargando"
      @refresh="recargar"
    />

    <div class="cf-pick">
      <q-select
        v-model="assetId"
        :options="assetOpts"
        outlined dense emit-value map-options label="Vehículo / activo"
        class="cf-select"
        @update:model-value="cargarActivo"
      />
    </div>

    <template v-if="assetId">
      <div v-if="resumen" class="cf-stats">
        <div class="cf-stat"><div class="cf-stat__v">C$ {{ fmt(resumen.grand_total) }}</div><div class="cf-stat__l">Costo total</div></div>
        <div class="cf-stat"><div class="cf-stat__v">C$ {{ fmt(resumen.fuel_total) }}</div><div class="cf-stat__l">Combustible</div></div>
        <div class="cf-stat"><div class="cf-stat__v">C$ {{ fmt(resumen.maintenance_total) }}</div><div class="cf-stat__l">Mantenimiento</div></div>
        <div class="cf-stat"><div class="cf-stat__v">C$ {{ fmt(resumen.expense_total) }}</div><div class="cf-stat__l">Otros gastos</div></div>
        <div class="cf-stat cf-stat--accent">
          <div class="cf-stat__v">{{ resumen.cost_per_unit ? 'C$ ' + fmt(resumen.cost_per_unit) : '—' }}</div>
          <div class="cf-stat__l">{{ resumen.cost_per_unit_label }}</div>
        </div>
        <div class="cf-stat cf-stat--accent">
          <div class="cf-stat__v">{{ resumen.consumption ?? '—' }}</div>
          <div class="cf-stat__l">{{ resumen.consumption_label }}</div>
        </div>
      </div>

      <q-tabs v-model="tab" no-caps align="left" class="cf-tabs">
        <q-tab name="fuel" label="Combustible" />
        <q-tab name="maint" label="Mantenimiento" />
        <q-tab name="exp" label="Otros gastos" />
      </q-tabs>

      <div class="cf-actions" v-if="puede('fleet.cost.manage')">
        <q-btn v-if="tab === 'fuel'" unelevated no-caps color="primary" icon="local_gas_station" label="Registrar carga" @click="dlgFuel = true" />
        <q-btn v-if="tab === 'maint'" unelevated no-caps color="primary" icon="build" label="Registrar mantenimiento" @click="dlgMaint = true" />
        <q-btn v-if="tab === 'exp'" unelevated no-caps color="primary" icon="receipt_long" label="Registrar gasto" @click="dlgExp = true" />
      </div>

      <q-table v-if="tab === 'fuel'" class="app-table" flat :rows="fuelLogs" :columns="fuelCols" row-key="id" :pagination="{ rowsPerPage: 25 }" no-data-label="Sin cargas de combustible." />
      <q-table v-if="tab === 'maint'" class="app-table" flat :rows="maintOrders" :columns="maintCols" row-key="id" :pagination="{ rowsPerPage: 25 }" no-data-label="Sin órdenes de mantenimiento." />
      <q-table v-if="tab === 'exp'" class="app-table" flat :rows="expenses" :columns="expCols" row-key="id" :pagination="{ rowsPerPage: 25 }" no-data-label="Sin gastos." />
    </template>

    <!-- Combustible -->
    <q-dialog v-model="dlgFuel">
      <q-card class="app-dialog">
        <q-card-section class="text-h6">Registrar carga de combustible</q-card-section>
        <q-card-section class="app-form">
          <q-input v-model="formFuel.liters" outlined dense type="number" label="Litros *" />
          <q-input v-model="formFuel.unit_cost" outlined dense type="number" label="Costo por litro *" />
          <q-input v-model="formFuel.meter_reading" outlined dense type="number" label="Lectura odómetro/horómetro" />
          <q-input v-model="formFuel.station_ref" outlined dense label="Estación / referencia" />
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat no-caps label="Cancelar" v-close-popup />
          <q-btn unelevated no-caps color="primary" label="Guardar" :loading="accionando" :disable="!formFuel.liters || !formFuel.unit_cost" @click="guardarFuel" />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <!-- Mantenimiento -->
    <q-dialog v-model="dlgMaint">
      <q-card class="app-dialog">
        <q-card-section class="text-h6">Registrar mantenimiento</q-card-section>
        <q-card-section class="app-form">
          <q-input v-model="formMaint.description" outlined dense label="Descripción *" />
          <q-input v-model="formMaint.labor_cost" outlined dense type="number" label="Mano de obra (C$)" />
          <q-input v-model="formMaint.parts_cost" outlined dense type="number" label="Repuestos (C$)" />
          <q-input v-model="formMaint.vendor" outlined dense label="Taller / proveedor" />
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat no-caps label="Cancelar" v-close-popup />
          <q-btn unelevated no-caps color="primary" label="Guardar" :loading="accionando" :disable="!formMaint.description.trim()" @click="guardarMaint" />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <!-- Gasto -->
    <q-dialog v-model="dlgExp">
      <q-card class="app-dialog">
        <q-card-section class="text-h6">Registrar gasto</q-card-section>
        <q-card-section class="app-form">
          <q-select v-model="formExp.category" :options="catOpts" outlined dense emit-value map-options label="Categoría *" />
          <q-input v-model="formExp.amount" outlined dense type="number" label="Monto (C$) *" />
          <q-input v-model="formExp.vendor" outlined dense label="Proveedor" />
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat no-caps label="Cancelar" v-close-popup />
          <q-btn unelevated no-caps color="primary" label="Guardar" :loading="accionando" :disable="!formExp.category || !formExp.amount" @click="guardarExp" />
        </q-card-actions>
      </q-card>
    </q-dialog>
  </q-page>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue';
import { useQuasar, type QTableColumn } from 'quasar';
import PageHeader from 'src/components/PageHeader.vue';
import { apiErrorMessage } from 'src/core/api';
import {
  FLEET_EXPENSE_CATEGORIES,
  createFleetExpense,
  createFuelLog,
  createMaintenanceOrder,
  getAssetCostSummary,
  listAssets,
  listFleetExpenses,
  listFuelLogs,
  listMaintenanceOrders,
  type AssetCostSummary,
  type FleetExpenseRow,
  type FuelLogRow,
  type MaintenanceOrderRow,
} from 'src/features/fleet/fleet.api';
import { useAclStore } from 'src/stores/acl.store';
import { useContextStore } from 'src/stores/context.store';

const $q = useQuasar();
const acl = useAclStore();
const ctx = useContextStore();

const cargando = ref(false);
const accionando = ref(false);
const assetOpts = ref<Array<{ value: number; label: string }>>([]);
const assetId = ref<number | null>(null);
const tab = ref<'fuel' | 'maint' | 'exp'>('fuel');
const catOpts = FLEET_EXPENSE_CATEGORIES;

const resumen = ref<AssetCostSummary | null>(null);
const fuelLogs = ref<FuelLogRow[]>([]);
const maintOrders = ref<MaintenanceOrderRow[]>([]);
const expenses = ref<FleetExpenseRow[]>([]);

function puede(code: string): boolean {
  const companyId = ctx.activeCompanyId;
  return companyId ? acl.hasPermission(companyId, code) : false;
}
function fmt(v: string): string {
  return Number(v).toLocaleString('es-NI', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

const fuelCols: QTableColumn<FuelLogRow>[] = [
  { name: 'occurred_at', label: 'Fecha', field: (r) => new Date(r.occurred_at).toLocaleDateString('es-NI'), align: 'left' },
  { name: 'liters', label: 'Litros', field: 'liters', align: 'right' },
  { name: 'unit_cost', label: 'C$/L', field: 'unit_cost', align: 'right' },
  { name: 'total_cost', label: 'Total', field: 'total_cost', align: 'right' },
  { name: 'distance', label: 'Recorrido', field: (r) => r.distance_since_last ?? '—', align: 'right' },
  { name: 'station', label: 'Estación', field: 'station_ref', align: 'left' },
];
const maintCols: QTableColumn<MaintenanceOrderRow>[] = [
  { name: 'opened_at', label: 'Fecha', field: (r) => new Date(r.opened_at).toLocaleDateString('es-NI'), align: 'left' },
  { name: 'description', label: 'Descripción', field: 'description', align: 'left' },
  { name: 'labor', label: 'M. obra', field: 'labor_cost', align: 'right' },
  { name: 'parts', label: 'Repuestos', field: 'parts_cost', align: 'right' },
  { name: 'total', label: 'Total', field: 'total_cost', align: 'right' },
  { name: 'vendor', label: 'Taller', field: 'vendor', align: 'left' },
];
const expCols: QTableColumn<FleetExpenseRow>[] = [
  { name: 'occurred_on', label: 'Fecha', field: 'occurred_on', align: 'left' },
  { name: 'category', label: 'Categoría', field: 'category_label', align: 'left' },
  { name: 'amount', label: 'Monto', field: 'amount', align: 'right' },
  { name: 'vendor', label: 'Proveedor', field: 'vendor', align: 'left' },
];

async function recargar() {
  cargando.value = true;
  try {
    const assets = await listAssets();
    assetOpts.value = assets.map((a) => ({ value: a.id, label: `${a.code} — ${a.name}` }));
    if (!assetId.value && assetOpts.value.length) {
      assetId.value = assetOpts.value[0]!.value;
    }
    if (assetId.value) await cargarActivo();
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudieron cargar los activos.') });
  } finally {
    cargando.value = false;
  }
}

async function cargarActivo() {
  if (!assetId.value) return;
  try {
    [resumen.value, fuelLogs.value, maintOrders.value, expenses.value] = await Promise.all([
      getAssetCostSummary(assetId.value),
      listFuelLogs(assetId.value),
      listMaintenanceOrders(assetId.value),
      listFleetExpenses(assetId.value),
    ]);
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo cargar el activo.') });
  }
}

const dlgFuel = ref(false);
const formFuel = reactive({ liters: '', unit_cost: '', meter_reading: '', station_ref: '' });
async function guardarFuel() {
  if (!assetId.value) return;
  accionando.value = true;
  try {
    await createFuelLog(assetId.value, {
      liters: formFuel.liters,
      unit_cost: formFuel.unit_cost,
      meter_reading: formFuel.meter_reading || null,
      station_ref: formFuel.station_ref,
    });
    $q.notify({ type: 'positive', message: 'Carga registrada.' });
    dlgFuel.value = false;
    Object.assign(formFuel, { liters: '', unit_cost: '', meter_reading: '', station_ref: '' });
    await cargarActivo();
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo registrar.') });
  } finally {
    accionando.value = false;
  }
}

const dlgMaint = ref(false);
const formMaint = reactive({ description: '', labor_cost: '', parts_cost: '', vendor: '' });
async function guardarMaint() {
  if (!assetId.value) return;
  accionando.value = true;
  try {
    await createMaintenanceOrder(assetId.value, {
      description: formMaint.description.trim(),
      labor_cost: formMaint.labor_cost || '0',
      parts_cost: formMaint.parts_cost || '0',
      vendor: formMaint.vendor,
    });
    $q.notify({ type: 'positive', message: 'Mantenimiento registrado.' });
    dlgMaint.value = false;
    Object.assign(formMaint, { description: '', labor_cost: '', parts_cost: '', vendor: '' });
    await cargarActivo();
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo registrar.') });
  } finally {
    accionando.value = false;
  }
}

const dlgExp = ref(false);
const formExp = reactive({ category: 'OTHER', amount: '', vendor: '' });
async function guardarExp() {
  if (!assetId.value) return;
  accionando.value = true;
  try {
    await createFleetExpense(assetId.value, { category: formExp.category, amount: formExp.amount, vendor: formExp.vendor });
    $q.notify({ type: 'positive', message: 'Gasto registrado.' });
    dlgExp.value = false;
    Object.assign(formExp, { category: 'OTHER', amount: '', vendor: '' });
    await cargarActivo();
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo registrar.') });
  } finally {
    accionando.value = false;
  }
}

onMounted(recargar);
</script>

<style scoped>
.cf-pick {
  margin-bottom: var(--app-space-4);
}
.cf-select {
  max-width: 420px;
}
.cf-stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: var(--app-space-3);
  margin-bottom: var(--app-space-4);
}
.cf-stat {
  padding: var(--app-space-4);
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-md);
  background: var(--app-surface);
}
.cf-stat--accent {
  border-color: var(--app-primary);
}
.cf-stat__v {
  font-size: 1.3rem;
  font-weight: 800;
  color: var(--app-text);
}
.cf-stat__l {
  font-size: 0.78rem;
  color: var(--app-text-muted);
}
.cf-tabs {
  margin-bottom: var(--app-space-2);
}
.cf-actions {
  margin-bottom: var(--app-space-3);
}
</style>
