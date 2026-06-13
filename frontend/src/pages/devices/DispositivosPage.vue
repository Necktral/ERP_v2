<template>
  <q-page class="app-page">
    <PageHeader
      title="Dispositivos"
      subtitle="Celulares y aparatos enrolados. Cada acción que hagan queda en la bitácora con su identidad."
      :loading="loading"
      @refresh="reload"
    >
      <template #actions>
        <q-btn
          unelevated
          no-caps
          color="primary"
          icon="qr_code_2"
          label="Generar código de enrolamiento"
          @click="openChallenge"
        />
      </template>
    </PageHeader>

    <q-table
      class="app-table"
      :rows="devices"
      :columns="columns"
      row-key="id"
      flat
      :loading="loading"
      :pagination="{ rowsPerPage: 25 }"
      no-data-label="Aún no hay dispositivos enrolados. Generá un código y canjealo desde el aparato."
    >
      <template #body-cell-label="props">
        <q-td :props="props">
          {{ props.row.label || '(sin etiqueta)' }}
          <q-chip v-if="props.row.id === myDeviceId" dense color="primary" text-color="white" label="Este dispositivo" />
        </q-td>
      </template>

      <template #body-cell-status="props">
        <q-td :props="props">
          <q-chip
            dense
            :color="statusColor(props.row.status)"
            text-color="white"
            :label="statusLabel(props.row.status)"
          />
        </q-td>
      </template>

      <template #body-cell-acciones="props">
        <q-td :props="props" class="text-right">
          <q-btn
            v-if="props.row.status === 'ACTIVE'"
            flat
            dense
            no-caps
            size="sm"
            color="negative"
            icon="block"
            label="Revocar"
            @click="doRevoke(props.row)"
          />
        </q-td>
      </template>
    </q-table>

    <!-- Diálogo: generar código -->
    <q-dialog v-model="challengeOpen">
      <q-card class="dev-dialog">
        <q-card-section>
          <div class="text-h6">Código de enrolamiento</div>
          <div class="dev-muted">Es de un solo uso y vence pronto: canjealo en el aparato ahora.</div>
        </q-card-section>

        <q-card-section v-if="!challenge" class="q-gutter-md">
          <q-input v-model="challengeForm.label_hint" outlined dense label="Etiqueta del aparato (p. ej. Cel del mandador)" autofocus />
          <q-input
            v-model.number="challengeForm.expires_in_minutes"
            outlined
            dense
            type="number"
            label="Vence en (minutos)"
            :min="5"
            :max="120"
          />
        </q-card-section>

        <q-card-section v-else class="dev-challenge">
          <img v-if="qrDataUrl" :src="qrDataUrl" alt="Código QR de enrolamiento" class="dev-qr" />
          <div class="dev-muted text-center">
            <strong>Escaneá el QR con la cámara del cel</strong>: abre la pantalla de enrolar con el
            código ya puesto. O pegá el código a mano:
          </div>
          <div class="dev-code" @click="copyCode">
            {{ challenge.enrollment_code }}
            <q-icon name="content_copy" size="18px" />
            <q-tooltip>Copiar</q-tooltip>
          </div>
          <div class="dev-muted text-center">
            Vence: {{ new Date(challenge.expires_at).toLocaleTimeString('es-NI') }} · un solo uso
          </div>
        </q-card-section>

        <q-card-actions align="right">
          <q-btn v-if="!challenge" flat no-caps label="Cancelar" v-close-popup />
          <q-btn
            v-if="!challenge"
            unelevated
            no-caps
            color="primary"
            label="Generar"
            :loading="saving"
            @click="doCreateChallenge"
          />
          <q-btn v-else unelevated no-caps color="primary" label="Listo" v-close-popup />
        </q-card-actions>
      </q-card>
    </q-dialog>
  </q-page>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue';
import { useQuasar, copyToClipboard, type QTableColumn } from 'quasar';
import PageHeader from 'src/components/PageHeader.vue';
import QRCode from 'qrcode';
import {
  createEnrollmentChallenge,
  listDevices,
  revokeDevice,
  type DeviceRow,
  type EnrollmentChallenge,
} from 'src/features/devices/devices.api';
import { getDeviceIdentity } from 'src/core/device';

const $q = useQuasar();
const loading = ref(false);
const saving = ref(false);
const devices = ref<DeviceRow[]>([]);
const myDeviceId = getDeviceIdentity()?.device_id ?? null;

