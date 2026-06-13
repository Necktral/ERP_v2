<template>
  <q-page class="app-page">
    <PageHeader
      title="Diagnóstico"
      subtitle="Supervisión técnica: errores de runtime por clase de riesgo, hallazgos de seguridad, gate de release y kill switch de IA."
      :loading="cargando"
      @refresh="recargar"
    >
      <template #actions>
        <q-toggle
          v-if="puede('diagnostics.ai_control.manage')"
          :model-value="iaEncendida"
          checked-icon="smart_toy"
          color="primary"
          label="IA"
          @update:model-value="toggleIA"
        >
          <q-tooltip>Kill switch de IA (apaga toda síntesis/análisis IA)</q-tooltip>
        </q-toggle>
      </template>
    </PageHeader>

    <div v-if="readiness" class="dgx-readiness" :class="readinessOk ? 'is-ok' : 'is-block'">
      <q-icon :name="readinessOk ? 'verified' : 'block'" size="20px" />
      {{ readinessOk ? 'Listo para release: sin errores C1 abiertos.' : 'Release BLOQUEADO: hay errores C1 abiertos.' }}
    </div>

    <q-tabs
      v-model="tab"
      dense
      no-caps
      align="left"
      class="dgx-tabs"
      active-color="primary"
      indicator-color="primary"
    >
      <q-tab name="errores" icon="bug_report" label="Errores" />
      <q-tab v-if="puede('diagnostics.finding.read')" name="seguridad" icon="security" label="Seguridad" />
    </q-tabs>
    <q-separator class="q-mb-md" />

    <q-tab-panels v-model="tab" animated class="dgx-panels">
      <q-tab-panel name="errores" class="q-pa-none">
        <div class="dgx-filtros">
          <q-select
            v-model="filtroRiesgo"
            :options="opcionesRiesgo"
            dense
            outlined
            emit-value
            map-options
            clearable
            label="Riesgo"
            class="dgx-filtros__sel"
            @update:model-value="recargar"
          />
          <q-select
            v-model="filtroEstado"
            :options="opcionesEstadoError"
            dense
            outlined
            emit-value
            map-options
            clearable
            label="Estado"
            class="dgx-filtros__sel"
            @update:model-value="recargar"
          />
        </div>
        <q-table
          class="app-table"
          :rows="errores"
          :columns="columnasError"
          row-key="id"
          flat
          dense
          :loading="cargando"
          :pagination="{ rowsPerPage: 25 }"
          no-data-label="Sin errores con esos filtros. Excelente."
        >
          <template #body-cell-riesgo="props">
            <q-td :props="props">
              <q-chip
                dense
                :color="props.row.risk_class === 'C1' ? 'negative' : props.row.risk_class === 'C2' ? 'warning' : 'grey-7'"
                text-color="white"
                :label="props.row.risk_class"
              />
            </q-td>
          </template>
          <template #body-cell-estado="props">
            <q-td :props="props">{{ ERROR_STATUS_LABELS[props.row.status] ?? props.row.status }}</q-td>
          </template>
          <template #body-cell-acciones="props">
            <q-td :props="props" class="text-right dgx-acciones">
              <q-btn
                v-if="puede('diagnostics.diagnose.run')"
                flat
                dense
                no-caps
                size="sm"
                icon="troubleshoot"
                label="Diagnosticar"
                @click="diagnosticar(props.row)"
              />
              <q-btn
                v-if="puede('diagnostics.error.triage') && props.row.status === 'open'"
                flat
                dense
                no-caps
                size="sm"
                label="Triage"
                @click="triage(props.row)"
              />
            </q-td>
          </template>
        </q-table>
      </q-tab-panel>

      <q-tab-panel name="seguridad" class="q-pa-none">
        <q-table
          class="app-table"
          :rows="hallazgos"
          :columns="columnasHallazgo"
          row-key="id"
          flat
          dense
          :loading="cargando"
          :pagination="{ rowsPerPage: 25 }"
          no-data-label="Sin hallazgos de seguridad."
        >
          <template #body-cell-acciones="props">
            <q-td :props="props" class="text-right">
              <q-btn
                v-if="puede('diagnostics.finding.triage') && props.row.status === 'open'"
                flat
                dense
                no-caps
                size="sm"
                label="Triage"
                @click="triageSeguridad(props.row)"
              />
            </q-td>
          </template>
        </q-table>
      </q-tab-panel>
    </q-tab-panels>

    <q-dialog v-model="dlgDiag">
      <q-card class="app-dialog dgx-detalle">
        <q-card-section class="text-h6">Diagnóstico</q-card-section>
        <q-card-section>
          <pre class="dgx-json">{{ textoDiag }}</pre>
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat no-caps label="Cerrar" v-close-popup />
        </q-card-actions>
      </q-card>
    </q-dialog>
  </q-page>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useQuasar, type QTableColumn } from 'quasar';
