<template>
  <q-page class="app-page">
    <PageHeader
      title="Cierre diario de la estación"
      subtitle="Consolidado del día: litros/galones despachados, ventas por tipo y por método de pago, alertas."
      :loading="cargando"
      @refresh="cargar"
    >
      <template #actions>
        <q-btn flat round dense icon="arrow_back" aria-label="Volver" to="/estacion" />
      </template>
    </PageHeader>

    <div class="rep-filtros">
      <q-input v-model="fecha" dense outlined type="date" label="Fecha" @update:model-value="cargar" />
    </div>

    <pre v-if="reporte" class="rep-json">{{ reporte }}</pre>
    <q-banner v-else class="rep-aviso" rounded>
      <template #avatar><q-icon name="info" color="primary" /></template>
      Elegí una fecha para ver el cierre diario.
    </q-banner>
  </q-page>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { useQuasar } from 'quasar';
import PageHeader from 'src/components/PageHeader.vue';
import { apiErrorMessage } from 'src/core/api';
import { getDailyCloseReport } from 'src/features/fuel/fuel.api';

const $q = useQuasar();
const fecha = ref(new Date().toISOString().slice(0, 10));
const cargando = ref(false);
const reporte = ref('');

async function cargar() {
  cargando.value = true;
  try {
    const r = await getDailyCloseReport(fecha.value);
    reporte.value = JSON.stringify(r, null, 2);
  } catch (e) {
    reporte.value = '';
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo cargar el cierre diario.') });
  } finally {
    cargando.value = false;
  }
}

onMounted(cargar);
</script>

<style scoped>
.rep-filtros {
  margin-bottom: var(--app-space-4);
  max-width: 220px;
}

.rep-json {
  margin: 0;
  font-size: 0.8rem;
  color: var(--app-text);
  background: var(--app-surface);
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-lg);
  padding: var(--app-space-4);
  white-space: pre-wrap;
}

.rep-aviso {
  background: var(--app-surface);
  border: 1px solid var(--app-border);
  color: var(--app-text-muted);
}
</style>
