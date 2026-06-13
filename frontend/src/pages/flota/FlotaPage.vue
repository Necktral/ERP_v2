<template>
  <q-page class="app-page">
    <PageHeader
      title="Flota"
      subtitle="Vehículos y maquinaria con sus lecturas y documentos por vencer. El mantenimiento y los conductores tienen su pantalla."
      :loading="cargando"
      @refresh="recargar"
    >
      <template #actions>
        <q-btn
          v-if="puede('fleet.driver.read')"
          flat
          no-caps
          icon="badge"
          label="Conductores"
          to="/flota/conductores"
        />
        <q-btn
          v-if="puede('fleet.maintenance.read')"
          flat
          no-caps
          icon="build"
          label="Mantenimiento"
          to="/flota/mantenimiento"
        />
        <q-btn
          v-if="puede('fleet.asset.manage')"
          unelevated
          no-caps
          color="primary"
          icon="add"
          label="Nuevo activo"
          @click="abrirActivo"
        />
      </template>
    </PageHeader>

    <div class="flo-cols">
      <div class="flo-main">
        <q-table
          class="app-table"
          :rows="activos"
          :columns="columnas"
          row-key="id"
          flat
          :loading="cargando"
          :pagination="{ rowsPerPage: 25 }"
          no-data-label="Aún no hay activos de flota."
        >
          <template #body-cell-tipo="props">
            <q-td :props="props">{{ ASSET_TYPE_LABELS[props.row.asset_type] ?? props.row.asset_type }}</q-td>
          </template>
          <template #body-cell-estado="props">
            <q-td :props="props">{{ ASSET_STATUS_LABELS[props.row.status] ?? props.row.status }}</q-td>
          </template>
          <template #body-cell-lectura="props">
            <q-td :props="props">
              {{
                Number(props.row.current_odometer_km) > 0
                  ? `${formatQty(props.row.current_odometer_km)} km`
                  : `${formatQty(props.row.current_hourmeter)} h`
              }}
            </q-td>
          </template>
          <template #body-cell-acciones="props">
            <q-td :props="props" class="text-right flo-acciones">
              <q-btn
                v-if="puede('fleet.meter.record')"
                flat
                dense
                no-caps
                size="sm"
                icon="speed"
                label="Lectura"
                @click="registrarLectura(props.row)"
              />
              <q-btn
                v-if="puede('fleet.document.manage')"
                flat
                dense
                no-caps
                size="sm"
                icon="description"
                label="Documento"
                @click="abrirDocumento(props.row)"
              />
            </q-td>
          </template>
        </q-table>
      </div>

      <div class="flo-side">
        <div class="flo-card">
          <div class="flo-card__title">Documentos por vencer</div>
          <q-list dense separator>
            <q-item v-for="d in documentos" :key="d.id">
              <q-item-section>
                <q-item-label>
                  {{ FLEET_DOC_TYPE_LABELS[d.doc_type] ?? d.doc_type }}
                  · {{ nombreActivo(d.asset_id) }}
                </q-item-label>
                <q-item-label caption>Vence: {{ formatDate(d.expiry_date) }}</q-item-label>
              </q-item-section>
              <q-item-section side>
                <q-chip
                  dense
                  :color="d.status === 'EXPIRED' ? 'negative' : d.status === 'EXPIRING' ? 'warning' : 'secondary'"
                  text-color="white"
                  :label="FLEET_DOC_STATUS_LABELS[d.status] ?? d.status"
                />
              </q-item-section>
            </q-item>
            <q-item v-if="documentos.length === 0">
              <q-item-section class="text-caption text-muted">Sin documentos registrados.</q-item-section>
            </q-item>
          </q-list>
          <q-btn
            v-if="puede('fleet.maintenance.manage')"
            class="q-mt-sm"
            flat
            dense
            no-caps
            icon="notifications_active"
            label="Ejecutar alertas (docs + mantenimiento)"
            @click="ejecutarAlertas"
          />
        </div>
      </div>
    </div>

    <!-- Diálogo: nuevo activo -->
    <q-dialog v-model="dlgActivo">
      <q-card class="app-dialog">
        <q-card-section class="text-h6">Nuevo activo</q-card-section>
        <q-card-section class="app-form">
          <q-input v-model="formActivo.code" outlined dense label="Código *" autofocus />
          <q-input v-model="formActivo.name" outlined dense label="Nombre *" />
          <q-select
            v-model="formActivo.asset_type"
            :options="opcionesTipo"
            label="Tipo *"
            outlined
            dense
            emit-value
            map-options
          />
          <q-input v-model="formActivo.plate" outlined dense label="Placa" />
          <q-input v-model="formActivo.make" outlined dense label="Marca" />
          <q-input v-model="formActivo.model" outlined dense label="Modelo" />
          <q-input v-model.number="formActivo.year" outlined dense type="number" label="Año" />
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat no-caps label="Cancelar" v-close-popup />
          <q-btn
            unelevated
            no-caps
            color="primary"
            label="Crear activo"
            :loading="guardando"
            :disable="!formActivo.code.trim() || !formActivo.name.trim()"
            @click="crearActivo"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <!-- Diálogo: documento -->
    <q-dialog v-model="dlgDocumento">
      <q-card class="app-dialog">
        <q-card-section class="text-h6">Documento de {{ activoDoc?.name }}</q-card-section>
        <q-card-section class="app-form">
          <q-select
            v-model="formDoc.doc_type"
            :options="opcionesDocTipo"
            label="Tipo *"
            outlined
            dense
            emit-value
            map-options
          />
          <q-input v-model="formDoc.number" outlined dense label="Número" />
          <q-input v-model="formDoc.issuer" outlined dense label="Emisor (aseguradora, tránsito…)" />
          <q-input v-model="formDoc.issue_date" outlined dense type="date" label="Emisión" />
          <q-input v-model="formDoc.expiry_date" outlined dense type="date" label="Vencimiento *" />
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat no-caps label="Cancelar" v-close-popup />
          <q-btn
            unelevated
            no-caps
            color="primary"
            label="Registrar"
            :loading="guardando"
            :disable="!formDoc.expiry_date"
            @click="registrarDocumento"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>
  </q-page>
