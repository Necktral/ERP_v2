<template>
  <AppContainer>
    <AppPageHeader
      title="Retail POS · Terminal"
      subtitle="Flujo operativo: sesion de caja, ticket y checkout para Fuel POS Spine."
    >
      <template #actions>
        <q-btn outline icon="monitor" label="Cockpit" :to="routes.retailPosCockpit" />
        <q-btn
          outline
          color="secondary"
          icon="sync"
          :label="`Cola (${queueStats.pending})`"
          :loading="queueLoading"
          @click="processOfflineQueueAction"
        />
        <q-btn color="primary" icon="refresh" label="Recargar" :loading="loading" @click="refreshAll" />
      </template>
    </AppPageHeader>

    <q-banner v-if="!canRead" dense rounded class="q-mt-md">
      No tienes permiso <b>retail.pos.ticket.read</b> o no hay contexto de empresa.
    </q-banner>

    <q-banner v-else-if="error" dense rounded class="q-mt-md bg-red-1 text-red-10">
      {{ error }}
    </q-banner>

    <q-card v-if="canRead" class="app-card q-mt-md">
      <q-card-section class="row items-center justify-between">
        <div>
          <div class="text-subtitle1">Cola Offline POS</div>
          <div class="text-caption text-grey-7">
            Reintentos automáticos con backoff para operaciones transientes.
          </div>
        </div>
        <q-badge outline>
          Pendientes: {{ queueStats.pending }} · Fallidos: {{ queueStats.failed }} · Due: {{ queueStats.due_now }}
        </q-badge>
      </q-card-section>
      <q-separator />
      <q-card-section class="q-pa-none">
        <q-markup-table flat dense>
          <thead>
            <tr>
              <th class="text-left">Tipo</th>
              <th class="text-left">Estado</th>
              <th class="text-left">Intentos</th>
              <th class="text-left">Próximo retry</th>
              <th class="text-left">Error</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="cmd in offlineCommands.slice(0, 10)" :key="cmd.id">
              <td>{{ cmd.kind }}</td>
              <td>{{ cmd.status }}</td>
              <td>{{ cmd.attempts }}</td>
              <td>{{ cmd.next_retry_at || '—' }}</td>
              <td>{{ cmd.last_error || '—' }}</td>
            </tr>
            <tr v-if="offlineCommands.length === 0">
              <td colspan="5" class="text-center text-grey-7 q-pa-md">Sin comandos en cola offline.</td>
            </tr>
          </tbody>
        </q-markup-table>
      </q-card-section>
    </q-card>

    <div v-if="canRead" class="row q-col-gutter-md q-mt-md">
      <div class="col-12 col-lg-5">
        <q-card class="app-card">
          <q-card-section>
            <div class="text-subtitle1">Sesion POS</div>
            <div class="text-caption text-grey-7">
              Apertura/cierre de caja por sucursal. Requiere contexto activo.
            </div>
          </q-card-section>
          <q-separator />

          <q-card-section v-if="session">
            <div class="row q-col-gutter-sm">
              <div class="col-6">
                <q-input label="Sesion" :model-value="String(session.id)" readonly outlined dense />
              </div>
              <div class="col-6">
                <q-input label="Estado" :model-value="session.status" readonly outlined dense />
              </div>
              <div class="col-6">
                <q-input label="Caja" :model-value="String(session.cash_session_id ?? '—')" readonly outlined dense />
              </div>
              <div class="col-6">
                <q-input label="Apertura" :model-value="session.opening_amount" readonly outlined dense />
              </div>
            </div>

            <div class="row q-col-gutter-sm q-mt-sm">
              <div class="col-6">
                <q-input
                  v-model="closeForm.counted_amount"
                  outlined
                  dense
                  label="Conteo de cierre"
                  type="number"
                  step="0.01"
                />
              </div>
              <div class="col-6">
                <q-input v-model="closeForm.note" outlined dense label="Nota cierre" />
              </div>
            </div>
          </q-card-section>

          <q-card-section v-else>
            <div class="row q-col-gutter-sm">
              <div class="col-6">
                <q-input
                  v-model="openForm.opening_amount"
                  outlined
                  dense
                  label="Apertura"
                  type="number"
                  step="0.01"
                />
              </div>
              <div class="col-6">
                <q-input v-model="openForm.note" outlined dense label="Nota apertura" />
              </div>
            </div>
          </q-card-section>

          <q-card-actions align="right">
            <q-btn
              v-if="!session"
              color="primary"
              icon="play_arrow"
              label="Abrir sesion"
              :disable="!canSessionOpen"
              :loading="actionLoading"
              @click="openSessionAction"
            />
            <q-btn
              v-else
              color="negative"
              icon="stop"
              label="Cerrar sesion"
              :disable="!canSessionClose"
              :loading="actionLoading"
              @click="closeSessionAction"
            />
          </q-card-actions>
        </q-card>
      </div>

      <div class="col-12 col-lg-7">
        <q-card class="app-card">
          <q-card-section>
            <div class="text-subtitle1">Nuevo ticket + checkout</div>
            <div class="text-caption text-grey-7">
              Crea ticket en sesion abierta y ejecuta checkout con una linea fuel.
            </div>
          </q-card-section>
          <q-separator />
          <q-card-section>
            <div class="row q-col-gutter-sm">
              <div class="col-4">
                <q-input v-model="ticketForm.shift_id" outlined dense type="number" label="Shift ID" />
              </div>
              <div class="col-4">
                <q-input v-model="ticketForm.idempotency_key" outlined dense label="Idempotency key" />
              </div>
              <div class="col-4">
                <q-input v-model="ticketForm.external_ref" outlined dense label="External ref" />
              </div>
              <div class="col-6">
                <q-input v-model="ticketForm.customer_name" outlined dense label="Cliente" />
              </div>
              <div class="col-3">
                <q-select
                  v-model="ticketForm.sale_type"
                  outlined
                  dense
                  emit-value
                  map-options
                  label="Sale type"
                  :options="saleTypeOptions"
                />
              </div>
              <div class="col-3">
                <q-select
                  v-model="ticketForm.payment_method"
                  outlined
                  dense
                  emit-value
                  map-options
                  label="Pago"
                  :options="paymentOptions"
                />
              </div>
              <div class="col-3">
                <q-select
                  v-model="ticketForm.product"
                  outlined
                  dense
                  emit-value
                  map-options
                  label="Producto"
                  :options="productOptions"
                />
              </div>
              <div class="col-3">
                <q-input v-model="ticketForm.volume" outlined dense type="number" step="0.0001" label="Volumen" />
              </div>
              <div class="col-3">
                <q-select
                  v-model="ticketForm.volume_uom"
                  outlined
                  dense
                  emit-value
                  map-options
                  label="UoM"
                  :options="volumeOptions"
                />
              </div>
              <div class="col-3">
                <q-input
                  v-model="ticketForm.unit_price_entered"
                  outlined
                  dense
                  type="number"
                  step="0.0001"
                  label="Precio"
                />
              </div>
            </div>
          </q-card-section>
          <q-card-actions align="right">
            <q-btn
              color="primary"
              icon="point_of_sale"
              label="Crear y checkout"
              :disable="!session || !canCheckout"
              :loading="actionLoading"
              @click="createAndCheckout"
            />
          </q-card-actions>
        </q-card>
      </div>
    </div>

    <q-card v-if="canRead" class="app-card q-mt-md">
      <q-card-section class="row items-center justify-between">
        <div class="text-subtitle1">Tickets recientes</div>
        <q-badge outline>{{ tickets.length }} tickets</q-badge>
      </q-card-section>
      <q-separator />
      <q-card-section class="q-pa-none">
        <q-markup-table flat dense>
          <thead>
            <tr>
              <th class="text-left">Ticket</th>
              <th class="text-left">Estado</th>
              <th class="text-left">Shift</th>
              <th class="text-left">Total</th>
              <th class="text-left">Pago</th>
              <th class="text-left">Acciones</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in tickets" :key="row.id">
              <td>#{{ row.id }}</td>
              <td>{{ row.status }}</td>
              <td>{{ row.shift_id }}</td>
              <td>{{ row.total_amount }}</td>
              <td>{{ row.payment_method }}</td>
              <td>
                <q-btn
                  flat
                  dense
                  color="warning"
                  label="Retry"
                  :disable="row.status !== 'CHECKOUT_PENDING' || !canCheckout"
                  @click="retryCompensationAction(row.id)"
                />
                <q-btn
                  flat
                  dense
                  color="negative"
                  label="Anular"
                  :disable="row.status === 'VOIDED' || !canVoid"
                  @click="voidAction(row.id)"
                />
              </td>
            </tr>
            <tr v-if="tickets.length === 0">
              <td colspan="6" class="text-center text-grey-7 q-pa-md">Sin tickets POS registrados.</td>
            </tr>
          </tbody>
        </q-markup-table>
      </q-card-section>
    </q-card>
  </AppContainer>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue';
