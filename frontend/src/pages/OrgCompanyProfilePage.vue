<template>
  <AppContainer>
    <AppPageHeader
      title="ORG · Perfil de compañía"
      subtitle="GET/PUT /org/company/profile/ (backend exige org.company.update incluso para ver)"
    >
      <template #badges>
        <q-badge outline color="primary">Company: {{ companyLabel }}</q-badge>
        <q-badge outline>Perm: org.company.update</q-badge>
      </template>

      <template #actions>
        <q-btn flat label="Recargar" :disable="loading || saving" @click="load" />
        <q-btn color="primary" label="Guardar" :loading="saving" @click="onSave" />
      </template>
    </AppPageHeader>

    <q-card class="app-card q-mt-md">
      <q-card-section>
        <q-form @submit.prevent="onSave">
          <div class="text-subtitle2">Identidad legal</div>
          <q-separator class="q-my-sm" />

          <div class="row q-col-gutter-md">
            <div class="col-12 col-md-8">
              <q-input
                v-model="form.legal_name"
                label="Razón social / nombre legal"
                outlined
                :rules="[(v) => !!String(v || '').trim() || 'Requerido']"
              />
            </div>
            <div class="col-12 col-md-4">
              <q-input v-model="form.tax_id" label="RIF / Tax ID" outlined />
            </div>
          </div>

          <div class="text-subtitle2 q-mt-md">Contacto</div>
          <q-separator class="q-my-sm" />

          <div class="row q-col-gutter-md">
            <div class="col-12 col-md-6">
              <q-input v-model="form.phone" label="Teléfono" outlined />
            </div>
            <div class="col-12 col-md-6">
              <q-input v-model="form.email" label="Email" outlined />
            </div>

            <div class="col-12">
              <q-input v-model="form.address" label="Dirección" outlined type="textarea" autogrow />
            </div>
          </div>

          <q-banner v-if="errorMsg" class="q-mt-md" dense rounded>
            {{ errorMsg }}
          </q-banner>

          <div v-if="lastLoadedAt" class="q-mt-sm text-caption app-muted">
            Última carga: {{ lastLoadedAt }}
          </div>

          <!-- Para permitir submit con Enter -->
          <button type="submit" class="hidden" />
        </q-form>
      </q-card-section>
    </q-card>
  </AppContainer>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import { useQuasar } from 'quasar';
import { useAclStore } from 'src/stores/acl.store';
import { useContextStore } from 'src/stores/context.store';
import { extractErrorMessage } from 'src/core/http/errors';
import {
  getCompanyProfile,
  updateCompanyProfile,
  type CompanyProfile,
} from 'src/services/org.service';
import AppContainer from 'src/ui/AppContainer.vue';
import AppPageHeader from 'src/ui/AppPageHeader.vue';

const $q = useQuasar();
const acl = useAclStore();
const ctx = useContextStore();

const loading = ref(false);
const saving = ref(false);
const errorMsg = ref<string | null>(null);
const lastLoadedAt = ref<string | null>(null);

const companyLabel = computed(
  () => acl.companyName(ctx.activeCompanyId) ?? ctx.activeCompanyId ?? '—',
);

const form = reactive<CompanyProfile>({
  legal_name: '',
  tax_id: '',
  address: '',
  phone: '',
  email: '',
});

async function load() {
  loading.value = true;
  errorMsg.value = null;
  try {
    const data = await getCompanyProfile();
    Object.assign(form, data);
    lastLoadedAt.value = new Date().toLocaleString();
  } catch (e: unknown) {
    errorMsg.value = extractErrorMessage(e);
  } finally {
    loading.value = false;
  }
}

async function onSave() {
  saving.value = true;
  errorMsg.value = null;
  try {
    await updateCompanyProfile({ ...form });
    $q.notify({ type: 'positive', message: 'Perfil actualizado' });
  } catch (e: unknown) {
    const msg = extractErrorMessage(e);
    errorMsg.value = msg;
    $q.notify({ type: 'negative', message: msg });
  } finally {
    saving.value = false;
  }
}

onMounted(load);
</script>
