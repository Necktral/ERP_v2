<template>
  <q-page class="q-pa-md">
    <div class="text-h6">Company Profile</div>
    <div class="text-caption text-grey-7">
      Requiere permiso <b>org.company.update</b> (el backend lo exige incluso para ver el perfil).
    </div>

    <q-card class="q-mt-md">
      <q-card-section>
        <q-form @submit.prevent="onSave">
          <q-input v-model="form.legal_name" label="Legal name" outlined />
          <div class="q-mt-sm" />
          <q-input v-model="form.tax_id" label="Tax ID" outlined />
          <div class="q-mt-sm" />
          <q-input v-model="form.address" label="Address" outlined />
          <div class="q-mt-sm" />
          <q-input v-model="form.phone" label="Phone" outlined />
          <div class="q-mt-sm" />
          <q-input v-model="form.email" label="Email" outlined />

          <div class="q-mt-lg">
            <q-btn type="submit" color="primary" label="Guardar" :loading="saving" />
            <q-btn flat label="Recargar" class="q-ml-sm" :disable="saving" @click="load" />
          </div>
        </q-form>

        <q-banner v-if="errorMsg" class="q-mt-md" dense rounded>
          {{ errorMsg }}
        </q-banner>
      </q-card-section>
    </q-card>
  </q-page>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue';
import { useQuasar } from 'quasar';
import {
  getCompanyProfile,
  updateCompanyProfile,
  type CompanyProfile,
} from 'src/services/org.service';
import { isAxiosError } from 'axios';

const $q = useQuasar();
const saving = ref(false);
const errorMsg = ref<string | null>(null);

const form = reactive<CompanyProfile>({
  legal_name: '',
  tax_id: '',
  address: '',
  phone: '',
  email: '',
});

async function load() {
  errorMsg.value = null;
  try {
    const data = await getCompanyProfile();
    Object.assign(form, data);
  } catch (e: unknown) {
    errorMsg.value = isAxiosError(e) ? (e.response?.data?.detail ?? e.message) : String(e);
  }
}

async function onSave() {
  saving.value = true;
  errorMsg.value = null;
  try {
    await updateCompanyProfile({ ...form });
    $q.notify({ type: 'positive', message: 'Perfil actualizado' });
  } catch (e: unknown) {
    errorMsg.value = isAxiosError(e) ? (e.response?.data?.detail ?? e.message) : String(e);
    $q.notify({ type: 'negative', message: 'No se pudo guardar' });
  } finally {
    saving.value = false;
  }
}

onMounted(load);
</script>
