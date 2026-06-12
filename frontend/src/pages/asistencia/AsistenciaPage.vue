<template>
  <q-page class="asis-page">
    <header class="asis-head">
      <div>
        <div class="asis-head__title">Asistencia del día</div>
        <div class="asis-head__subtitle">{{ fechaLabel }}</div>
      </div>
      <div class="asis-head__meta">
        <q-chip dense outline class="asis-counter" icon="how_to_reg">
          {{ data?.marcados ?? 0 }} / {{ data?.total ?? 0 }} marcados
        </q-chip>
        <q-btn flat round icon="refresh" :loading="loading" aria-label="Actualizar" @click="reload" />
      </div>
    </header>

    <q-banner v-if="!puedeMarcar" rounded class="asis-readonly">
      <template #avatar><q-icon name="visibility" color="info" /></template>
      Estás en modo consulta: tu rol puede ver la asistencia pero no marcarla.
    </q-banner>

    <q-input
      v-model="busqueda"
      outlined
      dense
      clearable
      debounce="150"
      placeholder="Buscar por nombre, código o puesto…"
      class="asis-search"
    >
      <template #prepend><q-icon name="search" /></template>
    </q-input>

    <div v-if="loading && !data" class="asis-loading"><q-spinner size="28px" /> Cargando personal…</div>

    <div v-else class="asis-list">
      <article
        v-for="p in filtrados"
        :key="p.employee_id"
        class="asis-card"
        :class="`asis-card--${p.estado.toLowerCase()}`"
      >
        <button class="asis-card__who" type="button" @click="verPerfil(p)">
          <EmployeeAvatar
            v-if="p.has_photo"
            :employee-id="p.employee_id"
            :nombre="`${p.first_name} ${p.last_name}`"
            :size="44"
            class="asis-card__foto"
            :class="`is-${p.estado.toLowerCase()}`"
          />
          <span v-else class="asis-card__avatar" :class="`is-${p.estado.toLowerCase()}`">
            {{ iniciales(p) }}
          </span>
          <span class="asis-card__id">
            <span class="asis-card__name">{{ p.first_name }} {{ p.last_name }}</span>
            <span class="asis-card__sub">
              {{ p.position_name || 'Sin puesto' }}
              <template v-if="p.employee_code"> · {{ p.employee_code }}</template>
            </span>
            <span
              v-if="p.estado === 'ENFERMO' && p.constancia_medica !== null"
              class="asis-card__constancia"
              :class="p.constancia_medica ? 'is-ok' : 'is-no'"
            >
              {{ p.constancia_medica ? 'Con constancia · día pagado' : 'Sin constancia · día no pagado' }}
            </span>
          </span>
        </button>

        <q-select
          :model-value="p.estado === 'SIN_MARCAR' ? null : p.estado"
          :options="opcionesEstado"
          outlined
          dense
          emit-value
          map-options
          :label="p.estado === 'SIN_MARCAR' ? (puedeMarcar ? 'Marcar…' : 'Sin marcar') : undefined"
          class="asis-card__select"
          :loading="marcando === p.employee_id"
          :readonly="!puedeMarcar"
          :disable="marcando !== null && marcando !== p.employee_id"
          @update:model-value="(v) => marcar(p, v)"
        >
          <template #selected-item="scope">
            <span class="asis-estado" :class="`asis-estado--${String(scope.opt.value).toLowerCase()}`">
              <q-icon :name="iconoEstado(scope.opt.value)" size="16px" />
              {{ scope.opt.label }}
            </span>
          </template>
          <template #option="scope">
            <q-item v-bind="scope.itemProps">
              <q-item-section avatar>
                <q-icon :name="iconoEstado(scope.opt.value)" :color="colorEstado(scope.opt.value)" />
              </q-item-section>
              <q-item-section>{{ scope.opt.label }}</q-item-section>
            </q-item>
          </template>
        </q-select>
      </article>

      <div v-if="filtrados.length === 0" class="asis-empty">
        {{ busqueda ? 'Nadie coincide con la búsqueda.' : 'No hay personal activo en esta empresa.' }}
      </div>
    </div>

    <!-- Perfil del trabajador: SOLO LECTURA -->
    <q-dialog v-model="perfilOpen">
      <q-card class="asis-perfil">
        <q-card-section class="asis-perfil__head">
          <EmployeeAvatar
            v-if="perfil?.has_photo"
            :employee-id="perfil.employee_id"
            :nombre="`${perfil.first_name} ${perfil.last_name}`"
            :size="56"
          />
          <span v-else class="asis-card__avatar is-perfil">{{ perfil ? iniciales(perfil) : '' }}</span>
          <div>
            <div class="asis-perfil__name">{{ perfil?.first_name }} {{ perfil?.last_name }}</div>
            <div class="asis-card__sub">{{ perfil?.position_name || 'Sin puesto' }}</div>
          </div>
        </q-card-section>
        <q-separator />
        <q-card-section class="asis-perfil__body">
          <div class="asis-perfil__row"><span>Código</span><strong>{{ perfil?.employee_code || '—' }}</strong></div>
          <div class="asis-perfil__row"><span>Teléfono</span><strong>{{ perfil?.phone || '—' }}</strong></div>
          <div class="asis-perfil__row">
            <span>Hoy</span>
            <strong class="asis-estado" :class="`asis-estado--${(perfil?.estado ?? '').toLowerCase()}`">
              {{ labelEstado(perfil?.estado) }}
            </strong>
          </div>
          <div class="asis-perfil__hint">El perfil se edita solo desde Recursos Humanos (PC).</div>
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat no-caps label="Cerrar" v-close-popup />
        </q-card-actions>
      </q-card>
    </q-dialog>
  </q-page>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useQuasar } from 'quasar';
