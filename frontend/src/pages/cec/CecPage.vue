<template>
  <q-page class="app-page">
    <PageHeader
      title="Cierre contable (CEC)"
      subtitle="Corridas de cierre con su avance por etapas, y las excepciones que bloquean la entrega."
      :loading="cargando"
      @refresh="recargar"
    >
      <template #actions>
        <q-btn
          v-if="puede('cec.close_run.create')"
          unelevated
          no-caps
          color="primary"
          icon="play_circle"
          label="Nueva corrida"
          @click="crearCorrida"
        />
      </template>
    </PageHeader>

    <q-tabs
      v-model="tab"
      dense
      no-caps
      align="left"
      class="cec-tabs"
      active-color="primary"
      indicator-color="primary"
    >
      <q-tab name="corridas" icon="all_inclusive" label="Corridas" />
      <q-tab v-if="puede('cec.exception.read')" name="excepciones" icon="report_problem" label="Excepciones" />
    </q-tabs>
    <q-separator class="q-mb-md" />

    <q-tab-panels v-model="tab" animated class="cec-panels">
      <q-tab-panel name="corridas" class="q-pa-none">
        <q-table
          class="app-table"
          :rows="corridas"
          :columns="columnasCorrida"
          row-key="run_id"
          flat
          :loading="cargando"
          :pagination="{ rowsPerPage: 25 }"
          no-data-label="Sin corridas de cierre."
        >
          <template #body-cell-estado="props">
            <q-td :props="props">
              {{ CLOSE_RUN_STATUS_LABELS[props.row.status] ?? props.row.status }}
            </q-td>
          </template>
          <template #body-cell-acciones="props">
            <q-td :props="props" class="text-right cec-acciones">
              <q-btn
                v-if="puede('cec.close_run.update') && siguienteEstado(props.row.status)"
                flat
                dense
                no-caps
                size="sm"
                color="primary"
                :label="`Avanzar a ${CLOSE_RUN_STATUS_LABELS[siguienteEstado(props.row.status)!]}`"
                @click="avanzar(props.row)"
              />
              <q-btn flat dense no-caps size="sm" icon="summarize" label="Resumen" @click="verDetalle(props.row, 'summary')" />
              <q-btn flat dense no-caps size="sm" icon="psychology" label="Explicar" @click="verDetalle(props.row, 'explain')" />
            </q-td>
          </template>
        </q-table>
      </q-tab-panel>

      <q-tab-panel name="excepciones" class="q-pa-none">
        <q-table
          class="app-table"
          :rows="excepciones"
          :columns="columnasExc"
          row-key="id"
          flat
          :loading="cargando"
          :pagination="{ rowsPerPage: 25 }"
          no-data-label="Sin excepciones — el cierre va limpio."
        >
          <template #body-cell-severidad="props">
            <q-td :props="props">
              <q-chip
                dense
                :color="props.row.severity === 'CRITICAL' || props.row.severity === 'HIGH' ? 'negative' : 'warning'"
                text-color="white"
                :label="CEC_SEVERITY_LABELS[props.row.severity] ?? props.row.severity"
              />
            </q-td>
          </template>
          <template #body-cell-acciones="props">
            <q-td :props="props" class="text-right">
              <q-btn
                v-if="puede('cec.exception.update') && props.row.status !== 'RESOLVED' && props.row.status !== 'CLOSED'"
                flat
                dense
                no-caps
                size="sm"
                color="primary"
                label="Resolver"
                @click="resolver(props.row)"
              />
            </q-td>
          </template>
        </q-table>
      </q-tab-panel>
    </q-tab-panels>

    <!-- Diálogo: resumen / explicación -->
    <q-dialog v-model="dlgDetalle">
      <q-card class="app-dialog cec-detalle">
        <q-card-section class="text-h6">{{ tituloDetalle }}</q-card-section>
        <q-card-section>
          <pre class="cec-json">{{ textoDetalle }}</pre>
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat no-caps label="Cerrar" v-close-popup />
        </q-card-actions>
      </q-card>
    </q-dialog>
  </q-page>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { useQuasar, type QTableColumn } from 'quasar';
import PageHeader from 'src/components/PageHeader.vue';
import { apiErrorMessage } from 'src/core/api';
import { formatDateTime } from 'src/core/format';
import {
  advanceCloseRun,
  CEC_SEVERITY_LABELS,
  CEC_STATUS_ORDER,
  CLOSE_RUN_STATUS_LABELS,
  createCloseRun,
  explainCloseRun,
  getCloseRunSummary,
  listCecExceptions,
  listCloseRuns,
  resolveCecException,
  type CecException,
  type CloseRunRow,
} from 'src/features/cec/cec.api';
import { useAclStore } from 'src/stores/acl.store';
import { useContextStore } from 'src/stores/context.store';

const $q = useQuasar();
const acl = useAclStore();
const ctx = useContextStore();

const tab = ref('corridas');
const cargando = ref(false);
const corridas = ref<CloseRunRow[]>([]);
const excepciones = ref<CecException[]>([]);

function puede(code: string): boolean {
  const companyId = ctx.activeCompanyId;
  return companyId ? acl.hasPermission(companyId, code) : false;
}

