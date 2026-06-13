<template>
  <q-page class="app-page">
    <div v-if="loading" class="hr-loading"><q-spinner size="32px" /> Cargando expediente…</div>

    <template v-else-if="profile">
      <!-- Encabezado del expediente -->
      <header class="perfil-head">
        <div class="perfil-head__main">
          <q-btn flat round icon="arrow_back" aria-label="Volver" to="/recursos-humanos/trabajadores" />
          <div class="perfil-head__foto">
            <EmployeeAvatar
              :key="photoVersion"
              :employee-id="employeeId"
              :nombre="`${profile.first_name} ${profile.last_name}`"
              :has-photo="profile.has_photo"
              :size="64"
            />
            <div class="perfil-head__foto-acciones">
              <q-btn
                flat
                dense
                round
                size="sm"
                icon="photo_camera"
                :loading="savingPhoto"
                aria-label="Cambiar foto"
                @click="fotoInputRef?.click()"
              >
                <q-tooltip>{{ profile.has_photo ? 'Cambiar foto' : 'Agregar foto' }}</q-tooltip>
              </q-btn>
              <q-btn
                v-if="profile.has_photo"
                flat
                dense
                round
                size="sm"
                icon="no_photography"
                aria-label="Quitar foto"
                @click="quitarFoto"
              >
                <q-tooltip>Quitar foto</q-tooltip>
              </q-btn>
            </div>
            <input
              ref="fotoInputRef"
              type="file"
              accept="image/*"
              capture="environment"
              class="hidden"
              @change="subirFoto"
            />
          </div>
          <div class="perfil-head__id">
            <div class="perfil-head__name">
              {{ profile.first_name }} {{ profile.last_name }}
              <q-chip
                dense
                :color="statusColor"
                text-color="white"
                class="perfil-head__status"
                :label="statusLabel"
              />
            </div>
            <div class="perfil-head__meta">
              <span v-if="profile.employee_code">Código: {{ profile.employee_code }}</span>
              <span v-if="profile.linked_username">
                Usuario: {{ profile.linked_username }}
                <q-icon
                  :name="profile.linked_user_active ? 'check_circle' : 'block'"
                  :color="profile.linked_user_active ? 'positive' : 'negative'"
                  size="14px"
                >
                  <q-tooltip>{{ profile.linked_user_active ? 'Acceso habilitado' : 'Acceso bloqueado' }}</q-tooltip>
                </q-icon>
              </span>
              <span v-else>Sin acceso al sistema</span>
            </div>
          </div>
        </div>
        <div class="perfil-head__actions">
          <template v-if="profile.employment_status === 'ACTIVO'">
            <q-btn outline no-caps color="warning" icon="pause_circle" label="Suspender" @click="suspendOpen = true" />
            <q-btn outline no-caps color="negative" icon="person_off" label="Dar de baja" @click="bajaOpen = true" />
          </template>
          <template v-else-if="profile.employment_status === 'SUSPENDIDO'">
            <q-btn unelevated no-caps color="primary" icon="play_circle" label="Reintegrar" @click="openSimple('REINTEGRO')" />
            <q-btn outline no-caps color="negative" icon="person_off" label="Dar de baja" @click="bajaOpen = true" />
          </template>
          <template v-else>
            <q-btn unelevated no-caps color="primary" icon="replay" label="Reingresar" @click="openSimple('REINGRESO')" />
          </template>
        </div>
      </header>

      <q-banner v-if="profile.employment_status === 'SUSPENDIDO'" rounded class="perfil-banner perfil-banner--warn">
        <template #avatar><q-icon name="pause_circle" color="warning" /></template>
        Trabajador suspendido{{ lastSuspension?.end_date ? ` hasta el ${lastSuspension.end_date}` : '' }}.
        {{ lastSuspension?.reason_detail || '' }}
      </q-banner>
      <q-banner v-else-if="profile.employment_status === 'BAJA'" rounded class="perfil-banner perfil-banner--neg">
        <template #avatar><q-icon name="person_off" color="negative" /></template>
        Trabajador dado de baja. Su acceso y asignaciones fueron revocados; el expediente queda como historial.
      </q-banner>

      <!-- Pestañas del expediente -->
      <q-tabs v-model="tab" dense no-caps align="left" class="perfil-tabs" active-color="primary">
        <q-tab name="datos" icon="badge" label="Datos y roles" />
        <q-tab name="contratos" icon="description" :label="`Contratos (${profile.contracts.length})`" />
        <q-tab name="memos" icon="sticky_note_2" :label="`Memorandos (${profile.memos.length})`" />
        <q-tab name="historial" icon="history" :label="`Historial (${profile.lifecycle_events.length})`" />
      </q-tabs>
      <q-separator class="q-mb-md" />

      <!-- ───── Datos + roles ───── -->
      <section v-if="tab === 'datos'" class="perfil-grid">
        <q-card flat class="perfil-card">
          <q-card-section>
            <div class="perfil-card__title">Datos personales</div>
            <q-form class="app-form" @submit.prevent="saveData">
              <q-input v-model="form.first_name" outlined dense label="Nombres" :rules="[(v) => !!v || 'Requerido']" />
              <q-input v-model="form.last_name" outlined dense label="Apellidos" />
              <q-input v-model="form.employee_code" outlined dense label="Código" />
              <q-input v-model="form.phone" outlined dense label="Teléfono" />
              <q-input v-model="form.email" outlined dense type="email" label="Correo" />
              <div class="perfil-card__title q-mt-sm">Datos de planilla</div>
              <div class="perfil-muted q-mb-xs">Se reflejan tal cual en la nómina.</div>
              <q-input v-model="form.cedula" outlined dense label="Cédula" hint="Ej: 241-150590-0003B" />
              <q-input v-model="form.inss_number" outlined dense label="No. INSS" />
              <q-select
                v-model="form.gender"
                :options="[
                  { label: 'Masculino', value: 'M' },
                  { label: 'Femenino', value: 'F' },
                ]"
                outlined
                dense
                emit-value
                map-options
                label="Género"
              />
              <q-select
                v-model="form.salary_type"
                :options="[
                  { label: 'Por día (jornal)', value: 'DAILY' },
                  { label: 'Mensual', value: 'MONTHLY' },
                ]"
                outlined
                dense
                emit-value
                map-options
                label="Tipo de salario"
              />
              <q-input
                v-model="form.salary_amount"
                outlined
                dense
                type="number"
                step="0.01"
                min="0"
                :label="form.salary_type === 'DAILY' ? 'Jornal diario C$' : 'Salario mensual C$'"
                :hint="form.salary_type === 'DAILY' ? 'Lo que gana por día trabajado' : 'Lo que gana al mes'"
              />
              <q-btn type="submit" unelevated no-caps color="primary" label="Guardar datos" :loading="savingData" />
            </q-form>
          </q-card-section>
        </q-card>

        <q-card flat class="perfil-card">
          <q-card-section>
            <div class="perfil-card__title">
              Roles del trabajador
              <span class="perfil-muted">({{ selectedRoleIds.length }})</span>
            </div>
            <div v-if="profile.employment_status === 'BAJA'" class="perfil-muted q-mb-sm">
              El trabajador está de baja: sus roles quedan como historial y no otorgan acceso.
            </div>
            <RoleMultiSelect v-model="selectedRoleIds" />
            <q-btn
              class="q-mt-md"
              unelevated
              no-caps
              color="primary"
              label="Guardar roles"
              :loading="savingRoles"
              @click="saveRoles"
            />
          </q-card-section>
        </q-card>
      </section>

      <!-- ───── Contratos ───── -->
      <section v-else-if="tab === 'contratos'">
        <div class="perfil-section-head">
          <div class="perfil-card__title">Contratos laborales</div>
          <q-btn
            unelevated
            no-caps
            color="primary"
            icon="post_add"
            label="Nuevo contrato"
            :disable="profile.employment_status === 'BAJA'"
            @click="openNewContract"
          />
        </div>
        <q-table
          flat
          :rows="profile.contracts"
          :columns="contractCols"
          row-key="id"
          hide-pagination
          :pagination="{ rowsPerPage: 0 }"
          no-data-label="Sin contratos. Creá el primero con «Nuevo contrato»."
        >
          <template #body-cell-status="props">
            <q-td :props="props">
              <q-chip dense :color="contractStatusColor(props.row.status)" text-color="white" :label="props.row.status" />
            </q-td>
          </template>
          <template #body-cell-acciones="props">
            <q-td :props="props" class="text-right">
              <q-btn flat dense round icon="visibility" @click="openContract(props.row.id)">
                <q-tooltip>Ver / editar texto</q-tooltip>
              </q-btn>
            </q-td>
          </template>
        </q-table>
      </section>

      <!-- ───── Memorandos ───── -->
      <section v-else-if="tab === 'memos'">
        <div class="perfil-section-head">
          <div class="perfil-card__title">Memorandos y relaciones laborales</div>
          <q-btn unelevated no-caps color="primary" icon="note_add" label="Nuevo memorando" @click="openNewMemo" />
        </div>
        <q-table
          flat
          :rows="profile.memos"
          :columns="memoCols"
          row-key="id"
          hide-pagination
          :pagination="{ rowsPerPage: 0 }"
          no-data-label="Sin memorandos registrados."
        >
          <template #body-cell-status="props">
            <q-td :props="props">
              <q-chip
                dense
                :color="props.row.status === 'EMITIDO' ? 'secondary' : 'grey-7'"
                text-color="white"
                :label="props.row.status"
              />
            </q-td>
          </template>
          <template #body-cell-acciones="props">
            <q-td :props="props" class="text-right">
              <q-btn flat dense round icon="visibility" @click="viewMemo(props.row)">
                <q-tooltip>Ver</q-tooltip>
              </q-btn>
              <q-btn
                v-if="props.row.status === 'EMITIDO'"
                flat
                dense
                round
                icon="cancel"
                color="negative"
                @click="doAnnulMemo(props.row)"
              >
                <q-tooltip>Anular</q-tooltip>
              </q-btn>
            </q-td>
          </template>
        </q-table>
      </section>

      <!-- ───── Historial ───── -->
      <section v-else>
        <div class="perfil-card__title q-mb-md">Historial laboral</div>
        <div v-if="profile.lifecycle_events.length === 0" class="perfil-muted">
          Sin eventos: el trabajador no ha tenido suspensiones, bajas ni reingresos.
        </div>
        <q-timeline v-else color="primary">
          <q-timeline-entry
            v-for="ev in profile.lifecycle_events"
            :key="ev.id"
            :title="ev.event_type_label + (ev.reason_code && ev.reason_code !== 'FIN_SUSPENSION' && ev.reason_code !== 'RECONTRATACION' ? ` — ${reasonLabel(ev)}` : '')"
            :subtitle="`Efectivo: ${ev.effective_date}${ev.end_date ? ' → ' + ev.end_date : ''}${ev.created_by ? ' · por ' + ev.created_by : ''}`"
            :icon="eventIcon(ev.event_type)"
            :color="eventColor(ev.event_type)"
          >
            <div v-if="ev.reason_detail">{{ ev.reason_detail }}</div>
            <div v-if="ev.event_type === 'SUSPENSION'" class="perfil-muted">
              {{ ev.with_pay ? 'Con goce de salario' : 'Sin goce de salario' }}
              {{ ev.access_suspended ? ' · acceso al sistema bloqueado' : '' }}
            </div>
          </q-timeline-entry>
        </q-timeline>
      </section>
    </template>

    <!-- ═══════ Diálogo: Suspender ═══════ -->
    <q-dialog v-model="suspendOpen">
      <q-card class="perfil-dialog">
        <q-card-section>
          <div class="text-h6">Suspender trabajador</div>
          <div class="perfil-muted">No pierde sus roles; opcionalmente se bloquea su acceso mientras dure.</div>
        </q-card-section>
        <q-card-section class="app-form">
          <q-select
            v-model="suspendForm.reason_code"
            outlined
            dense
            emit-value
            map-options
            label="Motivo"
            :options="catalogOptions('suspension_reasons')"
          />
          <q-input v-model="suspendForm.reason_detail" outlined dense autogrow label="Detalle (opcional)" />
          <div class="perfil-form__row">
            <q-input v-model="suspendForm.effective_date" outlined dense type="date" label="Desde" />
            <q-input v-model="suspendForm.end_date" outlined dense type="date" label="Hasta (previsto, opcional)" />
          </div>
          <q-toggle v-model="suspendForm.with_pay" label="Con goce de salario" />
          <q-toggle
            v-model="suspendForm.suspend_access"
            :disable="!profile?.linked_user_id"
            label="Bloquear acceso al sistema mientras dure"
          />
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat no-caps label="Cancelar" @click="suspendOpen = false" />
          <q-btn
            unelevated
            no-caps
            color="warning"
            text-color="white"
            label="Suspender"
            :loading="acting"
            :disable="!suspendForm.reason_code"
            @click="doSuspend"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <!-- ═══════ Diálogo: Dar de baja ═══════ -->
    <q-dialog v-model="bajaOpen">
      <q-card class="perfil-dialog">
        <q-card-section>
          <div class="text-h6">Dar de baja</div>
          <div class="perfil-muted">
            Termina sus asignaciones, revoca su acceso al sistema y finaliza contratos vigentes.
            El expediente queda como historial y puede reingresar después.
          </div>
        </q-card-section>
        <q-card-section class="app-form">
          <q-select
            v-model="bajaForm.reason_code"
            outlined
            dense
            emit-value
            map-options
            label="Motivo de la baja"
            :options="catalogOptions('baja_reasons')"
          />
          <q-input v-model="bajaForm.reason_detail" outlined dense autogrow label="Detalle (opcional)" />
          <q-input v-model="bajaForm.effective_date" outlined dense type="date" label="Fecha efectiva" />
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat no-caps label="Cancelar" @click="bajaOpen = false" />
          <q-btn
            unelevated
            no-caps
            color="negative"
            label="Confirmar baja"
            :loading="acting"
            :disable="!bajaForm.reason_code"
            @click="doTerminate"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <!-- ═══════ Diálogo: Reintegro / Reingreso ═══════ -->
    <q-dialog v-model="simpleOpen">
      <q-card class="perfil-dialog">
        <q-card-section>
          <div class="text-h6">{{ simpleMode === 'REINTEGRO' ? 'Reintegrar trabajador' : 'Reingreso del trabajador' }}</div>
          <div class="perfil-muted">
            {{
              simpleMode === 'REINTEGRO'
                ? 'Termina la suspensión; si se había bloqueado su acceso, se restituye.'
                : 'Reactiva la ficha (p. ej. nueva temporada). El acceso al sistema se gestiona aparte.'
            }}
          </div>
        </q-card-section>
        <q-card-section class="app-form">
          <q-input v-model="simpleForm.effective_date" outlined dense type="date" label="Fecha efectiva" />
          <q-input v-model="simpleForm.reason_detail" outlined dense autogrow label="Detalle (opcional)" />
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat no-caps label="Cancelar" @click="simpleOpen = false" />
          <q-btn unelevated no-caps color="primary" label="Confirmar" :loading="acting" @click="doSimple" />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <!-- ═══════ Diálogo: Nuevo contrato ═══════ -->
    <q-dialog v-model="newContractOpen">
      <q-card class="perfil-dialog">
        <q-card-section>
          <div class="text-h6">Nuevo contrato laboral</div>
          <div class="perfil-muted">Se redacta el borrador según el caso; podés ajustar el texto antes de emitirlo.</div>
        </q-card-section>
        <q-card-section class="app-form">
          <q-select
            v-model="contractForm.contract_type"
            outlined
            dense
            emit-value
            map-options
            label="Caso / tipo de contrato"
            :options="catalogOptions('contract_types')"
          />
          <q-select
            v-model="contractForm.position_id"
            outlined
            dense
            emit-value
            map-options
            clearable
            label="Puesto (para la redacción)"
            :options="positionOptions"
          />
          <div class="perfil-form__row">
            <q-input v-model="contractForm.start_date" outlined dense type="date" label="Inicio" />
            <q-input
              v-model="contractForm.end_date"
              outlined
              dense
              type="date"
              :label="needsEndDate ? 'Fin (requerido)' : 'Fin (opcional)'"
            />
          </div>
          <div class="perfil-form__row">
            <q-input v-model="contractForm.salary_amount" outlined dense type="number" step="0.01" label="Salario (monto)" />
            <q-select
              v-model="contractForm.salary_period"
              outlined
              dense
              emit-value
              map-options
              label="Período de pago"
              :options="catalogOptions('salary_periods')"
            />
          </div>
          <q-input
            v-if="contractForm.contract_type === 'OBRA'"
            v-model="contractForm.work_description"
            outlined
            dense
            autogrow
            label="Descripción de la obra o servicio"
          />
          <q-input
            v-if="contractForm.contract_type === 'TEMPORADA'"
            v-model="contractForm.season_description"
            outlined
            dense
            label="Temporada (p. ej. corte de café 2026-2027)"
          />
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat no-caps label="Cancelar" @click="newContractOpen = false" />
          <q-btn
            unelevated
            no-caps
            color="primary"
            label="Redactar borrador"
            :loading="acting"
            :disable="!contractForm.contract_type || !contractForm.start_date || (needsEndDate && !contractForm.end_date)"
            @click="doCreateContract"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <!-- ═══════ Diálogo: Ver / editar contrato ═══════ -->
    <q-dialog v-model="contractOpen" maximized>
      <q-card class="perfil-contract">
        <q-card-section class="perfil-contract__head">
          <div>
            <div class="text-h6">
              Contrato — {{ currentContract?.contract_type_label }}
              <q-chip
                v-if="currentContract"
                dense
                :color="contractStatusColor(currentContract.status)"
                text-color="white"
                :label="currentContract.status"
              />
            </div>
            <div class="perfil-muted">
              {{ currentContract?.status === 'BORRADOR' ? 'Texto editable: ajustalo al caso y emitilo cuando esté listo.' : 'Texto congelado (el contrato ya fue emitido).' }}
            </div>
          </div>
          <q-btn flat round icon="close" @click="contractOpen = false" />
        </q-card-section>
        <q-card-section class="perfil-contract__body">
          <q-input
            v-model="contractBody"
            outlined
            type="textarea"
            class="perfil-contract__text"
            :readonly="currentContract?.status !== 'BORRADOR'"
            input-class="perfil-contract__textarea"
          />
        </q-card-section>
        <q-card-actions align="right" class="perfil-contract__foot">
          <q-btn
            v-if="currentContract && (currentContract.status === 'BORRADOR' || currentContract.status === 'EMITIDO')"
            flat
            no-caps
            color="negative"
            label="Anular"
            :loading="acting"
            @click="doAnnulContract"
          />
          <q-space />
          <template v-if="currentContract?.status === 'BORRADOR'">
            <q-btn outline no-caps color="primary" label="Guardar texto" :loading="acting" @click="doSaveContractBody" />
            <q-btn unelevated no-caps color="primary" icon="task_alt" label="Emitir contrato" :loading="acting" @click="doIssueContract" />
          </template>
        </q-card-actions>
      </q-card>
    </q-dialog>

    <!-- ═══════ Diálogo: Nuevo / ver memorando ═══════ -->
    <q-dialog v-model="memoOpen">
      <q-card class="perfil-dialog">
        <q-card-section>
          <div class="text-h6">{{ memoReadonly ? 'Memorando' : 'Nuevo memorando' }}</div>
          <div v-if="!memoReadonly" class="perfil-muted">
            Queda en el expediente del trabajador (amonestaciones, acuerdos, reconocimientos…).
          </div>
        </q-card-section>
        <q-card-section class="app-form">
          <q-select
            v-model="memoForm.memo_type"
            outlined
            dense
            emit-value
            map-options
            label="Tipo"
            :readonly="memoReadonly"
            :options="catalogOptions('memo_types')"
          />
          <q-input v-model="memoForm.subject" outlined dense label="Asunto" :readonly="memoReadonly" />
          <q-input v-model="memoForm.issued_date" outlined dense type="date" label="Fecha" :readonly="memoReadonly" />
          <q-input v-model="memoForm.body" outlined autogrow type="textarea" label="Contenido" :readonly="memoReadonly" />
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat no-caps :label="memoReadonly ? 'Cerrar' : 'Cancelar'" @click="memoOpen = false" />
          <q-btn
            v-if="!memoReadonly"
            unelevated
            no-caps
            color="primary"
            label="Registrar memorando"
            :loading="acting"
            :disable="!memoForm.subject || !memoForm.memo_type"
            @click="doCreateMemo"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>
  </q-page>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import { useRoute } from 'vue-router';
