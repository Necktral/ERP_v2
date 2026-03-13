<template>
  <div class="app-page-header" :class="headerClass">
    <div class="app-page-header__zone app-page-header__zone--context">
      <div :class="titleClass">{{ title }}</div>
      <div v-if="subtitle" class="app-page-header__subtitle">
        {{ subtitle }}
      </div>

      <div v-if="$slots.badges" class="row items-center q-gutter-xs q-mt-sm">
        <slot name="badges" />
      </div>
    </div>

    <div v-if="$slots.actions" class="app-page-header__zone app-page-header__zone--actions">
      <div class="row items-center" :class="actionsGutterClass">
        <slot name="actions" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useUiStore } from 'src/stores/ui.store';

defineProps<{
  title: string;
  subtitle?: string;
}>();

const ui = useUiStore();
const isCompact = computed(() => ui.density === 'compact');
const actionsGutterClass = computed(() => (isCompact.value ? 'q-gutter-xs' : 'q-gutter-sm'));
const titleClass = computed(() => (isCompact.value ? 'text-subtitle1' : 'text-h6'));
const headerClass = computed(() => (isCompact.value ? 'app-page-header--compact' : ''));
</script>
