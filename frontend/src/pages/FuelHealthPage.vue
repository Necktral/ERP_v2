<template>
  <AppContainer>
    <AppPageHeader :title="`${labels.fuel} · Estado operativo`" subtitle="API: GET /fuel/health/">
      <template #actions>
        <q-btn outline label="Recargar" :loading="loading" @click="load" />
      </template>
    </AppPageHeader>

    <q-banner v-if="!canRead" dense rounded class="q-mb-md q-mt-md">
      No tienes permiso <b>fuel.shift.read</b> o no hay contexto de empresa.
    </q-banner>

    <q-card v-else class="app-card q-mt-md">
      <q-card-section>
        <div class="row items-center q-gutter-sm">
          <q-badge outline :color="health?.ok ? 'positive' : 'negative'">
            {{ health?.ok ? 'OK' : 'ERROR' }}
          </q-badge>
          <div class="text-caption text-grey-7">
            {{ health ? `modulo: ${health.module}` : 'Sin datos todavia.' }}
          </div>
        </div>

        <q-banner v-if="error" dense rounded class="q-mt-md bg-red-1 text-red-10">
          {{ error }}
        </q-banner>

        <q-separator spaced />

        <q-input
          :model-value="prettyJson"
          type="textarea"
          outlined
          autogrow
          readonly
          label="Respuesta"
        />
      </q-card-section>
    </q-card>
  </AppContainer>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import AppContainer from 'src/ui/AppContainer.vue';
import AppPageHeader from 'src/ui/AppPageHeader.vue';
import { BUSINESS_LABELS } from 'src/shared/ui/business-terms';
import { useAclStore } from 'src/stores/acl.store';
import { useContextStore } from 'src/stores/context.store';
import { getFuelHealth, type FuelHealth } from 'src/services/fuel.service';

const acl = useAclStore();
const ctx = useContextStore();
const labels = BUSINESS_LABELS;

const loading = ref(false);
const health = ref<FuelHealth | null>(null);
const error = ref<string | null>(null);

const canRead = computed(() => {
  const companyId = ctx.activeCompanyId;
  if (!companyId) return false;
  return acl.hasPermission(companyId, 'fuel.shift.read');
});

const prettyJson = computed(() => {
  if (error.value) return '';
  if (!health.value) return '';
  return JSON.stringify(health.value, null, 2);
});

async function load() {
  if (!canRead.value) return;

  loading.value = true;
  error.value = null;

  try {
    health.value = await getFuelHealth();
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    error.value = msg;
    health.value = null;
  } finally {
    loading.value = false;
  }
}

onMounted(() => {
  void load();
});
</script>