import { useQuasar, type QTableColumn } from 'quasar';
import {
  annulContract,
  annulMemo,
  createContract,
  createMemo,
  deleteEmployeePhoto,
  getContract,
  getEmployeeProfile,
  getHrCatalogs,
  issueContract,
  listPositions,
  rehireEmployee,
  reinstateEmployee,
  setEmployeeRoles,
  suspendEmployee,
  terminateEmployee,
  updateContract,
  updateEmployee,
  uploadEmployeePhoto,
  type ContractRow,
  type EmployeeProfile,
  type HrCatalogs,
  type HrGender,
  type HrSalaryType,
  type LifecycleEvent,
  type MemoRow,
  type Position,
} from 'src/features/hr/hr.api';
import EmployeeAvatar from 'src/features/hr/EmployeeAvatar.vue';
import RoleMultiSelect from 'src/features/hr/RoleMultiSelect.vue';

const $q = useQuasar();
const route = useRoute();
const employeeId = computed(() => Number(route.params.id));

const loading = ref(true);
const acting = ref(false);
const profile = ref<EmployeeProfile | null>(null);
const catalogs = ref<HrCatalogs | null>(null);
const positions = ref<Position[]>([]);
const tab = ref('datos');

const today = () => new Date().toISOString().slice(0, 10);

