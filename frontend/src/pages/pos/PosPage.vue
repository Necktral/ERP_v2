<template>
  <q-page class="app-page">
    <PageHeader
      title="Punto de venta"
      subtitle="TPV de la estación: abrí sesión, generá el ticket sobre el turno de combustible y cobralo en un paso."
      :loading="loading"
      @refresh="cargar"
    >
      <template #actions>
        <q-btn flat no-caps icon="receipt_long" label="Tickets" to="/pos/tickets" />
      </template>
    </PageHeader>

    <!-- Sin sesión -->
    <div v-if="!sesion" class="pos-card pos-abrir">
      <div class="pos-card__title">No hay sesión POS abierta</div>
      <div class="app-form">
        <q-input v-model="fondo" outlined dense type="number" min="0" label="Fondo inicial C$" />
      </div>
      <q-btn
        v-if="puede('retail.pos.session.open')"
        class="q-mt-md"
        unelevated
        no-caps
        color="primary"
        icon="point_of_sale"
        label="Abrir sesión POS"
        :loading="accionando"
        @click="abrirSesion"
      />
    </div>

    <template v-else>
      <div class="pos-resumen">
        <div class="pos-stat">
          <div class="pos-stat__label">Sesión</div>
          <div class="pos-stat__value">#{{ sesion.id }} · fondo {{ formatMoney(sesion.opening_amount) }}</div>
        </div>
        <div class="pos-stat">
          <div class="pos-stat__label">Turno combustible</div>
          <div class="pos-stat__value">
            {{ turno ? `#${turno.id} abierto` : 'SIN TURNO (abrilo en Estación)' }}
          </div>
        </div>
        <div class="pos-stat pos-stat--accion">
          <q-btn
            v-if="puede('retail.pos.session.close')"
            outline
            no-caps
            color="negative"
            icon="lock"
            label="Cerrar sesión"
            @click="confirmarCierre"
          />
        </div>
      </div>

      <div class="pos-card">
        <div class="pos-card__title">Venta rápida</div>
        <div v-if="!turno" class="text-caption text-muted">
          Necesitás un turno de combustible abierto (Estación de Servicio) para vender.
        </div>
        <div v-else class="app-form">
          <div class="row q-gutter-sm">
            <q-select
              v-model="venta.product"
              :options="opcionesProducto"
              label="Producto *"
              outlined
              dense
              emit-value
              map-options
              class="col"
            />
            <q-select
              v-model="venta.sale_type"
              :options="opcionesTipoVenta"
              label="Tipo *"
              outlined
              dense
              emit-value
              map-options
              class="col"
            />
            <q-select
              v-model="venta.payment_method"
              :options="opcionesPagoFuel"
              label="Pago *"
              outlined
              dense
              emit-value
              map-options
              class="col"
            />
          </div>
          <div class="row q-gutter-sm">
            <q-input v-model="venta.volume" outlined dense type="number" min="0" label="Volumen *" class="col" />
            <q-select
              v-model="venta.volume_uom"
              :options="opcionesUom"
              label="Unidad"
              outlined
              dense
              emit-value
              map-options
              class="col"
            />
            <q-input v-model="venta.unit_price" outlined dense type="number" min="0" label="Precio C$ *" class="col" />
          </div>
          <q-input v-model="venta.customer_name" outlined dense label="Cliente (opcional)" />
          <div class="pos-total">Total estimado: <strong>{{ formatMoney(totalEstimado) }}</strong></div>
          <q-btn
            v-if="puede('retail.pos.ticket.checkout')"
            unelevated
            no-caps
            color="primary"
            icon="shopping_cart_checkout"
            label="Cobrar"
            :loading="accionando"
            :disable="!ventaValida"
            @click="cobrar"
          />
        </div>
      </div>
    </template>
  </q-page>
</template>

<script setup lang="ts">
import { computed, reactive, ref, onMounted } from 'vue';
import { useQuasar } from 'quasar';
import PageHeader from 'src/components/PageHeader.vue';
import { apiErrorMessage } from 'src/core/api';
import { formatMoney } from 'src/core/format';
import {
  FUEL_PAYMENT_LABELS,
  FUEL_PRODUCT_LABELS,
  FUEL_SALE_TYPE_LABELS,
  listShifts,
  VOLUME_UOM_LABELS,
  type FuelShift,
} from 'src/features/fuel/fuel.api';
import {
  checkoutPosTicket,
  closePosSession,
  getCurrentPosSession,
  openPosSession,
  openPosTicket,
  type PosSession,
} from 'src/features/pos/pos.api';
import { useAclStore } from 'src/stores/acl.store';
import { useContextStore } from 'src/stores/context.store';

const $q = useQuasar();
const acl = useAclStore();
const ctx = useContextStore();

