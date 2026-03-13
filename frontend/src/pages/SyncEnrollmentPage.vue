<template>
  <AppContainer>
    <AppPageHeader
      :title="`${labels.synchronization} · Enrolamiento`"
      subtitle="API: POST /sync/enrollment/challenges/ · POST /sync/enroll/"
    />

    <q-banner v-if="!canEnroll" dense rounded class="q-mt-md">
      No tienes permiso <b>sync.device.enroll</b> o no hay contexto activo.
    </q-banner>

    <div v-else class="row q-col-gutter-md q-mt-md">
      <div class="col-12 col-lg-6">
        <q-card class="app-card full-height">
          <q-card-section>
            <div class="text-subtitle1">Generar codigo de enrolamiento</div>
            <div class="text-caption text-grey-7 q-mb-md">
              Crea un codigo one-time para registrar dispositivos.
            </div>

            <q-input
              v-model.number="challengeForm.expires_in_minutes"
              type="number"
              min="1"
              max="1440"
              outlined
              dense
              label="Expira en (minutos)"
              class="q-mb-sm"
            />
            <q-input
              v-model="challengeForm.label_hint"
              outlined
              dense
              maxlength="200"
              label="Etiqueta sugerida"
              class="q-mb-sm"
            />
            <q-input
              v-model.number="challengeForm.branch_id"
              type="number"
              min="1"
              outlined
              dense
              clearable
              label="Sucursal (opcional)"
            />

            <div class="q-mt-md">
              <q-btn color="primary" :loading="creatingChallenge" label="Generar" @click="onCreateChallenge" />
            </div>

            <q-banner v-if="challengeError" dense rounded class="q-mt-md bg-red-1 text-red-10">
              {{ challengeError }}
            </q-banner>

            <div v-if="challengeResult" class="q-mt-md">
              <q-input :model-value="challengeResult.enrollment_code" readonly outlined dense label="Codigo" />
              <q-input
                class="q-mt-sm"
                :model-value="challengeResult.expires_at"
                readonly
                outlined
                dense
                label="Expira en"
              />
              <div class="q-mt-md row justify-center">
                <q-img v-if="challengeQrDataUrl" :src="challengeQrDataUrl" style="max-width: 220px" />
              </div>
            </div>
          </q-card-section>
        </q-card>
      </div>

      <div class="col-12 col-lg-6">
        <q-card class="app-card full-height">
          <q-card-section>
            <div class="text-subtitle1">Alta de dispositivo por codigo</div>
            <div class="text-caption text-grey-7 q-mb-md">
              Permite ingreso manual del codigo y llave publica del dispositivo.
            </div>

            <q-input v-model="enrollForm.enrollment_code" outlined dense label="Codigo de enrolamiento" class="q-mb-sm" />
            <q-input v-model="enrollForm.label" outlined dense maxlength="200" label="Etiqueta" class="q-mb-sm" />
            <q-input
              v-model="enrollForm.public_key_b64"
              type="textarea"
              outlined
              autogrow
              label="Llave publica (Base64 Ed25519)"
            />

            <div class="q-mt-md">
              <q-btn color="secondary" :loading="enrolling" label="Registrar dispositivo" @click="onEnrollDevice" />
            </div>

            <q-banner v-if="enrollError" dense rounded class="q-mt-md bg-red-1 text-red-10">
              {{ enrollError }}
            </q-banner>

            <q-list v-if="enrollResult" bordered separator class="q-mt-md rounded-borders">
              <q-item>
                <q-item-section>
                  <q-item-label caption>Dispositivo</q-item-label>
                  <q-item-label>{{ enrollResult.device_id }}</q-item-label>
                </q-item-section>
              </q-item>
              <q-item>
                <q-item-section>
                  <q-item-label caption>Estado</q-item-label>
                  <q-item-label>{{ enrollResult.device_status }}</q-item-label>
                </q-item-section>
              </q-item>
              <q-item>
                <q-item-section>
                  <q-item-label caption>Empresa / Sucursal</q-item-label>
                  <q-item-label>{{ enrollResult.company_id }} / {{ enrollResult.branch_id ?? '-' }}</q-item-label>
                </q-item-section>
              </q-item>
            </q-list>
          </q-card-section>
        </q-card>
      </div>
    </div>
  </AppContainer>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from 'vue';
import QRCode from 'qrcode';

import AppContainer from 'src/ui/AppContainer.vue';
import AppPageHeader from 'src/ui/AppPageHeader.vue';
import { extractErrorMessage } from 'src/core/http/errors';
import { BUSINESS_LABELS } from 'src/shared/ui/business-terms';
import { useAclStore } from 'src/stores/acl.store';
import { useContextStore } from 'src/stores/context.store';
import {
  createEnrollmentChallenge,
  enrollDevice,
  type DeviceEnrollResponse,
  type EnrollmentChallengeResponse,
} from 'src/services/sync.service';

const labels = BUSINESS_LABELS;
const acl = useAclStore();
const ctx = useContextStore();

const canEnroll = computed(() => {
  const companyId = ctx.activeCompanyId;
  if (!companyId) return false;
  return acl.hasPermission(companyId, 'sync.device.enroll');
});

const creatingChallenge = ref(false);
const challengeError = ref<string | null>(null);
const challengeResult = ref<EnrollmentChallengeResponse | null>(null);
const challengeQrDataUrl = ref<string>('');
const challengeForm = reactive({
  expires_in_minutes: 15,
  label_hint: '',
  branch_id: ctx.activeBranchId ? Number(ctx.activeBranchId) : null as number | null,
});

const enrolling = ref(false);
const enrollError = ref<string | null>(null);
const enrollResult = ref<DeviceEnrollResponse | null>(null);
const enrollForm = reactive({
  enrollment_code: '',
  label: '',
  public_key_b64: '',
});

async function onCreateChallenge() {
  creatingChallenge.value = true;
  challengeError.value = null;
  challengeResult.value = null;
  challengeQrDataUrl.value = '';
  try {
    const data = await createEnrollmentChallenge({
      expires_in_minutes: Number(challengeForm.expires_in_minutes || 15),
      label_hint: challengeForm.label_hint || '',
      branch_id: challengeForm.branch_id || null,
    });
    challengeResult.value = data;
    challengeQrDataUrl.value = await QRCode.toDataURL(data.enrollment_code, { margin: 1, width: 280 });
  } catch (e) {
    challengeError.value = extractErrorMessage(e);
  } finally {
    creatingChallenge.value = false;
  }
}

async function onEnrollDevice() {
  enrolling.value = true;
  enrollError.value = null;
  enrollResult.value = null;
  try {
    enrollResult.value = await enrollDevice({
      enrollment_code: enrollForm.enrollment_code.trim(),
      label: enrollForm.label.trim(),
      public_key_b64: enrollForm.public_key_b64.trim(),
    });
  } catch (e) {
    enrollError.value = extractErrorMessage(e);
  } finally {
    enrolling.value = false;
  }
}
</script>
