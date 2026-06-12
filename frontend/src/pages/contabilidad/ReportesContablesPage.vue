<template>
  <q-page class="app-page">
    <PageHeader
      title="Reportes contables"
      subtitle="Balanza de comprobación, mayor por cuenta, estado de resultados y balance general."
      :loading="cargando"
      @refresh="cargar"
    />

    <div class="repc-filtros">
      <q-select
        v-model="reporte"
        :options="opcionesReporte"
        dense
        outlined
        emit-value
        map-options
        label="Reporte"
        class="repc-filtros__sel"
        @update:model-value="cargar"
      />
      <q-input
        v-model="periodo"
        dense
        outlined
        label="Período (AAAA-MM)"
        class="repc-filtros__per"
        :rules="[(v) => !v || /^\d{4}-\d{2}$/.test(v) || 'Formato AAAA-MM']"
        @keyup.enter="cargar"
      />
      <q-input
        v-if="reporte === 'general-ledger'"
        v-model="cuenta"
        dense
        outlined
        label="Código de cuenta *"
        class="repc-filtros__per"
        @keyup.enter="cargar"
      />
      <q-btn unelevated no-caps color="primary" icon="search" label="Consultar" @click="cargar" />
    </div>

    <q-table
      v-if="filas.length"
      class="app-table"
      :rows="filas"
      :columns="columnasDinamicas"
      row-key="__idx"
      flat
      dense
      :pagination="{ rowsPerPage: 50 }"
    />
    <q-banner v-else class="repc-aviso" rounded>
      <template #avatar><q-icon name="info" color="primary" /></template>
      {{ mensaje }}
    </q-banner>
  </q-page>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import { useQuasar, type QTableColumn } from 'quasar';
import PageHeader from 'src/components/PageHeader.vue';
import { apiErrorMessage } from 'src/core/api';
import { formatMoney } from 'src/core/format';
import { getAccountingReport, type ReportKey } from 'src/features/accounting/accounting.api';

const $q = useQuasar();

const reporte = ref<ReportKey>('trial-balance');
const periodo = ref('');
const cuenta = ref('');
const cargando = ref(false);
const filas = ref<Record<string, unknown>[]>([]);
const mensaje = ref('Elegí el reporte y el período, y consultá.');

const opcionesReporte = [
  { value: 'trial-balance', label: 'Balanza de comprobación' },
  { value: 'general-ledger', label: 'Mayor por cuenta' },
  { value: 'pnl', label: 'Estado de resultados (P&G)' },
  { value: 'balance-sheet', label: 'Balance general' },
];

// Columnas derivadas de las claves de la primera fila (los datasets varían por reporte).
const columnasDinamicas = computed<QTableColumn[]>(() => {
  if (!filas.value.length) return [];
  const primera = filas.value[0]!;
  return Object.keys(primera)
    .filter((k) => k !== '__idx')
    .map((k) => ({
      name: k,
      label: etiqueta(k),
      field: (row: Record<string, unknown>) => formatearCelda(k, row[k]),
      align: esNumerica(primera[k]) ? ('right' as const) : ('left' as const),
      sortable: true,
    }));
});

const ETIQUETAS: Record<string, string> = {
  account_code: 'Cuenta',
  account_name: 'Nombre',
  account_type: 'Tipo',
  debit: 'Debe',
  credit: 'Haber',
  debit_total: 'Debe',
  credit_total: 'Haber',
  balance: 'Saldo',
  opening_balance: 'Saldo inicial',
  closing_balance: 'Saldo final',
  entry_date: 'Fecha',
  description: 'Descripción',
  amount: 'Monto',
  total: 'Total',
};

function etiqueta(k: string): string {
  return ETIQUETAS[k] ?? k.replaceAll('_', ' ');
}

function esNumerica(v: unknown): boolean {
  return typeof v === 'number' || (typeof v === 'string' && v !== '' && !Number.isNaN(Number(v)));
}

const CLAVES_MONTO = new Set([
  'debit', 'credit', 'debit_total', 'credit_total', 'balance',
  'opening_balance', 'closing_balance', 'amount', 'total',
]);

function formatearCelda(k: string, v: unknown): string {
  if (v == null) return '—';
  if (CLAVES_MONTO.has(k) && esNumerica(v)) return formatMoney(v as string);
  if (typeof v === 'string') return v;
  if (typeof v === 'number' || typeof v === 'boolean' || typeof v === 'bigint') return String(v);
  try {
    return JSON.stringify(v);
  } catch {
    return '—';
  }
}

async function cargar() {
  cargando.value = true;
  try {
    const params: Record<string, string | number> = {};
    if (/^\d{4}-\d{2}$/.test(periodo.value)) {
      const [y, m] = periodo.value.split('-').map(Number);
      params.year = y!;
      params.month = m!;
    }
    if (reporte.value === 'general-ledger') {
      if (!cuenta.value.trim()) {
        mensaje.value = 'El mayor requiere un código de cuenta.';
        filas.value = [];
        return;
      }
      params.account_code = cuenta.value.trim();
    }
    const r = await getAccountingReport(reporte.value, params);
    filas.value = r.results.map((row, i) => ({ ...row, __idx: i }));
    mensaje.value = filas.value.length ? '' : 'El reporte no devolvió filas para ese período.';
  } catch (e) {
    filas.value = [];
    mensaje.value = apiErrorMessage(e, 'No se pudo cargar el reporte.');
    $q.notify({ type: 'negative', message: mensaje.value });
  } finally {
    cargando.value = false;
  }
}
</script>

<style scoped>
.repc-filtros {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  gap: var(--app-space-3);
  margin-bottom: var(--app-space-4);
}

.repc-filtros__sel {
  width: 260px;
}

.repc-filtros__per {
  width: 180px;
}

.repc-aviso {
  background: var(--app-surface);
  border: 1px solid var(--app-border);
  color: var(--app-text-muted);
}
</style>
