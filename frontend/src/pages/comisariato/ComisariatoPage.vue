<template>
  <q-page class="app-page">
    <PageHeader
      title="Comisariato"
      subtitle="Cuentas de crédito de la tienda: empleados (se descuenta en planilla), productores y público. El saldo vive en cartera."
      :loading="loading"
      @refresh="reload"
    >
      <template #actions>
        <q-btn
          v-if="puede('comisariato.sell')"
          unelevated
          no-caps
          color="primary"
          icon="shopping_bag"
          label="Venta a crédito"
          to="/comisariato/venta"
        />
        <q-btn
          v-if="puede('comisariato.payroll.apply')"
          outline
          no-caps
          color="primary"
          icon="payments"
          label="Aplicar a planilla"
          @click="abrirAplicar"
        />
        <q-btn
          v-if="puede('comisariato.account.manage')"
          flat
          no-caps
          icon="person_add_alt"
          label="Nueva cuenta"
          @click="abrirCuenta(null)"
        />
      </template>
    </PageHeader>

    <div class="com-filtros">
      <q-input
        v-model="filtroQ"
        dense
        outlined
        clearable
        placeholder="Buscar por nombre…"
        class="com-filtros__buscar"
        :debounce="350"
        @update:model-value="reload"
      >
        <template #prepend><q-icon name="search" /></template>
      </q-input>
      <q-select
        v-model="filtroSegmento"
        :options="opcionesSegmento"
        dense
        outlined
        emit-value
        map-options
        clearable
        label="Segmento"
        class="com-filtros__sel"
        @update:model-value="reload"
      />
    </div>

    <q-table
      class="app-table"
      :rows="rows"
      :columns="columns"
      row-key="id"
      flat
      :loading="loading"
      :pagination="{ rowsPerPage: 25 }"
      no-data-label="No hay cuentas de crédito. Creá la primera con «Nueva cuenta»."
    >
      <template #body-cell-segmento="props">
        <q-td :props="props">{{ SEGMENT_LABELS[props.row.segment as CustomerSegment] }}</q-td>
      </template>
      <template #body-cell-limite="props">
        <q-td :props="props">
          {{ props.row.credit_limit == null ? 'Sin tope' : Number(props.row.credit_limit) === 0 ? 'Sin crédito' : formatMoney(props.row.credit_limit) }}
        </q-td>
      </template>
      <template #body-cell-saldo="props">
        <q-td :props="props" :class="Number(props.row.outstanding) > 0 ? 'text-weight-bold' : ''">
          {{ formatMoney(props.row.outstanding) }}
        </q-td>
      </template>
      <template #body-cell-disponible="props">
        <q-td :props="props">
          {{ props.row.available == null ? '∞' : formatMoney(props.row.available) }}
        </q-td>
      </template>
      <template #body-cell-estado="props">
        <q-td :props="props">
          <q-chip v-if="props.row.is_active" dense color="secondary" text-color="white" label="Activa" />
          <q-chip v-else dense outline color="grey-7" label="Inactiva" />
        </q-td>
      </template>
      <template #body-cell-acciones="props">
        <q-td :props="props" class="text-right">
          <q-btn
            v-if="puede('comisariato.account.manage')"
            flat
            dense
            no-caps
            size="sm"
            icon="edit"
            label="Editar"
            @click="abrirCuenta(props.row)"
          />
        </q-td>
      </template>
    </q-table>

    <!-- Diálogo: cuenta -->
    <q-dialog v-model="dlgCuenta">
      <q-card class="app-dialog">
        <q-card-section class="text-h6">
          {{ enEdicion ? `Cuenta de ${enEdicion.party_display_name}` : 'Nueva cuenta de crédito' }}
        </q-card-section>
        <q-card-section class="app-form">
          <PartySelect v-if="!enEdicion" v-model="formCuenta.party_id" label="Tercero *" />
          <q-select
            v-model="formCuenta.segment"
            :options="opcionesSegmento"
            label="Segmento *"
            outlined
            dense
            emit-value
            map-options
          />
          <q-toggle v-model="formCuenta.sinTope" label="Sin tope de crédito" color="warning" />
          <q-input
            v-if="!formCuenta.sinTope"
            v-model="formCuenta.credit_limit"
            outlined
            dense
            type="number"
            min="0"
            label="Límite de crédito C$ (0 = sin crédito)"
          />
          <q-select
            v-if="formCuenta.segment === 'EMPLOYEE'"
            v-model="formCuenta.collecting_company_id"
            :options="opcionesEmpresa"
            label="Empresa que descuenta en planilla"
            outlined
            dense
            emit-value
            map-options
            clearable
            hint="Dónde trabaja el empleado (ahí se le descuenta)."
          />
          <q-toggle v-model="formCuenta.is_active" label="Cuenta activa" color="primary" />
          <q-input v-model="formCuenta.notes" outlined dense label="Notas" />
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat no-caps label="Cancelar" v-close-popup />
          <q-btn
            unelevated
            no-caps
            color="primary"
            label="Guardar cuenta"
            :loading="guardando"
            :disable="formCuenta.party_id == null"
            @click="guardarCuenta"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <!-- Diálogo: aplicar a planilla -->
    <q-dialog v-model="dlgAplicar">
      <q-card class="app-dialog">
        <q-card-section class="text-h6">Aplicar crédito del comisariato a planilla</q-card-section>
        <q-card-section class="app-form">
          <div class="text-caption text-muted">
            Toma los saldos de los empleados en el comisariato y los pone como deducción en la
            planilla indicada (y abona la CxC). Ejecutalo desde la EMPRESA de la planilla.
          </div>
          <q-input
            v-model.number="formAplicar.sheet_id"
            outlined
            dense
            type="number"
            min="1"
            label="ID de la planilla (Nómina → planilla) *"
          />
          <q-select
            v-model="formAplicar.comisariato_company_id"
            :options="opcionesEmpresa"
            label="Empresa comisariato *"
            outlined
            dense
            emit-value
            map-options
          />
          <q-input
            v-model="formAplicar.per_period_cap"
            outlined
            dense
            type="number"
            min="0"
            label="Tope de descuento por período C$ (opcional)"
          />
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat no-caps label="Cancelar" v-close-popup />
          <q-btn
            unelevated
            no-caps
            color="primary"
            label="Aplicar"
            :loading="guardando"
            :disable="!formAplicar.sheet_id || formAplicar.comisariato_company_id == null"
            @click="aplicarPlanilla"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>
  </q-page>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from 'vue';
