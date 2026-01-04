<template>
  <q-page class="row items-center justify-center">
    <q-card style="width: 420px; max-width: 92vw">
      <q-card-section>
        <div class="text-h6">Login</div>
        <div class="text-caption text-grey-7">Conecta contra el backend (JWT)</div>
      </q-card-section>

      <q-separator />

      <q-card-section>
        <q-form @submit.prevent="onSubmit">
          <q-input v-model="username" label="Username" autocomplete="username" outlined />
          <div class="q-mt-md" />
          <q-input
            v-model="password"
            label="Password"
            type="password"
            autocomplete="current-password"
            outlined
          />

          <div class="q-mt-lg">
            <q-btn
              :loading="loading"
              type="submit"
              label="Entrar"
              color="primary"
              class="full-width"
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
type ApiErrorBody = { detail?: string } | string;
import { isAxiosError } from 'axios';
import { ref } from 'vue';
import { useRouter } from 'vue-router';
import { useAuthStore } from 'src/stores/auth.store';
import { useAclStore } from 'src/stores/acl.store';
import { useContextStore } from 'src/stores/context.store';

const router = useRouter();
const auth = useAuthStore();
const acl = useAclStore();
const ctx = useContextStore();

const username = ref('loggin_user');
const password = ref('loggin_pass_change_me');

const loading = ref(false);
const errorMsg = ref<string | null>(null);

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
      const data: ApiErrorBody = e.response?.data;
      const detail = typeof data === 'string' ? data : data?.detail;

      errorMsg.value = detail ?? e.message ?? 'Error de login';
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
