<template>
  <q-page class="app-page">
    <PageHeader
      title="Venta a crédito"
      subtitle="Vende contra la cuenta del cliente: factura, baja inventario y carga el saldo a su cuenta por cobrar — todo en una operación."
      hide-refresh
    >
      <template #actions>
        <q-btn flat round dense icon="arrow_back" aria-label="Volver" to="/comisariato" />
      </template>
    </PageHeader>

    <div class="ven-grid">
      <div class="ven-card">
        <div class="ven-card__title">1. Cuenta y bodega</div>
        <div class="app-form">
          <q-select
            v-model="cuentaId"
            :options="opcionesCuenta"
            label="Cuenta de crédito *"
            outlined
            dense
            emit-value
            map-options
            use-input
            input-debounce="200"
            @filter="filtrarCuentas"
          >
            <template #option="scope">
              <q-item v-bind="scope.itemProps">
                <q-item-section>
                  <q-item-label>{{ scope.opt.label }}</q-item-label>
                  <q-item-label caption>{{ scope.opt.caption }}</q-item-label>
                </q-item-section>
              </q-item>
            </template>
          </q-select>
          <div v-if="cuenta" class="ven-cuenta-info">
            Saldo actual: <strong>{{ formatMoney(cuenta.outstanding) }}</strong>
            · Disponible:
            <strong>{{ cuenta.available == null ? 'sin tope' : formatMoney(cuenta.available) }}</strong>
          </div>
          <q-select
            v-model="bodegaId"
            :options="opcionesBodega"
            label="Bodega que despacha *"
            outlined
            dense
            emit-value
            map-options
          />
          <q-toggle v-model="esFiscal" label="Factura fiscal" color="primary" />
        </div>
      </div>

      <div class="ven-card">
        <div class="ven-card__title">2. Artículos</div>
        <div v-for="(linea, idx) in lineas" :key="idx" class="ven-linea">
          <q-select
            v-model="linea.inventory_item_id"
            :options="opcionesItemFiltradas"
            label="Artículo *"
            outlined
            dense
            emit-value
            map-options
            use-input
            input-debounce="200"
            class="ven-linea__item"
            @filter="filtrarItems"
            @update:model-value="(v: number | null) => completarDescripcion(linea, v)"
          />
          <q-input v-model="linea.quantity" outlined dense type="number" min="0" label="Cant. *" class="ven-linea__num" />
          <q-input v-model="linea.unit_price" outlined dense type="number" min="0" label="Precio C$ *" class="ven-linea__num" />
          <q-btn flat dense round icon="delete" color="grey-7" @click="lineas.splice(idx, 1)" />
        </div>
        <q-btn flat dense no-caps icon="add" label="Agregar artículo" @click="agregarLinea" />
        <div class="ven-total">Total: <strong>{{ formatMoney(total) }}</strong></div>
        <q-banner v-if="excedeLimite" class="ven-aviso" rounded>
          <template #avatar><q-icon name="warning" color="negative" /></template>
          El total supera el crédito disponible de la cuenta — el backend va a rechazar la venta.
        </q-banner>
        <q-btn
          class="q-mt-md"
          unelevated
          no-caps
          color="primary"
          icon="shopping_bag"
          label="Registrar venta a crédito"
          :loading="vendiendo"
          :disable="!ventaValida"
          @click="vender"
        />
      </div>
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useQuasar } from 'quasar';
import PageHeader from 'src/components/PageHeader.vue';
import { apiErrorMessage } from 'src/core/api';
import { formatMoney } from 'src/core/format';
import {
  createCreditSale,
  listAccounts,
  type CreditAccount,
  type SaleLineInput,
} from 'src/features/comisariato/comisariato.api';
import {
  listItems,
  listWarehouses,
  type InventoryItem,
  type Warehouse,
} from 'src/features/inventory/inventory.api';

const $q = useQuasar();

const cuentas = ref<CreditAccount[]>([]);
const bodegas = ref<Warehouse[]>([]);
const items = ref<InventoryItem[]>([]);

const cuentaId = ref<number | null>(null);
const bodegaId = ref<number | null>(null);
const esFiscal = ref(true);
const vendiendo = ref(false);

interface Linea extends SaleLineInput {
  inventory_item_id: number;
}

const lineas = ref<(Omit<Linea, 'inventory_item_id'> & { inventory_item_id: number | null })[]>([]);

function agregarLinea() {
  lineas.value.push({ description: '', quantity: '1', unit_price: '', inventory_item_id: null });
}

const cuenta = computed(() => cuentas.value.find((c) => c.id === cuentaId.value) ?? null);

const opcionesCuentaTodas = computed(() =>
  cuentas.value
    .filter((c) => c.is_active)
    .map((c) => ({
      value: c.id,
      label: c.party_display_name,
      caption: `Saldo ${formatMoney(c.outstanding)} · ${c.available == null ? 'sin tope' : `disponible ${formatMoney(c.available)}`}`,
    })),
);
const opcionesCuenta = ref<{ value: number; label: string; caption: string }[]>([]);

