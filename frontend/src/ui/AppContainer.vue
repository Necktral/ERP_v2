<template>
  <q-page :class="pagePadClass" class="app-page-container">
    <div class="app-container" :class="{ 'app-container--fluid': fluid }">
      <slot />
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useUiStore } from 'src/stores/ui.store';

defineProps<{ fluid?: boolean }>();

const ui = useUiStore();
const pagePadClass = computed(() => (ui.density === 'compact' ? 'q-pa-sm' : 'q-pa-md'));
</script>