const columns: QTableColumn<DeviceRow>[] = [
  { name: 'label', label: 'Aparato', field: 'label', align: 'left' },
  { name: 'status', label: 'Estado', field: 'status', align: 'center' },
  {
    name: 'last_seen_at',
    label: 'Última conexión',
    field: (r) => (r.last_seen_at ? new Date(r.last_seen_at).toLocaleString('es-NI') : 'nunca'),
    align: 'left',
  },
  {
    name: 'created_at',
    label: 'Enrolado',
    field: (r) => (r.created_at ? new Date(r.created_at).toLocaleDateString('es-NI') : ''),
    align: 'left',
  },
  { name: 'acciones', label: '', field: 'id', align: 'right' },
];

function statusColor(s: DeviceRow['status']): string {
  return { ACTIVE: 'positive', REVOKED: 'negative', QUARANTINED: 'warning' }[s] ?? 'grey-7';
}

function statusLabel(s: DeviceRow['status']): string {
  return { ACTIVE: 'Activo', REVOKED: 'Revocado', QUARANTINED: 'En cuarentena' }[s] ?? s;
}

async function reload() {
  loading.value = true;
  try {
    devices.value = await listDevices();
  } catch {
    $q.notify({ type: 'negative', message: 'No se pudieron cargar los dispositivos.' });
  } finally {
    loading.value = false;
  }
}

// --- generar código ---
const challengeOpen = ref(false);
const challenge = ref<EnrollmentChallenge | null>(null);
const qrDataUrl = ref('');
const challengeForm = reactive({ label_hint: '', expires_in_minutes: 15 });

function openChallenge() {
  challenge.value = null;
  qrDataUrl.value = '';
  challengeForm.label_hint = '';
  challengeForm.expires_in_minutes = 15;
  challengeOpen.value = true;
}

async function doCreateChallenge() {
  saving.value = true;
  try {
    const ch = await createEnrollmentChallenge({
      label_hint: challengeForm.label_hint,
      expires_in_minutes: challengeForm.expires_in_minutes,
    });
    challenge.value = ch;
    // El QR codifica la URL de enrolar con el código incluido (escanear → listo).
    const qrContent = ch.enrollment_uri || ch.enrollment_code;
    qrDataUrl.value = await QRCode.toDataURL(qrContent, { width: 260, margin: 1 });
  } catch {
    $q.notify({ type: 'negative', message: 'No se pudo generar el código.' });
  } finally {
    saving.value = false;
  }
}

function copyCode() {
  if (challenge.value) {
    void copyToClipboard(challenge.value.enrollment_code);
    $q.notify({ type: 'info', message: 'Código copiado.' });
  }
}

function doRevoke(d: DeviceRow) {
  $q.dialog({
    title: 'Revocar dispositivo',
    message: `«${d.label || d.id}» dejará de poder operar y su identidad quedará inválida. ¿Confirmás?`,
    cancel: { flat: true, label: 'Cancelar', noCaps: true },
    ok: { color: 'negative', label: 'Revocar', noCaps: true, unelevated: true },
  }).onOk(() => {
    void (async () => {
      try {
        await revokeDevice(d.id);
        $q.notify({ type: 'positive', message: 'Dispositivo revocado.' });
        await reload();
      } catch {
        $q.notify({ type: 'negative', message: 'No se pudo revocar.' });
      }
    })();
  });
}

onMounted(reload);
</script>

<style scoped>





.dev-dialog {
  width: 480px;
  max-width: 92vw;
  background: var(--app-surface-strong);
}

.dev-muted {
  color: var(--app-text-muted);
  font-size: 0.85rem;
}

.dev-challenge {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--app-space-3);
}

.dev-qr {
  width: 260px;
  max-width: 80vw;
  border-radius: var(--app-radius-md);
  border: 1px solid var(--app-border);
  background: #fff;
}

.dev-code {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--app-space-2);
  padding: var(--app-space-4);
  border: 1px dashed var(--app-border-strong);
  border-radius: var(--app-radius-md);
  background: var(--app-surface);
  font-family: 'IBM Plex Mono', monospace;
  font-size: 1.05rem;
  font-weight: 700;
  letter-spacing: 0.04em;
  word-break: break-all;
  cursor: pointer;
}
</style>
