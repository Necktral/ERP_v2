<template>
  <q-page class="app-page">
    <PageHeader
      title="Caja"
      subtitle="Sesión de caja de la sucursal activa: abrir con fondo, registrar movimientos, hacer el arqueo y cerrar contra lo esperado."
      :loading="loading"
      @refresh="cargar"
    >
      <template #actions>
        <q-btn flat no-caps icon="history" label="Historial" to="/caja/sesiones" />
        <q-btn
          v-if="puede('payments.intent.read')"
          flat
          no-caps
          icon="payments"
          label="Intentos de pago"
          to="/caja/pagos"
        />
      </template>
    </PageHeader>

    <!-- Sin sesión abierta -->
    <div v-if="!sesion" class="caja-abrir">
      <div class="caja-card">
        <div class="caja-card__title">No hay caja abierta</div>
        <p class="text-muted">
          Abrí la sesión con el fondo inicial (lo que hay en la gaveta al empezar el día).
        </p>
        <div class="app-form">
          <q-input
            v-model="fondoInicial"
            outlined
            dense
            type="number"
            min="0"
            label="Fondo inicial C$"
          />
          <q-input v-model="notaApertura" outlined dense label="Nota (opcional)" />
        </div>
        <q-btn
          v-if="puede('payments.cash_session.open')"
          class="q-mt-md"
          unelevated
          no-caps
          color="primary"
          icon="point_of_sale"
          label="Abrir caja"
          :loading="accionando"
          @click="abrirCaja"
        />
        <div v-else class="text-caption text-muted q-mt-md">No tenés permiso para abrir caja.</div>
      </div>
    </div>

    <!-- Sesión abierta -->
    <template v-else>
      <div class="caja-resumen">
        <div class="caja-stat">
          <div class="caja-stat__label">Estado</div>
          <div class="caja-stat__value">
            {{ CASH_SESSION_STATUS_LABELS[sesion.status] ?? sesion.status }}
          </div>
        </div>
        <div class="caja-stat">
          <div class="caja-stat__label">Fondo inicial</div>
          <div class="caja-stat__value">{{ formatMoney(sesion.opening_amount) }}</div>
        </div>
        <div class="caja-stat">
          <div class="caja-stat__label">Esperado en gaveta</div>
          <div class="caja-stat__value">{{ formatMoney(sesion.expected_amount) }}</div>
        </div>
        <div class="caja-stat">
          <div class="caja-stat__label">Abierta</div>
          <div class="caja-stat__value">{{ formatDateTime(sesion.opened_at) }}</div>
        </div>
      </div>

      <div class="caja-cols">
        <!-- Movimientos -->
        <div class="caja-card">
          <div class="caja-card__title">
            Movimientos
            <q-btn
              v-if="puede('payments.cash_movement.create')"
              flat
              dense
              no-caps
              size="sm"
              icon="add"
              label="Registrar"
              @click="abrirMovimiento"
            />
          </div>
          <q-list dense separator>
            <q-item v-for="m in movimientos" :key="m.id">
              <q-item-section>
                <q-item-label>{{ CASH_MOVEMENT_TYPE_LABELS[m.movement_type] ?? m.movement_type }}</q-item-label>
                <q-item-label caption>{{ m.reference || formatDateTime(m.created_at) }}</q-item-label>
              </q-item-section>
              <q-item-section side>
                <q-item-label
                  :class="m.movement_type === 'EXPENSE' || m.movement_type === 'REFUND' ? 'text-negative' : 'text-positive'"
                >
                  {{ m.movement_type === 'EXPENSE' || m.movement_type === 'REFUND' ? '-' : '+' }}{{ formatMoney(m.amount) }}
                </q-item-label>
              </q-item-section>
            </q-item>
            <q-item v-if="movimientos.length === 0">
              <q-item-section class="text-caption text-muted">Sin movimientos todavía.</q-item-section>
            </q-item>
          </q-list>
        </div>

        <!-- Arqueo + cierre -->
        <div class="caja-card">
          <div class="caja-card__title">Arqueo y cierre</div>
          <p class="text-caption text-muted">
            Contá la gaveta por denominación. El total contado se compara contra lo esperado.
          </p>
          <div class="caja-arqueo">
            <div v-for="d in arqueo" :key="`${d.denomination_type}-${d.denomination_value}`" class="caja-denominacion">
              <span class="caja-denominacion__valor">
                {{ d.denomination_type === 'BILL' ? 'Billete' : 'Moneda' }} {{ formatMoney(d.denomination_value) }}
              </span>
              <q-input
                v-model.number="d.quantity"
                dense
                outlined
                type="number"
                min="0"
                class="caja-denominacion__cant"
              />
              <span class="caja-denominacion__sub">
                {{ formatMoney(Number(d.denomination_value) * (d.quantity || 0)) }}
              </span>
            </div>
          </div>
          <div class="caja-total">
            Contado: <strong>{{ formatMoney(totalContado) }}</strong>
            · Esperado: <strong>{{ formatMoney(sesion.expected_amount) }}</strong>
            <span :class="diferencia === 0 ? 'text-positive' : 'text-negative'">
              · Diferencia: <strong>{{ formatMoney(diferencia) }}</strong>
            </span>
          </div>
          <div class="row q-gutter-sm q-mt-sm">
            <q-btn
              outline
              no-caps
              color="primary"
              icon="calculate"
              label="Guardar arqueo"
              :loading="accionando"
              @click="guardarArqueo"
            />
            <q-btn
              v-if="puede('payments.cash_session.close')"
              unelevated
              no-caps
              color="negative"
              icon="lock"
              label="Cerrar caja"
              :loading="accionando"
              @click="confirmarCierre"
            />
          </div>
        </div>
      </div>
    </template>

    <!-- Diálogo: movimiento -->
    <q-dialog v-model="dlgMovimiento">
      <q-card class="app-dialog">
        <q-card-section class="text-h6">Registrar movimiento de caja</q-card-section>
        <q-card-section class="app-form">
          <q-select
            v-model="formMov.movement_type"
            :options="opcionesMovimiento"
            label="Tipo *"
            outlined
            dense
            emit-value
            map-options
          />
          <q-input v-model="formMov.amount" outlined dense type="number" min="0" label="Monto C$ *" />
          <q-input v-model="formMov.reference" outlined dense label="Referencia (factura, recibo…)" />
          <q-input v-model="formMov.reason" outlined dense label="Motivo" />
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat no-caps label="Cancelar" v-close-popup />
          <q-btn
            unelevated
            no-caps
            color="primary"
            label="Registrar"
            :loading="accionando"
            :disable="!formMov.amount || Number(formMov.amount) <= 0"
            @click="registrarMovimiento"
          />
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
import { formatDateTime, formatMoney } from 'src/core/format';
import {
  CASH_MOVEMENT_TYPE_LABELS,
  CASH_SESSION_STATUS_LABELS,
  closeCashSession,
  createCashMovement,
  getCashSession,
  listCashMovements,
  listCashSessions,
  openCashSession,
  submitDenominations,
  type CashMovementRow,
  type CashSession,
  type Denomination,
} from 'src/features/payments/payments.api';
import { useAclStore } from 'src/stores/acl.store';
import { useContextStore } from 'src/stores/context.store';

