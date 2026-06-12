<template>
  <q-page class="app-page">
    <PageHeader
      title="Conductores"
      subtitle="Conductores de la flota con su licencia y vencimiento. Se pueden asignar a un activo."
      :loading="loading"
      @refresh="reload"
    >
      <template #actions>
        <q-btn flat round dense icon="arrow_back" aria-label="Volver" to="/flota" />
        <q-btn
          v-if="puedeGestionar"
          unelevated
          no-caps
          color="primary"
          icon="person_add"
          label="Nuevo conductor"
          @click="abrirCrear"
        />
      </template>
    </PageHeader>

    <q-table
      class="app-table"
      :rows="rows"
      :columns="columns"
      row-key="id"
      flat
      :loading="loading"
      :pagination="{ rowsPerPage: 25 }"
      no-data-label="Aún no hay conductores."
    >
      <template #body-cell-vence="props">
        <q-td :props="props">{{ formatDate(props.row.license_expiry) }}</q-td>
      </template>
      <template #body-cell-acciones="props">
        <q-td :props="props" class="text-right">
          <q-btn
            v-if="puedeGestionar"
            flat
            dense
            no-caps
            size="sm"
            icon="directions_car"
            label="Asignar a activo"
            @click="abrirAsignar(props.row)"
          />
        </q-td>
      </template>
    </q-table>

    <!-- Diálogo: conductor -->
    <q-dialog v-model="dlgCrear">
      <q-card class="app-dialog">
        <q-card-section class="text-h6">Nuevo conductor</q-card-section>
        <q-card-section class="app-form">
          <q-input v-model="form.full_name" outlined dense label="Nombre completo *" autofocus />
          <q-input v-model="form.national_id" outlined dense label="Cédula" />
          <q-input v-model="form.license_number" outlined dense label="Número de licencia" />
          <q-input v-model="form.license_category" outlined dense label="Categoría" />
          <q-input v-model="form.license_expiry" outlined dense type="date" label="Vencimiento de licencia" />
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat no-caps label="Cancelar" v-close-popup />
          <q-btn
            unelevated
            no-caps
            color="primary"
            label="Crear conductor"
            :loading="guardando"
            :disable="!form.full_name.trim()"
            @click="crear"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <!-- Diálogo: asignar -->
    <q-dialog v-model="dlgAsignar">
      <q-card class="app-dialog">
        <q-card-section class="text-h6">Asignar a {{ conductorAsignar?.full_name }}</q-card-section>
        <q-card-section class="app-form">
          <q-select
            v-model="activoAsignar"
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
            label="Asignar"
            :loading="guardando"
            :disable="activoAsignar == null"
            @click="asignar"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>
  </q-page>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import { useQuasar, type QTableColumn } from 'quasar';
import PageHeader from 'src/components/PageHeader.vue';
import { apiErrorMessage } from 'src/core/api';
import { useListado } from 'src/core/composables/useListado';
import { formatDate } from 'src/core/format';
import {
  assignDriver,
  listAssets,
  listDrivers,
  upsertDriver,
  type FleetAsset,
  type FleetDriver,
} from 'src/features/fleet/fleet.api';
import { useAclStore } from 'src/stores/acl.store';
import { useContextStore } from 'src/stores/context.store';

const $q = useQuasar();
const acl = useAclStore();
const ctx = useContextStore();

const { rows, loading, reload } = useListado<FleetDriver>(() => listDrivers(), {
  errorMessage: 'No se pudieron cargar los conductores.',
});

const activos = ref<FleetAsset[]>([]);
const guardando = ref(false);

const puedeGestionar = computed(() => {
  const companyId = ctx.activeCompanyId;
  return companyId ? acl.hasPermission(companyId, 'fleet.driver.manage') : false;
});

const opcionesActivo = computed(() =>
  activos.value.map((a) => ({ value: a.id, label: `${a.code} — ${a.name}` })),
);

const columns: QTableColumn<FleetDriver>[] = [
  { name: 'full_name', label: 'Conductor', field: 'full_name', align: 'left', sortable: true },
  { name: 'national_id', label: 'Cédula', field: 'national_id', align: 'left' },
  { name: 'license_number', label: 'Licencia', field: 'license_number', align: 'left' },
  { name: 'license_category', label: 'Categoría', field: 'license_category', align: 'left' },
  { name: 'vence', label: 'Vence', field: 'license_expiry', align: 'left' },
  { name: 'status', label: 'Estado', field: 'status', align: 'left' },
  { name: 'acciones', label: '', field: 'id', align: 'right' },
];

// --- Crear ---
const dlgCrear = ref(false);
const form = reactive({
  full_name: '',
  national_id: '',
  license_number: '',
  license_category: '',
  license_expiry: '',
});

function abrirCrear() {
  Object.assign(form, {
    full_name: '',
    national_id: '',
    license_number: '',
    license_category: '',
    license_expiry: '',
  });
  dlgCrear.value = true;
}

async function crear() {
  guardando.value = true;
  try {
    await upsertDriver({
      full_name: form.full_name.trim(),
      ...(form.national_id ? { national_id: form.national_id } : {}),
      ...(form.license_number ? { license_number: form.license_number } : {}),
      ...(form.license_category ? { license_category: form.license_category } : {}),
      ...(form.license_expiry ? { license_expiry: form.license_expiry } : {}),
    });
    dlgCrear.value = false;
    $q.notify({ type: 'positive', message: 'Conductor creado.' });
    await reload();
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo crear el conductor.') });
  } finally {
    guardando.value = false;
  }
}

// --- Asignar ---
const dlgAsignar = ref(false);
const conductorAsignar = ref<FleetDriver | null>(null);
const activoAsignar = ref<number | null>(null);

async function abrirAsignar(d: FleetDriver) {
  conductorAsignar.value = d;
  activoAsignar.value = null;
  if (activos.value.length === 0) {
    try {
      activos.value = await listAssets();
    } catch {
      /* sin activos */
    }
  }
  dlgAsignar.value = true;
}

async function asignar() {
  if (!conductorAsignar.value || activoAsignar.value == null) return;
  guardando.value = true;
  try {
    await assignDriver(activoAsignar.value, conductorAsignar.value.id);
    dlgAsignar.value = false;
    $q.notify({ type: 'positive', message: 'Conductor asignado.' });
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo asignar.') });
  } finally {
    guardando.value = false;
  }
}

onMounted(() => {
  /* la tabla carga sola con useListado */
});
</script>
