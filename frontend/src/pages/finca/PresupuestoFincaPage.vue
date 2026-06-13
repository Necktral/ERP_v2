<template>
  <q-page class="app-page">
    <PageHeader
      title="Presupuesto de finca"
      subtitle="Presupuesto por labor, lote y ciclo; comparalo contra el gasto real (jornales + insumos)."
      :loading="cargando"
      @refresh="recargar"
    >
      <template #actions>
        <q-btn
          v-if="puede('finca.budget.manage')"
          unelevated no-caps color="primary" icon="add" label="Nuevo presupuesto"
          @click="abrirNuevo"
        />
      </template>
    </PageHeader>

    <q-table
      class="app-table"
      flat
      :rows="budgets"
      :columns="cols"
      row-key="id"
      :loading="cargando"
      :pagination="{ rowsPerPage: 25 }"
      no-data-label="Sin presupuestos. Creá el primero."
    >
      <template #body-cell-status="props">
        <q-td :props="props">
          <q-chip dense square :class="`pf-st pf-st--${props.row.status}`" :label="props.row.status_label" />
        </q-td>
      </template>
      <template #body-cell-acciones="props">
        <q-td :props="props" class="text-right">
          <q-btn
            v-if="puede('finca.budget.manage') && props.row.status === 'DRAFT'"
            flat dense no-caps size="sm" icon="edit" label="Líneas" @click="abrirLineas(props.row)"
          />
          <q-btn
            v-if="puede('finca.budget.manage') && props.row.status === 'DRAFT'"
            flat dense no-caps size="sm" color="positive" icon="check" label="Aprobar" @click="aprobar(props.row)"
          />
          <q-btn flat dense no-caps size="sm" icon="bar_chart" label="Vs real" @click="abrirVsReal(props.row)" />
        </q-td>
      </template>
    </q-table>

    <!-- Nuevo presupuesto -->
    <q-dialog v-model="dlgNuevo">
      <q-card class="app-dialog">
        <q-card-section class="text-h6">Nuevo presupuesto</q-card-section>
        <q-card-section class="app-form">
          <q-select v-model="formNew.finca_id" :options="fincaOpts" outlined dense emit-value map-options label="Finca *" />
          <q-input v-model="formNew.season_label" outlined dense label="Ciclo / temporada *" hint="Ej.: 2025A, Cosecha 2025-26" />
          <q-input v-model="formNew.name" outlined dense label="Nombre *" />
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat no-caps label="Cancelar" v-close-popup />
          <q-btn
            unelevated no-caps color="primary" label="Crear" :loading="accionando"
            :disable="!formNew.finca_id || !formNew.season_label.trim() || !formNew.name.trim()" @click="crear"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <!-- Líneas -->
    <q-dialog v-model="dlgLineas">
      <q-card class="pf-dialog">
        <q-card-section class="text-h6">Líneas — {{ sel?.name }} ({{ sel?.season_label }})</q-card-section>
        <q-card-section>
          <q-markup-table flat dense class="pf-table">
            <thead>
              <tr>
                <th class="text-left">Labor</th>
                <th class="text-left">Lote</th>
                <th class="text-right">Jornales</th>
                <th class="text-right">Tarifa</th>
                <th class="text-right">Insumos C$</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(ln, i) in lineas" :key="i">
                <td><q-select v-model="ln.labor_id" :options="laborOpts" outlined dense emit-value map-options /></td>
                <td><q-select v-model="ln.plot_id" :options="plotOpts" outlined dense emit-value map-options /></td>
                <td><q-input v-model="ln.planned_jornales" outlined dense type="number" /></td>
                <td><q-input v-model="ln.planned_rate" outlined dense type="number" /></td>
                <td><q-input v-model="ln.planned_insumos_amount" outlined dense type="number" /></td>
                <td><q-btn flat dense round icon="close" size="sm" @click="lineas.splice(i, 1)" /></td>
              </tr>
            </tbody>
          </q-markup-table>
          <q-btn flat no-caps icon="add" label="Agregar línea" class="q-mt-sm" @click="agregarLinea" />
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat no-caps label="Cancelar" v-close-popup />
          <q-btn unelevated no-caps color="primary" label="Guardar líneas" :loading="accionando" @click="guardarLineas" />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <!-- Vs real -->
    <q-dialog v-model="dlgVs">
      <q-card class="pf-dialog">
        <q-card-section class="row items-center">
          <div class="text-h6">Presupuesto vs real — {{ sel?.name }}</div>
          <q-space />
          <q-chip dense square color="primary" text-color="white" :label="`Variación: C$ ${vs ? fmt(vs.total_variance) : '—'}`" />
        </q-card-section>
        <q-card-section v-if="vs">
          <q-markup-table flat dense class="pf-table">
            <thead>
              <tr>
                <th class="text-left">Labor</th>
                <th class="text-left">Lote</th>
                <th class="text-right">Presupuesto</th>
                <th class="text-right">Real</th>
                <th class="text-right">Variación</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="r in vs.rows" :key="`${r.labor_id}-${r.plot_id}`">
                <td>{{ r.labor_name }}</td>
                <td>{{ r.plot_code }}</td>
                <td class="text-right">{{ fmt(r.planned_total) }}</td>
                <td class="text-right">{{ fmt(r.actual_total) }}</td>
                <td class="text-right" :class="Number(r.variance) < 0 ? 'pf-neg' : 'pf-pos'">{{ fmt(r.variance) }}</td>
              </tr>
              <tr class="pf-total">
                <td colspan="2"><b>Total</b></td>
                <td class="text-right"><b>{{ fmt(vs.total_planned) }}</b></td>
                <td class="text-right"><b>{{ fmt(vs.total_actual) }}</b></td>
                <td class="text-right"><b>{{ fmt(vs.total_variance) }}</b></td>
              </tr>
            </tbody>
          </q-markup-table>
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
import {
  approveFincaBudget,
  createFincaBudget,
  getFincaBudget,
  getFincaBudgetVsActual,
  listFincaBudgets,
  listFincas,
  listLabors,
  listPlots,
  setFincaBudgetLines,
  type FincaBudgetRow,
  type FincaBudgetVsActual,
} from 'src/features/finca/finca.api';
import { useAclStore } from 'src/stores/acl.store';
import { useContextStore } from 'src/stores/context.store';