const $q = useQuasar();
const acl = useAclStore();
const ctx = useContextStore();

const loading = ref(false);
const accionando = ref(false);
const sesion = ref<CashSession | null>(null);
const movimientos = ref<CashMovementRow[]>([]);

const fondoInicial = ref('0');
const notaApertura = ref('');

// Denominaciones córdoba (billetes y monedas en circulación)
const arqueo = reactive<Denomination[]>([
  { denomination_type: 'BILL', denomination_value: '1000', quantity: 0 },
  { denomination_type: 'BILL', denomination_value: '500', quantity: 0 },
  { denomination_type: 'BILL', denomination_value: '200', quantity: 0 },
  { denomination_type: 'BILL', denomination_value: '100', quantity: 0 },
  { denomination_type: 'BILL', denomination_value: '50', quantity: 0 },
  { denomination_type: 'BILL', denomination_value: '20', quantity: 0 },
  { denomination_type: 'BILL', denomination_value: '10', quantity: 0 },
  { denomination_type: 'COIN', denomination_value: '5', quantity: 0 },
  { denomination_type: 'COIN', denomination_value: '1', quantity: 0 },
  { denomination_type: 'COIN', denomination_value: '0.50', quantity: 0 },
  { denomination_type: 'COIN', denomination_value: '0.25', quantity: 0 },
]);

function puede(code: string): boolean {
  const companyId = ctx.activeCompanyId;
  return companyId ? acl.hasPermission(companyId, code) : false;
}

const totalContado = computed(() =>
  arqueo.reduce((acc, d) => acc + Number(d.denomination_value) * (d.quantity || 0), 0),
);
const diferencia = computed(() => totalContado.value - Number(sesion.value?.expected_amount ?? 0));

const opcionesMovimiento = Object.entries(CASH_MOVEMENT_TYPE_LABELS).map(([value, label]) => ({
  value,
  label,
}));

async function cargar() {
  loading.value = true;
  try {
    const sesiones = await listCashSessions();
    const abierta = sesiones.find((s) =>
      ['OPEN', 'COUNT_PENDING', 'REVIEW_PENDING', 'REOPENED_FOR_INVESTIGATION'].includes(s.status),
    );
    if (abierta) {
      sesion.value = await getCashSession(abierta.id);
      movimientos.value = await listCashMovements(abierta.id);
    } else {
      sesion.value = null;
      movimientos.value = [];
    }
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo cargar la caja.') });
  } finally {
    loading.value = false;
  }
}

