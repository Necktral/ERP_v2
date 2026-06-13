<template>
  <q-page class="app-page">
    <header class="hr-head">
      <div class="row items-center q-gutter-sm">
        <q-btn flat round dense icon="arrow_back" :to="LIST_ROUTE" aria-label="Volver" />
        <div>
          <div class="hr-head__title">Nuevo trabajador</div>
          <div class="hr-head__subtitle">
            Cargá sus datos y otorgale los roles que necesite (pueden ser varios).
          </div>
        </div>
      </div>
    </header>

    <q-form @submit.prevent="create(false)">
      <!-- Datos del trabajador -->
      <section class="hr-block">
        <div class="hr-block__title">Datos</div>
        <div class="hr-foto-row">
          <img v-if="fotoPreview" :src="fotoPreview" alt="Foto" class="hr-foto-preview" />
          <span v-else class="hr-foto-placeholder"><q-icon name="person" size="28px" /></span>
          <q-btn
            outline
            no-caps
            color="primary"
            icon="photo_camera"
            :label="fotoFile ? 'Cambiar foto' : 'Foto (opcional)'"
            @click="fotoInputRef?.click()"
          />
          <q-btn v-if="fotoFile" flat dense round icon="close" aria-label="Quitar foto" @click="quitarFoto" />
          <input ref="fotoInputRef" type="file" accept="image/*" capture="environment" class="hidden" @change="elegirFoto" />
        </div>
        <div class="hr-data-grid">
          <q-input
            ref="firstFieldRef"
            v-model="form.first_name"
            label="Nombres *"
            outlined
            dense
            autofocus
            :rules="[(v) => !!v || 'Requerido']"
            hide-bottom-space
          />
          <q-input v-model="form.last_name" label="Apellidos" outlined dense hide-bottom-space />
          <q-input v-model="form.employee_code" label="Código" outlined dense hide-bottom-space />
          <q-input v-model="form.phone" label="Teléfono" outlined dense hide-bottom-space />
          <q-input
            v-model="form.email"
            label="Correo"
            type="email"
            outlined
            dense
            hide-bottom-space
          />
        </div>
      </section>

      <!-- Datos de planilla: lo que la nómina copia del expediente -->
      <section class="hr-block">
        <div class="hr-block__title">Datos de planilla</div>
        <div class="text-caption text-muted q-mb-sm">
          Estos datos se reflejan tal cual en la nómina (las casillas de la planilla legal).
        </div>
        <div class="hr-data-grid">
          <q-input
            v-model="form.cedula"
            label="Cédula"
            outlined
            dense
            hide-bottom-space
            hint="Ej: 241-150590-0003B"
          />
          <q-input v-model="form.inss_number" label="No. INSS" outlined dense hide-bottom-space />
          <q-select
            v-model="form.gender"
            :options="GENDER_OPTIONS"
            label="Género"
            outlined
            dense
            emit-value
            map-options
            hide-bottom-space
          />
          <q-select
            v-model="form.salary_type"
            :options="SALARY_TYPE_OPTIONS"
            label="Tipo de salario"
            outlined
            dense
            emit-value
            map-options
            hide-bottom-space
          />
          <q-input
            v-model="form.salary_amount"
            :label="form.salary_type === 'DAILY' ? 'Jornal diario C$' : 'Salario mensual C$'"
            type="number"
            step="0.01"
            min="0"
            outlined
            dense
            hide-bottom-space
            :hint="form.salary_type === 'DAILY' ? 'Lo que gana por día trabajado' : 'Lo que gana al mes'"
          />
        </div>
      </section>

      <!-- Roles -->
      <section class="hr-block">
        <div class="hr-block__title">Roles del trabajador</div>
        <div class="text-caption text-muted q-mb-sm">
          Marcá los roles que tendrá. Cada rol trae sus permisos. Podés elegir varios.
        </div>
        <RoleMultiSelect v-model="selectedRoleIds" />
      </section>

      <!-- Acciones -->
      <div class="hr-actions-row">
        <q-btn flat no-caps label="Cancelar" :to="LIST_ROUTE" />
        <q-space />
        <q-btn
          no-caps
          flat
          color="primary"
          label="Crear y agregar otro"
          :loading="saving"
          :disable="!form.first_name.trim()"
          @click="create(true)"
        />
        <q-btn
          type="submit"
          no-caps
          unelevated
          color="primary"
          label="Crear trabajador"
          :loading="saving"
          :disable="!form.first_name.trim()"
        />
      </div>
    </q-form>
  </q-page>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue';
import { QInput, useQuasar } from 'quasar';
import { useRouter } from 'vue-router';
import { apiErrorMessage } from 'src/core/api';
import { createEmployee, setEmployeeRoles, uploadEmployeePhoto } from 'src/features/hr/hr.api';
import type { HrGender, HrSalaryType } from 'src/features/hr/hr.api';
import RoleMultiSelect from 'src/features/hr/RoleMultiSelect.vue';

