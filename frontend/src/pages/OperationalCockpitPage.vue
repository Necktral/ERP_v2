<template>
  <AppContainer>
    <AppPageHeader
      title="Retail POS · Operational Cockpit"
      subtitle="Monitoreo tactico por sucursal: caja, tickets pendientes y perifericos."
    >
      <template #actions>
        <q-btn outline icon="point_of_sale" label="Terminal POS" :to="routes.retailPosTerminal" />
        <q-btn color="primary" icon="refresh" label="Actualizar" :loading="loading" @click="refreshAll" />
      </template>
    </AppPageHeader>

    <q-banner v-if="!canRead" dense rounded class="q-mt-md">
      No tienes permiso <b>retail.pos.ticket.read</b> o no hay contexto de empresa.
    </q-banner>

    <q-banner v-else-if="error" dense rounded class="q-mt-md bg-red-1 text-red-10">
      {{ error }}
    </q-banner>

    <div v-if="canRead" class="row q-col-gutter-md q-mt-md">
      <div class="col-12 col-md-4">
        <q-card class="app-card">
          <q-card-section>
            <div class="text-subtitle1">Sesion</div>
            <div class="text-h6">{{ cockpit?.session.status ?? 'NONE' }}</div>
            <div class="text-caption text-grey-7">
              Caja: {{ cockpit?.session.cash_session_id ?? '—' }} · Apertura: {{ cockpit?.session.opening_amount ?? '0.00' }}
            </div>
          </q-card-section>
        </q-card>
      </div>

      <div class="col-12 col-md-4">
        <q-card class="app-card">
          <q-card-section>
            <div class="text-subtitle1">Tickets</div>
            <div class="text-caption">Pendientes: {{ cockpit?.tickets.pending ?? 0 }}</div>
            <div class="text-caption">Cerrados: {{ cockpit?.tickets.closed ?? 0 }}</div>
            <div class="text-caption">Anulados: {{ cockpit?.tickets.voided ?? 0 }}</div>
            <div class="text-caption text-orange-8">Comp. pendientes: {{ cockpit?.compensation.pending ?? 0 }}</div>
            <div class="text-caption text-negative">Comp. vencidas: {{ cockpit?.compensation.overdue ?? 0 }}</div>
            <div class="text-caption text-grey-7">
              Max age pending: {{ cockpit?.compensation.max_pending_age_min ?? 0 }} min
            </div>
          </q-card-section>
        </q-card>
      </div>

      <div class="col-12 col-md-4">
        <q-card class="app-card">
          <q-card-section>
            <div class="text-subtitle1">Perifericos</div>
            <div class="text-caption">Total: {{ cockpit?.peripherals.total ?? 0 }}</div>
            <div class="text-caption text-positive">Online: {{ cockpit?.peripherals.online ?? 0 }}</div>
            <div class="text-caption text-orange-8">Degraded: {{ cockpit?.peripherals.degraded ?? 0 }}</div>
            <div class="text-caption text-negative">Offline: {{ cockpit?.peripherals.offline ?? 0 }}</div>
          </q-card-section>
        </q-card>
      </div>
    </div>

    <q-card v-if="canRead" class="app-card q-mt-md">
      <q-card-section class="row items-center justify-between">
        <div>
          <div class="text-subtitle1">Estado de perifericos</div>
          <div class="text-caption text-grey-7">Origen: `GET /api/retail/pos/peripherals/status/`.</div>
        </div>
        <q-badge outline>{{ peripherals.length }} dispositivos</q-badge>
      </q-card-section>
      <q-separator />
      <q-card-section class="q-pa-none">
        <q-markup-table flat dense>
          <thead>
            <tr>
              <th class="text-left">Device</th>
              <th class="text-left">Kind</th>
              <th class="text-left">Status</th>
              <th class="text-left">Capability</th>
              <th class="text-left">Connector</th>
              <th class="text-left">Last seen</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in peripherals" :key="row.id">
              <td>{{ row.device_key }}</td>
              <td>{{ row.device_kind }}</td>
              <td>{{ row.status }}</td>
              <td>{{ row.capability_level }}</td>
              <td>{{ row.connector_id }} {{ row.connector_version }}</td>
              <td>{{ row.last_seen_at }}</td>
            </tr>
            <tr v-if="peripherals.length === 0">
              <td colspan="6" class="text-center text-grey-7 q-pa-md">Sin perifericos reportados.</td>
            </tr>
          </tbody>
        </q-markup-table>
      </q-card-section>
    </q-card>

    <q-card v-if="canManagePeripherals" class="app-card q-mt-md">
      <q-card-section>
        <div class="text-subtitle1">Registrar/actualizar periferico</div>
        <div class="text-caption text-grey-7">Simulador de estado para pruebas operativas.</div>
      </q-card-section>
      <q-separator />
      <q-card-section>
        <div class="row q-col-gutter-sm">
          <div class="col-3">
            <q-input v-model="upsertForm.device_key" outlined dense label="Device key" />
          </div>
          <div class="col-3">
            <q-select
              v-model="upsertForm.device_kind"
              outlined
              dense
              emit-value
              map-options
              label="Kind"
              :options="deviceKindOptions"
            />
          </div>
          <div class="col-2">
            <q-select
              v-model="upsertForm.status"
              outlined
              dense
              emit-value
              map-options
              label="Status"
              :options="statusOptions"
            />
          </div>
          <div class="col-2">
            <q-select
              v-model="upsertForm.capability_level"
              outlined
              dense
              emit-value
              map-options
              label="Capability"
              :options="capabilityOptions"
            />
          </div>
          <div class="col-2">
            <q-input v-model="upsertForm.connector_id" outlined dense label="Connector" />
          </div>
        </div>
      </q-card-section>
      <q-card-actions align="right">
        <q-btn
          color="primary"
          icon="save"
          label="Guardar estado"
          :loading="loading"
          @click="upsertPeripheralAction"
        />
      </q-card-actions>
    </q-card>
  </AppContainer>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import AppContainer from 'src/ui/AppContainer.vue';