// --- carga -----------------------------------------------------------------
async function load() {
  loading.value = true;
  try {
    profile.value = await getEmployeeProfile(employeeId.value);
    syncForms();
  } catch {
    $q.notify({ type: 'negative', message: 'No se pudo cargar el expediente.' });
  } finally {
    loading.value = false;
  }
}

async function reload() {
  try {
    profile.value = await getEmployeeProfile(employeeId.value);
    syncForms();
  } catch {
    $q.notify({ type: 'negative', message: 'No se pudo refrescar el expediente.' });
  }
}

onMounted(async () => {
  await load();
  try {
    [catalogs.value, positions.value] = await Promise.all([getHrCatalogs(), listPositions()]);
  } catch {
    $q.notify({ type: 'warning', message: 'No se pudieron cargar los catálogos.' });
  }
});

// --- encabezado / foto ---------------------------------------------------------
const fotoInputRef = ref<HTMLInputElement | null>(null);
const savingPhoto = ref(false);
// El avatar cachea por employeeId: el version-key fuerza recargarlo tras subir/quitar.
const photoVersion = ref(0);

async function subirFoto(ev: Event) {
  const input = ev.target as HTMLInputElement;
  const file = input.files?.[0];
  input.value = '';
  if (!file) return;
  savingPhoto.value = true;
  try {
    await uploadEmployeePhoto(employeeId.value, file);
    $q.notify({ type: 'positive', message: 'Foto actualizada.' });
    photoVersion.value += 1;
    await reload();
  } catch {
    $q.notify({ type: 'negative', message: 'No se pudo subir la foto (usá JPG o PNG, máx. 8 MB).' });
  } finally {
    savingPhoto.value = false;
  }
}

