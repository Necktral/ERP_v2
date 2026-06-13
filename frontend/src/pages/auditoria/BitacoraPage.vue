<template>
  <q-page class="app-page">
    <PageHeader
      title="Bitácora de auditoría"
      subtitle="Registro inmutable de TODO lo que pasa en el sistema, encadenado criptográficamente. Solo lectura."
      :loading="cargando"
      @refresh="buscar()"
    />

    <q-expansion-item
      v-model="filtrosAbiertos"
      icon="filter_list"
      label="Filtros"
      dense
      class="bit-filtros-exp"
    >
      <div class="bit-filtros">
        <q-input v-model="filtros.event_type" dense outlined label="Tipo de evento" class="bit-f" />
        <q-input v-model="filtros.module" dense outlined label="Módulo" class="bit-f" />
        <q-input v-model="filtros.actor_user_id" dense outlined label="ID de usuario" class="bit-f" />
        <q-input v-model="filtros.subject_type" dense outlined label="Tipo de sujeto" class="bit-f" />
        <q-input v-model="filtros.path_contains" dense outlined label="Ruta contiene" class="bit-f" />
        <q-input v-model="filtros.after" dense outlined type="date" label="Desde" class="bit-f" />
        <q-input v-model="filtros.before" dense outlined type="date" label="Hasta" class="bit-f" />
        <q-btn unelevated no-caps color="primary" icon="search" label="Buscar" @click="buscar()" />
      </div>
    </q-expansion-item>

    <q-table
      class="app-table"
      :rows="eventos"
      :columns="columns"
      row-key="event_id"
      flat
      dense
      :loading="cargando"
      :pagination="{ rowsPerPage: 50 }"
      no-data-label="Sin eventos con esos filtros."
      @row-click="(_, row) => verDetalle(row as AuditEventRow)"
    >
      <template #body-cell-fecha="props">
        <q-td :props="props">{{ formatDateTime(props.row.timestamp_server) }}</q-td>
      </template>
    </q-table>
    <div v-if="cursorSiguiente" class="q-mt-sm">
      <q-btn flat no-caps icon="expand_more" label="Cargar más" :loading="cargando" @click="buscar(cursorSiguiente)" />
    </div>

    <q-dialog v-model="dlgDetalle">
      <q-card class="app-dialog bit-detalle">
        <q-card-section class="text-h6">Evento {{ String(eventoDetalle?.event_id ?? '').slice(0, 8) }}</q-card-section>
        <q-card-section>
          <pre class="bit-json">{{ textoDetalle }}</pre>
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat no-caps label="Cerrar" v-close-popup />
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
import { formatDateTime } from 'src/core/format';
import {
  getAuditEvent,
  listBitacora,
  type AuditEventRow,
  type BitacoraFilters,
} from 'src/features/audit/audit.api';

const $q = useQuasar();

const filtrosAbiertos = ref(false);
const filtros = reactive<BitacoraFilters>({});
const cargando = ref(false);
const eventos = ref<AuditEventRow[]>([]);
const cursorSiguiente = ref<string | null>(null);

const columns: QTableColumn<AuditEventRow>[] = [
  { name: 'fecha', label: 'Fecha', field: 'timestamp_server', align: 'left' },
  { name: 'module', label: 'Módulo', field: 'module', align: 'left' },
  { name: 'event_type', label: 'Evento', field: 'event_type', align: 'left' },
  { name: 'reason_code', label: 'Resultado', field: 'reason_code', align: 'left' },
  { name: 'actor_user', label: 'Usuario', field: (r) => r.actor_user ?? '—', align: 'left' },
  { name: 'path', label: 'Ruta', field: 'path', align: 'left' },
];

function extraerCursor(url: string | null): string | null {
  if (!url) return null;
  try {
    return new URL(url, window.location.origin).searchParams.get('cursor');
  } catch {
    return null;
  }
}

async function buscar(cursor?: string | null) {
  cargando.value = true;
  try {
    const page = await listBitacora({ ...filtros }, cursor ?? undefined);
    eventos.value = cursor ? [...eventos.value, ...page.results] : page.results;
    cursorSiguiente.value = extraerCursor(page.next);
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo cargar la bitácora.') });
  } finally {
    cargando.value = false;
  }
}

const dlgDetalle = ref(false);
const eventoDetalle = ref<AuditEventRow | null>(null);
const textoDetalle = ref('');

async function verDetalle(ev: AuditEventRow) {
  eventoDetalle.value = ev;
  textoDetalle.value = 'Cargando…';
  dlgDetalle.value = true;
  try {
    const r = await getAuditEvent(ev.event_id);
    textoDetalle.value = JSON.stringify(r, null, 2);
  } catch (e) {
    textoDetalle.value = apiErrorMessage(e, 'No se pudo cargar el detalle.');
  }
}

onMounted(() => {
  void buscar();
});
</script>

<style scoped>
.bit-filtros-exp {
  margin-bottom: var(--app-space-3);
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-md);
  background: var(--app-surface);
}

.bit-filtros {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--app-space-2);
  padding: var(--app-space-3);
}

.bit-f {
  width: 180px;
}

.bit-detalle {
  width: 680px;
}

.bit-json {
  margin: 0;
  max-height: 60vh;
  overflow: auto;
  font-size: 0.75rem;
  color: var(--app-text);
  background: var(--app-surface);
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-sm);
  padding: var(--app-space-3);
  white-space: pre-wrap;
}
</style>
