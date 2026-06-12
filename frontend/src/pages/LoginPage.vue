<template>
  <q-page class="login-page">
    <div class="login-card app-fade-up">
      <div class="login-brand">
        <img v-if="brand.logoUrl" :src="brand.logoUrl" :alt="brand.name" class="login-logo" />
        <span v-else class="login-mark" aria-hidden="true">◆</span>
        <div class="login-brand__text">
          <div class="login-brand__name">{{ brand.name }}</div>
          <div class="login-brand__claim">{{ brand.tagline }}</div>
        </div>
      </div>

      <q-banner v-if="bootstrapChecked && isFresh" class="login-banner login-banner--info" rounded>
        <div class="text-weight-medium">Primer arranque: aún no hay usuarios.</div>
        <div class="text-caption">Crea el usuario administrador inicial y configura tu organización.</div>
        <template #action>
          <q-btn unelevated color="primary" label="Crear usuario inicial" to="/bootstrap" />
        </template>
      </q-banner>

      <q-form class="login-form" @submit.prevent="onSubmit">
        <q-input
          v-model="username"
          label="Usuario"
          autocomplete="username"
          outlined
          :autofocus="!usuarioRecordado"
          :disable="isFresh"
        >
          <template #prepend>
            <q-icon name="person" />
          </template>
        </q-input>

        <q-input
          v-model="password"
          label="Contraseña"
          :type="showPassword ? 'text' : 'password'"
          autocomplete="current-password"
          outlined
          :autofocus="usuarioRecordado"
          :disable="isFresh"
        >
          <template #prepend>
            <q-icon name="lock" />
          </template>
          <template #append>
            <q-icon
              :name="showPassword ? 'visibility_off' : 'visibility'"
              class="cursor-pointer"
              :aria-label="showPassword ? 'Ocultar contraseña' : 'Mostrar contraseña'"
              @click="showPassword = !showPassword"
            />
          </template>
        </q-input>

        <q-checkbox
          v-model="rememberUser"
          label="Recordar usuario"
          dense
          class="login-remember"
          :disable="isFresh"
        />

        <q-btn
          :loading="loading"
          type="submit"
          label="Ingresar"
          color="primary"
          unelevated
          class="login-submit full-width"
          :disable="isFresh"
        />
      </q-form>

      <q-banner v-if="errorMsg" class="login-banner login-banner--error" rounded>
        {{ errorMsg }}
        <template #action>
          <q-btn flat label="Cerrar" @click="errorMsg = null" />
        </template>
      </q-banner>

      <div class="login-credit">Desarrollado por {{ brand.developer }}</div>
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { isAxiosError } from 'axios';
import { computed, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import { useAuthStore } from 'src/stores/auth.store';
import { useSessionBootstrapStore } from 'src/stores/session-bootstrap.store';
import { BRAND } from 'src/config/brand';

const brand = BRAND;

const router = useRouter();
const auth = useAuthStore();
const sessionBootstrap = useSessionBootstrapStore();

// Recordar usuario: SOLO el nombre (jamás la contraseña), en este navegador.
const REMEMBER_KEY = 'nt_remembered_username';
const savedUsername = localStorage.getItem(REMEMBER_KEY);
const usuarioRecordado = !!savedUsername;

const username = ref(savedUsername ?? '');
const password = ref('');
const showPassword = ref(false);
const rememberUser = ref(usuarioRecordado);

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

    // Login correcto: persistir (o borrar) el usuario según el checkbox.
    if (rememberUser.value) {
      localStorage.setItem(REMEMBER_KEY, username.value.trim());
    } else {
      localStorage.removeItem(REMEMBER_KEY);
    }

    if (auth.isTwoFactorRequired) {
      await router.replace('/login/2fa');
      return;
    }

    // Carril privado canónico: resolver sesión/contexto/capacidades desde bootstrap único.
    await sessionBootstrap.loadSession({ force: true });

    if (auth.user?.must_change_password) {
      await router.replace('/password-change');
      return;
    }

    if (sessionBootstrap.payload?.bootstrap_state?.setup_required) {
      await router.replace('/bootstrap');
      return;
    }

    // Frontend en reconstrucción: el app gated arranca en RR.HH.
    await router.replace('/');
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
      errorMsg.value = detail || e.message || 'No pudimos iniciar sesión';
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

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--app-space-4);
  background: var(--app-bg-gradient);
  background-color: var(--app-bg);
}

.login-card {
  width: 100%;
  max-width: 420px;
  display: flex;
  flex-direction: column;
  gap: var(--app-space-5);
  padding: var(--app-space-8) var(--app-space-6);
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-lg);
  background: var(--app-surface);
  box-shadow: var(--app-shadow-card);
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
}

.login-brand {
  display: flex;
  align-items: center;
  gap: var(--app-space-3);
}

.login-mark {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  border-radius: var(--app-radius-md);
  font-size: 1.25rem;
  color: #fff;
  background: linear-gradient(135deg, var(--app-primary), var(--app-secondary));
  box-shadow: var(--app-shadow-soft);
}

.login-brand__name {
  font-family: 'Manrope', 'IBM Plex Sans', sans-serif;
  font-size: 1.35rem;
  font-weight: 800;
  letter-spacing: 0.04em;
  line-height: 1.1;
  color: var(--app-text);
}

.login-brand__claim {
  font-size: 0.82rem;
  color: var(--app-text-muted);
}

.login-form {
  display: flex;
  flex-direction: column;
  gap: var(--app-space-4);
}

.login-remember {
  align-self: flex-start;
  color: var(--app-text-muted);
  font-size: 0.85rem;
}

.login-submit {
  height: 44px;
  font-weight: 600;
}

.login-banner {
  border: 1px solid var(--app-border);
  background: var(--app-surface-strong);
}

.login-banner--error {
  border-color: rgba(193, 56, 56, 0.4);
}

.login-logo {
  height: 44px;
  width: auto;
  max-width: 160px;
  object-fit: contain;
}

.login-credit {
  margin-top: var(--app-space-1);
  text-align: center;
  font-size: 0.72rem;
  letter-spacing: 0.02em;
  color: var(--app-text-muted);
}
</style>
