<template>
  <q-page>
    <AppContainer>
      <AppPageHeader
        title="Analytics"
        subtitle="Workspace enterprise sobre reporting kernel (Dash embed same-origin)."
      >
        <template #actions>
          <q-btn
            v-for="ws in dashboard.workspaces"
            :key="ws.workspace_key"
            :label="ws.title"
            flat
            :color="ws.workspace_key === dashboard.activeWorkspace ? 'primary' : 'grey-7'"
            @click="openWorkspace(ws.workspace_key)"
          />
          <q-btn label="Refrescar token" color="primary" :loading="dashboard.loading" @click="refreshActive" />
        </template>
      </AppPageHeader>

      <q-banner v-if="dashboard.lastError" class="q-mt-md" dense rounded>
        {{ dashboard.lastError }}
      </q-banner>

      <q-banner v-else-if="!dashboard.hasIframe" class="q-mt-md" dense rounded>
        No hay sesión de analytics activa. Presiona “Refrescar token”.
      </q-banner>

      <div class="q-mt-md analytics-frame-wrap">
        <iframe
          v-if="dashboard.hasIframe"
          class="analytics-frame"
          :src="dashboard.iframeUrl"
          title="Necktral Analytics"
          loading="eager"
        />
      </div>
    </AppContainer>
  </q-page>
</template>

<script setup lang="ts">
import { onMounted } from 'vue';

import AppContainer from 'src/ui/AppContainer.vue';
import AppPageHeader from 'src/ui/AppPageHeader.vue';
import { useDashboardStore } from 'src/stores/dashboard.store';

const dashboard = useDashboardStore();

async function openWorkspace(workspaceKey: string) {
  await dashboard.openWorkspace(workspaceKey);
}

async function refreshActive() {
  await dashboard.openWorkspace(dashboard.activeWorkspace || 'executive');
}

onMounted(async () => {
  await dashboard.loadWorkspaces();
  if (!dashboard.hasIframe) {
    await dashboard.openWorkspace(dashboard.activeWorkspace || 'executive');
  }
});
</script>

<style scoped>
.analytics-frame-wrap {
  width: 100%;
  min-height: calc(100vh - 220px);
  border: 1px solid rgba(0, 0, 0, 0.12);
  border-radius: 8px;
  overflow: hidden;
  background: #fff;
}

.analytics-frame {
  width: 100%;
  min-height: calc(100vh - 220px);
  border: 0;
}
</style>
