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
      <q-table v-bind="tableProps" :dense="isDense" :class="tablePadClass">
        <template v-for="name in tableSlotNames" :key="name" #[name]="slotProps">
          <slot :name="name" v-bind="slotProps" />
        </template>
      </q-table>
    </q-card-section>
  </q-card>
</template>

<script setup lang="ts">
import { computed, useSlots } from 'vue';
import { useUiStore } from 'src/stores/ui.store';
import type { QTableProps } from 'quasar';

type AppDataTableProps = { title?: string; caption?: string } & QTableProps;

const props = defineProps<AppDataTableProps>();
const emit = defineEmits<{
  (e: 'row-click', evt: unknown, row: unknown, index: number): void;
}>();
const slots = useSlots();
const ui = useUiStore();

const tableProps = computed<QTableProps>(() => {
  // title/caption son del wrapper; el resto son props de QTable.
  // Con exactOptionalPropertyTypes, no debemos pasar props con valor `undefined`.
  const out: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(props as Record<string, unknown>)) {
    if (key === 'title' || key === 'caption') continue;
    if (value === undefined) continue;
    out[key] = value;
  }
  return out as unknown as QTableProps;
});

// “toolbar” es solo del wrapper; no se lo pasamos a QTable
const tableSlotNames = computed(() => Object.keys(slots).filter((n) => n !== 'toolbar'));

const isCompact = computed(() => ui.density === 'compact');
const gutterClass = computed(() => (isCompact.value ? 'q-col-gutter-sm' : 'q-col-gutter-md'));
const toolbarGutterClass = computed(() => (isCompact.value ? 'q-gutter-xs' : 'q-gutter-sm'));
const tablePadClass = computed(() => (isCompact.value ? 'q-pa-sm' : 'q-pa-md'));

// Si alguien ya pasa dense explícito, lo respetamos; si no, lo activamos en compacto
const isDense = computed(() => {
  if (typeof props.dense === 'boolean') return props.dense;
  return isCompact.value;
});
</script>
