<template>
  <AppContainer>
    <AppPageHeader :title="`${labels.synchronization} · Dispositivos`" subtitle="API: GET /sync/devices/ · POST /sync/devices/{id}/revoke/">
      <template #actions>
        <q-btn outline label="Recargar" :loading="loading" @click="load" />
      </template>
    </AppPageHeader>

    <q-banner v-if="!canManage" dense rounded class="q-mt-md">
      No tienes permiso <b>sync.device.revoke</b> o no hay contexto activo.
    </q-banner>

    <q-card v-else class="app-card q-mt-md">
      <q-card-section class="row q-col-gutter-sm">
        <div class="col-12 col-md-4">
          <q-input v-model="filters.q" outlined dense clearable label="Buscar por etiqueta o UUID" />
        </div>
        <div class="col-12 col-md-3">
          <q-select
            v-model="filters.status"
            outlined
            dense
            emit-value
            map-options
            clearable
            label="Estado"
            :options="statusOptions"
          />
        </div>
        <div class="col-12 col-md-2">
          <q-input v-model.number="limit" type="number" min="1" max="200" outlined dense label="Limite" />
        </div>
        <div class="col-12 col-md-3">
          <div class="row justify-end q-gutter-sm">
            <q-btn outline label="Filtrar" :loading="loading" @click="onFilter" />
            <q-btn flat label="Limpiar" :disable="loading" @click="onReset" />
          </div>
        </div>
      </q-card-section>

      <q-banner v-if="errorMsg" dense rounded class="q-mx-md q-mb-md bg-red-1 text-red-10">
        {{ errorMsg }}
      </q-banner>

      <q-table
        row-key="id"
        flat
        :rows="rows"
        :columns="columns"
        :loading="loading"
        :pagination="{ rowsPerPage: limit, page: currentPage }"
      >
        <template #body-cell-status="props">
          <q-td :props="props">
            <q-badge :color="statusColor(props.row.status)" outline>
              {{ props.row.status }}
            </q-badge>
          </q-td>
        </template>
        <template #body-cell-actions="props">
          <q-td :props="props" class="text-right">
            <q-btn
              v-if="props.row.status !== 'REVOKED'"
              dense
              flat
              color="negative"
              label="Revocar"
              :loading="revokingId === props.row.id"
              @click="onRevoke(props.row)"
            />
          </q-td>
        </template>
      </q-table>

      <q-separator />

      <q-card-actions align="between">
        <div class="text-caption text-grey-7">Total: {{ total }}</div>
        <div class="row items-center q-gutter-sm">
          <q-btn flat label="Anterior" :disable="offset <= 0 || loading" @click="previousPage" />
          <q-btn flat label="Siguiente" :disable="offset + limit >= total || loading" @click="nextPage" />
        </div>
      </q-card-actions>
    </q-card>
  </AppContainer>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';

import AppContainer from 'src/ui/AppContainer.vue';
import AppPageHeader from 'src/ui/AppPageHeader.vue';
import { useQuasar } from 'quasar';
import { extractErrorMessage } from 'src/core/http/errors';
import { BUSINESS_LABELS } from 'src/shared/ui/business-terms';
import { useAclStore } from 'src/stores/acl.store';
import { useContextStore } from 'src/stores/context.store';
import { listSyncDevices, revokeSyncDevice, type DeviceRow } from 'src/services/sync.service';

const $q = useQuasar();
const labels = BUSINESS_LABELS;
const acl = useAclStore();
const ctx = useContextStore();

const canManage = computed(() => {
  const companyId = ctx.activeCompanyId;
  if (!companyId) return false;
  return acl.hasPermission(companyId, 'sync.device.revoke');
});

const loading = ref(false);
const errorMsg = ref<string | null>(null);
const rows = ref<DeviceRow[]>([]);
const total = ref(0);
const limit = ref(25);
const offset = ref(0);
const revokingId = ref('');

const filters = reactive<{ q: string; status: '' | 'ACTIVE' | 'REVOKED' | 'QUARANTINED' }>({
  q: '',
  status: '',
});

const statusOptions = [
  { label: 'Activo', value: 'ACTIVE' },
  { label: 'Revocado', value: 'REVOKED' },
  { label: 'Cuarentena', value: 'QUARANTINED' },
];

const currentPage = computed(() => Math.floor(offset.value / limit.value) + 1);

const columns = [
  { name: 'id', label: 'ID', field: 'id', align: 'left' as const },
  { name: 'label', label: 'Etiqueta', field: 'label', align: 'left' as const },
  { name: 'status', label: 'Estado', field: 'status', align: 'left' as const },
  { name: 'branch_id', label: 'Sucursal', field: 'branch_id', align: 'left' as const },
  { name: 'last_seen_at', label: 'Ultima actividad', field: 'last_seen_at', align: 'left' as const },
  { name: 'actions', label: '', field: 'actions', align: 'right' as const },
];

function statusColor(status: string): string {
  if (status === 'ACTIVE') return 'positive';
  if (status === 'REVOKED') return 'negative';
  return 'warning';
}

async function load() {
  if (!canManage.value) return;
  loading.value = true;
  errorMsg.value = null;
  try {
    const params: { q?: string; status?: string; limit: number; offset: number } = {
      limit: limit.value,
      offset: offset.value,
    };
    if (filters.q) params.q = filters.q;
    if (filters.status) params.status = filters.status;
    const data = await listSyncDevices({
      ...params,
    });
    rows.value = data.results;
    total.value = data.count;
  } catch (e) {
    errorMsg.value = extractErrorMessage(e);
  } finally {
    loading.value = false;
  }
}

function onFilter() {
  offset.value = 0;
  void load();
}

function onReset() {
  filters.q = '';
  filters.status = '';
  limit.value = 25;
  offset.value = 0;
  void load();
}

function previousPage() {
  offset.value = Math.max(0, offset.value - limit.value);
  void load();
}

function nextPage() {
  offset.value += limit.value;
  void load();
}

async function onRevoke(row: DeviceRow) {
  revokingId.value = row.id;
  try {
    await revokeSyncDevice(row.id);
    $q.notify({ type: 'positive', message: `Dispositivo ${row.id} revocado.` });
    await load();
  } catch (e) {
    $q.notify({ type: 'negative', message: extractErrorMessage(e) });
  } finally {
    revokingId.value = '';
  }
}

onMounted(() => {
  void load();
});
</script>
