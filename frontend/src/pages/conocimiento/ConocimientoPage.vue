<template>
  <q-page class="app-page">
    <PageHeader
      title="Conocimiento"
      subtitle="Busca en la documentación interna del sistema. La búsqueda siempre funciona; la síntesis con IA es opcional."
      hide-refresh
    />

    <div class="kno-buscador">
      <q-input
        v-model="consulta"
        outlined
        placeholder="¿Qué querés saber? (ej. cómo se cierra un período)"
        class="kno-buscador__input"
        @keyup.enter="buscar"
      >
        <template #prepend><q-icon name="search" /></template>
      </q-input>
      <q-toggle v-model="conIA" label="Sintetizar con IA" color="primary" />
      <q-btn unelevated no-caps color="primary" label="Buscar" :loading="buscando" @click="buscar" />
    </div>

    <div v-if="respuesta?.answer" class="kno-answer">
      <div class="kno-answer__head">
        <q-icon name="psychology" color="primary" />
        Respuesta sintetizada (IA{{ respuesta.ai_used ? '' : ' no disponible' }})
      </div>
      <p class="kno-answer__text">{{ respuesta.answer }}</p>
    </div>

    <q-list v-if="respuesta" separator class="app-table kno-resultados">
      <q-item v-for="(r, idx) in respuesta.results" :key="idx">
        <q-item-section>
          <q-item-label class="kno-res__heading">{{ r.heading || r.source_path }}</q-item-label>
          <q-item-label caption>{{ r.source_path }}</q-item-label>
          <p class="kno-res__content">{{ r.content }}</p>
        </q-item-section>
      </q-item>
      <q-item v-if="respuesta.results.length === 0">
        <q-item-section class="text-caption text-muted">Sin resultados para esa consulta.</q-item-section>
      </q-item>
    </q-list>
  </q-page>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { useQuasar } from 'quasar';
import PageHeader from 'src/components/PageHeader.vue';
import { apiErrorMessage } from 'src/core/api';
import { searchKnowledge, type KnowledgeResponse } from 'src/features/knowledge/knowledge.api';

const $q = useQuasar();

const consulta = ref('');
const conIA = ref(false);
const buscando = ref(false);
const respuesta = ref<KnowledgeResponse | null>(null);

async function buscar() {
  const q = consulta.value.trim();
  if (!q) return;
  buscando.value = true;
  try {
    respuesta.value = await searchKnowledge(q, { synthesize: conIA.value });
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo buscar.') });
  } finally {
    buscando.value = false;
  }
}
</script>

<style scoped>
.kno-buscador {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--app-space-3);
  margin-bottom: var(--app-space-4);
}

.kno-buscador__input {
  flex: 1;
  min-width: 280px;
}

.kno-answer {
  padding: var(--app-space-4);
  border: 1px solid var(--app-border-strong);
  border-radius: var(--app-radius-lg);
  background: var(--app-surface-strong);
  margin-bottom: var(--app-space-4);
}

.kno-answer__head {
  display: flex;
  align-items: center;
  gap: var(--app-space-2);
  font-weight: 800;
  color: var(--app-text);
  margin-bottom: var(--app-space-2);
}

.kno-answer__text {
  margin: 0;
  color: var(--app-text);
  white-space: pre-wrap;
}

.kno-resultados {
  background: var(--app-surface);
}

.kno-res__heading {
  font-weight: 700;
}

.kno-res__content {
  margin: var(--app-space-1) 0 0;
  font-size: 0.84rem;
  color: var(--app-text-muted);
  white-space: pre-wrap;
}
</style>