const LIST_ROUTE = '/recursos-humanos/trabajadores';

const GENDER_OPTIONS = [
  { label: 'Masculino', value: 'M' },
  { label: 'Femenino', value: 'F' },
];
const SALARY_TYPE_OPTIONS = [
  { label: 'Por día (jornal)', value: 'DAILY' },
  { label: 'Mensual', value: 'MONTHLY' },
];

const $q = useQuasar();
const router = useRouter();

const saving = ref(false);
const firstFieldRef = ref<QInput | null>(null);
const selectedRoleIds = ref<number[]>([]);

// Foto opcional: se elige acá y se sube DESPUÉS de crear (necesita el id).
const fotoInputRef = ref<HTMLInputElement | null>(null);
const fotoFile = ref<File | null>(null);
const fotoPreview = ref<string | null>(null);

function elegirFoto(ev: Event) {
  const input = ev.target as HTMLInputElement;
  const file = input.files?.[0];
  input.value = '';
  if (!file) return;
  if (fotoPreview.value) URL.revokeObjectURL(fotoPreview.value);
  fotoFile.value = file;
  fotoPreview.value = URL.createObjectURL(file);
}

function quitarFoto() {
  if (fotoPreview.value) URL.revokeObjectURL(fotoPreview.value);
  fotoFile.value = null;
  fotoPreview.value = null;
}

const form = reactive<{
  first_name: string;
  last_name: string;
  employee_code: string;
  phone: string;
  email: string;
  cedula: string;
  inss_number: string;
  gender: HrGender;
  salary_type: HrSalaryType;
  salary_amount: string;
}>({
  first_name: '',
  last_name: '',
  employee_code: '',
  phone: '',
  email: '',
  cedula: '',
  inss_number: '',
  gender: '',
  salary_type: 'DAILY',
  salary_amount: '',
});

function resetForm() {
  form.first_name = '';
  form.last_name = '';
  form.employee_code = '';
  form.phone = '';
  form.email = '';
  form.cedula = '';
  form.inss_number = '';
  form.gender = '';
  form.salary_type = 'DAILY';
  form.salary_amount = '';
  selectedRoleIds.value = [];
  quitarFoto();
}


async function create(another: boolean) {
  if (!form.first_name.trim()) return;
  saving.value = true;
  try {
    const id = await createEmployee({
      first_name: form.first_name.trim(),
      last_name: form.last_name.trim(),
      employee_code: form.employee_code.trim(),
      phone: form.phone.trim(),
      email: form.email.trim(),
      cedula: form.cedula.trim(),
      inss_number: form.inss_number.trim(),
      gender: form.gender,
      salary_type: form.salary_type,
      ...(form.salary_type === 'DAILY'
        ? { daily_rate_nio: form.salary_amount || '0' }
        : { monthly_salary_nio: form.salary_amount || '0' }),
    });
    if (selectedRoleIds.value.length > 0) {
      await setEmployeeRoles(id, selectedRoleIds.value);
    }
    if (fotoFile.value) {
      try {
        await uploadEmployeePhoto(id, fotoFile.value);
      } catch {
        $q.notify({ type: 'warning', message: 'Trabajador creado, pero la foto no se pudo subir (podés ponerla desde su perfil).' });
      }
    }
    $q.notify({ type: 'positive', message: 'Trabajador creado.' });
    if (another) {
      resetForm();
      firstFieldRef.value?.focus();
    } else {
      await router.push(LIST_ROUTE);
    }
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e) || 'No se pudo crear el trabajador.' });
  } finally {
    saving.value = false;
  }
}
</script>

<style scoped>

.hr-head {
  margin-bottom: var(--app-space-5);
}

.hr-head__title {
  font-family: 'Manrope', 'IBM Plex Sans', sans-serif;
  font-size: 1.5rem;
  font-weight: 800;
  color: var(--app-text);
}

.hr-head__subtitle {
  color: var(--app-text-muted);
  font-size: 0.85rem;
}

.hr-block {
  padding: var(--app-space-5);
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-lg);
  background: var(--app-surface);
  margin-bottom: var(--app-space-4);
}

.hr-block__title {
  font-weight: 800;
  font-size: 1.05rem;
  color: var(--app-text);
  margin-bottom: var(--app-space-3);
}

.hr-data-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: var(--app-space-3);
}

.hr-foto-row {
  display: flex;
  align-items: center;
  gap: var(--app-space-3);
  margin-bottom: var(--app-space-3);
}

.hr-foto-preview,
.hr-foto-placeholder {
  width: 56px;
  height: 56px;
  border-radius: 50%;
  object-fit: cover;
  border: 1px solid var(--app-border);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: var(--app-text-muted);
  background: var(--app-surface-strong);
  flex-shrink: 0;
}

.hidden {
  display: none;
}

.hr-actions-row {
  display: flex;
  align-items: center;
  gap: var(--app-space-2);
  margin-top: var(--app-space-4);
}

</style>
