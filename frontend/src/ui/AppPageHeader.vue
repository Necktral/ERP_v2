<template>
  <div class="row items-start justify-between q-col-gutter-md">
    <div class="col">
      <div class="text-h6">{{ title }}</div>
      <div v-if="subtitle" class="text-caption text-grey-7">
        {{ subtitle }}
      </div>

      <div v-if="$slots.badges" class="row items-center q-gutter-xs q-mt-xs">
        <slot name="badges" />
      </div>
    </div>

    <div v-if="$slots.actions" class="col-auto">
      <div class="row items-center q-gutter-sm">
        <slot name="actions" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  title: string;
  subtitle?: string;
}>();
</script>
