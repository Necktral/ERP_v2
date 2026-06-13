<template>
  <q-page class="app-page">
    <PageHeader
      title="Diario contable"
      subtitle="Borradores generados por la operación (SoD: quien aprueba no es quien generó) y asientos posteados con reversa."
      :loading="cargando"
      @refresh="recargar"
    >
      <template #actions>
        <q-btn
          v-if="puede('accounting.journal_draft.approve')"
          outline
          no-caps
          color="primary"
          icon="task_alt"
          label="Aprobar validados"
          :loading="accionando"
          @click="aprobar"
        />
        <q-btn
          v-if="puede('accounting.journal_draft.post')"
          unelevated
          no-caps
          color="primary"
          icon="publish"
          label="Postear aprobados"
          :loading="accionando"
          @click="postear"
        />
      </template>
    </PageHeader>

    <q-tabs
      v-model="tab"
      dense
      no-caps
      align="left"
      class="dia-tabs"
      active-color="primary"
      indicator-color="primary"
    >
      <q-tab name="borradores" icon="edit_note" label="Borradores" />
      <q-tab v-if="puede('accounting.journal_entry.read')" name="asientos" icon="menu_book" label="Asientos" />
    </q-tabs>
    <q-separator class="q-mb-md" />

    <q-tab-panels v-model="tab" animated class="dia-panels">
      <q-tab-panel name="borradores" class="q-pa-none">
        <div class="dia-filtros">
          <q-select
            v-model="filtroEstado"
            :options="opcionesEstado"
            dense
            outlined
            emit-value
            map-options
            clearable
            label="Estado"
            class="dia-filtros__sel"
            @update:model-value="recargar"
          />
        </div>
        <q-table
          class="app-table"
          :rows="borradores"
          :columns="columnasBorrador"
          row-key="id"
          flat
          :loading="cargando"
          :pagination="{ rowsPerPage: 25 }"
          no-data-label="Sin borradores con ese filtro."
        >
          <template #body-cell-estado="props">
            <q-td :props="props">
              <EstadoChip :estado="props.row.state" :map="MAPA_DRAFT" />
              <q-icon
                v-if="props.row.validation_passed === false"
                name="error"
                color="negative"
                size="18px"
              >
                <q-tooltip>La validación falló</q-tooltip>
              </q-icon>
            </q-td>
          </template>
          <template #body-cell-debe="props">
            <q-td :props="props">{{ formatMoney(props.row.total_debit) }}</q-td>
          </template>
          <template #body-cell-haber="props">
            <q-td :props="props">{{ formatMoney(props.row.total_credit) }}</q-td>
          </template>
          <template #body-cell-generado="props">
            <q-td :props="props">{{ formatDateTime(props.row.generated_at) }}</q-td>
          </template>
        </q-table>
      </q-tab-panel>

      <q-tab-panel name="asientos" class="q-pa-none">
        <q-table
          class="app-table"
          :rows="asientos"
          :columns="columnasAsiento"
          row-key="id"
          flat
          :loading="cargando"
          :pagination="{ rowsPerPage: 25 }"
          no-data-label="Sin asientos posteados."
        >
          <template #body-cell-fecha="props">
            <q-td :props="props">{{ formatDate(props.row.entry_date) }}</q-td>
          </template>
          <template #body-cell-debe="props">
            <q-td :props="props">{{ formatMoney(props.row.debit_total) }}</q-td>
          </template>
          <template #body-cell-haber="props">
            <q-td :props="props">{{ formatMoney(props.row.credit_total) }}</q-td>
          </template>
          <template #body-cell-acciones="props">
            <q-td :props="props" class="text-right">
              <q-btn
                v-if="puede('accounting.journal_entry.reverse')"
                flat
                dense
                no-caps
                size="sm"
                color="negative"
                icon="undo"
                label="Reversar"
                @click="reversar(props.row)"
              />
            </q-td>
          </template>
        </q-table>
      </q-tab-panel>
    </q-tab-panels>
  </q-page>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { useQuasar, type QTableColumn } from 'quasar';
import PageHeader from 'src/components/PageHeader.vue';
import EstadoChip, { type EstadoEstilo } from 'src/components/EstadoChip.vue';
import { apiErrorMessage } from 'src/core/api';
import { formatDate, formatDateTime, formatMoney } from 'src/core/format';
import {
  approveDrafts,
  DRAFT_STATE_LABELS,
  listJournalDrafts,
  listJournalEntries,
  postDrafts,
  reverseJournalEntry,
  type JournalDraftRow,
  type JournalEntryRow,
} from 'src/features/accounting/accounting.api';
import { useAclStore } from 'src/stores/acl.store';
import { useContextStore } from 'src/stores/context.store';

