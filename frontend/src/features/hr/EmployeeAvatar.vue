<template>
  <span class="emp-avatar" :style="{ width: `${size}px`, height: `${size}px` }">
    <img v-if="photoUrl" :src="photoUrl" :alt="nombre" class="emp-avatar__img" />
    <span v-else class="emp-avatar__iniciales" :style="{ fontSize: `${size * 0.38}px` }">
      {{ iniciales }}
    </span>
  </span>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { getEmployeePhotoUrl } from 'src/features/hr/hr.api';

const props = withDefaults(
  defineProps<{
    employeeId: number;
    nombre: string;
    /** Si el listado ya sabe que no hay foto, evita la petición. */
    hasPhoto?: boolean;
    size?: number;
  }>(),
  { hasPhoto: true, size: 40 },
);

const photoUrl = ref<string | null>(null);

const iniciales = computed(() =>
  props.nombre
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => (p[0] ?? '').toUpperCase())
    .join(''),
);

watch(
  () => [props.employeeId, props.hasPhoto] as const,
  async ([id, has]) => {
    photoUrl.value = null;
    if (!has || !id) return;
    photoUrl.value = await getEmployeePhotoUrl(id);
  },
  { immediate: true },
);
</script>

<style scoped>
.emp-avatar {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  overflow: hidden;
  flex-shrink: 0;
  background: var(--app-surface-strong);
  border: 1px solid var(--app-border);
}

.emp-avatar__img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.emp-avatar__iniciales {
  font-weight: 700;
  color: var(--app-text-muted);
  letter-spacing: 0.02em;
}
</style>
