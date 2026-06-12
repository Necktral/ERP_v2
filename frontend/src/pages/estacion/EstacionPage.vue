<template>
  <q-page class="app-page">
    <PageHeader
      title="Estación de servicio"
      subtitle="Turno del día: despachos por surtidor y sus ventas (interna, empleado o público). Al cerrar el turno sale el reporte."
      :loading="loading"
      @refresh="cargar"
    >
      <template #actions>
        <q-btn flat no-caps icon="history" label="Turnos" to="/estacion/turnos" />
        <q-btn
          v-if="puede('fuel.reports.view')"
          flat
          no-caps
          icon="summarize"
          label="Cierre diario"
          to="/estacion/reportes"
        />
        <q-btn
          v-if="puede('fuel.uom_preferences.manage')"
          flat
          round
          icon="straighten"
          aria-label="Preferencias de unidades"
          @click="abrirPrefs"
        >
          <q-tooltip>Litros o galones por producto</q-tooltip>
        </q-btn>
      </template>
    </PageHeader>

    <!-- Sin turno -->
    <div v-if="!turno" class="est-card est-abrir">
      <div class="est-card__title">No hay turno abierto</div>
      <p class="text-muted">Abrí el turno para empezar a registrar despachos y ventas.</p>
      <q-btn
        v-if="puede('fuel.shift.open')"
        unelevated
        no-caps
        color="primary"
        icon="play_circle"
        label="Abrir turno"
        :loading="accionando"
        @click="abrirTurno"
      />
      <div v-else class="text-caption text-muted">No tenés permiso para abrir turno.</div>
    </div>

    <template v-else>
      <div class="est-resumen">
        <div class="est-stat">
          <div class="est-stat__label">Turno</div>
          <div class="est-stat__value">#{{ turno.id }} · abierto {{ formatDateTime(turno.opened_at) }}</div>
        </div>
        <div class="est-stat">
          <div class="est-stat__label">Despachos</div>
          <div class="est-stat__value">{{ despachos.length }}</div>
        </div>
        <div class="est-stat">
          <div class="est-stat__label">Ventas</div>
          <div class="est-stat__value">{{ ventas.length }} · {{ formatMoney(totalVentas) }}</div>
        </div>
        <div class="est-stat est-stat--accion">
          <q-btn
            v-if="puede('fuel.shift.close')"
            outline
            no-caps
            color="negative"
            icon="stop_circle"
            label="Cerrar turno"
            :loading="accionando"
            @click="confirmarCierre"
          />
        </div>
      </div>

      <div class="est-cols">
        <!-- Despachos -->
        <div class="est-card">
          <div class="est-card__title">
            Despachos
            <q-btn
              v-if="puede('fuel.dispense.create')"
              flat
              dense
              no-caps
              size="sm"
              icon="local_gas_station"
              label="Registrar despacho"
              @click="abrirDespacho"
            />
          </div>
          <q-list dense separator>
            <q-item v-for="d in despachos" :key="d.id">
              <q-item-section>
                <q-item-label>
                  {{ FUEL_PRODUCT_LABELS[d.product] ?? d.product }} ·
                  {{ formatQty(d.volume_entered ?? d.liters) }}
                  {{ VOLUME_UOM_LABELS[d.uom_entered ?? 'LITER'] ?? '' }}
                </q-item-label>
                <q-item-label caption>
                  {{ d.vehicle_plate || 'sin placa' }} · {{ d.driver_name || 'sin conductor' }} ·
                  bomba {{ d.pump_code || '—' }}
                </q-item-label>
              </q-item-section>
              <q-item-section side>
                <q-item-label>{{ formatMoney(d.amount) }}</q-item-label>
                <q-btn
                  v-if="puede('fuel.sale.create') && !ventaPorDespacho.has(d.id)"
                  flat
                  dense
                  no-caps
                  size="sm"
                  color="primary"
                  label="Facturar venta"
                  @click="abrirVenta(d)"
                />
                <q-chip v-else-if="ventaPorDespacho.has(d.id)" dense outline color="secondary" label="Vendido" />
              </q-item-section>
            </q-item>
            <q-item v-if="despachos.length === 0">
              <q-item-section class="text-caption text-muted">Sin despachos en el turno.</q-item-section>
            </q-item>
          </q-list>
        </div>

        <!-- Ventas -->
        <div class="est-card">
          <div class="est-card__title">Ventas del turno</div>
          <q-list dense separator>
            <q-item v-for="v in ventas" :key="v.id">
              <q-item-section>
                <q-item-label>
                  {{ FUEL_SALE_TYPE_LABELS[v.sale_type] ?? v.sale_type }} ·
                  {{ FUEL_PAYMENT_LABELS[v.payment_method] ?? v.payment_method }}
                </q-item-label>
                <q-item-label caption>
                  {{ v.customer_name || '—' }} · {{ FUEL_SALE_STATUS_LABELS[v.status] ?? v.status }}
                </q-item-label>
              </q-item-section>
              <q-item-section side>
                <q-item-label>{{ formatMoney(v.total_amount) }}</q-item-label>
                <div class="row no-wrap">
                  <q-btn
                    v-if="puede('fuel.sale.void') && v.status === 'ACTIVE'"
                    flat
                    dense
                    no-caps
                    size="sm"
                    color="negative"
                    label="Cancelar"
                    @click="cancelar(v)"
                  />
                  <q-btn
                    v-if="puede('fuel.sale.void') && v.status === 'COMPENSATION_FAILED'"
                    flat
                    dense
                    no-caps
                    size="sm"
                    color="warning"
                    label="Reintentar"
                    @click="reintentar(v)"
                  />
                </div>
              </q-item-section>
            </q-item>
            <q-item v-if="ventas.length === 0">
              <q-item-section class="text-caption text-muted">Sin ventas en el turno.</q-item-section>
            </q-item>
          </q-list>
        </div>
      </div>
    </template>

    <!-- Diálogo: despacho -->
    <q-dialog v-model="dlgDespacho">
      <q-card class="app-dialog">
        <q-card-section class="text-h6">Registrar despacho</q-card-section>
        <q-card-section class="app-form">
          <q-select
            v-model="formDesp.product"
            :options="opcionesProducto"
            label="Producto *"
            outlined
            dense
            emit-value
            map-options
            @update:model-value="aplicarUomPreferida"
          />
          <div class="row q-gutter-sm">
            <q-input v-model="formDesp.volume" outlined dense type="number" min="0" label="Volumen *" class="col" />
            <q-select
              v-model="formDesp.volume_uom"
              :options="opcionesUom"
              label="Unidad"
              outlined
              dense
              emit-value
              map-options
              class="col"
            />
          </div>
          <q-input
            v-model="formDesp.unit_price"
            outlined
            dense
            type="number"
            min="0"
            :label="`Precio C$ por ${formDesp.volume_uom === 'LITER' ? 'litro' : 'galón'} *`"
          />
          <q-input v-model="formDesp.vehicle_plate" outlined dense label="Placa del vehículo" />
          <q-input v-model="formDesp.driver_name" outlined dense label="Conductor" />
          <q-input v-model="formDesp.pump_code" outlined dense label="Bomba / surtidor" />
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat no-caps label="Cancelar" v-close-popup />
          <q-btn
            unelevated
            no-caps
            color="primary"
            label="Registrar"
            :loading="accionando"
            :disable="!formDesp.volume || Number(formDesp.volume) <= 0 || !formDesp.unit_price"
            @click="registrarDespacho"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <!-- Diálogo: venta -->
    <q-dialog v-model="dlgVenta">
      <q-card class="app-dialog">
        <q-card-section class="text-h6">Venta del despacho</q-card-section>
        <q-card-section class="app-form">
          <q-select
            v-model="formVenta.sale_type"
            :options="opcionesTipoVenta"
            label="Tipo de venta *"
            outlined
            dense
            emit-value
            map-options
          />
          <q-select
            v-model="formVenta.payment_method"
            :options="opcionesPagoFuel"
            label="Método de pago *"
            outlined
            dense
            emit-value
            map-options
          />
          <PartySelect
            v-if="formVenta.sale_type === 'PUBLIC'"
            v-model="formVenta.customer_party_id"
            role="CUSTOMER"
            label="Cliente (Terceros)"
          />
          <q-input v-model="formVenta.customer_name" outlined dense label="Nombre del cliente (texto)" />
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat no-caps label="Cancelar" v-close-popup />
          <q-btn
            unelevated
            no-caps
            color="primary"
            label="Registrar venta"
            :loading="accionando"
            @click="registrarVenta"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <!-- Diálogo: preferencias UoM -->
    <q-dialog v-model="dlgPrefs">
      <q-card class="app-dialog">
        <q-card-section class="text-h6">Unidades por producto</q-card-section>
        <q-card-section class="app-form">
          <q-select
            v-model="prefs.gasoline_volume_uom"
            :options="opcionesUom"
            label="Gasolina"
            outlined
            dense
            emit-value
            map-options
          />
          <q-select
            v-model="prefs.diesel_volume_uom"
            :options="opcionesUom"
            label="Diésel"
            outlined
            dense
            emit-value
            map-options
          />
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat no-caps label="Cancelar" v-close-popup />
          <q-btn unelevated no-caps color="primary" label="Guardar" :loading="accionando" @click="guardarPrefs" />
        </q-card-actions>
      </q-card>
    </q-dialog>
  </q-page>