const $q = useQuasar();
const acl = useAclStore();
const ctx = useContextStore();

function estiloDraft(code: string, label: string): EstadoEstilo {
  const estilo: EstadoEstilo = {
    label,
    color:
      code === 'POSTED'
        ? 'secondary'
        : code === 'EXCEPTION'
          ? 'negative'
          : code === 'APPROVED_FOR_POSTING'
            ? 'primary'
            : 'grey-7',
    outline: code !== 'POSTED',
  };
  if (code === 'POSTED') {
    estilo.textColor = 'white';
  }
  return estilo;
}

const MAPA_DRAFT: Record<string, EstadoEstilo> = Object.fromEntries(
  Object.entries(DRAFT_STATE_LABELS).map(([code, label]) => [code, estiloDraft(code, label)]),
);

const tab = ref('borradores');
const cargando = ref(false);
const accionando = ref(false);
const filtroEstado = ref<string | null>(null);
const borradores = ref<JournalDraftRow[]>([]);
const asientos = ref<JournalEntryRow[]>([]);

function puede(code: string): boolean {
  const companyId = ctx.activeCompanyId;
  return companyId ? acl.hasPermission(companyId, code) : false;
}

const opcionesEstado = Object.entries(DRAFT_STATE_LABELS).map(([value, label]) => ({ value, label }));

const columnasBorrador: QTableColumn<JournalDraftRow>[] = [
  { name: 'id', label: '#', field: 'id', align: 'left' },
  { name: 'estado', label: 'Estado', field: 'state', align: 'left' },
  { name: 'debe', label: 'Debe', field: 'total_debit', align: 'right' },
  { name: 'haber', label: 'Haber', field: 'total_credit', align: 'right' },
  { name: 'generado', label: 'Generado', field: 'generated_at', align: 'left' },
  { name: 'evento', label: 'Evento', field: 'economic_event_id', align: 'left' },
];

const columnasAsiento: QTableColumn<JournalEntryRow>[] = [
  { name: 'id', label: '#', field: 'id', align: 'left' },
  { name: 'fecha', label: 'Fecha', field: 'entry_date', align: 'left' },
  { name: 'descripcion', label: 'Descripción', field: 'description', align: 'left' },
  { name: 'debe', label: 'Debe', field: 'debit_total', align: 'right' },
  { name: 'haber', label: 'Haber', field: 'credit_total', align: 'right' },
  { name: 'acciones', label: '', field: 'id', align: 'right' },
];

async function recargar() {
  cargando.value = true;
  try {
    const tareas: Promise<void>[] = [
      listJournalDrafts(filtroEstado.value ?? undefined).then((r) => {
        borradores.value = r;
      }),
    ];
    if (puede('accounting.journal_entry.read')) {
      tareas.push(
        listJournalEntries().then((r) => {
          asientos.value = r;
        }),
      );
    }
    await Promise.all(tareas);
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo cargar el diario.') });
  } finally {
    cargando.value = false;
  }
}

async function aprobar() {
  accionando.value = true;
  try {
    const r = await approveDrafts();
    $q.notify({
      type: 'positive',
      message: `Aprobados ${r.approved} de ${r.attempted} (omitidos ${r.skipped}).`,
    });
    await recargar();
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo aprobar (¿SoD: vos generaste estos borradores?).') });
  } finally {
    accionando.value = false;
  }
}

async function postear() {
  accionando.value = true;
  try {
    await postDrafts();
    $q.notify({ type: 'positive', message: 'Borradores aprobados posteados al diario.' });
    await recargar();
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo postear.') });
  } finally {
    accionando.value = false;
  }
}

function reversar(a: JournalEntryRow) {
  $q.dialog({
    title: `Reversar asiento #${a.id}`,
    message: 'Motivo de la reversa (genera el asiento contrario):',
    prompt: { model: '', type: 'text', isValid: (v: string) => v.trim().length >= 5 },
    cancel: { flat: true, noCaps: true, label: 'Cancelar' },
    ok: { unelevated: true, noCaps: true, color: 'negative', label: 'Reversar' },
    persistent: true,
  }).onOk((motivo: string) => {
    void (async () => {
      try {
        await reverseJournalEntry(a.id, motivo.trim());
        $q.notify({ type: 'positive', message: 'Asiento reversado.' });
        await recargar();
      } catch (e) {
        $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo reversar.') });
      }
    })();
  });
}

onMounted(recargar);
</script>

<style scoped>
.dia-tabs {
  color: var(--app-text-muted);
}

.dia-panels {
  background: transparent;
}

.dia-filtros {
  margin-bottom: var(--app-space-3);
}

.dia-filtros__sel {
  width: 220px;
}
</style>
