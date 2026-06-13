<template>
  <q-page class="app-page">
    <PageHeader
      title="Nómina"
      subtitle="Períodos de planilla, configuración del año y exportes legales."
      :loading="loading"
      @refresh="reload"
    >
      <template #actions>
        <q-btn
          unelevated
          no-caps
          color="primary"
          icon="post_add"
          label="Nuevo período"
          :disable="!configActiva"
          @click="openNewPeriod"
        />
      </template>
    </PageHeader>

    <!-- Configuración del año (requisito para crear períodos) -->
    <q-banner v-if="!loading && !configActiva" rounded class="nom-config-banner">
      <template #avatar><q-icon name="settings_suggest" color="warning" /></template>
      <strong>Falta la configuración de nómina del año.</strong>
      Define las tasas de ley (INSS, INATEC, vacaciones, aguinaldo) y la tabla del IR — sin ella no se
      pueden crear períodos.
      <template #action>
        <q-btn
          unelevated
          no-caps
          color="primary"
          label="Crear configuración Nicaragua por defecto"
          :loading="creatingConfig"
          @click="doCreateConfig"
        />
      </template>
    </q-banner>

    <q-banner v-else-if="configActiva" rounded class="nom-config-ok">
      <template #avatar><q-icon name="verified" color="positive" /></template>
      Configuración {{ configActiva.fiscal_year }} activa — INSS laboral
      {{ pct(configActiva.inss_laboral_rate) }} · INATEC {{ pct(configActiva.inatec_rate) }} ·
      vacaciones {{ pct(configActiva.vacation_rate) }} · aguinaldo
      {{ pct(configActiva.thirteenth_month_rate) }} · tabla IR de
      {{ configActiva.ir_brackets.length }} tramos.
    </q-banner>

    <!-- Períodos -->
    <q-table
      class="app-table"
      :rows="periods"
      :columns="columns"
      row-key="id"
      flat
      :loading="loading"
      :pagination="{ rowsPerPage: 25 }"
      no-data-label="Aún no hay períodos. Creá el primero con «Nuevo período»."
      @row-click="(_, row) => abrirPeriodo(row)"
    >
      <template #body-cell-periodo="props">
        <q-td :props="props" class="nom-link">
          {{ etiquetaPeriodo(props.row) }}
        </q-td>
      </template>
      <template #body-cell-status="props">
        <q-td :props="props">
          <q-chip dense :color="statusColor(props.row.status)" text-color="white" :label="statusLabel(props.row.status)" />
        </q-td>
      </template>
      <template #body-cell-acciones="props">
        <q-td :props="props" class="text-right">
          <q-btn flat dense no-caps size="sm" icon="open_in_new" label="Abrir" :to="`/nomina/periodos/${props.row.id}`" />
        </q-td>
      </template>
    </q-table>

    <!-- Diálogo: nuevo período -->
    <q-dialog v-model="newOpen">
      <q-card class="nom-dialog">
        <q-card-section>
          <div class="text-h6">Nuevo período de planilla</div>
          <div class="nom-muted">Las fechas se sugieren según el tipo; ajustalas si hace falta.</div>
        </q-card-section>
        <q-card-section class="app-form">
          <div class="nom-form__row">
            <q-input v-model.number="form.year" outlined dense type="number" label="Año" />
            <q-select
              v-model="form.month"
              outlined
              dense
              emit-value
              map-options
              label="Mes"
              :options="meses"
              @update:model-value="sugerirFechas"
            />
          </div>
          <q-select
            v-model="form.period_type"
            outlined
            dense
            emit-value
            map-options
            label="Tipo de período"
            :options="tiposPeriodo"
            @update:model-value="sugerirFechas"
          />
          <div class="nom-form__row">
            <q-input v-model="form.start_date" outlined dense type="date" label="Inicio" />
            <q-input v-model="form.end_date" outlined dense type="date" label="Fin" />
          </div>
          <div class="nom-form__row">
            <q-input v-model.number="form.working_days" outlined dense type="number" label="Días laborables" />
            <q-input v-model="form.exchange_rate_usd" outlined dense type="number" step="0.0001" label="Tasa USD→NIO" />
          </div>
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat no-caps label="Cancelar" v-close-popup />
          <q-btn
            unelevated
            no-caps
            color="primary"
            label="Crear período"
            :loading="saving"
            :disable="!form.start_date || !form.end_date"
            @click="doCreatePeriod"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>
  </q-page>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue';
import { useRouter } from 'vue-router';
import { useQuasar, type QTableColumn } from 'quasar';
import PageHeader from 'src/components/PageHeader.vue';
import {
  createDefaultConfig,
  createPeriod,
  listConfigs,
  listPeriods,
  type NominaConfig,
  type PayrollPeriod,
  type PeriodType,
} from 'src/features/nomina/nomina.api';

const $q = useQuasar();
const router = useRouter();

const loading = ref(false);
const saving = ref(false);
const creatingConfig = ref(false);
const periods = ref<PayrollPeriod[]>([]);
const configActiva = ref<NominaConfig | null>(null);

const MESES_ES = [
  'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
  'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre',
];

const meses = MESES_ES.map((label, i) => ({ label, value: i + 1 }));

const tiposPeriodo = [
  { label: 'Primera quincena (1–15)', value: 'FIRST_HALF' },
  { label: 'Segunda quincena (16–fin)', value: 'SECOND_HALF' },
  { label: 'Catorcena (14 días)', value: 'CATORCENA' },
  { label: 'Mensual', value: 'MONTHLY' },
];

const STATUS_META: Record<string, { label: string; color: string }> = {
  DRAFT: { label: 'Borrador', color: 'grey-7' },
  IN_REVIEW: { label: 'En revisión', color: 'info' },
  APPROVED: { label: 'Aprobado', color: 'secondary' },
  PAID: { label: 'Pagado', color: 'positive' },
  CLOSED: { label: 'Cerrado', color: 'primary' },
};

