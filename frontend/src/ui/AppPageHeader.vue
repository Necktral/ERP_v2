<template>
  <div class="row items-start justify-between" :class="gutterClass">
    <div class="col">
      <div :class="titleClass">{{ title }}</div>
      <div v-if="subtitle" class="text-caption text-grey-7">
        {{ subtitle }}
      </div>

      <div v-if="$slots.badges" class="row items-center q-gutter-xs q-mt-xs">
        <slot name="badges" />
      </div>
    </div>

    <div v-if="$slots.actions" class="col-auto">
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
const gutterClass = computed(() => (isCompact.value ? 'q-col-gutter-sm' : 'q-col-gutter-md'));
const actionsGutterClass = computed(() => (isCompact.value ? 'q-gutter-xs' : 'q-gutter-sm'));
const titleClass = computed(() => (isCompact.value ? 'text-subtitle1' : 'text-h6'));
</script>
