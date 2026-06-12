/**
 * Estado de conexión con el servidor de recepción — fuente única.
 *
 * No basta `navigator.onLine` (dice si hay red, no si el SERVIDOR responde):
 * se hace un latido real a `/api/nomina/health/` (público) cada 25 s, con
 * verificación inmediata al recuperar red o volver a la app (móvil).
 * Notifica SOLO en las transiciones (conectado ↔ sin conexión).
 */
import { ref } from 'vue';
import { Notify } from 'quasar';

const HEARTBEAT_MS = 25_000;
const PROBE_TIMEOUT_MS = 5_000;
const HEALTH_URL = '/api/nomina/health/';

const online = ref(true);
const lastCheckAt = ref<Date | null>(null);

let started = false;
let probing = false;

async function probeServer(): Promise<boolean> {
  if (typeof navigator !== 'undefined' && !navigator.onLine) return false;
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), PROBE_TIMEOUT_MS);
  try {
    const res = await fetch(HEALTH_URL, { signal: ctrl.signal, cache: 'no-store' });
    return res.ok;
  } catch {
    return false;
  } finally {
    clearTimeout(timer);
  }
}

function setOnline(value: boolean) {
  if (value === online.value) return;
  online.value = value;
  Notify.create(
    value
      ? { type: 'positive', icon: 'wifi', message: 'Conexión con el servidor restablecida.' }
      : {
          type: 'negative',
          icon: 'wifi_off',
          message: 'Sin conexión con el servidor.',
          caption: 'Verificá la red. Los cambios locales no se enviarán hasta reconectar.',
          timeout: 4000,
        },
  );
}

async function refresh() {
  if (probing) return;
  probing = true;
  try {
    setOnline(await probeServer());
    lastCheckAt.value = new Date();
  } finally {
    probing = false;
  }
}

export function useConnectivity() {
  if (!started && typeof window !== 'undefined') {
    started = true;
    window.addEventListener('online', () => void refresh());
    window.addEventListener('offline', () => setOnline(false));
    // En el cel: al volver a la app (estaba en segundo plano), verificar al instante.
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'visible') void refresh();
    });
    window.setInterval(() => void refresh(), HEARTBEAT_MS);
    void refresh();
  }
  return { online, lastCheckAt, refresh };
}