import AppContainer from 'src/ui/AppContainer.vue';
import AppPageHeader from 'src/ui/AppPageHeader.vue';
import { UI_ROUTE_PATHS } from 'src/shared/ui/business-terms';
import { useAclStore } from 'src/stores/acl.store';
import { useContextStore } from 'src/stores/context.store';
import {
  buildCreateCheckoutDedupeKey,
  drainPosOfflineQueue,
  enqueuePosOfflineCommand,
  getPosOfflineQueueStats,
  listPosOfflineCommands,
  type PosOfflineCommand,
  type PosOfflineQueueStats,
} from 'src/services/retail-pos-offline-queue';
import {
  checkoutPosTicket,
  closePosSession,
  getPosCurrentSession,
  listPosTickets,
  openPosSession,
  openPosTicket,
  retryPosTicketCompensation,
  type PosSessionSummary,
  type PosTicket,
  voidPosTicket,
} from 'src/services/retail-pos.service';

const acl = useAclStore();
const ctx = useContextStore();
const routes = UI_ROUTE_PATHS;

const loading = ref(false);
const actionLoading = ref(false);
const queueLoading = ref(false);
const error = ref<string | null>(null);
const session = ref<PosSessionSummary | null>(null);
const tickets = ref<PosTicket[]>([]);
const offlineCommands = ref<PosOfflineCommand[]>([]);
const queueStats = ref<PosOfflineQueueStats>({
  total: 0,
  pending: 0,
  processing: 0,
  failed: 0,
  done: 0,
  due_now: 0,
});