const columns: QTableColumn<PayrollPeriod>[] = [
  { name: 'periodo', label: 'Período', field: 'id', align: 'left' },
  { name: 'start_date', label: 'Inicio', field: 'start_date', align: 'left' },
  { name: 'end_date', label: 'Fin', field: 'end_date', align: 'left' },
  { name: 'working_days', label: 'Días', field: 'working_days', align: 'center' },
  { name: 'total_net', label: 'Neto C$', field: (r) => money(r.total_net), align: 'right' },
  { name: 'total_payroll_cost', label: 'Costo total C$', field: (r) => money(r.total_payroll_cost), align: 'right' },
  { name: 'status', label: 'Estado', field: 'status', align: 'center' },
  { name: 'acciones', label: '', field: 'id', align: 'right' },
];

function money(v: string): string {
  const n = Number(v);
  return Number.isFinite(n) ? n.toLocaleString('es-NI', { minimumFractionDigits: 2 }) : v;
}

function pct(v: string): string {
  const n = Number(v);
  return Number.isFinite(n) ? `${(n * 100).toFixed(2).replace(/\.?0+$/, '')}%` : v;
}

function statusLabel(s: string): string {
  return STATUS_META[s]?.label ?? s;
}

function statusColor(s: string): string {
  return STATUS_META[s]?.color ?? 'grey-7';
}

function etiquetaPeriodo(p: PayrollPeriod): string {
  const mes = MESES_ES[p.month - 1] ?? String(p.month);
  const tipo = tiposPeriodo.find((t) => t.value === p.period_type)?.label ?? p.period_type;
  return `${mes} ${p.year} — ${tipo}`;
}

async function reload() {
  loading.value = true;
  try {
    const [configs, rows] = await Promise.all([listConfigs(), listPeriods()]);
    configActiva.value = configs.find((c) => c.is_active) ?? configs[0] ?? null;
    periods.value = rows;
  } catch {
    $q.notify({ type: 'negative', message: 'No se pudo cargar nómina.' });
  } finally {
    loading.value = false;
  }
}

async function doCreateConfig() {
  creatingConfig.value = true;
  try {
    await createDefaultConfig(new Date().getFullYear());
    $q.notify({ type: 'positive', message: 'Configuración de nómina creada (tasas Nicaragua + tabla IR).' });
    await reload();
  } catch {
    $q.notify({ type: 'negative', message: 'No se pudo crear la configuración.' });
  } finally {
    creatingConfig.value = false;
  }
}

// --- nuevo período ---
const newOpen = ref(false);
const form = reactive<{
  year: number;
  month: number;
  period_type: PeriodType;
  start_date: string;
  end_date: string;
  working_days: number;
  exchange_rate_usd: string;
}>({
  year: new Date().getFullYear(),
  month: new Date().getMonth() + 1,
  period_type: 'FIRST_HALF',
  start_date: '',
  end_date: '',
  working_days: 15,
  exchange_rate_usd: '',
});

function sugerirFechas() {
  const y = form.year;
  const m = form.month;
  const fin = new Date(y, m, 0).getDate(); // último día del mes
  const f = (d: number) => `${y}-${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
  if (form.period_type === 'FIRST_HALF') {
    form.start_date = f(1);
    form.end_date = f(15);
    form.working_days = 15;
  } else if (form.period_type === 'SECOND_HALF') {
    form.start_date = f(16);
    form.end_date = f(fin);
    form.working_days = fin - 15;
  } else if (form.period_type === 'MONTHLY') {
    form.start_date = f(1);
    form.end_date = f(fin);
    form.working_days = fin;
  } else {
    form.start_date = f(1);
    form.end_date = f(Math.min(14, fin));
    form.working_days = 14;
  }
}

function openNewPeriod() {
  form.year = new Date().getFullYear();
  form.month = new Date().getMonth() + 1;
  form.period_type = 'FIRST_HALF';
  form.exchange_rate_usd = '';
  sugerirFechas();
  newOpen.value = true;
}

async function doCreatePeriod() {
  saving.value = true;
  try {
    const created = await createPeriod({
      year: form.year,
      month: form.month,
      period_type: form.period_type,
      start_date: form.start_date,
      end_date: form.end_date,
      working_days: form.working_days,
      exchange_rate_usd: form.exchange_rate_usd || null,
    });
    newOpen.value = false;
    $q.notify({ type: 'positive', message: 'Período creado.' });
    await router.push(`/nomina/periodos/${created.id}`);
  } catch (e) {
    const err = e as { response?: { data?: { detail?: string } } };
    $q.notify({
      type: 'negative',
      message: err.response?.data?.detail || 'No se pudo crear el período (¿ya existe ese mes/tipo?).',
    });
  } finally {
    saving.value = false;
  }
}

function abrirPeriodo(p: PayrollPeriod) {
  void router.push(`/nomina/periodos/${p.id}`);
}

onMounted(reload);
</script>

<style scoped>




.nom-config-banner,
.nom-config-ok {
  margin-bottom: var(--app-space-4);
  border: 1px solid var(--app-border-strong);
  background: var(--app-surface-strong);
  font-size: 0.88rem;
}


.app-table :deep(tbody tr) {
  cursor: pointer;
}

.nom-link {
  font-weight: 700;
  color: var(--app-primary);
}

.nom-dialog {
  width: 520px;
  max-width: 94vw;
  background: var(--app-surface-strong);
}

.nom-muted {
  color: var(--app-text-muted);
  font-size: 0.85rem;
}


.nom-form__row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--app-space-3);
}
</style>