import { useQuasar, type QTableColumn } from 'quasar';
import PageHeader from 'src/components/PageHeader.vue';
import { apiErrorMessage } from 'src/core/api';
import { useListado } from 'src/core/composables/useListado';
import { formatMoney } from 'src/core/format';
import PartySelect from 'src/features/parties/PartySelect.vue';
import {
  applyStoreCredit,
  listAccounts,
  SEGMENT_LABELS,
  upsertAccount,
  type CreditAccount,
  type CustomerSegment,
} from 'src/features/comisariato/comisariato.api';
import { useAclStore } from 'src/stores/acl.store';
import { useContextStore } from 'src/stores/context.store';

const $q = useQuasar();
const acl = useAclStore();
const ctx = useContextStore();

const filtroQ = ref('');
const filtroSegmento = ref<CustomerSegment | null>(null);

const { rows, loading, reload } = useListado<CreditAccount>(
  () => listAccounts({ q: filtroQ.value?.trim() ?? '', segment: filtroSegmento.value ?? '' }),
  { errorMessage: 'No se pudieron cargar las cuentas.' },
);

function puede(code: string): boolean {
  const companyId = ctx.activeCompanyId;
  return companyId ? acl.hasPermission(companyId, code) : false;
}

const opcionesSegmento = Object.entries(SEGMENT_LABELS).map(([value, label]) => ({ value, label }));
const opcionesEmpresa = computed(() =>
  acl.companies.map((c) => ({ value: Number(c.company_id), label: c.company_name })),
);

