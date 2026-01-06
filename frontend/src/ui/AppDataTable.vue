<template>
  <q-card class="app-card">
    <q-card-section v-if="title || caption || $slots.toolbar">
      <div class="row items-start justify-between q-col-gutter-md">
        <div class="col">
          <div v-if="title" class="text-subtitle1">{{ title }}</div>
          <div v-if="caption" class="text-caption text-grey-7">{{ caption }}</div>
        </div>

        <div v-if="$slots.toolbar" class="col-auto">
          <div class="row items-center q-gutter-sm">
            <slot name="toolbar" />
          </div>
        </div>
      </div>
    </q-card-section>

    <q-separator v-if="title || caption || $slots.toolbar" />

    <q-card-section class="q-pa-none">
      <q-table v-bind="boundAttrs" class="q-pa-md">
        <template v-for="name in tableSlotNames" :key="name" #[name]="slotProps">
          <slot :name="name" v-bind="slotProps" />
        </template>
      </q-table>
    </q-card-section>
  </q-card>
</template>

<script setup lang="ts">
import { computed, useAttrs, useSlots } from 'vue';

defineProps<{ title?: string; caption?: string }>();

const attrs = useAttrs();
const slots = useSlots();

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const boundAttrs = computed(() => attrs as any);

// “toolbar” es solo del wrapper; no se lo pasamos a QTable
const tableSlotNames = computed(() => Object.keys(slots).filter((n) => n !== 'toolbar'));
</script>
