<template>
  <AppContainer fluid>
    <AppPageHeader
      title="Auditoría · Bitácora"
      subtitle="GET /audit/bitacora/ · GET /audit/events/{event_id}/"
    >
      <template #badges>
        <q-badge outline color="primary">Company: {{ companyLabel }}</q-badge>
        <q-badge outline>Read: audit.read</q-badge>
      </template>

      <template #actions>
        <q-btn flat label="Limpiar" :disable="loading" @click="clearFilters" />
        <q-btn flat label="Recargar" :disable="loading" @click="load()" />
      </template>
    </AppPageHeader>

    <div class="q-mt-md">
      <q-card class="app-card">
        <q-card-section>
          <div class="row q-col-gutter-sm">
            <div class="col-12 col-md-3">
              <q-input v-model="filters.event_type" dense outlined label="event_type" />
            </div>
            <div class="col-12 col-md-3">
              <q-input v-model="filters.reason_code" dense outlined label="reason_code" />
            </div>
            <div class="col-12 col-md-3">
              <q-input v-model="filters.module" dense outlined label="module" />
            </div>
            <div class="col-12 col-md-3">
              <q-input
                v-model="filters.method"
                dense
                outlined
                label="method"
                placeholder="GET/POST/PATCH…"
              />
            </div>
          </div>

          <div class="row q-col-gutter-sm q-mt-xs">
            <div class="col-12 col-md-3">
              <q-input v-model="filters.actor_user_id" dense outlined label="actor_user_id" />
            </div>
            <div class="col-12 col-md-3">
              <q-input v-model="filters.subject_type" dense outlined label="subject_type" />
            </div>
            <div class="col-12 col-md-3">
              <q-input v-model="filters.subject_id" dense outlined label="subject_id" />
            </div>
            <div class="col-12 col-md-3">
              <q-select
                v-model="filters.offline_mode"
                dense
                outlined
                label="offline_mode"
                emit-value
                map-options
                :options="offlineOptions"
              />
            </div>
          </div>

          <div class="row q-col-gutter-sm q-mt-xs">
            <div class="col-12 col-md-4">
              <q-input v-model="filters.path_contains" dense outlined label="path contiene" />
            </div>
            <div class="col-12 col-md-2">
              <q-input v-model="filters.ip" dense outlined label="ip" />
            </div>
            <div class="col-12 col-md-2">
              <q-input v-model="filters.device_id" dense outlined label="device_id" />
            </div>
            <div class="col-12 col-md-2">
              <q-input
                v-model="filters.after"
                dense
                outlined
                label="after"
                placeholder="YYYY-MM-DD"
              />
            </div>
            <div class="col-12 col-md-2">
              <q-input
                v-model="filters.before"
                dense
                outlined
                label="before"
                placeholder="YYYY-MM-DD"
              />
            </div>
          </div>

          <div class="row items-center q-gutter-sm q-mt-sm">
            <q-btn color="primary" label="Buscar" :loading="loading" @click="load()" />

            <q-btn outline label="Anterior" :disable="loading || !page?.previous" @click="goPrev" />
            <q-btn outline label="Siguiente" :disable="loading || !page?.next" @click="goNext" />

            <q-space />

            <q-toggle v-model="filters.include_integrity" label="include_integrity" />
          </div>

          <q-banner v-if="errorMsg" class="q-mt-sm" dense rounded>
            {{ errorMsg }}
          </q-banner>
        </q-card-section>
      </q-card>

      <div class="q-mt-md">
        <AppDataTable
          title="Eventos"
          caption="Paginación por cursor: usa Anterior/Siguiente. Usa la lupa para ver detalle."
          :rows="rows"
          :columns="columns"
          row-key="event_id"
          :loading="loading"
          :rows-per-page-options="[0]"
        >
          <template #body-cell-actions="props">
            <q-td :props="props" class="text-right">
              <q-btn dense flat icon="search" @click.stop="openDetail(props.row)" />
            </q-td>
          </template>

          <template #body-cell-offline_mode="props">
            <q-td :props="props">
              <q-badge v-if="props.row.offline_mode" outline color="warning">OFFLINE</q-badge>
              <q-badge v-else outline color="grey-7">ONLINE</q-badge>
            </q-td>
          </template>

          <template #body-cell-actor_user="props">
            <q-td :props="props">
              <q-badge v-if="props.row.actor_user" outline>
                user#{{ props.row.actor_user }}
              </q-badge>
              <q-badge v-else outline color="grey-7">(system)</q-badge>
            </q-td>
          </template>

          <template #body-cell-subject="props">
            <q-td :props="props">
              <div v-if="props.row.subject_type || props.row.subject_id" class="text-caption">
                {{ props.row.subject_type || '-' }} · {{ props.row.subject_id || '-' }}
              </div>
              <q-badge v-else outline color="grey-7">(none)</q-badge>
            </q-td>
          </template>

          <template #body-cell-path="props">
            <q-td :props="props">
              <div class="ellipsis" style="max-width: 520px">
                {{ props.row.path }}
              </div>
            </q-td>
          </template>

          <template #body-cell-event_id="props">
            <q-td :props="props">
              <div class="text-caption">
                {{ props.row.event_id }}
              </div>
            </q-td>
          </template>
        </AppDataTable>
      </div>
    </div>

    <!-- Detail dialog -->
    <q-dialog v-model="detailDialog">
      <q-card style="width: 980px; max-width: 96vw" class="app-card">
        <q-card-section class="row items-center justify-between">
          <div class="text-h6">Detalle de evento</div>
          <q-btn flat icon="close" v-close-popup />
        </q-card-section>

        <q-separator />

        <q-card-section>
          <div class="text-caption text-grey-7">event_id</div>
          <div class="text-body2 q-mb-sm">{{ detailId }}</div>

          <q-banner v-if="detailError" class="q-mb-md" dense rounded>
            {{ detailError }}
          </q-banner>

          <q-input
            v-model="detailJson"
            type="textarea"
            outlined
            autogrow
            readonly
            :loading="detailLoading"
            label="Payload (JSON)"
          />

          <div class="row items-center q-gutter-sm q-mt-sm">
            <q-btn outline label="Copiar JSON" :disable="!detailJson" @click="copyDetail" />
          </div>
        </q-card-section>
      </q-card>
    </q-dialog>
  </AppContainer>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import { useQuasar } from 'quasar';
