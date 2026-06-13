<template>
  <q-page class="app-page">
    <PageHeader
      title="Configuración fiscal"
      subtitle="Modo fiscal de la sucursal activa: cómo se numeran e imprimen los documentos fiscales."
      :loading="loading"
      @refresh="cargar"
    >
      <template #actions>
        <q-btn flat round dense icon="arrow_back" aria-label="Volver" to="/facturacion" />
      </template>
    </PageHeader>

    <div class="cfg-card">
      <div class="app-form">
        <q-select
          v-model="form.fiscal_mode"
          :options="opcionesModo"
          label="Modo fiscal"
          outlined
          dense
          emit-value
          map-options
          :readonly="!puedeEditar"
          hint="NOOP = sin integración fiscal (numeración interna)."
        />
        <q-input
          v-model="form.adapter_code"
          outlined
          dense
          label="Adaptador de impresora"
          :readonly="!puedeEditar"
        />
        <q-toggle
          v-model="form.print_required"
          label="Impresión obligatoria para cerrar la venta"
          color="primary"
          :disable="!puedeEditar"
        />
        <q-toggle
          v-model="form.strict_integrity"
          label="Integridad estricta (rechaza si la impresora no confirma)"
          color="primary"
          :disable="!puedeEditar"
        />
        <q-input
          v-model.number="form.contingency_max_attempts"
          outlined
          dense
          type="number"
          min="1"
          max="20"
          label="Máx. reintentos antes de contingencia"
          :readonly="!puedeEditar"
        />
        <q-toggle
          v-model="form.is_active"
          label="Configuración activa"
          color="primary"
          :disable="!puedeEditar"
        />
      </div>
      <div v-if="puedeEditar" class="q-mt-md">
        <q-btn
          unelevated
          no-caps
          color="primary"
          icon="save"
          label="Guardar configuración"
          :loading="guardando"
          @click="guardar"
        />
      </div>
      <div v-else class="text-caption text-muted q-mt-md">
        Solo lectura: no tenés permiso para cambiar la configuración fiscal.
      </div>
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import { useQuasar } from 'quasar';
import PageHeader from 'src/components/PageHeader.vue';
import { apiErrorMessage } from 'src/core/api';
import { getFiscalConfig, updateFiscalConfig } from 'src/features/billing/billing.api';
import { useAclStore } from 'src/stores/acl.store';
import { useContextStore } from 'src/stores/context.store';

const $q = useQuasar();
const acl = useAclStore();
const ctx = useContextStore();

const loading = ref(false);
const guardando = ref(false);

const form = reactive({
  fiscal_mode: 'NOOP',
  adapter_code: '',
  print_required: false,
  strict_integrity: false,
  contingency_max_attempts: 3,
  is_active: true,
});

const opcionesModo = [
  { value: 'NOOP', label: 'Sin integración (NOOP)' },
  { value: 'A', label: 'Modo A' },
  { value: 'B', label: 'Modo B' },
];

const puedeEditar = computed(() => {
  const companyId = ctx.activeCompanyId;
  return companyId ? acl.hasPermission(companyId, 'billing.fiscal.config.update') : false;
});

async function cargar() {
  loading.value = true;
  try {
    Object.assign(form, await getFiscalConfig());
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo cargar la configuración.') });
  } finally {
    loading.value = false;
  }
}

async function guardar() {
  guardando.value = true;
  try {
    Object.assign(form, await updateFiscalConfig({ ...form }));
    $q.notify({ type: 'positive', message: 'Configuración fiscal guardada.' });
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo guardar.') });
  } finally {
    guardando.value = false;
  }
}

onMounted(cargar);
</script>

<style scoped>
.cfg-card {
  max-width: 560px;
  padding: var(--app-space-5);
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-lg);
  background: var(--app-surface);
}
</style>
