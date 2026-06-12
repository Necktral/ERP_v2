<template>
  <q-page class="app-page">
    <PageHeader
      title="Mantenimiento de flota"
      subtitle="Tipos de mantenimiento, planes con reglas (cada X km/horas/días) y aplicación de planes a los activos."
      :loading="cargando"
      @refresh="recargar"
    >
      <template #actions>
        <q-btn flat round dense icon="arrow_back" aria-label="Volver" to="/flota" />
      </template>
    </PageHeader>

    <div class="man-grid">
      <!-- Tipos -->
      <div class="man-card">
        <div class="man-card__title">
          Tipos de mantenimiento
          <q-btn
            v-if="puedeGestionar"
            flat
            dense
            no-caps
            size="sm"
            icon="add"
            label="Nuevo"
            @click="dlgTipo = true"
          />
        </div>
        <q-list dense separator>
          <q-item v-for="t in tipos" :key="t.id">
            <q-item-section>
              <q-item-label>{{ t.name }}</q-item-label>
              <q-item-label caption>{{ t.code }} · {{ t.kind }} · {{ t.trigger_basis }}</q-item-label>
            </q-item-section>
          </q-item>
          <q-item v-if="tipos.length === 0">
            <q-item-section class="text-caption text-muted">Sin tipos (ej. cambio de aceite).</q-item-section>
          </q-item>
        </q-list>
      </div>

      <!-- Planes -->
      <div class="man-card">
        <div class="man-card__title">
          Planes
          <q-btn
            v-if="puedeGestionar"
            flat
            dense
            no-caps
            size="sm"
            icon="add"
            label="Nuevo"
            @click="dlgPlan = true"
          />
        </div>
        <q-list dense separator>
          <q-item v-for="p in planes" :key="p.id">
            <q-item-section>
              <q-item-label>{{ p.name }}</q-item-label>
              <q-item-label caption>{{ p.asset_class || 'cualquier activo' }}</q-item-label>
            </q-item-section>
            <q-item-section side v-if="puedeGestionar">
              <div class="row no-wrap">
                <q-btn flat dense no-caps size="sm" label="Regla" @click="abrirRegla(p)" />
                <q-btn flat dense no-caps size="sm" color="primary" label="Aplicar" @click="abrirAplicar(p)" />
              </div>
            </q-item-section>
          </q-item>
          <q-item v-if="planes.length === 0">
            <q-item-section class="text-caption text-muted">Sin planes de mantenimiento.</q-item-section>
          </q-item>
        </q-list>
        <q-btn
          v-if="puedeGestionar"
          class="q-mt-sm"
          flat
          dense
          no-caps
          icon="notifications_active"
          label="Ejecutar alertas"
          @click="ejecutarAlertas"
        />
      </div>
    </div>

    <!-- Diálogo: tipo -->
    <q-dialog v-model="dlgTipo">
      <q-card class="app-dialog">
        <q-card-section class="text-h6">Nuevo tipo de mantenimiento</q-card-section>
        <q-card-section class="app-form">
          <q-input v-model="formTipo.code" outlined dense label="Código * (ej. ACEITE)" autofocus />
          <q-input v-model="formTipo.name" outlined dense label="Nombre * (ej. Cambio de aceite)" />
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat no-caps label="Cancelar" v-close-popup />
          <q-btn
            unelevated
            no-caps
            color="primary"
            label="Crear"
            :loading="guardando"
            :disable="!formTipo.code.trim() || !formTipo.name.trim()"
            @click="crearTipo"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <!-- Diálogo: plan -->
    <q-dialog v-model="dlgPlan">
      <q-card class="app-dialog">
        <q-card-section class="text-h6">Nuevo plan</q-card-section>
        <q-card-section class="app-form">
          <q-input v-model="formPlan.name" outlined dense label="Nombre * (ej. Plan camiones)" autofocus />
          <q-input v-model="formPlan.asset_class" outlined dense label="Clase de activo (opcional)" />
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat no-caps label="Cancelar" v-close-popup />
          <q-btn
            unelevated
            no-caps
            color="primary"
            label="Crear"
            :loading="guardando"
            :disable="!formPlan.name.trim()"
            @click="crearPlan"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <!-- Diálogo: regla -->
    <q-dialog v-model="dlgRegla">
      <q-card class="app-dialog">
        <q-card-section class="text-h6">Regla para "{{ planRegla?.name }}"</q-card-section>
        <q-card-section class="app-form">
          <q-select
            v-model="formRegla.maintenance_type_id"
            :options="opcionesTipoMant"
            label="Tipo de mantenimiento *"
            outlined
            dense
            emit-value
            map-options
          />
          <q-select
            v-model="formRegla.trigger_basis"
            :options="[
              { value: 'KM', label: 'Cada X kilómetros' },
              { value: 'HOURS', label: 'Cada X horas' },
              { value: 'TIME', label: 'Cada X días' },
            ]"
            label="Disparador *"
            outlined
            dense
            emit-value
            map-options
          />
          <q-input
            v-model.number="formRegla.intervalo"
            outlined
            dense
            type="number"
            min="1"
            :label="
              formRegla.trigger_basis === 'KM'
                ? 'Kilómetros *'
                : formRegla.trigger_basis === 'HOURS'
                  ? 'Horas *'
                  : 'Días *'
            "
          />
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat no-caps label="Cancelar" v-close-popup />
          <q-btn
            unelevated
            no-caps
            color="primary"
            label="Agregar regla"
            :loading="guardando"
            :disable="formRegla.maintenance_type_id == null || !formRegla.intervalo"
            @click="crearRegla"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <!-- Diálogo: aplicar plan -->
    <q-dialog v-model="dlgAplicar">
      <q-card class="app-dialog">
        <q-card-section class="text-h6">Aplicar "{{ planAplicar?.name }}" a un activo</q-card-section>
        <q-card-section class="app-form">
          <q-select
            v-model="activoAplicar"
            :options="opcionesActivo"
            label="Activo *"
            outlined
            dense
            emit-value
            map-options
          />
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat no-caps label="Cancelar" v-close-popup />
          <q-btn
            unelevated
            no-caps
            color="primary"
            label="Aplicar plan"
            :loading="guardando"
            :disable="activoAplicar == null"
            @click="aplicarPlan"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>
  </q-page>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import { useQuasar } from 'quasar';
