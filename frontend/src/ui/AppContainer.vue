<template>
  <q-page class="app-page-container">
    <div class="app-container" :class="containerClass">
      <slot />
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useUiStore } from 'src/stores/ui.store';

const ui = useUiStore();
const props = defineProps<{ fluid?: boolean }>();
const containerClass = computed(() => ({
  'app-container--fluid': Boolean(props.fluid),
  'app-container--compact': ui.density === 'compact',
}));
</script>