import AppPageHeader from 'src/ui/AppPageHeader.vue';
import { UI_ROUTE_PATHS } from 'src/shared/ui/business-terms';
import { useAclStore } from 'src/stores/acl.store';
import { useContextStore } from 'src/stores/context.store';
import {
  getPosCockpit,
  listPosPeripherals,
  type PosCockpit,
  type PosPeripheralRow,
  upsertPosPeripheral,
} from 'src/services/retail-pos.service';

const acl = useAclStore();
const ctx = useContextStore();
const routes = UI_ROUTE_PATHS;

const loading = ref(false);
const error = ref<string | null>(null);
const cockpit = ref<PosCockpit | null>(null);
const peripherals = ref<PosPeripheralRow[]>([]);

const upsertForm = reactive({
  connector_id: 'edge-connector',
  connector_version: '0.1.0',
  device_key: 'printer-01',
  device_kind: 'THERMAL_PRINTER',
  capability_level: 'experimental',
  status: 'ONLINE',
});

const deviceKindOptions = [
  { label: 'Thermal printer', value: 'THERMAL_PRINTER' },
  { label: 'Scanner', value: 'SCANNER' },
  { label: 'Cash drawer', value: 'DRAWER' },
  { label: 'Scale', value: 'SCALE' },
  { label: 'Payment terminal', value: 'PAYMENT_TERMINAL' },
];
const statusOptions = [
  { label: 'ONLINE', value: 'ONLINE' },
  { label: 'DEGRADED', value: 'DEGRADED' },
  { label: 'OFFLINE', value: 'OFFLINE' },
];
const capabilityOptions = [
  { label: 'supported', value: 'supported' },
  { label: 'experimental', value: 'experimental' },
  { label: 'unsupported', value: 'unsupported' },
];

function hasPermission(code: string): boolean {
  const companyId = ctx.activeCompanyId;
  if (!companyId) return false;
  return acl.hasPermission(companyId, code);
}

const canRead = computed(() => hasPermission('retail.pos.ticket.read'));
const canManagePeripherals = computed(() => hasPermission('retail.pos.peripherals.manage'));

function asErrorMessage(cause: unknown): string {
  if (typeof cause === 'object' && cause !== null) {
    const response = (cause as { response?: { data?: { error?: { message?: string } } } }).response;
    const msg = response?.data?.error?.message;
    if (msg) return msg;
  }
  if (cause instanceof Error) return cause.message;
  return String(cause);
}

async function refreshAll() {
  if (!canRead.value) return;
  loading.value = true;
  error.value = null;
  try {
    const [cockpitData, peripheralsData] = await Promise.all([getPosCockpit(), listPosPeripherals()]);
    cockpit.value = cockpitData;
    peripherals.value = peripheralsData.results;
  } catch (cause) {
    error.value = asErrorMessage(cause);
  } finally {
    loading.value = false;
  }
}

async function upsertPeripheralAction() {
  if (!canManagePeripherals.value) return;
  loading.value = true;
  error.value = null;
  try {
    await upsertPosPeripheral({
      connector_id: upsertForm.connector_id,
      connector_version: upsertForm.connector_version,
      device_key: upsertForm.device_key,
      device_kind: upsertForm.device_kind as
        | 'THERMAL_PRINTER'
        | 'SCANNER'
        | 'DRAWER'
        | 'SCALE'
        | 'PAYMENT_TERMINAL',
      capability_level: upsertForm.capability_level as 'supported' | 'experimental' | 'unsupported',
      status: upsertForm.status as 'ONLINE' | 'DEGRADED' | 'OFFLINE',
      metadata: { source: 'frontend-pos-cockpit' },
    });
    await refreshAll();
  } catch (cause) {
    error.value = asErrorMessage(cause);
  } finally {
    loading.value = false;
  }
}

onMounted(() => {
  void refreshAll();
});
</script>