</template>

<script setup lang="ts">
import { computed, reactive, ref, onMounted } from 'vue';
import { useQuasar } from 'quasar';
import PageHeader from 'src/components/PageHeader.vue';
import { apiErrorMessage } from 'src/core/api';
import { formatDateTime, formatMoney, formatQty } from 'src/core/format';
import PartySelect from 'src/features/parties/PartySelect.vue';
import {
  cancelSale,
  closeShift,
  createDispense,
  createSale,
  FUEL_PAYMENT_LABELS,
  FUEL_PRODUCT_LABELS,
  FUEL_SALE_STATUS_LABELS,
  FUEL_SALE_TYPE_LABELS,
  getUomPreferences,
  listDispenses,
  listSales,
  listShifts,
  openShift,
  retrySaleCompensation,
  updateUomPreferences,
  VOLUME_UOM_LABELS,
  type FuelDispense,
  type FuelSale,
  type FuelShift,
} from 'src/features/fuel/fuel.api';
import { useAclStore } from 'src/stores/acl.store';
import { useContextStore } from 'src/stores/context.store';

const $q = useQuasar();
const acl = useAclStore();
const ctx = useContextStore();

const loading = ref(false);
const accionando = ref(false);
const turno = ref<FuelShift | null>(null);
const despachos = ref<FuelDispense[]>([]);
const ventas = ref<FuelSale[]>([]);
const prefs = reactive({ gasoline_volume_uom: 'LITER', diesel_volume_uom: 'GALLON' });