async function quitarFoto() {
  try {
    await deleteEmployeePhoto(employeeId.value);
    $q.notify({ type: 'positive', message: 'Foto quitada.' });
    photoVersion.value += 1;
    await reload();
  } catch {
    $q.notify({ type: 'negative', message: 'No se pudo quitar la foto.' });
  }
}

const statusColor = computed(() => {
  switch (profile.value?.employment_status) {
    case 'SUSPENDIDO':
      return 'warning';
    case 'BAJA':
      return 'negative';
    default:
      return 'positive';
  }
});

const statusLabel = computed(() => {
  const v = profile.value?.employment_status;
  const found = catalogs.value?.employment_statuses.find((c) => c.value === v);
  return found?.label ?? v ?? '';
});

const lastSuspension = computed<LifecycleEvent | null>(() => {
  const evs = profile.value?.lifecycle_events ?? [];
  return evs.find((e) => e.event_type === 'SUSPENSION') ?? null;
});

function catalogOptions(key: keyof HrCatalogs) {
  return (catalogs.value?.[key] ?? []).map((c) => ({ label: c.label, value: c.value }));
}

const positionOptions = computed(() =>
  positions.value.filter((p) => p.is_active).map((p) => ({ label: p.name, value: p.id })),
);

function reasonLabel(ev: LifecycleEvent): string {
  const pool = ev.event_type === 'BAJA' ? catalogs.value?.baja_reasons : catalogs.value?.suspension_reasons;
  return pool?.find((c) => c.value === ev.reason_code)?.label ?? ev.reason_code;
}