</template>

<script setup lang="ts">
import { reactive, ref, onMounted } from 'vue';
import { useQuasar, type QTableColumn } from 'quasar';
import PageHeader from 'src/components/PageHeader.vue';
import { apiErrorMessage } from 'src/core/api';
import { formatDate, formatQty } from 'src/core/format';
import {
  ASSET_STATUS_LABELS,
  ASSET_TYPE_LABELS,
  FLEET_DOC_STATUS_LABELS,
  FLEET_DOC_TYPE_LABELS,
  listAssets,
  listFleetDocuments,
  recordMeterReading,
  registerFleetDocument,
  runFleetAlerts,
  upsertAsset,
  type FleetAsset,
  type FleetDocument,
} from 'src/features/fleet/fleet.api';
import { useAclStore } from 'src/stores/acl.store';
import { useContextStore } from 'src/stores/context.store';

const $q = useQuasar();
const acl = useAclStore();
const ctx = useContextStore();

const cargando = ref(false);
const guardando = ref(false);
const activos = ref<FleetAsset[]>([]);
const documentos = ref<FleetDocument[]>([]);

function puede(code: string): boolean {
  const companyId = ctx.activeCompanyId;
  return companyId ? acl.hasPermission(companyId, code) : false;
}

function nombreActivo(assetId: number | null): string {
  if (assetId == null) return 'conductor';
  return activos.value.find((a) => a.id === assetId)?.name ?? `Activo #${assetId}`;
}

const opcionesTipo = Object.entries(ASSET_TYPE_LABELS).map(([value, label]) => ({ value, label }));
const opcionesDocTipo = Object.entries(FLEET_DOC_TYPE_LABELS).map(([value, label]) => ({ value, label }));

const columnas: QTableColumn<FleetAsset>[] = [
  { name: 'code', label: 'Código', field: 'code', align: 'left', sortable: true },
  { name: 'name', label: 'Nombre', field: 'name', align: 'left' },
  { name: 'tipo', label: 'Tipo', field: 'asset_type', align: 'left' },
  { name: 'plate', label: 'Placa', field: 'plate', align: 'left' },
  { name: 'lectura', label: 'Lectura', field: 'current_odometer_km', align: 'right' },
  { name: 'estado', label: 'Estado', field: 'status', align: 'left' },
  { name: 'acciones', label: '', field: 'id', align: 'right' },
];

async function recargar() {
  cargando.value = true;
  try {
    const tareas: Promise<void>[] = [
      listAssets().then((r) => {
        activos.value = r;
      }),
    ];
    if (puede('fleet.document.read')) {
      tareas.push(
        listFleetDocuments().then((r) => {
          documentos.value = r;
        }),
      );
    }
    await Promise.all(tareas);
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo cargar la flota.') });
  } finally {
    cargando.value = false;
  }
}