function filtrarCuentas(input: string, update: (fn: () => void) => void) {
  update(() => {
    const q = input.trim().toLowerCase();
    opcionesCuenta.value = q
      ? opcionesCuentaTodas.value.filter((o) => o.label.toLowerCase().includes(q))
      : opcionesCuentaTodas.value;
  });
}

const opcionesBodega = computed(() => bodegas.value.map((w) => ({ value: w.id, label: w.name })));

const opcionesItem = computed(() =>
  items.value.map((i) => ({ value: i.id, label: `${i.sku} — ${i.name}` })),
);
const opcionesItemFiltradas = ref<{ value: number; label: string }[]>([]);

function filtrarItems(input: string, update: (fn: () => void) => void) {
  update(() => {
    const q = input.trim().toLowerCase();
    opcionesItemFiltradas.value = q
      ? opcionesItem.value.filter((o) => o.label.toLowerCase().includes(q))
      : opcionesItem.value;
  });
}

function completarDescripcion(
  linea: { description: string; inventory_item_id: number | null },
  itemId: number | null,
) {
  if (itemId == null) return;
  const item = items.value.find((i) => i.id === itemId);
  if (item && !linea.description) linea.description = item.name;
  else if (item) linea.description = item.name;
}

const total = computed(() =>
  lineas.value.reduce((acc, l) => acc + Number(l.quantity || 0) * Number(l.unit_price || 0), 0),
);

const excedeLimite = computed(
  () => cuenta.value?.available != null && total.value > Number(cuenta.value.available),
);

const ventaValida = computed(
  () =>
    cuentaId.value != null &&
    bodegaId.value != null &&
    lineas.value.length > 0 &&
    lineas.value.every(
      (l) => l.inventory_item_id != null && Number(l.quantity) > 0 && Number(l.unit_price) > 0,
    ),
);

async function vender() {
  if (!ventaValida.value || cuentaId.value == null || bodegaId.value == null) return;
  vendiendo.value = true;
  try {
    await createCreditSale({
      account_id: cuentaId.value,
      warehouse_id: bodegaId.value,
      reference_code: `COM-${crypto.randomUUID().slice(0, 12)}`,
      is_fiscal: esFiscal.value,
      lines: lineas.value.map((l) => ({
        description: l.description || 'Artículo',
        quantity: String(l.quantity),
        unit_price: String(l.unit_price),
        inventory_item_id: l.inventory_item_id!,
      })),
    });
    $q.notify({
      type: 'positive',
      message: `Venta registrada por ${formatMoney(total.value)} a la cuenta de ${cuenta.value?.party_display_name}.`,
      timeout: 6000,
    });
    lineas.value = [];
    agregarLinea();
    // refrescar saldos de cuentas
    cuentas.value = await listAccounts();
  } catch (e) {
    const msg = apiErrorMessage(e, 'No se pudo registrar la venta.');
    $q.notify({
      type: 'negative',
      message:
        msg === 'COMISARIATO_CREDIT_LIMIT_EXCEEDED'
          ? 'Límite de crédito excedido: la venta supera el disponible de la cuenta.'
          : msg,
    });
  } finally {
    vendiendo.value = false;
  }
}

onMounted(async () => {
  try {
    [cuentas.value, bodegas.value, items.value] = await Promise.all([
      listAccounts(),
      listWarehouses(),
      listItems({ is_active: true }),
    ]);
    opcionesCuenta.value = opcionesCuentaTodas.value;
    opcionesItemFiltradas.value = opcionesItem.value;
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudieron cargar los datos.') });
  }
  agregarLinea();
});
</script>

<style scoped>
.ven-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(340px, 1fr));
  gap: var(--app-space-4);
}

.ven-card {
  padding: var(--app-space-4);
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-lg);
  background: var(--app-surface);
}

.ven-card__title {
  font-weight: 800;
  color: var(--app-text);
  margin-bottom: var(--app-space-3);
}

.ven-cuenta-info {
  font-size: 0.85rem;
  color: var(--app-text-muted);
}

.ven-linea {
  display: flex;
  align-items: center;
  gap: var(--app-space-2);
  margin-bottom: var(--app-space-2);
}

.ven-linea__item {
  flex: 1;
}

.ven-linea__num {
  width: 110px;
}

.ven-total {
  margin-top: var(--app-space-3);
  padding-top: var(--app-space-3);
  border-top: 1px solid var(--app-border);
  font-size: 1.05rem;
  color: var(--app-text);
}

.ven-aviso {
  margin-top: var(--app-space-3);
  background: var(--app-surface-strong);
  border: 1px solid var(--app-border);
  color: var(--app-text);
}
</style>