function eventIcon(t: LifecycleEvent['event_type']): string {
  return { SUSPENSION: 'pause_circle', REINTEGRO: 'play_circle', BAJA: 'person_off', REINGRESO: 'replay' }[t];
}

function eventColor(t: LifecycleEvent['event_type']): string {
  return { SUSPENSION: 'warning', REINTEGRO: 'primary', BAJA: 'negative', REINGRESO: 'secondary' }[t];
}

// --- datos + roles -----------------------------------------------------------
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
const selectedRoleIds = ref<number[]>([]);
const savingData = ref(false);
const savingRoles = ref(false);

function syncForms() {
  const p = profile.value;
  if (!p) return;
  form.first_name = p.first_name;
  form.last_name = p.last_name;
  form.employee_code = p.employee_code;
  form.phone = p.phone;
  form.email = p.email;
  form.cedula = p.cedula;
  form.inss_number = p.inss_number;
  form.gender = p.gender;
  form.salary_type = p.salary_type;
  form.salary_amount = p.salary_type === 'DAILY' ? p.daily_rate_nio : p.monthly_salary_nio;
  selectedRoleIds.value = p.roles.map((r) => r.role_id);
}

async function saveData() {
  savingData.value = true;
  try {
    await updateEmployee(employeeId.value, {
      first_name: form.first_name,
      last_name: form.last_name,
      employee_code: form.employee_code,
      phone: form.phone,
      email: form.email,
      cedula: form.cedula.trim(),
      inss_number: form.inss_number.trim(),
      gender: form.gender,
      salary_type: form.salary_type,
      ...(form.salary_type === 'DAILY'
        ? { daily_rate_nio: form.salary_amount || '0' }
        : { monthly_salary_nio: form.salary_amount || '0' }),
    });
    $q.notify({ type: 'positive', message: 'Datos del trabajador actualizados.' });
    await reload();
  } catch {
    $q.notify({ type: 'negative', message: 'No se pudieron guardar los datos.' });
  } finally {
    savingData.value = false;
  }
}