function puede(code: string): boolean {
  const companyId = ctx.activeCompanyId;
  return companyId ? acl.hasPermission(companyId, code) : false;
}

const totalVentas = computed(() =>
  ventas.value.filter((v) => v.status === 'ACTIVE').reduce((a, v) => a + Number(v.total_amount), 0),
);
const ventaPorDespacho = computed(() => new Set(ventas.value.filter((v) => v.status !== 'CANCELLED').map((v) => v.dispense)));

const opcionesProducto = Object.entries(FUEL_PRODUCT_LABELS).map(([value, label]) => ({ value, label }));
const opcionesUom = Object.entries(VOLUME_UOM_LABELS).map(([value, label]) => ({ value, label }));
const opcionesTipoVenta = Object.entries(FUEL_SALE_TYPE_LABELS).map(([value, label]) => ({ value, label }));
const opcionesPagoFuel = Object.entries(FUEL_PAYMENT_LABELS).map(([value, label]) => ({ value, label }));

async function cargar() {
  loading.value = true;
  try {
    const shifts = await listShifts();
    turno.value = shifts.find((s) => s.status === 'OPEN') ?? null;
    if (turno.value) {
      [despachos.value, ventas.value] = await Promise.all([
        listDispenses(turno.value.id),
        listSales(turno.value.id),
      ]);
    } else {
      despachos.value = [];
      ventas.value = [];
    }
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo cargar la estación.') });
  } finally {
    loading.value = false;
  }
}

async function abrirTurno() {
  accionando.value = true;
  try {
    await openShift();
    $q.notify({ type: 'positive', message: 'Turno abierto.' });
    await cargar();
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo abrir el turno.') });
  } finally {
    accionando.value = false;
  }
}

function confirmarCierre() {
  if (!turno.value) return;
  $q.dialog({
    title: 'Cerrar turno',
    message: `Cerrar el turno #${turno.value.id} con ${despachos.value.length} despachos y ${formatMoney(totalVentas.value)} en ventas. El reporte queda en «Turnos».`,
    cancel: { flat: true, noCaps: true, label: 'Cancelar' },
    ok: { unelevated: true, noCaps: true, color: 'negative', label: 'Cerrar turno' },
  }).onOk(() => {
    void (async () => {
      accionando.value = true;
      try {
        await closeShift(turno.value!.id);
        $q.notify({ type: 'positive', message: 'Turno cerrado.' });
        await cargar();
      } catch (e) {
        $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo cerrar el turno.') });
      } finally {
        accionando.value = false;
      }
    })();
  });
}

// --- Despacho ---
const dlgDespacho = ref(false);
const formDesp = reactive({
  product: 'DIESEL',
  volume: '',
  volume_uom: 'GALLON',
  unit_price: '',
  vehicle_plate: '',
  driver_name: '',
  pump_code: '',
});

function aplicarUomPreferida() {
  formDesp.volume_uom =
    formDesp.product === 'GASOLINE' ? prefs.gasoline_volume_uom : prefs.diesel_volume_uom;
}

function abrirDespacho() {
  Object.assign(formDesp, {
    product: 'DIESEL',
    volume: '',
    unit_price: '',
    vehicle_plate: '',
    driver_name: '',
    pump_code: '',
  });
  aplicarUomPreferida();
  dlgDespacho.value = true;
}

