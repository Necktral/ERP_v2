<template>
  <q-page class="app-page">
    <PageHeader
      title="Analítica"
      subtitle="Workspaces de tableros. El token de embed da acceso temporal al tablero sin sesión."
      :loading="loading"
      @refresh="reload"
    />

    <div class="ana-grid">
      <div v-for="w in rows" :key="w.key" class="ana-card">
        <q-icon name="insights" size="28px" class="ana-card__icon" />
        <div class="ana-card__title">{{ w.label || w.key }}</div>
        <q-btn
          flat
          dense
          no-caps
          color="primary"
          icon="link"
          label="Generar acceso"
          @click="generar(w)"
        />
      </div>
      <div v-if="rows.length === 0 && !loading" class="text-caption text-muted">
        No hay workspaces de tableros configurados todavía.
      </div>
    </div>

    <q-dialog v-model="dlgToken">
      <q-card class="app-dialog">
        <q-card-section class="text-h6">Acceso al tablero</q-card-section>
        <q-card-section>
          <pre class="ana-json">{{ tokenInfo }}</pre>
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat no-caps label="Cerrar" v-close-popup />
        </q-card-actions>
      </q-card>
    </q-dialog>
  </q-page>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import PageHeader from 'src/components/PageHeader.vue';
import { apiErrorMessage } from 'src/core/api';
import { useListado } from 'src/core/composables/useListado';
import {
  createEmbedToken,
  listWorkspaces,
  type WorkspaceRow,
} from 'src/features/dashboard/dashboard.api';

const { rows, loading, reload } = useListado<WorkspaceRow>(() => listWorkspaces(), {
  errorMessage: 'No se pudieron cargar los workspaces.',
});

const dlgToken = ref(false);
const tokenInfo = ref('');

async function generar(w: WorkspaceRow) {
  tokenInfo.value = 'Generando…';
  dlgToken.value = true;
  try {
    const r = await createEmbedToken(w.key);
    tokenInfo.value = JSON.stringify(r, null, 2);
  } catch (e) {
    tokenInfo.value = apiErrorMessage(e, 'No se pudo generar el token.');
  }
}
</script>

<style scoped>
.ana-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: var(--app-space-4);
}

.ana-card {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--app-space-2);
  padding: var(--app-space-5);
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-lg);
  background: var(--app-surface);
}

.ana-card__icon {
  color: var(--app-primary);
}

.ana-card__title {
  font-weight: 800;
  color: var(--app-text);
}

.ana-json {
  margin: 0;
  max-height: 50vh;
  overflow: auto;
  font-size: 0.78rem;
  color: var(--app-text);
  background: var(--app-surface);
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-sm);
  padding: var(--app-space-3);
  white-space: pre-wrap;
}
</style>