import PageHeader from 'src/components/PageHeader.vue';
import { apiErrorMessage } from 'src/core/api';
import {
  addMaintenanceRule,
  applyMaintenancePlan,
  createMaintenancePlan,
  createMaintenanceType,
  listAssets,
  listMaintenancePlans,
  listMaintenanceTypes,
  runFleetAlerts,
  type FleetAsset,
  type MaintenancePlanRow,
  type MaintenanceTypeRow,
} from 'src/features/fleet/fleet.api';
import { useAclStore } from 'src/stores/acl.store';
import { useContextStore } from 'src/stores/context.store';

const $q = useQuasar();
const acl = useAclStore();
const ctx = useContextStore();

const cargando = ref(false);
const guardando = ref(false);
const tipos = ref<MaintenanceTypeRow[]>([]);
const planes = ref<MaintenancePlanRow[]>([]);
const activos = ref<FleetAsset[]>([]);

const puedeGestionar = computed(() => {
  const companyId = ctx.activeCompanyId;
  return companyId ? acl.hasPermission(companyId, 'fleet.maintenance.manage') : false;
});

const opcionesTipoMant = computed(() => tipos.value.map((t) => ({ value: t.id, label: t.name })));
const opcionesActivo = computed(() =>
  activos.value.map((a) => ({ value: a.id, label: `${a.code} — ${a.name}` })),
);

async function recargar() {
  cargando.value = true;
  try {
    [tipos.value, planes.value] = await Promise.all([listMaintenanceTypes(), listMaintenancePlans()]);
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo cargar mantenimiento.') });
  } finally {
    cargando.value = false;
  }
}