async function saveRoles() {
  savingRoles.value = true;
  try {
    await setEmployeeRoles(employeeId.value, selectedRoleIds.value);
    $q.notify({ type: 'positive', message: 'Roles actualizados.' });
    await reload();
  } catch {
    $q.notify({ type: 'negative', message: 'No se pudieron guardar los roles.' });
  } finally {
    savingRoles.value = false;
  }
}

// --- ciclo de vida -------------------------------------------------------------
const suspendOpen = ref(false);
const suspendForm = reactive({
  reason_code: '',
  reason_detail: '',
  effective_date: today(),
  end_date: '',
  with_pay: false,
  suspend_access: false,
});

const bajaOpen = ref(false);
const bajaForm = reactive({ reason_code: '', reason_detail: '', effective_date: today() });

const simpleOpen = ref(false);
const simpleMode = ref<'REINTEGRO' | 'REINGRESO'>('REINTEGRO');
const simpleForm = reactive({ effective_date: today(), reason_detail: '' });

function openSimple(mode: 'REINTEGRO' | 'REINGRESO') {
  simpleMode.value = mode;
  simpleForm.effective_date = today();
  simpleForm.reason_detail = '';
  simpleOpen.value = true;
}

async function doSuspend() {
  acting.value = true;
  try {
    await suspendEmployee(employeeId.value, {
      reason_code: suspendForm.reason_code,
      reason_detail: suspendForm.reason_detail,
      effective_date: suspendForm.effective_date,
      end_date: suspendForm.end_date || null,
      with_pay: suspendForm.with_pay,
      suspend_access: suspendForm.suspend_access,
    });
    $q.notify({ type: 'positive', message: 'Trabajador suspendido.' });
    suspendOpen.value = false;
    await reload();
  } catch {
    $q.notify({ type: 'negative', message: 'No se pudo suspender.' });
  } finally {
    acting.value = false;
  }
}

async function doTerminate() {
  acting.value = true;
  try {
    await terminateEmployee(employeeId.value, { ...bajaForm });
    $q.notify({ type: 'positive', message: 'Baja registrada. Acceso y asignaciones revocados.' });
    bajaOpen.value = false;
    await reload();
  } catch {
    $q.notify({ type: 'negative', message: 'No se pudo registrar la baja.' });
  } finally {
    acting.value = false;
  }
}

async function doSimple() {
  acting.value = true;
  try {
    if (simpleMode.value === 'REINTEGRO') {
      await reinstateEmployee(employeeId.value, { ...simpleForm });
      $q.notify({ type: 'positive', message: 'Trabajador reintegrado.' });
    } else {
      await rehireEmployee(employeeId.value, { ...simpleForm });
      $q.notify({ type: 'positive', message: 'Reingreso registrado. Gestioná su acceso si lo necesita.' });
    }
    simpleOpen.value = false;
    await reload();
  } catch {
    $q.notify({ type: 'negative', message: 'No se pudo completar la acción.' });
  } finally {
    acting.value = false;
  }
}

