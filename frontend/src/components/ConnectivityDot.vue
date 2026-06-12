<template>
  <div
    class="conn"
    :class="online ? 'conn--on' : 'conn--off'"
    role="status"
    :aria-label="online ? 'Conectado al servidor' : 'Sin conexión con el servidor'"
  >
    <span class="conn__dot" aria-hidden="true" />
    <span class="conn__label">{{ online ? 'En línea' : 'Sin conexión' }}</span>
    <q-tooltip>
      {{ online ? 'Conectado al servidor de recepción' : 'Sin conexión con el servidor' }}
      <template v-if="lastCheckAt"> · verificado {{ lastCheckLabel }}</template>
    </q-tooltip>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useConnectivity } from 'src/core/connectivity';

const { online, lastCheckAt } = useConnectivity();

const lastCheckLabel = computed(() => {
  const d = lastCheckAt.value;
  if (!d) return '';
  return d.toLocaleTimeString('es-NI', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
});
</script>

<style scoped>
.conn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 999px;
  border: 1px solid var(--app-border);
  background: var(--app-surface);
  font-size: 0.74rem;
  font-weight: 700;
  letter-spacing: 0.02em;
  user-select: none;
}

.conn__dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}

.conn--on .conn__dot {
  background: var(--q-positive);
  box-shadow: 0 0 0 0 rgba(33, 186, 69, 0.55);
  animation: conn-pulse 2.2s ease-out infinite;
}

.conn--on .conn__label {
  color: var(--q-positive);
}

.conn--off .conn__dot {
  background: var(--q-negative);
  animation: conn-blink 1.1s steps(2, start) infinite;
}

.conn--off .conn__label {
  color: var(--q-negative);
}

@keyframes conn-pulse {
  0% {
    box-shadow: 0 0 0 0 rgba(33, 186, 69, 0.55);
  }
  70% {
    box-shadow: 0 0 0 7px rgba(33, 186, 69, 0);
  }
  100% {
    box-shadow: 0 0 0 0 rgba(33, 186, 69, 0);
  }
}

@keyframes conn-blink {
  to {
    visibility: hidden;
  }
}

@media (max-width: 599px) {
  .conn__label {
    display: none; /* en el cel queda solo el punto */
  }
}
</style>
