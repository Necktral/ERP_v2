<template>
  <q-page class="row items-center justify-center">
    <q-card style="width: 420px; max-width: 92vw">
      <q-card-section>
        <div class="text-h6">Login</div>
        <div class="text-caption text-grey-7">Conecta contra el backend (JWT)</div>
      </q-card-section>

      <q-separator />

      <q-card-section>
        <q-banner v-if="bootstrapChecked && isFresh" class="q-mb-md" dense rounded inline-actions>
          <div class="text-weight-medium">Primer arranque: no hay usuarios creados.</div>
          <div class="text-caption text-grey-7">
            Crea el usuario administrador inicial y luego configura Holding → Company → Branch.
          </div>
          <template #action>
            <q-btn color="primary" label="Crear usuario inicial" to="/bootstrap" />
          </template>
        </q-banner>

        <q-form @submit.prevent="onSubmit">
          <q-input
            v-model="username"
            label="Username"
            autocomplete="username"
            outlined
            :disable="isFresh"
          />
          <div class="q-mt-md" />
          <q-input
            v-model="password"
            label="Password"
            type="password"
            autocomplete="current-password"
            outlined
            :disable="isFresh"
          />

          <div class="q-mt-lg">
            <q-btn
              :loading="loading"
              type="submit"
              label="Entrar"
              color="primary"
              class="full-width"
              :disable="isFresh"
            />
          </div>
        </q-form>

        <q-banner v-if="errorMsg" class="q-mt-md" dense rounded inline-actions>
          {{ errorMsg }}
          <template #action>
            <q-btn flat label="Cerrar" @click="errorMsg = null" />
          </template>
        </q-banner>
      </q-card-section>
    </q-card>
  </q-page>
</template>

<script setup lang="ts">
import { isAxiosError } from 'axios';
import { computed, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import { useAuthStore } from 'src/stores/auth.store';
import { useAclStore } from 'src/stores/acl.store';
import { useContextStore } from 'src/stores/context.store';

const router = useRouter();
const auth = useAuthStore();
const acl = useAclStore();
const ctx = useContextStore();

const username = ref('');
const password = ref('');

const loading = ref(false);
const errorMsg = ref<string | null>(null);

const bootstrapChecked = ref(false);
const isFresh = computed(() => auth.bootstrapState.is_fresh);

onMounted(async () => {
  try {
    await auth.checkBootstrap();
  } finally {
    bootstrapChecked.value = true;
  }
});

async function onSubmit() {
  loading.value = true;
  errorMsg.value = null;

  try {
    await auth.login(username.value.trim(), password.value);
    await acl.loadAcl();

    // Autoselección si viene recomendación
    const recCompany = acl.recommendedCompanyId;
    const recBranch = acl.recommendedBranchId;

    if (recCompany) {
      ctx.setContext(recCompany, recBranch ?? null);
      await router.replace('/dashboard');
      return;
    }

    await router.replace('/select-context');
  } catch (e: unknown) {
    if (isAxiosError(e)) {
      const data: unknown = e.response?.data;
      let detail = '';
      if (typeof data === 'string') {
        detail = data;
      } else if (
        typeof data === 'object' &&
        data !== null &&
        'non_field_errors' in data &&
        Array.isArray((data as Record<string, unknown>).non_field_errors)
      ) {
        detail = (data as { non_field_errors: string[] }).non_field_errors[0] ?? '';
      } else if (
        typeof data === 'object' &&
        data !== null &&
        'detail' in data &&
        typeof (data as Record<string, unknown>).detail === 'string'
      ) {
        detail = (data as { detail: string }).detail;
      }
      errorMsg.value = detail || e.message || 'Error de login';
    } else if (e instanceof Error) {
      errorMsg.value = e.message;
    } else {
      errorMsg.value = String(e);
    }
  } finally {
    loading.value = false;
  }
}
</script>