// --- contratos -------------------------------------------------------------------
const contractCols: QTableColumn[] = [
  { name: 'contract_type_label', label: 'Tipo', field: 'contract_type_label', align: 'left' },
  { name: 'position_name', label: 'Puesto', field: 'position_name', align: 'left' },
  { name: 'start_date', label: 'Inicio', field: 'start_date', align: 'left' },
  { name: 'end_date', label: 'Fin', field: (r: ContractRow) => r.end_date ?? '—', align: 'left' },
  { name: 'salary_amount', label: 'Salario', field: (r: ContractRow) => r.salary_amount ?? '—', align: 'right' },
  { name: 'status', label: 'Estado', field: 'status', align: 'center' },
  { name: 'acciones', label: '', field: 'id', align: 'right' },
];

const newContractOpen = ref(false);
const contractForm = reactive({
  contract_type: '',
  position_id: null as number | null,
  start_date: today(),
  end_date: '',
  salary_amount: '',
  salary_period: 'MENSUAL',
  work_description: '',
  season_description: '',
});

const needsEndDate = computed(
  () => contractForm.contract_type === 'PLAZO_FIJO' || contractForm.contract_type === 'TEMPORADA',
);

function openNewContract() {
  contractForm.contract_type = '';
  contractForm.position_id = profile.value?.assignments.find((a) => a.is_active)?.position_id ?? null;
  contractForm.start_date = today();
  contractForm.end_date = '';
  contractForm.salary_amount = '';
  contractForm.salary_period = 'MENSUAL';
  contractForm.work_description = '';
  contractForm.season_description = '';
  newContractOpen.value = true;
}

const contractOpen = ref(false);
const currentContract = ref<ContractRow | null>(null);
const contractBody = ref('');

async function doCreateContract() {
  acting.value = true;
  try {
    const created = await createContract(employeeId.value, {
      contract_type: contractForm.contract_type,
      position_id: contractForm.position_id,
      start_date: contractForm.start_date,
      end_date: contractForm.end_date || null,
      salary_amount: contractForm.salary_amount || null,
      salary_period: contractForm.salary_period,
      work_description: contractForm.work_description,
      season_description: contractForm.season_description,
    });
    newContractOpen.value = false;
    $q.notify({ type: 'positive', message: 'Borrador redactado. Revisá el texto y emitilo.' });
    await reload();
    currentContract.value = created;
    contractBody.value = created.body ?? '';
    contractOpen.value = true;
  } catch {
    $q.notify({ type: 'negative', message: 'No se pudo crear el contrato (verificá fechas).' });
  } finally {
    acting.value = false;
  }
}

async function openContract(id: number) {
  try {
    const c = await getContract(id);
    currentContract.value = c;
    contractBody.value = c.body ?? '';
    contractOpen.value = true;
  } catch {
    $q.notify({ type: 'negative', message: 'No se pudo abrir el contrato.' });
  }
}

async function doSaveContractBody() {
  if (!currentContract.value) return;
  acting.value = true;
  try {
    currentContract.value = await updateContract(currentContract.value.id, { body: contractBody.value });
    $q.notify({ type: 'positive', message: 'Texto del contrato guardado.' });
  } catch {
    $q.notify({ type: 'negative', message: 'No se pudo guardar el texto.' });
  } finally {
    acting.value = false;
  }
}

async function doIssueContract() {
  if (!currentContract.value) return;
  acting.value = true;
  try {
    if (currentContract.value.body !== contractBody.value) {
      await updateContract(currentContract.value.id, { body: contractBody.value });
    }
    currentContract.value = await issueContract(currentContract.value.id);
    $q.notify({ type: 'positive', message: 'Contrato emitido. El texto queda congelado.' });
    await reload();
  } catch {
    $q.notify({ type: 'negative', message: 'No se pudo emitir el contrato.' });
  } finally {
    acting.value = false;
  }
}

function doAnnulContract() {
  if (!currentContract.value) return;
  $q.dialog({
    title: 'Anular contrato',
    message: 'El contrato quedará ANULADO (no se borra, queda en el expediente). ¿Confirmás?',
    cancel: { flat: true, label: 'Cancelar', noCaps: true },
    ok: { color: 'negative', label: 'Anular', noCaps: true, unelevated: true },
  }).onOk(() => {
    void (async () => {
      acting.value = true;
      try {
        currentContract.value = await annulContract(currentContract.value!.id);
        $q.notify({ type: 'positive', message: 'Contrato anulado.' });
        await reload();
      } catch {
        $q.notify({ type: 'negative', message: 'No se pudo anular.' });
      } finally {
        acting.value = false;
      }
    })();
  });
}

function contractStatusColor(s: ContractRow['status']): string {
  return { BORRADOR: 'grey-7', EMITIDO: 'secondary', FINALIZADO: 'primary', ANULADO: 'negative' }[s] ?? 'grey-7';
}