// --- Activo ---
const dlgActivo = ref(false);
const formActivo = reactive<{
  code: string;
  name: string;
  asset_type: string;
  plate: string;
  make: string;
  model: string;
  year: number | null;
}>({ code: '', name: '', asset_type: 'VEHICLE', plate: '', make: '', model: '', year: null });

function abrirActivo() {
  Object.assign(formActivo, {
    code: '',
    name: '',
    asset_type: 'VEHICLE',
    plate: '',
    make: '',
    model: '',
    year: null,
  });
  dlgActivo.value = true;
}

async function crearActivo() {
  guardando.value = true;
  try {
    await upsertAsset({
      code: formActivo.code.trim(),
      name: formActivo.name.trim(),
      asset_type: formActivo.asset_type,
      ...(formActivo.plate ? { plate: formActivo.plate } : {}),
      ...(formActivo.make ? { make: formActivo.make } : {}),
      ...(formActivo.model ? { model: formActivo.model } : {}),
      ...(formActivo.year ? { year: formActivo.year } : {}),
    });
    dlgActivo.value = false;
    $q.notify({ type: 'positive', message: 'Activo creado.' });
    await recargar();
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo crear el activo.') });
  } finally {
    guardando.value = false;
  }
}

// --- Lectura ---
function registrarLectura(a: FleetAsset) {
  const esKm = Number(a.current_odometer_km) > 0 || a.asset_type === 'VEHICLE';
  $q.dialog({
    title: `Lectura de ${a.name}`,
    message: esKm ? 'Odómetro (km):' : 'Horómetro (horas):',
    prompt: {
      model: esKm ? a.current_odometer_km : a.current_hourmeter,
      type: 'number',
      isValid: (v) => Number(v) >= 0,
    },
    cancel: { flat: true, noCaps: true, label: 'Cancelar' },
    ok: { unelevated: true, noCaps: true, color: 'primary', label: 'Registrar' },
  }).onOk((valor: string) => {
    void (async () => {
      try {
        await recordMeterReading({
          asset_id: a.id,
          ...(esKm ? { odometer_km: Number(valor).toFixed(2) } : { hourmeter: Number(valor).toFixed(2) }),
        });
        $q.notify({ type: 'positive', message: 'Lectura registrada.' });
        await recargar();
      } catch (e) {
        $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo registrar la lectura.') });
      }
    })();
  });
}

// --- Documento ---
const dlgDocumento = ref(false);
const activoDoc = ref<FleetAsset | null>(null);
const formDoc = reactive({ doc_type: 'INSURANCE', number: '', issuer: '', issue_date: '', expiry_date: '' });

function abrirDocumento(a: FleetAsset) {
  activoDoc.value = a;
  Object.assign(formDoc, { doc_type: 'INSURANCE', number: '', issuer: '', issue_date: '', expiry_date: '' });
  dlgDocumento.value = true;
}

async function registrarDocumento() {
  if (!activoDoc.value) return;
  guardando.value = true;
  try {
    await registerFleetDocument({
      doc_type: formDoc.doc_type,
      asset_id: activoDoc.value.id,
      ...(formDoc.number ? { number: formDoc.number } : {}),
      ...(formDoc.issuer ? { issuer: formDoc.issuer } : {}),
      ...(formDoc.issue_date ? { issue_date: formDoc.issue_date } : {}),
      expiry_date: formDoc.expiry_date,
    });
    dlgDocumento.value = false;
    $q.notify({ type: 'positive', message: 'Documento registrado.' });
    await recargar();
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo registrar el documento.') });
  } finally {
    guardando.value = false;
  }
}

async function ejecutarAlertas() {
  try {
    await runFleetAlerts(30);
    $q.notify({ type: 'positive', message: 'Alertas ejecutadas (horizonte 30 días).' });
    await recargar();
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudieron ejecutar las alertas.') });
  }
}

onMounted(recargar);
</script>

<style scoped>
.flo-cols {
  display: grid;
  grid-template-columns: 2fr 1fr;
  gap: var(--app-space-4);
}

@media (max-width: 1023px) {
  .flo-cols {
    grid-template-columns: 1fr;
  }
}

.flo-card {
  padding: var(--app-space-4);
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-lg);
  background: var(--app-surface);
}

.flo-card__title {
  font-weight: 800;
  color: var(--app-text);
  margin-bottom: var(--app-space-3);
}

.flo-acciones {
  white-space: nowrap;
}
</style>
