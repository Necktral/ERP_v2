<template>
  <header class="app-page-header page-header">
    <div class="page-header__text">
      <div class="page-header__title">{{ title }}</div>
      <div v-if="subtitle" class="page-header__subtitle">{{ subtitle }}</div>
    </div>
    <div class="page-header__actions">
      <slot name="actions" />
      <q-btn
        v-if="!hideRefresh"
        flat
        round
        icon="refresh"
        :loading="loading"
        aria-label="Actualizar"
        @click="emit('refresh')"
      />
    </div>
  </header>
</template>

<script setup lang="ts">
defineProps<{
  title: string;
  subtitle?: string;
  loading?: boolean;
  hideRefresh?: boolean;
}>();

const emit = defineEmits<{ refresh: [] }>();
</script>

<style scoped>
.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: var(--app-space-3);
  margin-bottom: var(--app-space-5);
}

.page-header__title {
  font-family: 'Manrope', 'IBM Plex Sans', sans-serif;
  font-size: 1.5rem;
  font-weight: 800;
  color: var(--app-text);
}

.page-header__subtitle {
  color: var(--app-text-muted);
  font-size: 0.85rem;
  max-width: 640px;
}

.page-header__actions {
  display: flex;
  align-items: center;
  gap: var(--app-space-2);
  flex-shrink: 0;
}
</style>