const loading = ref(false);
const accionando = ref(false);
const sesion = ref<PosSession | null>(null);
const turno = ref<FuelShift | null>(null);
const fondo = ref('0');

const venta = reactive({
  product: 'GASOLINE',
  sale_type: 'PUBLIC',
  payment_method: 'CASH',
  volume: '',
  volume_uom: 'LITER',
  unit_price: '',
  customer_name: '',
});

function puede(code: string): boolean {
  const companyId = ctx.activeCompanyId;
  return companyId ? acl.hasPermission(companyId, code) : false;
}

const opcionesProducto = Object.entries(FUEL_PRODUCT_LABELS).map(([value, label]) => ({ value, label }));
const opcionesTipoVenta = Object.entries(FUEL_SALE_TYPE_LABELS).map(([value, label]) => ({ value, label }));
const opcionesPagoFuel = Object.entries(FUEL_PAYMENT_LABELS).map(([value, label]) => ({ value, label }));
const opcionesUom = Object.entries(VOLUME_UOM_LABELS).map(([value, label]) => ({ value, label }));

const totalEstimado = computed(() => Number(venta.volume || 0) * Number(venta.unit_price || 0));
const ventaValida = computed(
  () => turno.value != null && Number(venta.volume) > 0 && Number(venta.unit_price) > 0,
);

async function cargar() {
  loading.value = true;
  try {
    const [ses, shifts] = await Promise.all([getCurrentPosSession(), listShifts()]);
    sesion.value = ses;
    turno.value = shifts.find((s) => s.status === 'OPEN') ?? null;
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo cargar el POS.') });
  } finally {
    loading.value = false;
  }
}

async function abrirSesion() {
  accionando.value = true;
  try {
    await openPosSession(Number(fondo.value || 0).toFixed(2));
    $q.notify({ type: 'positive', message: 'Sesión POS abierta.' });
    await cargar();
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo abrir la sesión.') });
  } finally {
    accionando.value = false;
  }
}

function confirmarCierre() {
  if (!sesion.value) return;
  $q.dialog({
    title: 'Cerrar sesión POS',
    message: 'Monto contado en la gaveta C$:',
    prompt: { model: '0', type: 'number', isValid: (v) => Number(v) >= 0 },
    cancel: { flat: true, noCaps: true, label: 'Cancelar' },
    ok: { unelevated: true, noCaps: true, color: 'negative', label: 'Cerrar' },
    persistent: true,
  }).onOk((monto: string) => {
    void (async () => {
      try {
        const r = await closePosSession(sesion.value!.id, Number(monto).toFixed(2));
        $q.notify({
          type: Number(r.difference_amount ?? 0) === 0 ? 'positive' : 'warning',
          message: `Sesión cerrada. Diferencia: ${formatMoney(r.difference_amount ?? 0)}.`,
        });
        await cargar();
      } catch (e) {
        $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo cerrar.') });
      }
    })();
  });
}

async function cobrar() {
  if (!ventaValida.value || !turno.value) return;
  accionando.value = true;
  try {
    const ticket = await openPosTicket({
      shift_id: turno.value.id,
      sale_type: venta.sale_type,
      payment_method: venta.payment_method,
      ...(venta.customer_name ? { customer_name: venta.customer_name } : {}),
    });
    await checkoutPosTicket(ticket.id, {
      product: venta.product,
      volume: String(venta.volume),
      volume_uom: venta.volume_uom,
      unit_price_entered: String(venta.unit_price),
      unit_price_uom: venta.volume_uom === 'LITER' ? 'PER_LITER' : 'PER_GALLON',
    });
    $q.notify({
      type: 'positive',
      message: `Cobrado ${formatMoney(totalEstimado.value)} (${FUEL_PAYMENT_LABELS[venta.payment_method]}).`,
      timeout: 5000,
    });
    Object.assign(venta, { volume: '', unit_price: '', customer_name: '' });
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo completar el cobro.') });
  } finally {
    accionando.value = false;
  }
}

onMounted(cargar);
</script>

<style scoped>
.pos-card {
  padding: var(--app-space-4);
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-lg);
  background: var(--app-surface);
}

.pos-abrir {
  max-width: 480px;
}

.pos-card__title {
  font-weight: 800;
  color: var(--app-text);
  margin-bottom: var(--app-space-3);
}

.pos-resumen {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: var(--app-space-3);
  margin-bottom: var(--app-space-4);
}

.pos-stat {
  padding: var(--app-space-3) var(--app-space-4);
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-md);
  background: var(--app-surface);
}

.pos-stat--accion {
  display: flex;
  align-items: center;
  justify-content: center;
  border-style: dashed;
}

.pos-stat__label {
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--app-text-muted);
}

.pos-stat__value {
  font-weight: 800;
  color: var(--app-text);
}

.pos-total {
  font-size: 1.05rem;
  color: var(--app-text);
}
</style>
