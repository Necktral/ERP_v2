<template>
  <q-page class="bootstrap-page">
    <div class="bootstrap-card app-fade-up">
      <!-- Marca configurable por despliegue -->
      <div class="bootstrap-brand">
        <img v-if="brand.logoUrl" :src="brand.logoUrl" :alt="brand.name" class="bootstrap-logo" />
        <span v-else class="bootstrap-mark" aria-hidden="true">◆</span>
        <div class="bootstrap-brand__text">
          <div class="bootstrap-brand__name">{{ brand.name }}</div>
          <div class="bootstrap-brand__claim">Configuración inicial del sistema</div>
        </div>
      </div>

      <!-- Indicador de pasos -->
      <div class="bootstrap-steps" v-if="step < 3">
        <div class="bootstrap-step" :class="{ 'is-active': step === 1, 'is-done': step > 1 }">
          <span class="bootstrap-step__dot">
            <q-icon v-if="step > 1" name="check" size="16px" />
            <template v-else>1</template>
          </span>
          <span class="bootstrap-step__label">Administrador</span>
        </div>
        <span class="bootstrap-step__sep" />
        <div class="bootstrap-step" :class="{ 'is-active': step === 2 }">
          <span class="bootstrap-step__dot">2</span>
          <span class="bootstrap-step__label">Organización</span>
        </div>
      </div>

      <q-banner v-if="errorMsg" class="bootstrap-banner" rounded>
        <template #avatar><q-icon name="error" color="negative" /></template>
        {{ errorMsg }}
        <template #action>
          <q-btn flat label="Cerrar" @click="errorMsg = null" />
        </template>
      </q-banner>

      <!-- Paso 1: Administrador inicial -->
      <q-form v-if="step === 1" class="bootstrap-form" @submit.prevent="createAdmin">
        <div class="text-caption text-muted">
          Crea la cuenta de administrador con la que gobernarás el sistema.
        </div>
        <div class="row q-col-gutter-md">
          <div class="col-12 col-sm-6">
            <q-input v-model="adminForm.first_name" label="Nombres" outlined dense />
          </div>
          <div class="col-12 col-sm-6">
            <q-input v-model="adminForm.last_name" label="Apellidos" outlined dense />
          </div>
        </div>
        <q-input
          v-model="adminForm.username"
          label="Usuario"
          hint="Con este usuario iniciarás sesión como administrador"
          autocomplete="username"
          outlined
          dense
          :rules="[(val) => !!val || 'Requerido']"
        >
          <template #prepend><q-icon name="person" /></template>
        </q-input>
        <q-input
          v-model="adminForm.email"
          label="Correo electrónico (opcional)"
          type="email"
          autocomplete="email"
          outlined
          dense
        >
          <template #prepend><q-icon name="mail" /></template>
        </q-input>
        <q-input
          v-model="adminForm.password"
          label="Contraseña"
          :type="showPassword ? 'text' : 'password'"
          :hint="hint"
          autocomplete="new-password"
          outlined
          dense
          :rules="[
            (val) => !!val || 'Requerido',
            () => strength.meetsPolicy || 'Aún no cumple la política de seguridad',
          ]"
        >
          <template #prepend><q-icon name="lock" /></template>
          <template #append>
            <q-icon
              :name="showPassword ? 'visibility_off' : 'visibility'"
              class="cursor-pointer"
              :aria-label="showPassword ? 'Ocultar contraseña' : 'Mostrar contraseña'"
              @click="showPassword = !showPassword"
            />
          </template>
        </q-input>
        <PasswordStrengthMeter
          :password="adminForm.password"
          :checks="checks"
          :strength="strength"
        />
        <q-input
          v-model="adminForm.password_confirm"
          label="Confirmar contraseña"
          :type="showPassword ? 'text' : 'password'"
          hint="Vuelve a escribir la contraseña para confirmarla"
          autocomplete="new-password"
          outlined
          dense
          :rules="[
            (val) => !!val || 'Requerido',
            (val) => val === adminForm.password || 'Las contraseñas no coinciden',
          ]"
        >
          <template #prepend><q-icon name="lock_reset" /></template>
        </q-input>
        <q-btn
          type="submit"
          label="Crear administrador y continuar"
          color="primary"
          unelevated
          class="bootstrap-submit full-width"
          :loading="loading"
          :disable="!strength.meetsPolicy"
        />
      </q-form>

      <!-- Paso 2: Organización -->
      <q-form v-else-if="step === 2" class="bootstrap-form" @submit.prevent="createOrg">
        <div class="text-caption text-muted">
          Define la estructura inicial: un <strong>grupo (holding)</strong>, su primera
          <strong>empresa</strong> (con RUC) y una <strong>sucursal</strong>.
        </div>

        <div class="bootstrap-group-title">Grupo empresarial (holding)</div>
        <q-input
          v-model="orgForm.holding_name"
          label="Nombre del holding"
          hint="El grupo que agrupa a tus empresas"
          outlined
          dense
          :rules="[(val) => !!val || 'Requerido']"
        >
          <template #prepend><q-icon name="account_tree" /></template>
        </q-input>

        <div class="bootstrap-group-title">Empresa operativa</div>
        <div class="row q-col-gutter-md">
          <div class="col-12 col-sm-8">
            <q-input
              v-model="orgForm.company_name"
              label="Nombre de la empresa"
              outlined
              dense
              :rules="[(val) => !!val || 'Requerido']"
            >
              <template #prepend><q-icon name="business" /></template>
            </q-input>
          </div>
          <div class="col-12 col-sm-4">
            <q-input
              v-model="orgForm.company_tax_id"
              label="RUC (opcional)"
              hint="Identificación fiscal"
              outlined
              dense
            />
          </div>
        </div>

        <div class="bootstrap-group-title">Sucursal principal</div>
        <q-input
          v-model="orgForm.branch_name"
          label="Nombre de la sucursal"
          outlined
          dense
          :rules="[(val) => !!val || 'Requerido']"
        >
          <template #prepend><q-icon name="store" /></template>
        </q-input>
        <q-input
          v-model="orgForm.branch_address"
          label="Dirección de la sucursal (opcional)"
          outlined
          dense
        />

        <q-btn
          type="submit"
          label="Completar configuración"
          color="positive"
          unelevated
          class="bootstrap-submit full-width"
          :loading="loading"
        />
      </q-form>

      <!-- Paso 3: Listo -->
      <div v-else class="bootstrap-done">
        <q-icon name="check_circle" color="positive" size="56px" />
        <div class="bootstrap-done__title">¡Configuración completa!</div>
        <div class="bootstrap-done__summary">
          <div><strong>Holding:</strong> {{ orgForm.holding_name }}</div>
          <div><strong>Empresa:</strong> {{ orgForm.company_name }}</div>
          <div><strong>Sucursal:</strong> {{ orgForm.branch_name }}</div>
        </div>
        <div class="text-caption text-muted">
          Quedaste como administrador de <strong>{{ orgForm.company_name }}</strong>. Los módulos de
          esta empresa se configurarán a continuación (cada empresa habilita los suyos).
        </div>
        <q-btn label="Entrar al sistema" color="primary" unelevated to="/" />
      </div>

      <div class="bootstrap-credit">Desarrollado por {{ brand.developer }}</div>
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref, toRef } from 'vue';
import { isAxiosError } from 'axios';
import { useRouter } from 'vue-router';
import { api } from 'src/boot/axios';
import { useAuthStore } from 'src/stores/auth.store';
import { BRAND } from 'src/config/brand';
import {
  DEFAULT_PASSWORD_POLICY,
  fetchPasswordPolicy,
  usePasswordStrength,
  type PasswordPolicy,
} from 'src/features/auth/usePasswordStrength';
import PasswordStrengthMeter from 'src/features/auth/PasswordStrengthMeter.vue';