// --- memorandos ---------------------------------------------------------------
const memoCols: QTableColumn[] = [
  { name: 'issued_date', label: 'Fecha', field: 'issued_date', align: 'left' },
  { name: 'memo_type_label', label: 'Tipo', field: 'memo_type_label', align: 'left' },
  { name: 'subject', label: 'Asunto', field: 'subject', align: 'left' },
  { name: 'status', label: 'Estado', field: 'status', align: 'center' },
  { name: 'acciones', label: '', field: 'id', align: 'right' },
];

const memoOpen = ref(false);
const memoReadonly = ref(false);
const memoForm = reactive({ memo_type: 'MEMORANDO', subject: '', body: '', issued_date: today() });

function openNewMemo() {
  memoReadonly.value = false;
  memoForm.memo_type = 'MEMORANDO';
  memoForm.subject = '';
  memoForm.body = '';
  memoForm.issued_date = today();
  memoOpen.value = true;
}

function viewMemo(m: MemoRow) {
  memoReadonly.value = true;
  memoForm.memo_type = m.memo_type;
  memoForm.subject = m.subject;
  memoForm.body = m.body;
  memoForm.issued_date = m.issued_date;
  memoOpen.value = true;
}

async function doCreateMemo() {
  acting.value = true;
  try {
    await createMemo(employeeId.value, { ...memoForm });
    $q.notify({ type: 'positive', message: 'Memorando registrado en el expediente.' });
    memoOpen.value = false;
    await reload();
  } catch {
    $q.notify({ type: 'negative', message: 'No se pudo registrar el memorando.' });
  } finally {
    acting.value = false;
  }
}

function doAnnulMemo(m: MemoRow) {
  $q.dialog({
    title: 'Anular memorando',
    message: `«${m.subject}» quedará ANULADO (permanece en el expediente). ¿Confirmás?`,
    cancel: { flat: true, label: 'Cancelar', noCaps: true },
    ok: { color: 'negative', label: 'Anular', noCaps: true, unelevated: true },
  }).onOk(() => {
    void (async () => {
      try {
        await annulMemo(m.id);
        $q.notify({ type: 'positive', message: 'Memorando anulado.' });
        await reload();
      } catch {
        $q.notify({ type: 'negative', message: 'No se pudo anular.' });
      }
    })();
  });
}
</script>

<style scoped>

.hr-loading {
  display: flex;
  align-items: center;
  gap: var(--app-space-3);
  color: var(--app-text-muted);
}

.perfil-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--app-space-4);
  flex-wrap: wrap;
  padding: var(--app-space-5);
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-lg);
  background: var(--app-surface);
  box-shadow: var(--app-shadow-soft);
  margin-bottom: var(--app-space-4);
}

.perfil-head__main {
  display: flex;
  align-items: center;
  gap: var(--app-space-3);
  min-width: 0;
}

.perfil-head__foto {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  flex-shrink: 0;
}

.perfil-head__foto-acciones {
  display: flex;
  gap: 2px;
  color: var(--app-text-muted);
}

.perfil-head__foto .hidden {
  display: none;
}

.perfil-head__name {
  font-family: 'Manrope', 'IBM Plex Sans', sans-serif;
  font-size: 1.25rem;
  font-weight: 800;
  color: var(--app-text);
  display: flex;
  align-items: center;
  gap: var(--app-space-2);
  flex-wrap: wrap;
}

.perfil-head__meta {
  display: flex;
  gap: var(--app-space-4);
  flex-wrap: wrap;
  color: var(--app-text-muted);
  font-size: 0.85rem;
}

.perfil-head__actions {
  display: flex;
  gap: var(--app-space-2);
  flex-wrap: wrap;
}

.perfil-banner {
  margin-bottom: var(--app-space-4);
  border: 1px solid var(--app-border-strong);
  background: var(--app-surface-strong);
}

.perfil-tabs {
  color: var(--app-text-muted);
}

.perfil-grid {
  display: grid;
  grid-template-columns: minmax(300px, 420px) minmax(0, 1fr);
  gap: var(--app-space-4);
  align-items: start;
}

@media (max-width: 1023px) {
  .perfil-grid {
    grid-template-columns: 1fr;
  }
}

.perfil-card {
  background: var(--app-surface-strong);
}

.perfil-card__title {
  font-weight: 800;
  color: var(--app-text);
  margin-bottom: var(--app-space-3);
}

.perfil-muted {
  color: var(--app-text-muted);
  font-size: 0.85rem;
  font-weight: 400;
}


.perfil-form__row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--app-space-3);
}

.perfil-section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--app-space-3);
  margin-bottom: var(--app-space-3);
}

.perfil-dialog {
  width: 560px;
  max-width: 95vw;
  background: var(--app-surface-strong);
}

.perfil-contract {
  background: var(--app-surface-strong);
  display: flex;
  flex-direction: column;
}

.perfil-contract__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  border-bottom: 1px solid var(--app-border);
}

.perfil-contract__body {
  flex: 1;
  overflow: auto;
}

.perfil-contract__text :deep(textarea) {
  min-height: 60vh;
  font-family: 'IBM Plex Mono', 'Courier New', monospace;
  font-size: 0.9rem;
  line-height: 1.55;
}

.perfil-contract__foot {
  border-top: 1px solid var(--app-border);
  padding: var(--app-space-3) var(--app-space-4);
}
</style>