import PageHeader from 'src/components/PageHeader.vue';
import { apiErrorMessage } from 'src/core/api';
import { formatDateTime } from 'src/core/format';
import {
  diagnoseError,
  ERROR_STATUS_LABELS,
  getAiControl,
  getReleaseReadiness,
  listErrors,
  listSecurityFindings,
  RISK_LABELS,
  setAiControl,
  triageError,
  triageSecurityFinding,
  type ErrorEventRow,
  type SecurityFindingRow,
} from 'src/features/diagnostics/diagnostics.api';
import { useAclStore } from 'src/stores/acl.store';
import { useContextStore } from 'src/stores/context.store';

const $q = useQuasar();
const acl = useAclStore();
const ctx = useContextStore();

const tab = ref('errores');
const cargando = ref(false);
const filtroRiesgo = ref<string | null>(null);
const filtroEstado = ref<string | null>(null);
const errores = ref<ErrorEventRow[]>([]);
const hallazgos = ref<SecurityFindingRow[]>([]);
const readiness = ref<Record<string, unknown> | null>(null);
const iaEncendida = ref(false);

function puede(code: string): boolean {
  const companyId = ctx.activeCompanyId;
  return companyId ? acl.hasPermission(companyId, code) : false;
}

const readinessOk = computed(() => {
  const r = readiness.value;
  if (!r) return true;
  if (typeof r.blocked === 'boolean') return !r.blocked;
  return true;
});

const opcionesRiesgo = Object.entries(RISK_LABELS).map(([value, label]) => ({ value, label }));
const opcionesEstadoError = Object.entries(ERROR_STATUS_LABELS).map(([value, label]) => ({ value, label }));

const columnasError: QTableColumn<ErrorEventRow>[] = [
  { name: 'id', label: '#', field: 'id', align: 'left' },
  { name: 'riesgo', label: 'Riesgo', field: 'risk_class', align: 'left' },
  { name: 'domain', label: 'Dominio', field: 'domain', align: 'left' },
  { name: 'mensaje', label: 'Error', field: (r) => `${r.exception_type ?? ''} ${r.message ?? ''}`.trim() || '—', align: 'left' },
  { name: 'veces', label: 'Veces', field: (r) => r.occurrences ?? 1, align: 'right' },
  {
    name: 'ultima',
    label: 'Última vez',
    field: (r) => (r.last_seen_at ? formatDateTime(String(r.last_seen_at)) : '—'),
    align: 'left',
  },
  { name: 'estado', label: 'Estado', field: 'status', align: 'left' },
  { name: 'acciones', label: '', field: 'id', align: 'right' },
];

const columnasHallazgo: QTableColumn<SecurityFindingRow>[] = [
  { name: 'id', label: '#', field: 'id', align: 'left' },
  { name: 'title', label: 'Hallazgo', field: (r) => (r.title as string) || '—', align: 'left' },
  { name: 'severity', label: 'Severidad', field: (r) => (r.severity as string) || '—', align: 'left' },
  { name: 'source', label: 'Fuente', field: (r) => (r.source as string) || '—', align: 'left' },
  { name: 'status', label: 'Estado', field: (r) => ERROR_STATUS_LABELS[r.status] ?? r.status, align: 'left' },
  { name: 'acciones', label: '', field: 'id', align: 'right' },
];