const brand = BRAND;
const router = useRouter();
const authStore = useAuthStore();

const step = ref(1);
const loading = ref(false);
const errorMsg = ref<string | null>(null);
const showPassword = ref(false);

const adminForm = reactive({
  first_name: '',
  last_name: '',
  username: '',
  email: '',
  password: '',
  password_confirm: '',
});

const orgForm = reactive({
  holding_name: '',
  company_name: '',
  company_tax_id: '',
  branch_name: 'Sucursal principal',
  branch_address: '',
});

// Política real del backend (fuente única) para el medidor de fortaleza.
const passwordPolicy = ref<PasswordPolicy>({ ...DEFAULT_PASSWORD_POLICY });
const { hint, checks, strength } = usePasswordStrength(toRef(adminForm, 'password'), passwordPolicy);

onMounted(async () => {
  await authStore.checkBootstrap();

  const policy = await fetchPasswordPolicy();
  if (policy) passwordPolicy.value = policy;

  // Si ya hay un admin (sesión iniciada) y falta la organización, saltar al paso 2.
  if (authStore.isAuthenticated) {
    step.value = 2;
    return;
  }
  // No es primer arranque y no hay sesión → este asistente no aplica.
  if (!authStore.bootstrapState.is_fresh) {
    await router.replace('/login');
  }
});

