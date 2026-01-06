<template>
  <q-page class="q-pa-md">
    <div class="app-container" :class="{ 'app-container--fluid': fluid }">
      <slot />
    </div>
  </q-page>
</template>

<script setup lang="ts">
defineProps<{ fluid?: boolean }>();
</script>