import type { QTableColumn } from 'quasar';

import AppContainer from 'src/ui/AppContainer.vue';
import AppPageHeader from 'src/ui/AppPageHeader.vue';
import AppDataTable from 'src/ui/AppDataTable.vue';

import { extractErrorMessage } from 'src/core/http/errors';
import { useAclStore } from 'src/stores/acl.store';
import { useContextStore } from 'src/stores/context.store';
import {
  getAuditEvent,
  listAuditEvents,
  type AuditEventRow,
  type CursorPage,
} from 'src/services/audit.service';

const $q = useQuasar();
const acl = useAclStore();
const ctx = useContextStore();

const companyLabel = computed(() => {
  const c = ctx.activeCompanyId;
  if (!c) return '-';
  return acl.companyName(c) ?? c;
});

type OfflineModeFilter = 'any' | 'true' | 'false';

const offlineOptions = [
  { label: 'Cualquiera', value: 'any' },
  { label: 'Solo offline', value: 'true' },
  { label: 'Solo online', value: 'false' },
];

const filters = reactive({
  event_type: '',
  reason_code: '',
  module: '',
  method: '',
  actor_user_id: '',
  subject_type: '',
  subject_id: '',
  device_id: '',
  ip: '',
  path_contains: '',
  offline_mode: 'any' as OfflineModeFilter,
  after: '',
  before: '',
  include_integrity: false,
});

const loading = ref(false);
const errorMsg = ref('');

const page = ref<CursorPage<AuditEventRow> | null>(null);
const rows = ref<AuditEventRow[]>([]);

