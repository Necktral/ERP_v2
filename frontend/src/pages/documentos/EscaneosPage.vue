<template>
  <q-page class="app-page">
    <PageHeader
      title="Documentos escaneados"
      subtitle="Bandeja IDP: subir → OCR → extracción de campos → revisión humana. Extraer nunca integra nada solo."
      :loading="loading"
      @refresh="reload"
    >
      <template #actions>
        <q-btn
          v-if="puede('documents.scan.create')"
          unelevated
          no-caps
          color="primary"
          icon="upload_file"
          label="Subir documento"
          @click="abrirSubir"
        />
      </template>
    </PageHeader>

    <div class="esc-filtros">
      <q-select
        v-model="filtroEstado"
        :options="opcionesEstado"
        dense
        outlined
        emit-value
        map-options
        clearable
        label="Estado"
        class="esc-filtros__sel"
        @update:model-value="reload"
      />
    </div>

    <q-table
      class="app-table"
      :rows="rows"
      :columns="columns"
      row-key="id"
      flat
      :loading="loading"
      :pagination="{ rowsPerPage: 25 }"
      no-data-label="Sin documentos con ese filtro."
    >
      <template #body-cell-tipo="props">
        <q-td :props="props">{{ DOC_TYPE_LABELS[props.row.doc_type] ?? props.row.doc_type }}</q-td>
      </template>
      <template #body-cell-estado="props">
        <q-td :props="props">{{ SCAN_STATUS_LABELS[props.row.status] ?? props.row.status }}</q-td>
      </template>
      <template #body-cell-acciones="props">
        <q-td :props="props" class="text-right esc-acciones">
          <q-btn flat dense no-caps size="sm" icon="visibility" label="Ver" @click="verDetalle(props.row)" />
          <q-btn
            v-if="puede('documents.scan.review') && props.row.status === 'PROCESSED'"
            flat
            dense
            no-caps
            size="sm"
            color="primary"
            label="Extraer"
            @click="extraer(props.row)"
          />
          <q-btn
            v-if="puede('documents.scan.review') && props.row.status === 'EXTRACTED'"
            flat
            dense
            no-caps
            size="sm"
            color="primary"
            label="Revisar"
            @click="verDetalle(props.row)"
          />
        </q-td>
      </template>
    </q-table>

    <!-- Diálogo: subir -->
    <q-dialog v-model="dlgSubir">
      <q-card class="app-dialog">
        <q-card-section class="text-h6">Subir documento escaneado</q-card-section>
        <q-card-section class="app-form">
          <q-select
            v-model="formSubir.doc_type"
            :options="opcionesTipo"
            label="Tipo de documento *"
            outlined
            dense
            emit-value
            map-options
          />
          <q-file
            v-model="formSubir.archivo"
            outlined
            dense
            label="Imagen o PDF *"
            accept="image/*,.pdf"
          >
            <template #prepend><q-icon name="attach_file" /></template>
          </q-file>
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat no-caps label="Cancelar" v-close-popup />
          <q-btn
            unelevated
            no-caps
            color="primary"
            label="Subir"
            :loading="subiendo"
            :disable="!formSubir.archivo"
            @click="subir"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <!-- Diálogo: detalle / revisión -->
    <q-dialog v-model="dlgDetalle">
      <q-card class="app-dialog esc-detalle">
        <q-card-section class="text-h6">
          Documento #{{ detalle?.id }} · {{ SCAN_STATUS_LABELS[detalle?.status ?? ''] ?? detalle?.status }}
        </q-card-section>
        <q-card-section>
          <div class="text-subtitle2 q-mb-xs">Campos extraídos</div>
          <pre class="esc-json">{{ camposTexto }}</pre>
          <div v-if="detalle?.ocr_text" class="text-subtitle2 q-mt-md q-mb-xs">Texto OCR</div>
          <pre v-if="detalle?.ocr_text" class="esc-json esc-json--ocr">{{ detalle.ocr_text }}</pre>
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat no-caps label="Cerrar" v-close-popup />
          <q-btn
            v-if="puede('documents.scan.review') && detalle?.status === 'EXTRACTED'"
            unelevated
            no-caps
            color="primary"
            icon="task_alt"
            label="Aprobar revisión"
            :loading="subiendo"
            @click="aprobarRevision"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>
  </q-page>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from 'vue';
