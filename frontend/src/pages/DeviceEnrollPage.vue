<template>
  <q-page class="row items-center justify-center q-pa-md">
    <q-card style="width: 560px; max-width: 96vw">
      <q-card-section>
        <div class="text-h6">Enrolamiento de dispositivo (PWA)</div>
        <div class="text-caption text-grey-7">
          Escaneado por QR: completa alta y prueba de batch firmado en carril canónico <code>/api/sync/*</code>.
        </div>
      </q-card-section>

      <q-separator />

      <q-card-section>
        <q-input
          v-model="enrollmentCode"
          outlined
          dense
          label="Código de enrolamiento"
          class="q-mb-sm"
        />
        <q-input
          v-model="deviceLabel"
          outlined
          dense
          maxlength="200"
          label="Etiqueta del dispositivo (opcional)"
          class="q-mb-sm"
        />
        <div class="text-caption text-grey-7 q-mb-md">
          Requiere navegador con WebCrypto Ed25519 y contexto seguro (HTTPS).
        </div>

        <q-btn
          color="primary"
          :loading="processing"
          label="Enrolar y probar batch DEMO_PING"
          @click="onEnrollAndPing"
        />

        <q-banner v-if="errorMsg" dense rounded class="q-mt-md bg-red-1 text-red-10">
          {{ errorMsg }}
        </q-banner>
      </q-card-section>

      <q-card-section v-if="enrollResult || batchResult">
        <q-list bordered separator>
          <q-item v-if="enrollResult">
            <q-item-section>
              <q-item-label caption>Enroll</q-item-label>
              <q-item-label>
                status=201 · device_id={{ enrollResult.device_id }} · trace.request_id={{ enrollResult.trace?.request_id || '-' }}
              </q-item-label>
              <q-item-label caption>
                audit_event_id={{ enrollResult.trace?.audit_event_id || '-' }}
              </q-item-label>
            </q-item-section>
          </q-item>

          <q-item v-if="batchResult">
            <q-item-section>
              <q-item-label caption>Batch</q-item-label>
              <q-item-label>
                status=200 · result={{ batchResult.firstStatus }} · trace.request_id={{ batchResult.traceRequestId || '-' }}
              </q-item-label>
            </q-item-section>
          </q-item>

          <q-item v-if="storedIdentity">
            <q-item-section>
              <q-item-label caption>Dispositivo activo en PWA</q-item-label>
              <q-item-label>
                {{ storedIdentity.deviceId }} · company={{ storedIdentity.companyId }} · branch={{ storedIdentity.branchId ?? '-' }}
              </q-item-label>
            </q-item-section>
          </q-item>
        </q-list>
      </q-card-section>
    </q-card>
  </q-page>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { useRoute } from 'vue-router';
import { api } from 'src/boot/axios';
import { extractErrorMessage } from 'src/shared/http/api-error';
import { buildRequestSigningMessage, canonJson, generateDeviceEd25519KeyPair, signEd25519Pkcs8 } from 'src/services/sync-device-crypto';
import { getActiveSyncDeviceIdentity, saveActiveSyncDeviceIdentity, type StoredSyncDeviceIdentity } from 'src/services/sync-device-storage';
import type { DeviceEnrollResponse } from 'src/services/sync.service';

type BatchResponse = {
  trace?: { request_id?: string };
  results?: Array<{ status?: string }>;
};

const route = useRoute();

const processing = ref(false);
const errorMsg = ref<string | null>(null);
const enrollmentCode = ref('');
const deviceLabel = ref('PWA-Sync-Device');
const enrollResult = ref<(DeviceEnrollResponse & { trace?: { request_id?: string; audit_event_id?: string } }) | null>(null);
const batchResult = ref<{ firstStatus: string; traceRequestId: string } | null>(null);
const storedIdentity = ref<StoredSyncDeviceIdentity | null>(null);

function loadCodeFromRoute() {
  const q = route.query.code;
  const value = Array.isArray(q) ? q[0] : q;
  enrollmentCode.value = typeof value === 'string' ? value.trim() : '';
}

async function refreshStoredIdentity() {
  try {
    storedIdentity.value = await getActiveSyncDeviceIdentity();
  } catch {
    storedIdentity.value = null;
  }
}

onMounted(async () => {
  loadCodeFromRoute();
  await refreshStoredIdentity();
});

async function onEnrollAndPing() {
  processing.value = true;
  errorMsg.value = null;
  enrollResult.value = null;
  batchResult.value = null;

  try {
    const code = enrollmentCode.value.trim();
    if (!code) {
      throw new Error('Falta código de enrolamiento en la URL o ingreso manual.');
    }

    const keys = await generateDeviceEd25519KeyPair();
    const enrollResp = await api.post<DeviceEnrollResponse & { trace?: { request_id?: string; audit_event_id?: string } }>(
      '/sync/enroll/',
      {
        enrollment_code: code,
        public_key_b64: keys.publicKeyB64,
        label: deviceLabel.value.trim() || 'PWA-Sync-Device',
        meta: { channel: 'pwa', source: 'device-enroll-page' },
      },
    );
    const enrolled = enrollResp.data;
    enrollResult.value = enrolled;

    const now = new Date().toISOString();
    await saveActiveSyncDeviceIdentity({
      deviceId: enrolled.device_id,
      companyId: enrolled.company_id,
      branchId: enrolled.branch_id,
      label: deviceLabel.value.trim() || 'PWA-Sync-Device',
      publicKeyB64: keys.publicKeyB64,
      privateKeyPkcs8B64: keys.privateKeyPkcs8B64,
      createdAt: now,
      updatedAt: now,
    });
    await refreshStoredIdentity();

    const ts = Math.floor(Date.now() / 1000);
    const nonce = `pwa-${crypto.randomUUID().replace(/-/g, '').slice(0, 20)}`;
    const payload = {
      protocol_version: '2',
      device_id: enrolled.device_id,
      ts,
      nonce,
      auth: { scheme: 'ed25519', signature: '' },
      batch_id: crypto.randomUUID(),
      batch: [
        {
          command_id: crypto.randomUUID(),
          type: 'DEMO_PING',
          scope: {
            company_id: enrolled.company_id,
            branch_id: enrolled.branch_id,
          },
          occurred_at: new Date().toISOString(),
          payload: { msg: 'pwa-enroll-probe' },
        },
      ],
    };
    const signingBody = new TextEncoder().encode(canonJson(payload));
    const message = await buildRequestSigningMessage({
      ts,
      nonce,
      canonicalBodyBytes: signingBody,
    });
    payload.auth.signature = await signEd25519Pkcs8(keys.privateKeyPkcs8B64, message);

    const batchResp = await api.post<BatchResponse>('/sync/batch/', payload, {
      headers: { 'X-Device-Id': enrolled.device_id },
    });
    const firstStatus = String(batchResp.data?.results?.[0]?.status || '');
    if (!['APPLIED', 'DUPLICATE'].includes(firstStatus)) {
      throw new Error(`Batch no aplicado: ${firstStatus || 'UNKNOWN'}`);
    }

    batchResult.value = {
      firstStatus,
      traceRequestId: String(batchResp.data?.trace?.request_id || batchResp.headers['x-request-id'] || ''),
    };
  } catch (e) {
    errorMsg.value = extractErrorMessage(e);
  } finally {
    processing.value = false;
  }
}
</script>