const columns = computed<QTableColumn<AuditEventRow>[]>(() => [
  {
    name: 'actions',
    label: '',
    field: () => '',
    align: 'right',
  },
  {
    name: 'timestamp_server',
    label: 'Timestamp',
    field: 'timestamp_server',
    align: 'left',
    sortable: false,
  },
  { name: 'event_type', label: 'Event', field: 'event_type', align: 'left' },
  { name: 'reason_code', label: 'Reason', field: 'reason_code', align: 'left' },
  { name: 'module', label: 'Module', field: 'module', align: 'left' },
  { name: 'method', label: 'Method', field: 'method', align: 'left' },
  { name: 'path', label: 'Path', field: 'path', align: 'left' },
  { name: 'actor_user', label: 'Actor', field: 'actor_user', align: 'left' },
  { name: 'subject', label: 'Subject', field: () => '', align: 'left' },
  { name: 'device_id', label: 'Device', field: 'device_id', align: 'left' },
  { name: 'ip_server_seen', label: 'IP', field: 'ip_server_seen', align: 'left' },
  { name: 'offline_mode', label: 'Offline', field: 'offline_mode', align: 'left' },
  { name: 'event_id', label: 'ID', field: 'event_id', align: 'left' },
]);

function normalizeStr(v: string): string | undefined {
  const s = String(v ?? '').trim();
  return s ? s : undefined;
}

function cursorFromUrl(url: string | null): string | undefined {
  if (!url) return undefined;
  try {
    const u = new URL(url);
    return u.searchParams.get('cursor') ?? undefined;
  } catch {
    // Si el backend devolviera una URL relativa, intentamos extraer a mano.
    const idx = url.indexOf('cursor=');
    if (idx < 0) return undefined;
    return decodeURIComponent(url.slice(idx + 'cursor='.length).split('&')[0] ?? '');
  }
}

function buildParams(cursor?: string) {
  const offline = filters.offline_mode === 'any' ? undefined : filters.offline_mode === 'true';

  return {
    cursor,
    event_type: normalizeStr(filters.event_type),
    reason_code: normalizeStr(filters.reason_code),
    module: normalizeStr(filters.module),
    method: normalizeStr(filters.method)?.toUpperCase(),
    actor_user_id: normalizeStr(filters.actor_user_id),
    subject_type: normalizeStr(filters.subject_type),
    subject_id: normalizeStr(filters.subject_id),
    device_id: normalizeStr(filters.device_id),
    ip: normalizeStr(filters.ip),
    path_contains: normalizeStr(filters.path_contains),
    offline_mode: offline,
    after: normalizeStr(filters.after),
    before: normalizeStr(filters.before),
    page_size: 50,
    include_integrity: filters.include_integrity || undefined,
  };
}

async function load(cursor?: string) {
  loading.value = true;
  errorMsg.value = '';
  try {
    const data = await listAuditEvents(buildParams(cursor));
    page.value = data;
    rows.value = data.results;
  } catch (e) {
    errorMsg.value = extractErrorMessage(e);
  } finally {
    loading.value = false;
  }
}

function clearFilters() {
  filters.event_type = '';
  filters.reason_code = '';
  filters.module = '';
  filters.method = '';
  filters.actor_user_id = '';
  filters.subject_type = '';
  filters.subject_id = '';
  filters.device_id = '';
  filters.ip = '';
  filters.path_contains = '';
  filters.offline_mode = 'any';
  filters.after = '';
  filters.before = '';
  filters.include_integrity = false;
  void load();
}

function goNext() {
  const c = cursorFromUrl(page.value?.next ?? null);
  void load(c);
}

function goPrev() {
  const c = cursorFromUrl(page.value?.previous ?? null);
  void load(c);
}

const detailDialog = ref(false);
const detailLoading = ref(false);
const detailError = ref('');
const detailId = ref<string>('');
const detail = ref<Record<string, unknown> | null>(null);

const detailJson = computed({
  get: () => (detail.value ? JSON.stringify(detail.value, null, 2) : ''),
  set: () => {
    // readonly
  },
});

async function openDetail(row: AuditEventRow) {
  detailDialog.value = true;
  detailLoading.value = true;
  detailError.value = '';
  detailId.value = row.event_id;
  detail.value = null;

  try {
    detail.value = await getAuditEvent(row.event_id);
  } catch (e) {
    detailError.value = extractErrorMessage(e);
  } finally {
    detailLoading.value = false;
  }
}

async function copyDetail() {
  try {
    await navigator.clipboard.writeText(detailJson.value);
    $q.notify({ type: 'positive', message: 'JSON copiado' });
  } catch {
    $q.notify({ type: 'negative', message: 'No pude copiar al portapapeles' });
  }
}

onMounted(() => {
  void load();
});
</script>