import {
  getAsistenciaHoy,
  marcarAsistencia,
  type AsistenciaHoy,
  type EstadoAsistencia,
  type PersonalRow,
} from 'src/features/asistencia/asistencia.api';
import EmployeeAvatar from 'src/features/hr/EmployeeAvatar.vue';
import { useAclStore } from 'src/stores/acl.store';
import { useContextStore } from 'src/stores/context.store';

const $q = useQuasar();
const acl = useAclStore();
const ctx = useContextStore();

// SoD: el supervisor (nomina.field.read + approve) VE la lista pero no marca;
// marcar es del que captura (mandador/capataz/planillero: nomina.field.capture).
const puedeMarcar = computed(() =>
  ctx.activeCompanyId ? acl.hasPermission(ctx.activeCompanyId, 'nomina.field.capture') : false,
);
const loading = ref(false);
const data = ref<AsistenciaHoy | null>(null);
const busqueda = ref('');
const marcando = ref<number | null>(null);

const opcionesEstado = [
  { label: 'Presente en el trabajo', value: 'PRESENTE' },
  { label: 'Se enfermó', value: 'ENFERMO' },
  { label: 'Trabajó medio día', value: 'MEDIO_DIA' },
  { label: 'Accidentado', value: 'ACCIDENTADO' },
  { label: 'Ausente', value: 'AUSENTE' },
];

const ESTADO_META: Record<string, { label: string; icon: string; color: string }> = {
  PRESENTE: { label: 'Presente', icon: 'check_circle', color: 'positive' },
  ENFERMO: { label: 'Enfermo', icon: 'sick', color: 'warning' },
  MEDIO_DIA: { label: 'Medio día', icon: 'timelapse', color: 'info' },
  ACCIDENTADO: { label: 'Accidentado', icon: 'emergency', color: 'negative' },
  AUSENTE: { label: 'Ausente', icon: 'cancel', color: 'grey-7' },
  SIN_MARCAR: { label: 'Sin marcar', icon: 'radio_button_unchecked', color: 'grey-5' },
};

const fechaLabel = computed(() => {
  const f = data.value?.work_date ? new Date(`${data.value.work_date}T12:00:00`) : new Date();
  return f.toLocaleDateString('es-NI', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });
});