function extractError(e: unknown, fallback: string): string {
  if (isAxiosError(e)) {
    const data: unknown = e.response?.data;
    if (typeof data === 'string') return data;
    if (data && typeof data === 'object') {
      const d = data as Record<string, unknown>;
      if (typeof d.detail === 'string') return d.detail;
      if (Array.isArray(d.non_field_errors) && d.non_field_errors.length > 0) {
        return String(d.non_field_errors[0]);
      }
      for (const key of Object.keys(d)) {
        const v = d[key];
        if (Array.isArray(v) && v.length > 0) return `${key}: ${String(v[0])}`;
        if (typeof v === 'string') return `${key}: ${v}`;
      }
    }
    return e.message || fallback;
  }
  return e instanceof Error ? e.message : fallback;
}

async function createAdmin() {
  loading.value = true;
  errorMsg.value = null;
  try {
    await api.post('/auth/bootstrap/init/', adminForm);
    // Auto-login con la cuenta recién creada (BootstrapOrgView exige autenticación).
    await authStore.login(adminForm.username.trim(), adminForm.password);
    step.value = 2;
  } catch (e) {
    errorMsg.value = extractError(e, 'No se pudo crear el administrador.');
  } finally {
    loading.value = false;
  }
}

async function createOrg() {
  loading.value = true;
  errorMsg.value = null;
  try {
    await api.post('/auth/bootstrap/org/', orgForm);
    step.value = 3;
  } catch (e) {
    errorMsg.value = extractError(e, 'No se pudo completar la configuración.');
  } finally {
    loading.value = false;
  }
}
</script>

<style scoped>
.bootstrap-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--app-space-4);
  background: var(--app-bg-gradient);
  background-color: var(--app-bg);
}

.bootstrap-card {
  width: 100%;
  max-width: 560px;
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

.bootstrap-brand {
  display: flex;
  align-items: center;
  gap: var(--app-space-3);
}

.bootstrap-mark {
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

.bootstrap-logo {
  height: 44px;
  width: auto;
  max-width: 160px;
  object-fit: contain;
}

.bootstrap-brand__name {
  font-family: 'Manrope', 'IBM Plex Sans', sans-serif;
  font-size: 1.35rem;
  font-weight: 800;
  letter-spacing: 0.04em;
  line-height: 1.1;
  color: var(--app-text);
}

.bootstrap-brand__claim {
  font-size: 0.82rem;
  color: var(--app-text-muted);
}

.bootstrap-steps {
  display: flex;
  align-items: center;
  gap: var(--app-space-2);
}

.bootstrap-step {
  display: flex;
  align-items: center;
  gap: var(--app-space-2);
  color: var(--app-text-muted);
}

.bootstrap-step__dot {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  border-radius: 50%;
  font-size: 0.85rem;
  font-weight: 700;
  border: 1px solid var(--app-border);
  background: var(--app-surface-strong);
}

.bootstrap-step.is-active .bootstrap-step__dot {
  color: #fff;
  background: var(--app-primary);
  border-color: var(--app-primary);
}

.bootstrap-step.is-done .bootstrap-step__dot {
  color: #fff;
  background: var(--app-secondary);
  border-color: var(--app-secondary);
}

.bootstrap-step.is-active .bootstrap-step__label {
  color: var(--app-text);
  font-weight: 600;
}

.bootstrap-step__sep {
  flex: 1;
  height: 1px;
  background: var(--app-border);
}

.bootstrap-form {
  display: flex;
  flex-direction: column;
  gap: var(--app-space-4);
}

.bootstrap-group-title {
  font-size: 0.82rem;
  font-weight: 700;
  letter-spacing: 0.02em;
  color: var(--app-primary);
  margin-top: var(--app-space-2);
}

.bootstrap-submit {
  height: 44px;
  font-weight: 600;
  margin-top: var(--app-space-2);
}

.bootstrap-banner {
  border: 1px solid var(--app-border-strong);
  background: var(--app-surface-strong);
}

.bootstrap-done {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  gap: var(--app-space-3);
  padding: var(--app-space-4) 0;
}

.bootstrap-done__title {
  font-size: 1.25rem;
  font-weight: 800;
  color: var(--app-text);
}

.bootstrap-done__summary {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 0.9rem;
  color: var(--app-text);
}

.text-muted {
  color: var(--app-text-muted);
}

.bootstrap-credit {
  margin-top: var(--app-space-1);
  text-align: center;
  font-size: 0.72rem;
  letter-spacing: 0.02em;
  color: var(--app-text-muted);
}
</style>
