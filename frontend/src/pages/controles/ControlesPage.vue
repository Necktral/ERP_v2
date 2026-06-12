<template>
  <q-page class="app-page">
    <PageHeader
      title="Controles anti-fraude"
      subtitle="Reglas de segregación de funciones (SoD), violaciones vivas y hallazgos con su triage."
      :loading="cargando"
      @refresh="recargar"
    >
      <template #actions>
        <q-btn
          v-if="puede('controls.findings.manage')"
          unelevated
          no-caps
          color="primary"
          icon="radar"
          label="Escanear"
          :loading="escaneando"
          @click="escanear"
        />
      </template>
    </PageHeader>

    <q-tabs
      v-model="tab"
      dense
      no-caps
      align="left"
      class="ctl-tabs"
      active-color="primary"
      indicator-color="primary"
    >
      <q-tab name="violaciones" icon="warning" label="Violaciones vivas" />
      <q-tab name="hallazgos" icon="assignment_late" label="Hallazgos" />
      <q-tab name="reglas" icon="rule" label="Reglas SoD" />
    </q-tabs>
    <q-separator class="q-mb-md" />

    <q-tab-panels v-model="tab" animated class="ctl-panels">
      <q-tab-panel name="violaciones" class="q-pa-none">
        <div class="text-caption text-muted q-mb-sm">
          Usuarios que HOY tienen pares de permisos incompatibles (ej. crear factura y aprobar pago).
        </div>
        <q-table
          class="app-table"
          :rows="violaciones"
          :columns="columnasViolacion"
          row-key="rule_code"
          flat
          :loading="cargando"
          :pagination="{ rowsPerPage: 25 }"
          no-data-label="Sin violaciones vivas. Buena señal."
        >
          <template #body-cell-severidad="props">
            <q-td :props="props">
              <q-chip
                dense
                :color="props.row.severity === 'CRITICAL' || props.row.severity === 'HIGH' ? 'negative' : 'warning'"
                text-color="white"
                :label="SEVERITY_LABELS[props.row.severity] ?? props.row.severity"
              />
            </q-td>
          </template>
        </q-table>
      </q-tab-panel>

      <q-tab-panel name="hallazgos" class="q-pa-none">
        <q-table
          class="app-table"
          :rows="hallazgos"
          :columns="columnasHallazgo"
          row-key="id"
          flat
          :loading="cargando"
          :pagination="{ rowsPerPage: 25 }"
          no-data-label="Sin hallazgos. Corré un escaneo para detectar."
        >
          <template #body-cell-estado="props">
            <q-td :props="props">{{ FINDING_STATUS_LABELS[props.row.status] ?? props.row.status }}</q-td>
          </template>
          <template #body-cell-acciones="props">
            <q-td :props="props" class="text-right">
              <q-btn
                v-if="puede('controls.findings.manage') && props.row.status === 'OPEN'"
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

      <q-tab-panel name="reglas" class="q-pa-none">
        <q-table
          class="app-table"
          :rows="reglas"
          :columns="columnasRegla"
          row-key="id"
          flat
          :loading="cargando"
          :pagination="{ rowsPerPage: 25 }"
          no-data-label="Sin reglas SoD configuradas."
        />
      </q-tab-panel>
    </q-tab-panels>
  </q-page>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { useQuasar, type QTableColumn } from 'quasar';
import PageHeader from 'src/components/PageHeader.vue';
import { apiErrorMessage } from 'src/core/api';
import {
  FINDING_STATUS_LABELS,
  listFindings,
  listSodRules,
  listSodViolations,
  resolveFinding,
  runControlScan,
  SEVERITY_LABELS,
  type ControlFinding,
  type SodRule,
  type SodViolation,
} from 'src/features/controls/controls.api';
import { useAclStore } from 'src/stores/acl.store';
import { useContextStore } from 'src/stores/context.store';

const $q = useQuasar();
const acl = useAclStore();
const ctx = useContextStore();

const tab = ref('violaciones');
const cargando = ref(false);
const escaneando = ref(false);
const reglas = ref<SodRule[]>([]);
const violaciones = ref<SodViolation[]>([]);
const hallazgos = ref<ControlFinding[]>([]);

function puede(code: string): boolean {
  const companyId = ctx.activeCompanyId;
  return companyId ? acl.hasPermission(companyId, code) : false;
}

const columnasViolacion: QTableColumn<SodViolation>[] = [
  { name: 'username', label: 'Usuario', field: 'username', align: 'left' },
  { name: 'rule_code', label: 'Regla', field: 'rule_code', align: 'left' },
  { name: 'permission_a', label: 'Permiso A', field: 'permission_a', align: 'left' },
  { name: 'permission_b', label: 'Permiso B', field: 'permission_b', align: 'left' },
  { name: 'severidad', label: 'Severidad', field: 'severity', align: 'left' },
];

const columnasHallazgo: QTableColumn<ControlFinding>[] = [
  { name: 'id', label: '#', field: 'id', align: 'left' },
  { name: 'control_code', label: 'Control', field: 'control_code', align: 'left' },
  { name: 'severity', label: 'Severidad', field: (r) => SEVERITY_LABELS[r.severity] ?? r.severity, align: 'left' },
  { name: 'estado', label: 'Estado', field: 'status', align: 'left' },
  { name: 'acciones', label: '', field: 'id', align: 'right' },
];

const columnasRegla: QTableColumn<SodRule>[] = [
  { name: 'code', label: 'Código', field: 'code', align: 'left' },
  { name: 'permission_a', label: 'Permiso A', field: 'permission_a', align: 'left' },
  { name: 'permission_b', label: 'Permiso B', field: 'permission_b', align: 'left' },
  { name: 'severity', label: 'Severidad', field: (r) => SEVERITY_LABELS[r.severity] ?? r.severity, align: 'left' },
];

async function recargar() {
  cargando.value = true;
  try {
    const [r, v, h] = await Promise.all([listSodRules(), listSodViolations(), listFindings()]);
    reglas.value = r;
    violaciones.value = v;
    hallazgos.value = h;
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudieron cargar los controles.') });
  } finally {
    cargando.value = false;
  }
}

async function escanear() {
  escaneando.value = true;
  try {
    const r = await runControlScan(90);
    $q.notify({ type: 'positive', message: `Escaneo listo: ${r.created} hallazgos nuevos.` });
    await recargar();
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo escanear.') });
  } finally {
    escaneando.value = false;
  }
}

function triage(h: ControlFinding) {
  $q.dialog({
    title: `Triage del hallazgo #${h.id}`,
    message: 'Decisión:',
    options: {
      type: 'radio',
      model: 'ACKNOWLEDGED',
      items: [
        { label: 'Reconocido (se investiga)', value: 'ACKNOWLEDGED' },
        { label: 'Resuelto (se corrigió)', value: 'RESOLVED' },
        { label: 'Descartado (falso positivo)', value: 'DISMISSED' },
      ],
    },
    cancel: { flat: true, noCaps: true, label: 'Cancelar' },
    ok: { unelevated: true, noCaps: true, color: 'primary', label: 'Aplicar' },
  }).onOk((decision: 'ACKNOWLEDGED' | 'RESOLVED' | 'DISMISSED') => {
    void (async () => {
      try {
        await resolveFinding(h.id, decision);
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
.ctl-tabs {
  color: var(--app-text-muted);
}

.ctl-panels {
  background: transparent;
}
</style>