const filtrados = computed(() => {
  const rows = data.value?.results ?? [];
  const q = (busqueda.value || '').trim().toLowerCase();
  if (!q) return rows;
  return rows.filter((p) =>
    `${p.first_name} ${p.last_name} ${p.employee_code} ${p.position_name}`.toLowerCase().includes(q),
  );
});

function iniciales(p: PersonalRow): string {
  return `${p.first_name.charAt(0)}${(p.last_name || '').charAt(0)}`.toUpperCase();
}

function labelEstado(e?: string): string {
  return ESTADO_META[e ?? 'SIN_MARCAR']?.label ?? e ?? '';
}

function iconoEstado(e: string): string {
  return ESTADO_META[e]?.icon ?? 'help';
}

function colorEstado(e: string): string {
  return ESTADO_META[e]?.color ?? 'grey-5';
}

async function reload() {
  loading.value = true;
  try {
    data.value = await getAsistenciaHoy();
  } catch {
    $q.notify({ type: 'negative', message: 'No se pudo cargar la asistencia.' });
  } finally {
    loading.value = false;
  }
}

async function marcar(p: PersonalRow, estado: string | null) {
  if (!puedeMarcar.value) return;
  if (!estado || estado === p.estado) return;

  // ENFERMO: el día se paga SOLO con constancia médica certificada → se pregunta.
  let constancia = false;
  if (estado === 'ENFERMO') {
    constancia = await new Promise<boolean>((resolve) => {
      $q.dialog({
        title: 'Enfermo',
        message: `¿${p.first_name} ${p.last_name} presentó constancia médica certificada? Con constancia el día SE PAGA; sin constancia no.`,
        ok: { label: 'Con constancia', color: 'primary', noCaps: true, unelevated: true },
        cancel: { label: 'Sin constancia', color: 'warning', noCaps: true, outline: true },
        persistent: true,
      })
        .onOk(() => resolve(true))
        .onCancel(() => resolve(false));
    });
  }

  marcando.value = p.employee_id;
  const anterior = p.estado;
  const constanciaAnterior = p.constancia_medica;
  p.estado = estado as EstadoAsistencia; // optimista: en campo la señal tarda
  p.constancia_medica = estado === 'ENFERMO' ? constancia : null;
  try {
    await marcarAsistencia(p.employee_id, estado as Exclude<EstadoAsistencia, 'SIN_MARCAR'>, {
      constancia_medica: constancia,
    });
    if (data.value) data.value.marcados = data.value.results.filter((r) => r.estado !== 'SIN_MARCAR').length;
  } catch {
    p.estado = anterior;
    p.constancia_medica = constanciaAnterior;
    $q.notify({ type: 'negative', message: 'No se pudo marcar. Verificá la conexión.' });
  } finally {
    marcando.value = null;
  }
}

// --- perfil solo lectura ---
const perfilOpen = ref(false);
const perfil = ref<PersonalRow | null>(null);

function verPerfil(p: PersonalRow) {
  perfil.value = p;
  perfilOpen.value = true;
}

onMounted(reload);
</script>

<style scoped>
.asis-page {
  padding: var(--app-space-4);
  max-width: 760px;
  margin: 0 auto;
}

.asis-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--app-space-3);
  margin-bottom: var(--app-space-3);
}

.asis-head__title {
  font-family: 'Manrope', 'IBM Plex Sans', sans-serif;
  font-size: 1.35rem;
  font-weight: 800;
  color: var(--app-text);
}

.asis-head__subtitle {
  color: var(--app-text-muted);
  font-size: 0.85rem;
  text-transform: capitalize;
}

.asis-head__meta {
  display: flex;
  align-items: center;
  gap: var(--app-space-2);
}

.asis-counter {
  color: var(--app-text-muted);
  border-color: var(--app-border-strong);
}

.asis-search {
  margin-bottom: var(--app-space-4);
}

.asis-readonly {
  margin-bottom: var(--app-space-3);
  border: 1px solid var(--app-border-strong);
  background: var(--app-surface-strong);
  color: var(--app-text-muted);
  font-size: 0.85rem;
}