async function registrarDespacho() {
  if (!turno.value) return;
  accionando.value = true;
  try {
    await createDispense({
      shift_id: turno.value.id,
      product: formDesp.product,
      volume: String(formDesp.volume),
      volume_uom: formDesp.volume_uom,
      unit_price: String(formDesp.unit_price),
      unit_price_uom: formDesp.volume_uom === 'LITER' ? 'PER_LITER' : 'PER_GALLON',
      ...(formDesp.vehicle_plate ? { vehicle_plate: formDesp.vehicle_plate } : {}),
      ...(formDesp.driver_name ? { driver_name: formDesp.driver_name } : {}),
      ...(formDesp.pump_code ? { pump_code: formDesp.pump_code } : {}),
    });
    dlgDespacho.value = false;
    $q.notify({ type: 'positive', message: 'Despacho registrado.' });
    await cargar();
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo registrar el despacho.') });
  } finally {
    accionando.value = false;
  }
}

// --- Venta ---
const dlgVenta = ref(false);
const despachoVenta = ref<FuelDispense | null>(null);
const formVenta = reactive<{
  sale_type: string;
  payment_method: string;
  customer_party_id: number | null;
  customer_name: string;
}>({ sale_type: 'PUBLIC', payment_method: 'CASH', customer_party_id: null, customer_name: '' });

function abrirVenta(d: FuelDispense) {
  despachoVenta.value = d;
  Object.assign(formVenta, {
    sale_type: 'PUBLIC',
    payment_method: 'CASH',
    customer_party_id: null,
    customer_name: '',
  });
  dlgVenta.value = true;
}

async function registrarVenta() {
  if (!turno.value || !despachoVenta.value) return;
  accionando.value = true;
  try {
    await createSale({
      shift_id: turno.value.id,
      dispense_id: despachoVenta.value.id,
      sale_type: formVenta.sale_type,
      payment_method: formVenta.payment_method,
      ...(formVenta.customer_name ? { customer_name: formVenta.customer_name } : {}),
      ...(formVenta.customer_party_id != null
        ? { customer_party_id: formVenta.customer_party_id }
        : {}),
    });
    dlgVenta.value = false;
    $q.notify({ type: 'positive', message: 'Venta registrada.' });
    await cargar();
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo registrar la venta.') });
  } finally {
    accionando.value = false;
  }
}

function cancelar(v: FuelSale) {
  $q.dialog({
    title: 'Cancelar venta',
    message: 'Motivo de la cancelación:',
    prompt: { model: '', type: 'text', isValid: (x: string) => x.trim().length >= 3 },
    cancel: { flat: true, noCaps: true, label: 'Volver' },
    ok: { unelevated: true, noCaps: true, color: 'negative', label: 'Cancelar venta' },
  }).onOk((motivo: string) => {
    void (async () => {
      try {
        await cancelSale(v.id, motivo.trim());
        $q.notify({ type: 'positive', message: 'Venta cancelada (compensación en curso).' });
        await cargar();
      } catch (e) {
        $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo cancelar.') });
      }
    })();
  });
}

async function reintentar(v: FuelSale) {
  try {
    await retrySaleCompensation(v.id);
    $q.notify({ type: 'positive', message: 'Reintento de compensación encolado.' });
    await cargar();
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo reintentar.') });
  }
}

// --- Prefs ---
const dlgPrefs = ref(false);

async function abrirPrefs() {
  try {
    Object.assign(prefs, await getUomPreferences());
  } catch {
    /* defaults */
  }
  dlgPrefs.value = true;
}

async function guardarPrefs() {
  accionando.value = true;
  try {
    Object.assign(prefs, await updateUomPreferences({ ...prefs }));
    dlgPrefs.value = false;
    $q.notify({ type: 'positive', message: 'Preferencias guardadas.' });
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudieron guardar.') });
  } finally {
    accionando.value = false;
  }
}

onMounted(async () => {
  await cargar();
  try {
    Object.assign(prefs, await getUomPreferences());
  } catch {
    /* defaults */
  }
});
</script>

<style scoped>
.est-card {
  padding: var(--app-space-4);
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-lg);
  background: var(--app-surface);
}

.est-abrir {
  max-width: 480px;
}

.est-card__title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-weight: 800;
  color: var(--app-text);
  margin-bottom: var(--app-space-3);
}

.est-resumen {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
  gap: var(--app-space-3);
  margin-bottom: var(--app-space-4);
}

.est-stat {
  padding: var(--app-space-3) var(--app-space-4);
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-md);
  background: var(--app-surface);
}

.est-stat--accion {
  display: flex;
  align-items: center;
  justify-content: center;
  border-style: dashed;
}

.est-stat__label {
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--app-text-muted);
}

.est-stat__value {
  font-weight: 800;
  color: var(--app-text);
}

.est-cols {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(340px, 1fr));
  gap: var(--app-space-4);
}
</style>
