<template>
  <q-page class="enr-page">
    <div class="enr-card">
      <div class="enr-title">Enrolar este dispositivo</div>

      <!-- Ya enrolado -->
      <template v-if="identity">
        <q-banner rounded class="enr-ok">
          <template #avatar><q-icon name="verified" color="positive" /></template>
          Este aparato ya está enrolado como
          <strong>{{ identity.label || 'dispositivo' }}</strong>
        </q-banner>
        <div class="enr-meta">
          <div>ID: <code>{{ identity.device_id }}</code></div>
          <div>Enrolado: {{ new Date(identity.enrolled_at).toLocaleString('es-NI') }}</div>
        </div>
        <q-btn flat no-caps color="negative" icon="link_off" label="Olvidar enrolamiento en este aparato" @click="doForget" />
        <q-btn unelevated no-caps color="primary" class="q-mt-sm" label="Ir al inicio" to="/login" />
      </template>

      <!-- Enrolar -->
      <template v-else>
        <div class="enr-help">
          Pedile al administrador un <strong>código de enrolamiento</strong> (web → Dispositivos →
          “Generar código”). Es de un solo uso y vence en minutos.
        </div>
        <q-form class="enr-form" @submit.prevent="doEnroll">
          <q-input
            v-model="code"
            outlined
            dense
            autofocus
            label="Código de enrolamiento"
            :disable="enrolling"
          />
          <q-input
            v-model="label"
            outlined
            dense
            label="Nombre de este aparato (p. ej. Cel del mandador)"
            :disable="enrolling"
          />
          <q-btn
            type="submit"
            unelevated
            no-caps
            color="primary"
            icon="phonelink_lock"
            label="Enrolar dispositivo"
            :loading="enrolling"
            :disable="!code.trim() || !label.trim()"
          />
        </q-form>
        <q-banner v-if="error" rounded class="enr-err">
          <template #avatar><q-icon name="error" color="negative" /></template>
          {{ error }}
        </q-banner>
      </template>
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { useRoute } from 'vue-router';
import { useQuasar } from 'quasar';
import { enrollDevice, forgetDevice, getDeviceIdentity, type DeviceIdentity } from 'src/core/device';

const $q = useQuasar();
const route = useRoute();
const identity = ref<DeviceIdentity | null>(getDeviceIdentity());
// Si se llegó escaneando el QR, el código viene en la URL (?code=...)
const code = ref(typeof route.query.code === 'string' ? route.query.code : '');
const label = ref('');
const enrolling = ref(false);
const error = ref('');

async function doEnroll() {
  enrolling.value = true;
  error.value = '';
  try {
    identity.value = await enrollDevice(code.value, label.value);
    $q.notify({ type: 'positive', message: 'Dispositivo enrolado. Sus acciones quedarán identificadas.' });
  } catch (e) {
    const err = e as { response?: { status?: number; data?: { detail?: string } } };
    error.value =
      err.response?.data?.detail ||
      (err.response?.status === 400
        ? 'Código inválido, vencido o ya usado. Pedí uno nuevo.'
        : 'No se pudo enrolar. Verificá la conexión con el servidor.');
  } finally {
    enrolling.value = false;
  }
}

function doForget() {
  $q.dialog({
    title: 'Olvidar enrolamiento',
    message:
      'Este aparato dejará de identificarse. La revocación del lado del servidor se hace en la web (Dispositivos). ¿Confirmás?',
    cancel: { flat: true, label: 'Cancelar', noCaps: true },
    ok: { color: 'negative', label: 'Olvidar', noCaps: true, unelevated: true },
  }).onOk(() => {
    forgetDevice();
    identity.value = null;
  });
}
</script>

<style scoped>
.enr-page {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--app-space-4);
  background: var(--app-bg-gradient);
}

.enr-card {
  width: 460px;
  max-width: 94vw;
  display: flex;
  flex-direction: column;
  gap: var(--app-space-4);
  padding: var(--app-space-6);
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-lg);
  background: var(--app-surface);
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
  box-shadow: var(--app-shadow-card);
  animation: app-fade-up 240ms ease-out;
}

.enr-title {
  font-family: 'Manrope', 'IBM Plex Sans', sans-serif;
  font-size: 1.3rem;
  font-weight: 800;
  color: var(--app-text);
}

.enr-help {
  color: var(--app-text-muted);
  font-size: 0.88rem;
}

.enr-form {
  display: flex;
  flex-direction: column;
  gap: var(--app-space-3);
}

.enr-meta {
  color: var(--app-text-muted);
  font-size: 0.84rem;
  display: flex;
  flex-direction: column;
  gap: var(--app-space-1);
  word-break: break-all;
}

.enr-ok,
.enr-err {
  border: 1px solid var(--app-border-strong);
  background: var(--app-surface-strong);
}
</style>
