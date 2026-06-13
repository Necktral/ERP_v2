<template>
  <q-layout view="hHh lpR fFf">
    <!-- Estado del servidor visible desde el login (clave en el cel/campo) -->
    <ConnectivityDot class="auth-conn" />
    <q-page-container>
      <router-view />
    </q-page-container>
    <router-link v-if="!isEnrollRoute" to="/enrolar" class="auth-enroll">
      <q-icon name="phonelink_lock" size="14px" />
      {{ enrolled ? 'Dispositivo enrolado' : 'Enrolar este dispositivo' }}
    </router-link>
  </q-layout>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useRoute } from 'vue-router';
import ConnectivityDot from 'src/components/ConnectivityDot.vue';
import { isEnrolled } from 'src/core/device';

const route = useRoute();
const isEnrollRoute = computed(() => route.path.startsWith('/enrolar'));
const enrolled = isEnrolled();
</script>

<style scoped>
.auth-conn {
  position: fixed;
  top: 12px;
  right: 12px;
  z-index: 2000;
}

.auth-enroll {
  position: fixed;
  bottom: 12px;
  right: 14px;
  z-index: 2000;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 0.78rem;
  color: var(--app-text-muted);
  text-decoration: none;
}

.auth-enroll:hover {
  color: var(--app-primary);
  text-decoration: underline;
}
</style>
