<template>
  <q-page class="app-page">
    <PageHeader
      title="Costos de finca"
      subtitle="Costo real por finca (jornales de planilla + insumos) y su reclasificación al libro contable."
      :loading="cargando"
      @refresh="cargar"
    >
      <template #actions>
        <q-btn flat round dense icon="arrow_back" aria-label="Volver" to="/finca" />
      </template>
    </PageHeader>

    <div class="cos-filtros">
      <q-select
        v-model="fincaId"
        :options="opcionesFinca"
        dense
        outlined
        emit-value
        map-options
        clearable
        label="Finca"
        class="cos-filtros__sel"
        @update:model-value="cargar"
      />
      <q-input v-model="desde" dense outlined type="date" label="Desde" @update:model-value="cargar" />
      <q-input v-model="hasta" dense outlined type="date" label="Hasta" @update:model-value="cargar" />
      <q-btn
        v-if="puedeContabilizar && fincaId != null"
        unelevated
        no-caps
        color="primary"
        icon="receipt_long"
        label="Contabilizar a GL"
        :loading="posteando"
        @click="contabilizar"
      />
    </div>

    <pre v-if="reporte" class="cos-json">{{ reporte }}</pre>
    <q-banner v-else class="cos-aviso" rounded>
      <template #avatar><q-icon name="info" color="primary" /></template>
      Elegí filtros para ver el costo real consolidado.
    </q-banner>
  </q-page>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useQuasar } from 'quasar';
import PageHeader from 'src/components/PageHeader.vue';
import { apiErrorMessage } from 'src/core/api';
import {
  getFincaCostReport,
  listFincas,
  postFincaCostToGL,
  type FincaRow,
} from 'src/features/finca/finca.api';
import { useAclStore } from 'src/stores/acl.store';
import { useContextStore } from 'src/stores/context.store';

const $q = useQuasar();
const acl = useAclStore();
const ctx = useContextStore();

const fincas = ref<FincaRow[]>([]);
const fincaId = ref<number | null>(null);
const desde = ref('');
const hasta = ref('');
const cargando = ref(false);
const posteando = ref(false);
const reporte = ref('');

const opcionesFinca = computed(() =>
  fincas.value.map((f) => ({ value: Number(f.finca_id), label: (f.name as string) ?? `#${f.finca_id}` })),
);

const puedeContabilizar = computed(() => {
  const companyId = ctx.activeCompanyId;
  return companyId ? acl.hasPermission(companyId, 'finca.cost.post') : false;
});

async function cargar() {
  cargando.value = true;
  try {
    const r = await getFincaCostReport({
      ...(fincaId.value ? { finca_id: fincaId.value } : {}),
      ...(desde.value ? { date_from: desde.value } : {}),
      ...(hasta.value ? { date_to: hasta.value } : {}),
    });
    reporte.value = JSON.stringify(r, null, 2);
  } catch (e) {
    reporte.value = '';
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo cargar el costo.') });
  } finally {
    cargando.value = false;
  }
}

function contabilizar() {
  if (fincaId.value == null) return;
  $q.dialog({
    title: 'Contabilizar costo de finca',
    message:
      'Genera el asiento de reclasificación del costo real (jornales + insumos) de la finca al período elegido. ¿Continuar?',
    cancel: { flat: true, noCaps: true, label: 'Cancelar' },
    ok: { unelevated: true, noCaps: true, color: 'primary', label: 'Contabilizar' },
  }).onOk(() => {
    void (async () => {
      posteando.value = true;
      try {
        await postFincaCostToGL({
          finca_id: fincaId.value!,
          ...(desde.value ? { date_from: desde.value } : {}),
          ...(hasta.value ? { date_to: hasta.value } : {}),
        });
        $q.notify({ type: 'positive', message: 'Costo contabilizado (borrador en el diario).' });
        await cargar();
      } catch (e) {
        $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo contabilizar.') });
      } finally {
        posteando.value = false;
      }
    })();
  });
}

onMounted(async () => {
  try {
    fincas.value = await listFincas();
  } catch {
    /* sin fincas */
  }
  await cargar();
});
</script>

<style scoped>
.cos-filtros {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--app-space-3);
  margin-bottom: var(--app-space-4);
}

.cos-filtros__sel {
  width: 240px;
}

.cos-json {
  margin: 0;
  font-size: 0.8rem;
  color: var(--app-text);
  background: var(--app-surface);
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-lg);
  padding: var(--app-space-4);
  white-space: pre-wrap;
}

.cos-aviso {
  background: var(--app-surface);
  border: 1px solid var(--app-border);
  color: var(--app-text-muted);
}
</style>