async function abrirCaja() {
  accionando.value = true;
  try {
    await openCashSession({
      opening_amount: Number(fondoInicial.value || 0).toFixed(2),
      ...(notaApertura.value ? { notes: notaApertura.value } : {}),
    });
    $q.notify({ type: 'positive', message: 'Caja abierta.' });
    await cargar();
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo abrir la caja.') });
  } finally {
    accionando.value = false;
  }
}

// --- Movimientos ---
const dlgMovimiento = ref(false);
const formMov = reactive({ movement_type: 'INCOME', amount: '', reference: '', reason: '' });

function abrirMovimiento() {
  Object.assign(formMov, { movement_type: 'INCOME', amount: '', reference: '', reason: '' });
  dlgMovimiento.value = true;
}

async function registrarMovimiento() {
  if (!sesion.value) return;
  accionando.value = true;
  try {
    await createCashMovement(sesion.value.id, {
      movement_type: formMov.movement_type,
      amount: Number(formMov.amount).toFixed(2),
      ...(formMov.reference ? { reference: formMov.reference } : {}),
      ...(formMov.reason ? { reason: formMov.reason } : {}),
    });
    dlgMovimiento.value = false;
    $q.notify({ type: 'positive', message: 'Movimiento registrado.' });
    await cargar();
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo registrar.') });
  } finally {
    accionando.value = false;
  }
}

// --- Arqueo / cierre ---
async function guardarArqueo() {
  if (!sesion.value) return;
  accionando.value = true;
  try {
    const conCantidad = arqueo.filter((d) => (d.quantity || 0) > 0);
    await submitDenominations(sesion.value.id, conCantidad.length ? conCantidad : arqueo);
    $q.notify({ type: 'positive', message: `Arqueo guardado: ${formatMoney(totalContado.value)}.` });
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo guardar el arqueo.') });
  } finally {
    accionando.value = false;
  }
}

function confirmarCierre() {
  if (!sesion.value) return;
  $q.dialog({
    title: 'Cerrar caja',
    message: `Contado ${formatMoney(totalContado.value)} vs esperado ${formatMoney(
      sesion.value.expected_amount,
    )} (diferencia ${formatMoney(diferencia.value)}). ¿Cerrar la sesión?`,
    cancel: { flat: true, noCaps: true, label: 'Cancelar' },
    ok: { unelevated: true, noCaps: true, color: 'negative', label: 'Cerrar caja' },
    persistent: true,
  }).onOk(() => {
    void cerrarCaja();
  });
}

async function cerrarCaja() {
  if (!sesion.value) return;
  accionando.value = true;
  try {
    const r = await closeCashSession(sesion.value.id, {
      counted_amount: totalContado.value.toFixed(2),
    });
    $q.notify({
      type: Number(r.difference_amount) === 0 ? 'positive' : 'warning',
      message: `Caja cerrada. Diferencia: ${formatMoney(r.difference_amount)}.`,
      timeout: 6000,
    });
    await cargar();
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo cerrar la caja.') });
  } finally {
    accionando.value = false;
  }
}

onMounted(cargar);
</script>

<style scoped>
.caja-abrir {
  max-width: 480px;
}

.caja-card {
  padding: var(--app-space-4);
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-lg);
  background: var(--app-surface);
}

.caja-card__title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-weight: 800;
  color: var(--app-text);
  margin-bottom: var(--app-space-3);
}

.caja-resumen {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: var(--app-space-3);
  margin-bottom: var(--app-space-4);
}

.caja-stat {
  padding: var(--app-space-3) var(--app-space-4);
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-md);
  background: var(--app-surface);
}

.caja-stat__label {
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--app-text-muted);
}

.caja-stat__value {
  font-weight: 800;
  font-size: 1.05rem;
  color: var(--app-text);
}

.caja-cols {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(340px, 1fr));
  gap: var(--app-space-4);
}

.caja-arqueo {
  display: flex;
  flex-direction: column;
  gap: var(--app-space-1);
}

.caja-denominacion {
  display: flex;
  align-items: center;
  gap: var(--app-space-3);
}

.caja-denominacion__valor {
  width: 150px;
  color: var(--app-text);
  font-size: 0.85rem;
}

.caja-denominacion__cant {
  width: 100px;
}

.caja-denominacion__sub {
  flex: 1;
  text-align: right;
  color: var(--app-text-muted);
  font-size: 0.85rem;
}

.caja-total {
  margin-top: var(--app-space-3);
  padding-top: var(--app-space-3);
  border-top: 1px solid var(--app-border);
  color: var(--app-text);
}
</style>