.asis-loading {
  display: flex;
  align-items: center;
  gap: var(--app-space-3);
  color: var(--app-text-muted);
}

.asis-list {
  display: flex;
  flex-direction: column;
  gap: var(--app-space-3);
}

.asis-card {
  display: flex;
  align-items: center;
  gap: var(--app-space-3);
  padding: var(--app-space-3) var(--app-space-4);
  border: 1px solid var(--app-border);
  border-left: 4px solid var(--app-border);
  border-radius: var(--app-radius-md);
  background: var(--app-surface);
  box-shadow: var(--app-shadow-soft);
}

.asis-card--presente { border-left-color: var(--q-positive); }
.asis-card--enfermo { border-left-color: var(--q-warning); }
.asis-card--medio_dia { border-left-color: var(--q-info); }
.asis-card--accidentado { border-left-color: var(--q-negative); }
.asis-card--ausente { border-left-color: var(--app-text-muted); }

.asis-card__who {
  display: flex;
  align-items: center;
  gap: var(--app-space-3);
  flex: 1;
  min-width: 0;
  background: none;
  border: none;
  padding: 0;
  cursor: pointer;
  text-align: left;
}

.asis-card__avatar {
  width: 42px;
  height: 42px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  font-weight: 800;
  color: #fff;
  background: var(--app-stat-blue);
}

.asis-card__avatar.is-enfermo { background: var(--app-stat-amber); }
.asis-card__avatar.is-accidentado { background: var(--app-stat-coral); }
.asis-card__avatar.is-presente { background: var(--app-stat-teal); }

.asis-card__constancia {
  font-size: 0.7rem;
  font-weight: 600;
}

.asis-card__constancia.is-ok { color: var(--app-stat-teal); }
.asis-card__constancia.is-no { color: var(--app-stat-amber); }

/* Con foto, el estado se señala con el anillo (mismos colores que las iniciales) */
.asis-card__foto { border: 2px solid var(--app-stat-blue); }
.asis-card__foto.is-enfermo { border-color: var(--app-stat-amber); }
.asis-card__foto.is-accidentado { border-color: var(--app-stat-coral); }
.asis-card__foto.is-presente { border-color: var(--app-stat-teal); }

.asis-card__id {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.asis-card__name {
  font-weight: 700;
  color: var(--app-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.asis-card__sub {
  color: var(--app-text-muted);
  font-size: 0.78rem;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.asis-card__select {
  width: 210px;
  flex-shrink: 0;
}

.asis-estado {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-weight: 700;
  font-size: 0.85rem;
}

.asis-estado--presente { color: var(--q-positive); }
.asis-estado--enfermo { color: var(--q-warning); }
.asis-estado--medio_dia { color: var(--q-info); }
.asis-estado--accidentado { color: var(--q-negative); }
.asis-estado--ausente,
.asis-estado--sin_marcar { color: var(--app-text-muted); }

.asis-empty {
  color: var(--app-text-muted);
  text-align: center;
  padding: var(--app-space-6);
}

.asis-perfil {
  width: 380px;
  max-width: 92vw;
  background: var(--app-surface-strong);
}

.asis-perfil__head {
  display: flex;
  align-items: center;
  gap: var(--app-space-3);
}

.asis-perfil__name {
  font-weight: 800;
  font-size: 1.05rem;
  color: var(--app-text);
}

.asis-perfil__body {
  display: flex;
  flex-direction: column;
  gap: var(--app-space-2);
}

.asis-perfil__row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--app-space-3);
  color: var(--app-text-muted);
  font-size: 0.9rem;
}

.asis-perfil__row strong {
  color: var(--app-text);
}

.asis-perfil__hint {
  margin-top: var(--app-space-2);
  font-size: 0.76rem;
  color: var(--app-text-muted);
}

@media (max-width: 599px) {
  .asis-card {
    flex-wrap: wrap;
  }

  .asis-card__select {
    width: 100%;
  }
}
</style>