const columns: QTableColumn<CreditAccount>[] = [
  { name: 'party_display_name', label: 'Tercero', field: 'party_display_name', align: 'left', sortable: true },
  { name: 'segmento', label: 'Segmento', field: 'segment', align: 'left' },
  { name: 'limite', label: 'Límite', field: 'credit_limit', align: 'right' },
  { name: 'saldo', label: 'Saldo', field: 'outstanding', align: 'right' },
  { name: 'disponible', label: 'Disponible', field: 'available', align: 'right' },
  { name: 'estado', label: 'Estado', field: 'is_active', align: 'left' },
  { name: 'acciones', label: '', field: 'id', align: 'right' },
];

// --- Cuenta ---
const dlgCuenta = ref(false);
const guardando = ref(false);
const enEdicion = ref<CreditAccount | null>(null);
const formCuenta = reactive<{
  party_id: number | null;
  segment: CustomerSegment;
  sinTope: boolean;
  credit_limit: string;
  collecting_company_id: number | null;
  is_active: boolean;
  notes: string;
}>({
  party_id: null,
  segment: 'EMPLOYEE',
  sinTope: false,
  credit_limit: '0',
  collecting_company_id: null,
  is_active: true,
  notes: '',
});

function abrirCuenta(cuenta: CreditAccount | null) {
  enEdicion.value = cuenta;
  Object.assign(formCuenta, {
    party_id: cuenta?.party_id ?? null,
    segment: cuenta?.segment ?? 'EMPLOYEE',
    sinTope: cuenta ? cuenta.credit_limit == null : false,
    credit_limit: cuenta?.credit_limit ?? '0',
    collecting_company_id: cuenta?.collecting_company_id ?? null,
    is_active: cuenta?.is_active ?? true,
    notes: cuenta?.notes ?? '',
  });
  dlgCuenta.value = true;
}

async function guardarCuenta() {
  if (formCuenta.party_id == null) return;
  guardando.value = true;
  try {
    await upsertAccount({
      party_id: formCuenta.party_id,
      segment: formCuenta.segment,
      credit_limit: formCuenta.sinTope ? null : Number(formCuenta.credit_limit || 0).toFixed(2),
      collecting_company_id:
        formCuenta.segment === 'EMPLOYEE' ? formCuenta.collecting_company_id : null,
      is_active: formCuenta.is_active,
      ...(formCuenta.notes ? { notes: formCuenta.notes } : {}),
    });
    dlgCuenta.value = false;
    $q.notify({ type: 'positive', message: 'Cuenta guardada.' });
    await reload();
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo guardar la cuenta.') });
  } finally {
    guardando.value = false;
  }
}

// --- Aplicar a planilla ---
const dlgAplicar = ref(false);
const formAplicar = reactive<{
  sheet_id: number | null;
  comisariato_company_id: number | null;
  per_period_cap: string;
}>({ sheet_id: null, comisariato_company_id: null, per_period_cap: '' });

function abrirAplicar() {
  Object.assign(formAplicar, {
    sheet_id: null,
    comisariato_company_id: Number(ctx.activeCompanyId),
    per_period_cap: '',
  });
  dlgAplicar.value = true;
}

async function aplicarPlanilla() {
  if (!formAplicar.sheet_id || formAplicar.comisariato_company_id == null) return;
  guardando.value = true;
  try {
    await applyStoreCredit(formAplicar.sheet_id, {
      comisariato_company_id: formAplicar.comisariato_company_id,
      ...(formAplicar.per_period_cap
        ? { per_period_cap: Number(formAplicar.per_period_cap).toFixed(2) }
        : {}),
    });
    dlgAplicar.value = false;
    $q.notify({ type: 'positive', message: 'Descuentos aplicados a la planilla.' });
    await reload();
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo aplicar a planilla.') });
  } finally {
    guardando.value = false;
  }
}
</script>

<style scoped>
.com-filtros {
  display: flex;
  flex-wrap: wrap;
  gap: var(--app-space-3);
  margin-bottom: var(--app-space-4);
}

.com-filtros__buscar {
  width: 300px;
  max-width: 100%;
}

.com-filtros__sel {
  width: 260px;
}
</style>