// --- Tipo ---
const dlgTipo = ref(false);
const formTipo = reactive({ code: '', name: '' });

async function crearTipo() {
  guardando.value = true;
  try {
    await createMaintenanceType({ code: formTipo.code.trim(), name: formTipo.name.trim() });
    dlgTipo.value = false;
    Object.assign(formTipo, { code: '', name: '' });
    $q.notify({ type: 'positive', message: 'Tipo creado.' });
    await recargar();
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo crear el tipo.') });
  } finally {
    guardando.value = false;
  }
}

// --- Plan ---
const dlgPlan = ref(false);
const formPlan = reactive({ name: '', asset_class: '' });

async function crearPlan() {
  guardando.value = true;
  try {
    await createMaintenancePlan({
      name: formPlan.name.trim(),
      ...(formPlan.asset_class ? { asset_class: formPlan.asset_class } : {}),
    });
    dlgPlan.value = false;
    Object.assign(formPlan, { name: '', asset_class: '' });
    $q.notify({ type: 'positive', message: 'Plan creado.' });
    await recargar();
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo crear el plan.') });
  } finally {
    guardando.value = false;
  }
}

// --- Regla ---
const dlgRegla = ref(false);
const planRegla = ref<MaintenancePlanRow | null>(null);
const formRegla = reactive<{
  maintenance_type_id: number | null;
  trigger_basis: string;
  intervalo: number | null;
}>({ maintenance_type_id: null, trigger_basis: 'KM', intervalo: null });

function abrirRegla(p: MaintenancePlanRow) {
  planRegla.value = p;
  Object.assign(formRegla, { maintenance_type_id: null, trigger_basis: 'KM', intervalo: null });
  dlgRegla.value = true;
}

async function crearRegla() {
  if (!planRegla.value || formRegla.maintenance_type_id == null || !formRegla.intervalo) return;
  guardando.value = true;
  try {
    await addMaintenanceRule({
      plan_id: planRegla.value.id,
      maintenance_type_id: formRegla.maintenance_type_id,
      trigger_basis: formRegla.trigger_basis,
      ...(formRegla.trigger_basis === 'KM' ? { interval_km: formRegla.intervalo } : {}),
      ...(formRegla.trigger_basis === 'HOURS' ? { interval_hours: formRegla.intervalo } : {}),
      ...(formRegla.trigger_basis === 'TIME' ? { interval_days: formRegla.intervalo } : {}),
    });
    dlgRegla.value = false;
    $q.notify({ type: 'positive', message: 'Regla agregada.' });
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo agregar la regla.') });
  } finally {
    guardando.value = false;
  }
}

// --- Aplicar ---
const dlgAplicar = ref(false);
const planAplicar = ref<MaintenancePlanRow | null>(null);
const activoAplicar = ref<number | null>(null);

async function abrirAplicar(p: MaintenancePlanRow) {
  planAplicar.value = p;
  activoAplicar.value = null;
  if (activos.value.length === 0) {
    try {
      activos.value = await listAssets();
    } catch {
      /* sin activos */
    }
  }
  dlgAplicar.value = true;
}

async function aplicarPlan() {
  if (!planAplicar.value || activoAplicar.value == null) return;
  guardando.value = true;
  try {
    await applyMaintenancePlan(activoAplicar.value, planAplicar.value.id);
    dlgAplicar.value = false;
    $q.notify({ type: 'positive', message: 'Plan aplicado al activo.' });
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo aplicar el plan.') });
  } finally {
    guardando.value = false;
  }
}

async function ejecutarAlertas() {
  try {
    await runFleetAlerts(30);
    $q.notify({ type: 'positive', message: 'Alertas ejecutadas.' });
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudieron ejecutar.') });
  }
}

onMounted(recargar);
</script>

<style scoped>
.man-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(340px, 1fr));
  gap: var(--app-space-4);
}

.man-card {
  padding: var(--app-space-4);
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-lg);
  background: var(--app-surface);
}

.man-card__title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-weight: 800;
  color: var(--app-text);
  margin-bottom: var(--app-space-3);
}
</style>
