<template>
  <q-page class="q-pa-md">
    <div class="text-h6">Acceso denegado</div>
    <div class="text-caption text-grey-7">
      No tienes permisos para acceder a esta sección con el contexto actual.
    </div>

    <div class="q-mt-md">
      <q-btn label="Volver al Dashboard" color="primary" @click="goHome" />
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router';
const router = useRouter();

async function goHome() {
  await router.replace('/dashboard');
}
</script>
