<template>
  <q-page class="app-page">
    <PageHeader
      title="Sesiones de caja"
      subtitle="Historial de cajas: aperturas, cierres y diferencias. Reabrir una caja cerrada requiere aprobación de otra persona."
      :loading="loading"
      @refresh="reload"
    >
      <template #actions>
        <q-btn flat round dense icon="arrow_back" aria-label="Volver" to="/caja" />
      </template>
    </PageHeader>

    <q-table
      class="app-table"
      :rows="rows"
      :columns="columns"
      row-key="id"
      flat
      :loading="loading"
      :pagination="{ rowsPerPage: 25 }"
      no-data-label="Aún no hay sesiones de caja."
    >
      <template #body-cell-estado="props">
        <q-td :props="props">
          {{ CASH_SESSION_STATUS_LABELS[props.row.status] ?? props.row.status }}
        </q-td>
      </template>
      <template #body-cell-apertura="props">
        <q-td :props="props">{{ formatDateTime(props.row.opened_at) }}</q-td>
      </template>
      <template #body-cell-cierre="props">
        <q-td :props="props">{{ formatDateTime(props.row.closed_at) }}</q-td>
      </template>
      <template #body-cell-esperado="props">
        <q-td :props="props">{{ formatMoney(props.row.expected_amount) }}</q-td>
      </template>
      <template #body-cell-contado="props">
        <q-td :props="props">{{ props.row.counted_amount != null ? formatMoney(props.row.counted_amount) : '—' }}</q-td>
      </template>
      <template #body-cell-diferencia="props">
        <q-td
          :props="props"
          :class="Number(props.row.difference_amount ?? 0) === 0 ? '' : 'text-negative text-weight-bold'"
        >
          {{ props.row.difference_amount != null ? formatMoney(props.row.difference_amount) : '—' }}
        </q-td>
      </template>
      <template #body-cell-acciones="props">
        <q-td :props="props" class="text-right">
          <q-btn
            v-if="props.row.status === 'CLOSED' && puedeSolicitarReapertura"
            flat
            dense
            no-caps
            size="sm"
            icon="lock_open"
            label="Solicitar reapertura"
            @click="solicitarReapertura(props.row)"
          />
        </q-td>
      </template>
    </q-table>

    <div v-if="solicitudes.length" class="ses-aprobaciones">
      <div class="text-subtitle2 q-mb-sm">Solicitudes de reapertura pendientes (de esta ventana)</div>
      <q-list dense separator class="app-table">
        <q-item v-for="s in solicitudes" :key="s.id">
          <q-item-section>
            <q-item-label>Sesión #{{ s.sessionId }}</q-item-label>
            <q-item-label caption>Solicitud {{ s.id }}</q-item-label>
          </q-item-section>
          <q-item-section side>
            <q-btn
              v-if="puedeAprobarReapertura"
              dense
              no-caps
              unelevated
              color="primary"
              label="Aprobar (checker)"
              @click="aprobar(s)"
            />
            <span v-else class="text-caption text-muted">Esperando a un aprobador distinto</span>
          </q-item-section>
        </q-item>
      </q-list>
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import { useQuasar, type QTableColumn } from 'quasar';
import PageHeader from 'src/components/PageHeader.vue';
import { apiErrorMessage } from 'src/core/api';
import { useListado } from 'src/core/composables/useListado';
import { formatDateTime, formatMoney } from 'src/core/format';
import {
  approveReopen,
  CASH_SESSION_STATUS_LABELS,
  listCashSessions,
  requestReopenCashSession,
  type CashSessionRow,
} from 'src/features/payments/payments.api';
import { useAclStore } from 'src/stores/acl.store';
import { useContextStore } from 'src/stores/context.store';

const $q = useQuasar();
const acl = useAclStore();
const ctx = useContextStore();

const { rows, loading, reload } = useListado<CashSessionRow>(() => listCashSessions(), {
  errorMessage: 'No se pudieron cargar las sesiones.',
});

const solicitudes = ref<{ id: string; sessionId: number }[]>([]);

function tienePermiso(code: string): boolean {
  const companyId = ctx.activeCompanyId;
  return companyId ? acl.hasPermission(companyId, code) : false;
}

const puedeSolicitarReapertura = computed(() => tienePermiso('payments.cash.reopen.request'));
const puedeAprobarReapertura = computed(() => tienePermiso('payments.cash.reopen.approve'));

const columns: QTableColumn<CashSessionRow>[] = [
  { name: 'id', label: '#', field: 'id', align: 'left' },
  { name: 'estado', label: 'Estado', field: 'status', align: 'left' },
  { name: 'apertura', label: 'Apertura', field: 'opened_at', align: 'left' },
  { name: 'cierre', label: 'Cierre', field: 'closed_at', align: 'left' },
  { name: 'esperado', label: 'Esperado', field: 'expected_amount', align: 'right' },
  { name: 'contado', label: 'Contado', field: 'counted_amount', align: 'right' },
  { name: 'diferencia', label: 'Diferencia', field: 'difference_amount', align: 'right' },
  { name: 'acciones', label: '', field: 'id', align: 'right' },
];

function solicitarReapertura(s: CashSessionRow) {
  $q.dialog({
    title: `Reabrir sesión #${s.id}`,
    message: 'Motivo de la reapertura (lo verá quien apruebe):',
    prompt: { model: '', type: 'text', isValid: (v: string) => v.trim().length >= 5 },
    cancel: { flat: true, noCaps: true, label: 'Cancelar' },
    ok: { unelevated: true, noCaps: true, color: 'primary', label: 'Solicitar' },
    persistent: true,
  }).onOk((motivo: string) => {
    void (async () => {
      try {
        const r = await requestReopenCashSession(s.id, motivo.trim());
        solicitudes.value.push({ id: r.approval_request_id, sessionId: s.id });
        $q.notify({
          type: 'info',
          message: 'Solicitud creada. Otra persona con permiso de aprobación debe autorizarla.',
        });
      } catch (e) {
        $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo solicitar.') });
      }
    })();
  });
}

async function aprobar(s: { id: string; sessionId: number }) {
  try {
    await approveReopen(s.id);
    solicitudes.value = solicitudes.value.filter((x) => x.id !== s.id);
    $q.notify({ type: 'positive', message: `Sesión #${s.sessionId} reabierta.` });
    await reload();
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo aprobar (¿mismo usuario que solicitó?).') });
  }
}
</script>

<style scoped>
.ses-aprobaciones {
  margin-top: var(--app-space-5);
}
</style>