import { useQuasar, type QTableColumn } from 'quasar';
import PageHeader from 'src/components/PageHeader.vue';
import { apiErrorMessage } from 'src/core/api';
import { useListado } from 'src/core/composables/useListado';
import { formatDateTime } from 'src/core/format';
import {
  DOC_TYPE_LABELS,
  extractScan,
  getScan,
  listScans,
  reviewScan,
  SCAN_STATUS_LABELS,
  uploadScan,
  type ScanRow,
} from 'src/features/documents/documents.api';
import { useAclStore } from 'src/stores/acl.store';
import { useContextStore } from 'src/stores/context.store';

const $q = useQuasar();
const acl = useAclStore();
const ctx = useContextStore();

const filtroEstado = ref<string | null>(null);

const { rows, loading, reload } = useListado<ScanRow>(
  () => listScans(filtroEstado.value ?? undefined),
  { errorMessage: 'No se pudieron cargar los documentos.' },
);

function puede(code: string): boolean {
  const companyId = ctx.activeCompanyId;
  return companyId ? acl.hasPermission(companyId, code) : false;
}

const opcionesTipo = Object.entries(DOC_TYPE_LABELS).map(([value, label]) => ({ value, label }));
const opcionesEstado = Object.entries(SCAN_STATUS_LABELS).map(([value, label]) => ({ value, label }));

const columns: QTableColumn<ScanRow>[] = [
  { name: 'id', label: '#', field: 'id', align: 'left' },
  { name: 'tipo', label: 'Tipo', field: 'doc_type', align: 'left' },
  { name: 'estado', label: 'Estado', field: 'status', align: 'left' },
  {
    name: 'creado',
    label: 'Subido',
    field: (r) => (r.created_at ? formatDateTime(String(r.created_at)) : '—'),
    align: 'left',
  },
  { name: 'acciones', label: '', field: 'id', align: 'right' },
];

// --- Subir ---
const dlgSubir = ref(false);
const subiendo = ref(false);
const formSubir = reactive<{ doc_type: string; archivo: File | null }>({
  doc_type: 'GENERAL',
  archivo: null,
});

function abrirSubir() {
  Object.assign(formSubir, { doc_type: 'GENERAL', archivo: null });
  dlgSubir.value = true;
}

function archivoABase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const dataUrl = typeof reader.result === 'string' ? reader.result : '';
      resolve(dataUrl.split(',')[1] ?? '');
    };
    reader.onerror = () => reject(new Error('No se pudo leer el archivo'));
    reader.readAsDataURL(file);
  });
}

async function subir() {
  if (!formSubir.archivo) return;
  subiendo.value = true;
  try {
    const b64 = await archivoABase64(formSubir.archivo);
    await uploadScan(formSubir.doc_type, b64);
    dlgSubir.value = false;
    $q.notify({ type: 'positive', message: 'Documento subido; queda en cola de OCR.' });
    await reload();
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo subir.') });
  } finally {
    subiendo.value = false;
  }
}

// --- Detalle / revisión ---
const dlgDetalle = ref(false);
const detalle = ref<ScanRow | null>(null);

const camposTexto = computed(() =>
  detalle.value?.extracted_fields
    ? JSON.stringify(detalle.value.extracted_fields, null, 2)
    : 'Sin campos extraídos todavía.',
);

async function verDetalle(s: ScanRow) {
  dlgDetalle.value = true;
  detalle.value = s;
  try {
    detalle.value = await getScan(s.id);
  } catch {
    /* se muestra lo de la fila */
  }
}

async function extraer(s: ScanRow) {
  try {
    await extractScan(s.id);
    $q.notify({ type: 'positive', message: 'Extracción ejecutada.' });
    await reload();
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo extraer.') });
  }
}

async function aprobarRevision() {
  if (!detalle.value) return;
  subiendo.value = true;
  try {
    await reviewScan(detalle.value.id, {});
    dlgDetalle.value = false;
    $q.notify({ type: 'positive', message: 'Documento marcado como revisado.' });
    await reload();
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo revisar.') });
  } finally {
    subiendo.value = false;
  }
}
</script>

<style scoped>
.esc-filtros {
  margin-bottom: var(--app-space-3);
}

.esc-filtros__sel {
  width: 240px;
}

.esc-acciones {
  white-space: nowrap;
}

.esc-detalle {
  width: 640px;
}

.esc-json {
  margin: 0;
  max-height: 30vh;
  overflow: auto;
  font-size: 0.78rem;
  color: var(--app-text);
  background: var(--app-surface);
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-sm);
  padding: var(--app-space-3);
  white-space: pre-wrap;
}

.esc-json--ocr {
  color: var(--app-text-muted);
}
</style>