const openForm = reactive({
  opening_amount: '0.00',
  note: '',
});

const closeForm = reactive({
  counted_amount: '0.00',
  note: '',
});

const ticketForm = reactive({
  shift_id: '',
  idempotency_key: '',
  external_ref: '',
  customer_name: '',
  sale_type: 'PUBLIC',
  payment_method: 'CASH',
  product: 'DIESEL',
  volume: '1.0000',
  volume_uom: 'LITER',
  unit_price_entered: '0.0000',
});

const productOptions = [
  { label: 'Diesel', value: 'DIESEL' },
  { label: 'Gasolina', value: 'GASOLINE' },
];
const paymentOptions = [
  { label: 'Efectivo', value: 'CASH' },
  { label: 'Transferencia', value: 'TRANSFER' },
  { label: 'Credito', value: 'CREDIT' },
];
const saleTypeOptions = [
  { label: 'Publico', value: 'PUBLIC' },
  { label: 'Interno', value: 'INTERNAL' },
  { label: 'Empleado', value: 'EMPLOYEE' },
];
const volumeOptions = [
  { label: 'Litro', value: 'LITER' },
  { label: 'Galon US', value: 'GALLON_US' },
];

function hasPermission(code: string): boolean {
  const companyId = ctx.activeCompanyId;
  if (!companyId) return false;
  return acl.hasPermission(companyId, code);
}

const canRead = computed(() => hasPermission('retail.pos.ticket.read'));
const canSessionOpen = computed(() => hasPermission('retail.pos.session.open'));
const canSessionClose = computed(() => hasPermission('retail.pos.session.close'));
const canCheckout = computed(() => hasPermission('retail.pos.ticket.checkout'));
const canVoid = computed(() => hasPermission('retail.pos.ticket.void'));

function asErrorMessage(cause: unknown): string {
  if (typeof cause === 'object' && cause !== null) {
    const response = (cause as { response?: { data?: { error?: { message?: string; details?: unknown } } } })
      .response;
    const msg = response?.data?.error?.message;
    if (msg) return msg;
  }
  if (cause instanceof Error) return cause.message;
  return String(cause);
}