function siguienteEstado(actual: string): string | null {
  const idx = CEC_STATUS_ORDER.indexOf(actual);
  if (idx < 0 || idx === CEC_STATUS_ORDER.length - 1) return null;
  return CEC_STATUS_ORDER[idx + 1] ?? null;
}

const columnasCorrida: QTableColumn<CloseRunRow>[] = [
  { name: 'run_id', label: 'Corrida', field: (r) => String(r.run_id).slice(0, 8), align: 'left' },
  { name: 'run_type', label: 'Tipo', field: (r) => (r.run_type === 'DAILY' ? 'Diaria' : 'Periódica'), align: 'left' },
  { name: 'estado', label: 'Estado', field: 'status', align: 'left' },
  {
    name: 'creada',
    label: 'Creada',
    field: (r) => (r.created_at ? formatDateTime(String(r.created_at)) : '—'),
    align: 'left',
  },
  { name: 'acciones', label: '', field: 'run_id', align: 'right' },
];

const columnasExc: QTableColumn<CecException>[] = [
  { name: 'id', label: '#', field: 'id', align: 'left' },
  { name: 'source_module', label: 'Módulo', field: 'source_module', align: 'left' },
  { name: 'code', label: 'Código', field: 'code', align: 'left' },
  { name: 'severidad', label: 'Severidad', field: 'severity', align: 'left' },
  { name: 'status', label: 'Estado', field: 'status', align: 'left' },
  { name: 'acciones', label: '', field: 'id', align: 'right' },
];

async function recargar() {
  cargando.value = true;
  try {
    const tareas: Promise<void>[] = [
      listCloseRuns().then((r) => {
        corridas.value = r;
      }),
    ];
    if (puede('cec.exception.read')) {
      tareas.push(
        listCecExceptions().then((r) => {
          excepciones.value = r;
        }),
      );
    }
    await Promise.all(tareas);
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo cargar el CEC.') });
  } finally {
    cargando.value = false;
  }
}

function crearCorrida() {
  $q.dialog({
    title: 'Nueva corrida de cierre',
    message: 'Tipo de corrida:',
    options: {
      type: 'radio',
      model: 'DAILY',
      items: [
        { label: 'Diaria', value: 'DAILY' },
        { label: 'Periódica (mes)', value: 'PERIODIC' },
      ],
    },
    cancel: { flat: true, noCaps: true, label: 'Cancelar' },
    ok: { unelevated: true, noCaps: true, color: 'primary', label: 'Crear' },
  }).onOk((tipo: 'DAILY' | 'PERIODIC') => {
    void (async () => {
      try {
        await createCloseRun(tipo);
        $q.notify({ type: 'positive', message: 'Corrida creada.' });
        await recargar();
      } catch (e) {
        $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo crear la corrida.') });
      }
    })();
  });
}

async function avanzar(run: CloseRunRow) {
  const destino = siguienteEstado(run.status);
  if (!destino) return;
  try {
    await advanceCloseRun(run.run_id, destino);
    $q.notify({
      type: 'positive',
      message: `Corrida avanzada a ${CLOSE_RUN_STATUS_LABELS[destino]}.`,
    });
    await recargar();
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo avanzar (¿excepciones abiertas?).') });
  }
}

const dlgDetalle = ref(false);
const tituloDetalle = ref('');
const textoDetalle = ref('');

async function verDetalle(run: CloseRunRow, tipo: 'summary' | 'explain') {
  tituloDetalle.value = tipo === 'summary' ? 'Resumen de la corrida' : 'Explicación del cierre';
  textoDetalle.value = 'Cargando…';
  dlgDetalle.value = true;
  try {
    const r = tipo === 'summary' ? await getCloseRunSummary(run.run_id) : await explainCloseRun(run.run_id);
    textoDetalle.value = JSON.stringify(r, null, 2);
  } catch (e) {
    textoDetalle.value = apiErrorMessage(e, 'No se pudo cargar.');
  }
}

function resolver(exc: CecException) {
  $q.dialog({
    title: `Resolver excepción #${exc.id}`,
    message: 'Nota de resolución (qué se corrigió):',
    prompt: { model: '', type: 'text', isValid: (v: string) => v.trim().length >= 5 },
    cancel: { flat: true, noCaps: true, label: 'Cancelar' },
    ok: { unelevated: true, noCaps: true, color: 'primary', label: 'Resolver' },
    persistent: true,
  }).onOk((nota: string) => {
    void (async () => {
      try {
        await resolveCecException(exc.id, nota.trim());
        $q.notify({ type: 'positive', message: 'Excepción resuelta.' });
        await recargar();
      } catch (e) {
        $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo resolver.') });
      }
    })();
  });
}

onMounted(recargar);
</script>

<style scoped>
.cec-tabs {
  color: var(--app-text-muted);
}

.cec-panels {
  background: transparent;
}

.cec-acciones {
  white-space: nowrap;
}

.cec-detalle {
  width: 640px;
}

.cec-json {
  margin: 0;
  max-height: 60vh;
  overflow: auto;
  font-size: 0.78rem;
  color: var(--app-text);
  background: var(--app-surface);
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-sm);
  padding: var(--app-space-3);
  white-space: pre-wrap;
}
</style>