const $q = useQuasar();
const acl = useAclStore();
const ctx = useContextStore();

const cargando = ref(false);
const accionando = ref(false);
const budgets = ref<FincaBudgetRow[]>([]);
const fincaOpts = ref<Array<{ value: number; label: string }>>([]);
const laborOpts = ref<Array<{ value: number; label: string }>>([]);
const plotOpts = ref<Array<{ value: number; label: string }>>([]);

interface LineEdit {
  labor_id: number | null;
  plot_id: number | null;
  planned_jornales: string;
  planned_rate: string;
  planned_insumos_amount: string;
}
const lineas = ref<LineEdit[]>([]);

function puede(code: string): boolean {
  const companyId = ctx.activeCompanyId;
  return companyId ? acl.hasPermission(companyId, code) : false;
}
function fmt(v: string): string {
  return Number(v).toLocaleString('es-NI', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

const cols: QTableColumn<FincaBudgetRow>[] = [
  { name: 'finca', label: 'Finca', field: 'finca_name', align: 'left' },
  { name: 'season', label: 'Ciclo', field: 'season_label', align: 'left' },
  { name: 'name', label: 'Nombre', field: 'name', align: 'left' },
  { name: 'status', label: 'Estado', field: 'status', align: 'left' },
  { name: 'acciones', label: '', field: 'id', align: 'right' },
];

async function recargar() {
  cargando.value = true;
  try {
    budgets.value = await listFincaBudgets();
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudieron cargar los presupuestos.') });
  } finally {
    cargando.value = false;
  }
}

async function cargarCatalogos() {
  try {
    const [fincas, labors] = await Promise.all([listFincas(), listLabors()]);
    fincaOpts.value = fincas.map((f) => ({ value: f.finca_id, label: f.name ?? `Finca ${f.finca_id}` }));
    laborOpts.value = labors.map((l) => ({ value: l.id, label: l.name }));
  } catch {
    /* opcional */
  }
}

const sel = ref<FincaBudgetRow | null>(null);

const dlgNuevo = ref(false);
const formNew = reactive<{ finca_id: number | null; season_label: string; name: string }>({ finca_id: null, season_label: '', name: '' });
function abrirNuevo() {
  Object.assign(formNew, { finca_id: null, season_label: '', name: '' });
  dlgNuevo.value = true;
}
async function crear() {
  if (!formNew.finca_id) return;
  accionando.value = true;
  try {
    await createFincaBudget({ finca_id: formNew.finca_id, season_label: formNew.season_label.trim(), name: formNew.name.trim() });
    $q.notify({ type: 'positive', message: 'Presupuesto creado.' });
    dlgNuevo.value = false;
    await recargar();
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo crear.') });
  } finally {
    accionando.value = false;
  }
}

const dlgLineas = ref(false);
async function abrirLineas(b: FincaBudgetRow) {
  sel.value = b;
  lineas.value = [];
  dlgLineas.value = true;
  try {
    plotOpts.value = (await listPlots(b.finca_id)).map((p) => ({ value: p.id, label: `${p.code}${p.name ? ' — ' + p.name : ''}` }));
    const full = await getFincaBudget(b.id);
    lineas.value = full.lines.map((ln) => ({
      labor_id: ln.labor_id,
      plot_id: ln.plot_id,
      planned_jornales: ln.planned_jornales,
      planned_rate: ln.planned_rate,
      planned_insumos_amount: ln.planned_insumos_amount,
    }));
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudieron cargar las líneas.') });
  }
}
function agregarLinea() {
  lineas.value.push({ labor_id: null, plot_id: null, planned_jornales: '0', planned_rate: '0', planned_insumos_amount: '0' });
}
async function guardarLineas() {
  if (!sel.value) return;
  const valid = lineas.value.filter((l) => l.labor_id && l.plot_id);
  accionando.value = true;
  try {
    await setFincaBudgetLines(
      sel.value.id,
      valid.map((l) => ({
        labor_id: l.labor_id as number,
        plot_id: l.plot_id as number,
        planned_jornales: l.planned_jornales || '0',
        planned_rate: l.planned_rate || '0',
        planned_insumos_amount: l.planned_insumos_amount || '0',
      })),
    );
    $q.notify({ type: 'positive', message: 'Líneas guardadas.' });
    dlgLineas.value = false;
    await recargar();
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudieron guardar las líneas.') });
  } finally {
    accionando.value = false;
  }
}

async function aprobar(b: FincaBudgetRow) {
  try {
    await approveFincaBudget(b.id);
    $q.notify({ type: 'positive', message: 'Presupuesto aprobado.' });
    await recargar();
  } catch (e) {
    const code = (e as { response?: { data?: { code?: string } } }).response?.data?.code;
    const msg = code === 'SOD_SELF_APPROVAL' ? 'Debe aprobarlo otra persona (segregación de funciones).' : apiErrorMessage(e, 'No se pudo aprobar.');
    $q.notify({ type: 'negative', message: msg });
  }
}

const dlgVs = ref(false);
const vs = ref<FincaBudgetVsActual | null>(null);
async function abrirVsReal(b: FincaBudgetRow) {
  sel.value = b;
  vs.value = null;
  dlgVs.value = true;
  try {
    vs.value = await getFincaBudgetVsActual(b.id);
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo cargar el comparativo.') });
  }
}

onMounted(async () => {
  await cargarCatalogos();
  await recargar();
});
</script>

<style scoped>
.pf-st {
  border: 1px solid var(--app-border);
  background: transparent;
}
.pf-st--DRAFT {
  color: var(--app-text-muted);
}
.pf-st--APPROVED {
  color: var(--app-secondary);
  border-color: var(--app-secondary);
}
.pf-st--ARCHIVED {
  color: var(--app-text-muted);
  border-color: var(--app-border-strong);
}
.pf-dialog {
  width: 760px;
  max-width: 96vw;
  background: var(--app-surface-strong);
}
.pf-table {
  background: transparent;
}
.pf-neg {
  color: var(--q-negative);
  font-weight: 700;
}
.pf-pos {
  color: var(--q-positive);
  font-weight: 700;
}
.pf-total td {
  border-top: 2px solid var(--app-border-strong);
}
</style>
