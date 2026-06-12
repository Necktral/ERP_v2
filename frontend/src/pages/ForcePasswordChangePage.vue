<template>
  <q-page class="flex flex-center bg-grey-3">
    <q-card style="width: 440px; max-width: 92vw">
      <q-card-section>
        <div class="text-h6 text-center text-primary">Cambiar contraseña</div>
        <div class="text-caption text-center text-grey">
          Tu cuenta requiere un cambio de contraseña.
        </div>
      </q-card-section>

      <q-card-section>
        <q-form @submit.prevent="submitChange">
          <q-input
            v-model="form.old_password"
            label="Contraseña actual"
            :type="showPassword ? 'text' : 'password'"
            outlined
            dense
            :rules="[(val) => !!val || 'Requerido']"
          >
            <template #append>
              <q-icon
                :name="showPassword ? 'visibility_off' : 'visibility'"
                class="cursor-pointer"
                :aria-label="showPassword ? 'Ocultar contraseña' : 'Mostrar contraseña'"
                @click="showPassword = !showPassword"
              />
            </template>
          </q-input>

          <q-input
            v-model="form.new_password"
            label="Nueva contraseña"
            :type="showPassword ? 'text' : 'password'"
            :hint="hint"
            class="q-mt-md"
            outlined
            dense
            :rules="[
              (val) => !!val || 'Requerido',
              () => strength.meetsPolicy || 'Aún no cumple la política de seguridad',
            ]"
          />
          <PasswordStrengthMeter :password="form.new_password" :checks="checks" :strength="strength" />

          <q-input
            v-model="form.confirm_password"
            label="Confirmar nueva contraseña"
            :type="showPassword ? 'text' : 'password'"
            hint="Vuelve a escribir la nueva contraseña para confirmarla"
            class="q-mt-md"
            outlined
            dense
            :rules="[
              (val) => !!val || 'Requerido',
              (val) => val === form.new_password || 'Las contraseñas no coinciden',
            ]"
          />

          <div class="q-mt-lg">
            <q-btn
              label="Actualizar contraseña"
              type="submit"
              color="primary"
              class="full-width"
              :loading="loading"
            />
          </div>
        </q-form>
      </q-card-section>
    </q-card>
  </q-page>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref, toRef } from 'vue';
import { useRouter } from 'vue-router';
import { api } from 'src/boot/axios';
import { useAuthStore } from 'src/stores/auth.store';
import { useQuasar } from 'quasar';
import {
  DEFAULT_PASSWORD_POLICY,
  fetchPasswordPolicy,
  usePasswordStrength,
  type PasswordPolicy,
} from 'src/features/auth/usePasswordStrength';
import PasswordStrengthMeter from 'src/features/auth/PasswordStrengthMeter.vue';

const router = useRouter();
const authStore = useAuthStore();
const $q = useQuasar();

const loading = ref(false);
const showPassword = ref(false);
const form = reactive({
  old_password: '',
  new_password: '',
  confirm_password: '',
});

// Política real del backend (fuente única) para el medidor de fortaleza.
const passwordPolicy = ref<PasswordPolicy>({ ...DEFAULT_PASSWORD_POLICY });
const { hint, checks, strength } = usePasswordStrength(toRef(form, 'new_password'), passwordPolicy);

onMounted(async () => {
  const policy = await fetchPasswordPolicy();
  if (policy) passwordPolicy.value = policy;
});

async function submitChange() {
  loading.value = true;
  try {
    await api.post('/auth/password/', form);

    $q.notify({ type: 'positive', message: 'Contraseña actualizada correctamente' });

    // Actualizar estado local
    if (authStore.user) {
      authStore.user.must_change_password = false;
    }

    await router.push('/dashboard');
  } catch (error) {
    const err = error as { response?: { data?: { detail?: string } } };
    const msg = err.response?.data?.detail || 'No se pudo actualizar la contraseña';
    $q.notify({ type: 'negative', message: msg });
  } finally {
    loading.value = false;
  }
}
</script>
