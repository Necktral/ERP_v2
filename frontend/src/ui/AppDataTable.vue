<template>
  <q-card class="app-card">
    <q-card-section v-if="title || caption || $slots.toolbar">
      <div class="row items-start justify-between" :class="gutterClass">
        <div class="col">
          <div v-if="title" class="text-subtitle1">{{ title }}</div>
          <div v-if="caption" class="text-caption text-grey-7">{{ caption }}</div>
        </div>

        <div v-if="$slots.toolbar" class="col-auto">
          <div class="row items-center" :class="toolbarGutterClass">
            <slot name="toolbar" />
          </div>
        </div>
      </div>
    </q-card-section>

    <q-separator v-if="title || caption || $slots.toolbar" />

    <q-card-section class="q-pa-none">
      <q-table v-bind="boundAttrs" :dense="isDense" :class="tablePadClass">
        <template v-for="name in tableSlotNames" :key="name" #[name]="slotProps">
          <slot :name="name" v-bind="slotProps" />
        </template>
      </q-table>
    </q-card-section>
  </q-card>
</template>

<script setup lang="ts">
import { computed, useAttrs, useSlots } from 'vue';
import { useUiStore } from 'src/stores/ui.store';

defineProps<{ title?: string; caption?: string }>();

const attrs = useAttrs();
const slots = useSlots();
const ui = useUiStore();

const boundAttrs = computed(() => attrs as Record<string, unknown>);

// “toolbar” es solo del wrapper; no se lo pasamos a QTable
const tableSlotNames = computed(() => Object.keys(slots).filter((n) => n !== 'toolbar'));

const isCompact = computed(() => ui.density === 'compact');
const gutterClass = computed(() => (isCompact.value ? 'q-col-gutter-sm' : 'q-col-gutter-md'));
const toolbarGutterClass = computed(() => (isCompact.value ? 'q-gutter-xs' : 'q-gutter-sm'));
const tablePadClass = computed(() => (isCompact.value ? 'q-pa-sm' : 'q-pa-md'));

// Si alguien ya pasa dense explícito, lo respetamos; si no, lo activamos en compacto
const isDense = computed(() => {
  const dense = boundAttrs.value.dense;
  if (typeof dense === 'boolean') return dense;
  return isCompact.value;
});
</script>