async function recargar() {
  cargando.value = true;
  try {
    const tareas: Promise<void>[] = [
      listErrors({
        ...(filtroRiesgo.value ? { risk_class: filtroRiesgo.value } : {}),
        ...(filtroEstado.value ? { status: filtroEstado.value } : {}),
      }).then((r) => {
        errores.value = r;
      }),
      getReleaseReadiness()
        .then((r) => {
          readiness.value = r;
        })
        .catch(() => {
          readiness.value = null;
        }),
    ];
    if (puede('diagnostics.finding.read')) {
      tareas.push(
        listSecurityFindings().then((r) => {
          hallazgos.value = r;
        }),
      );
    }
    if (puede('diagnostics.ai_control.read')) {
      tareas.push(
        getAiControl()
          .then((r) => {
            iaEncendida.value = Boolean(r.enabled);
          })
          .catch(() => undefined),
      );
    }
    await Promise.all(tareas);
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo cargar el diagnóstico.') });
  } finally {
    cargando.value = false;
  }
}

async function toggleIA(valor: boolean) {
  try {
    await setAiControl(valor, valor ? 'encendido desde panel' : 'apagado desde panel');
    iaEncendida.value = valor;
    $q.notify({
      type: valor ? 'positive' : 'warning',
      message: valor ? 'IA encendida.' : 'IA APAGADA (kill switch).',
    });
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo cambiar el kill switch.') });
  }
}

const dlgDiag = ref(false);
const textoDiag = ref('');

async function diagnosticar(err: ErrorEventRow) {
  textoDiag.value = 'Corriendo diagnóstico determinista…';
  dlgDiag.value = true;
  try {
    const r = await diagnoseError(err.id);
    textoDiag.value = JSON.stringify(r, null, 2);
  } catch (e) {
    textoDiag.value = apiErrorMessage(e, 'No se pudo diagnosticar.');
  }
}

function triage(err: ErrorEventRow) {
  $q.dialog({
    title: `Triage del error #${err.id}`,
    message: 'Decisión:',
    options: {
      type: 'radio',
      model: 'confirmed',
      items: [
        { label: 'Confirmado (es un bug real)', value: 'confirmed' },
        { label: 'Corregido', value: 'fixed' },
        { label: 'Riesgo aceptado', value: 'accepted_risk' },
        { label: 'Falso positivo', value: 'false_positive' },
      ],
    },
    cancel: { flat: true, noCaps: true, label: 'Cancelar' },
    ok: { unelevated: true, noCaps: true, color: 'primary', label: 'Aplicar' },
  }).onOk((decision: string) => {
    void (async () => {
      try {
        await triageError(err.id, decision);
        $q.notify({ type: 'positive', message: 'Triage aplicado.' });
        await recargar();
      } catch (e) {
        $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo aplicar.') });
      }
    })();
  });
}

function triageSeguridad(f: SecurityFindingRow) {
  $q.dialog({
    title: `Triage del hallazgo #${f.id}`,
    message: 'Decisión:',
    options: {
      type: 'radio',
      model: 'confirmed',
      items: [
        { label: 'Confirmado', value: 'confirmed' },
        { label: 'Corregido', value: 'fixed' },
        { label: 'Riesgo aceptado', value: 'accepted_risk' },
        { label: 'Falso positivo', value: 'false_positive' },
      ],
    },
    cancel: { flat: true, noCaps: true, label: 'Cancelar' },
    ok: { unelevated: true, noCaps: true, color: 'primary', label: 'Aplicar' },
  }).onOk((decision: string) => {
    void (async () => {
      try {
        await triageSecurityFinding(f.id, decision);
        $q.notify({ type: 'positive', message: 'Triage aplicado.' });
        await recargar();
      } catch (e) {
        $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo aplicar.') });
      }
    })();
  });
}

onMounted(recargar);
</script>

<style scoped>
.dgx-readiness {
  display: flex;
  align-items: center;
  gap: var(--app-space-2);
  padding: var(--app-space-3) var(--app-space-4);
  border-radius: var(--app-radius-md);
  border: 1px solid var(--app-border);
  background: var(--app-surface);
  margin-bottom: var(--app-space-4);
  font-weight: 600;
  color: var(--app-text);
}

.dgx-readiness.is-block {
  border-color: var(--app-border-strong);
  color: var(--app-text);
}

.dgx-tabs {
  color: var(--app-text-muted);
}

.dgx-panels {
  background: transparent;
}

.dgx-filtros {
  display: flex;
  gap: var(--app-space-3);
  margin-bottom: var(--app-space-3);
}

.dgx-filtros__sel {
  width: 200px;
}

.dgx-acciones {
  white-space: nowrap;
}

.dgx-detalle {
  width: 680px;
}

.dgx-json {
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