function shouldQueueOffline(cause: unknown): boolean {
  if (!navigator.onLine) return true;
  if (typeof cause === 'object' && cause !== null) {
    const status = Number((cause as { response?: { status?: number } }).response?.status || 0);
    if (!status) return true;
    if (status >= 500 || status === 429) return true;
  }
  return false;
}

function ensurePosIdempotencyKey(value: string): string {
  const raw = (value || '').trim();
  if (raw) return raw;
  return `pos-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function refreshOfflineQueueSnapshot() {
  offlineCommands.value = listPosOfflineCommands();
  queueStats.value = getPosOfflineQueueStats();
}

async function refreshAll() {
  if (!canRead.value) return;
  loading.value = true;
  error.value = null;
  try {
    const [current, list] = await Promise.all([
      getPosCurrentSession(),
      listPosTickets({ limit: 20, offset: 0 }),
    ]);
    session.value = current;
    tickets.value = list.results;
    if (session.value) {
      closeForm.counted_amount = session.value.opening_amount;
    }
    refreshOfflineQueueSnapshot();
  } catch (cause) {
    error.value = asErrorMessage(cause);
  } finally {
    loading.value = false;
  }
}

async function openSessionAction() {
  if (!canSessionOpen.value) return;
  actionLoading.value = true;
  error.value = null;
  try {
    await openPosSession({
      opening_amount: openForm.opening_amount || '0.00',
      note: openForm.note,
    });
    await refreshAll();
  } catch (cause) {
    error.value = asErrorMessage(cause);
  } finally {
    actionLoading.value = false;
  }
}

async function closeSessionAction() {
  if (!session.value || !canSessionClose.value) return;
  actionLoading.value = true;
  error.value = null;
  try {
    await closePosSession(session.value.id, {
      counted_amount: closeForm.counted_amount || '0.00',
      note: closeForm.note,
    });
    await refreshAll();
  } catch (cause) {
    error.value = asErrorMessage(cause);
  } finally {
    actionLoading.value = false;
  }
}

async function createAndCheckout() {
  if (!session.value || !canCheckout.value) return;
  actionLoading.value = true;
  error.value = null;
  const fallbackIdempotency = ensurePosIdempotencyKey(ticketForm.idempotency_key);
  try {
    const shiftId = Number(ticketForm.shift_id);
    if (!Number.isFinite(shiftId) || shiftId <= 0) {
      throw new Error('Shift ID invalido.');
    }
    const openPayload: Parameters<typeof openPosTicket>[0] = {
      shift_id: shiftId,
      sale_type: ticketForm.sale_type as 'PUBLIC' | 'INTERNAL' | 'EMPLOYEE',
      payment_method: ticketForm.payment_method as 'CASH' | 'TRANSFER' | 'CREDIT',
    };
    openPayload.idempotency_key = fallbackIdempotency;
    if (ticketForm.external_ref) openPayload.external_ref = ticketForm.external_ref;
    if (ticketForm.customer_name) openPayload.customer_name = ticketForm.customer_name;

    const opened = await openPosTicket(openPayload);
    await checkoutPosTicket(opened.id, {
      line: {
        product: ticketForm.product as 'DIESEL' | 'GASOLINE',
        volume: ticketForm.volume,
        volume_uom: ticketForm.volume_uom as 'LITER' | 'GALLON' | 'GALLON_US',
        unit_price_entered: ticketForm.unit_price_entered,
        unit_price_uom: 'PER_LITER',
        metadata: { source: 'frontend-pos-terminal' },
      },
    });
    await refreshAll();
  } catch (cause) {
    if (shouldQueueOffline(cause)) {
      const companyId = Number(ctx.activeCompanyId || 0);
      const branchId = Number(ctx.activeBranchId || 0);
      if (companyId > 0 && branchId > 0) {
        const dedupeKey = buildCreateCheckoutDedupeKey({
          company_id: companyId,
          branch_id: branchId,
          idempotency_key: fallbackIdempotency,
        });
        enqueuePosOfflineCommand({
          kind: 'CREATE_AND_CHECKOUT',
          company_id: companyId,
          branch_id: branchId,
          dedupe_key: dedupeKey,
          payload: {
            open_ticket: {
              shift_id: Number(ticketForm.shift_id),
              idempotency_key: fallbackIdempotency,
              sale_type: ticketForm.sale_type as 'PUBLIC' | 'INTERNAL' | 'EMPLOYEE',
              payment_method: ticketForm.payment_method as 'CASH' | 'TRANSFER' | 'CREDIT',
              ...(ticketForm.external_ref ? { external_ref: ticketForm.external_ref } : {}),
              ...(ticketForm.customer_name ? { customer_name: ticketForm.customer_name } : {}),
            },
            checkout: {
              line: {
                product: ticketForm.product as 'DIESEL' | 'GASOLINE',
                volume: ticketForm.volume,
                volume_uom: ticketForm.volume_uom as 'LITER' | 'GALLON' | 'GALLON_US',
                unit_price_entered: ticketForm.unit_price_entered,
                unit_price_uom: 'PER_LITER',
                metadata: { source: 'frontend-pos-terminal', mode: 'offline_queue' },
              },
            },
          },
        });
        refreshOfflineQueueSnapshot();
        error.value = 'Operacion encolada para reintento offline. Procesa la cola cuando vuelva la conectividad.';
      } else {
        error.value = `${asErrorMessage(cause)} (sin contexto válido para encolar)`;
      }
    } else {
      error.value = asErrorMessage(cause);
    }
  } finally {
    actionLoading.value = false;
  }
}

async function voidAction(ticketId: number) {
  if (!canVoid.value) return;
  actionLoading.value = true;
  error.value = null;
  try {
    await voidPosTicket(ticketId, { reason: 'VOID_FROM_POS_TERMINAL' });
    await refreshAll();
  } catch (cause) {
    error.value = asErrorMessage(cause);
  } finally {
    actionLoading.value = false;
  }
}

async function retryCompensationAction(ticketId: number) {
  if (!canCheckout.value) return;
  actionLoading.value = true;
  error.value = null;
  try {
    await retryPosTicketCompensation(ticketId, { reason: 'MANUAL_RETRY_TERMINAL' });
    await refreshAll();
  } catch (cause) {
    error.value = asErrorMessage(cause);
  } finally {
    actionLoading.value = false;
  }
}

async function processOfflineQueueAction() {
  if (queueLoading.value) return;
  queueLoading.value = true;
  error.value = null;
  try {
    const result = await drainPosOfflineQueue({
      maxCommands: 20,
      executor: async (command) => {
        if (command.kind === 'CREATE_AND_CHECKOUT') {
          const payload = command.payload as {
            open_ticket: Parameters<typeof openPosTicket>[0];
            checkout: Parameters<typeof checkoutPosTicket>[1];
          };
          const opened = await openPosTicket(payload.open_ticket);
          await checkoutPosTicket(opened.id, payload.checkout);
          return;
        }
        if (command.kind === 'VOID_TICKET') {
          const payload = command.payload as { ticket_id: number; reason?: string };
          await voidPosTicket(payload.ticket_id, { reason: payload.reason || 'VOID_OFFLINE_QUEUE' });
          return;
        }
        if (command.kind === 'COMPENSATION_RETRY') {
          const payload = command.payload as { ticket_id: number; reason?: string };
          await retryPosTicketCompensation(payload.ticket_id, {
            reason: payload.reason || 'RETRY_OFFLINE_QUEUE',
          });
        }
      },
    });
    refreshOfflineQueueSnapshot();
    await refreshAll();
    if (result.failed > 0) {
      error.value = `Cola offline procesada con fallos: ${result.failed}. Revisa errores de comandos.`;
    }
  } catch (cause) {
    error.value = asErrorMessage(cause);
  } finally {
    queueLoading.value = false;
  }
}

function onOnline() {
  if (getPosOfflineQueueStats().due_now > 0) {
    void processOfflineQueueAction();
  }
}

onMounted(() => {
  refreshOfflineQueueSnapshot();
  window.addEventListener('online', onOnline);
  void refreshAll();
});

onUnmounted(() => {
  window.removeEventListener('online', onOnline);
});
</script>
