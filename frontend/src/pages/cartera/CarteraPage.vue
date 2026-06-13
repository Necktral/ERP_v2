<template>
  <q-page class="app-page">
    <PageHeader
      title="Cartera"
      subtitle="Cuentas por cobrar (lo que te deben) y por pagar (lo que debés), con su antigüedad. Los saldos nacen de facturación y compras."
      :loading="cargando"
      @refresh="recargar"
    >
      <template #actions>
        <q-btn
          v-if="puede('portfolio.credit.read')"
          flat
          no-caps
          icon="real_estate_agent"
          label="Créditos"
          to="/cartera/creditos"
        />
      </template>
    </PageHeader>

    <q-tabs
      v-model="tab"
      dense
      no-caps
      align="left"
      class="car-tabs"
      active-color="primary"
      indicator-color="primary"
    >
      <q-tab name="cxc" icon="call_received" label="Por cobrar (CxC)" />
      <q-tab v-if="puede('portfolio.payable.read')" name="cxp" icon="call_made" label="Por pagar (CxP)" />
      <q-tab
        v-if="puede('portfolio.payment.allocation.read')"
        name="aplicaciones"
        icon="rule"
        label="Aplicaciones"
      />
    </q-tabs>
    <q-separator class="q-mb-md" />

    <q-tab-panels v-model="tab" animated class="car-panels">
      <!-- ============ CxC ============ -->
      <q-tab-panel name="cxc" class="q-pa-none">
        <q-table
          class="app-table"
          :rows="cxc"
          :columns="columnasObligacion()"
          row-key="id"
          flat
          :loading="cargando"
          :pagination="{ rowsPerPage: 25 }"
          no-data-label="No hay cuentas por cobrar."
        >
          <template #body-cell-parte="props">
            <q-td :props="props">{{ nombreParte(props.row.party) }}</q-td>
          </template>
          <template #body-cell-saldo="props">
            <q-td :props="props" class="text-weight-bold">{{ formatMoney(props.row.outstanding_amount) }}</q-td>
          </template>
          <template #body-cell-vence="props">
            <q-td :props="props" :class="props.row.is_overdue ? 'text-negative' : ''">
              {{ formatDate(props.row.due_date) }}
              <span v-if="props.row.days_overdue > 0" class="text-caption">
                (+{{ props.row.days_overdue }} d)
              </span>
            </q-td>
          </template>
          <template #body-cell-aging="props">
            <q-td :props="props">{{ AGING_BUCKET_LABELS[props.row.aging_bucket] ?? props.row.aging_bucket }}</q-td>
          </template>
          <template #body-cell-estado="props">
            <q-td :props="props"><EstadoChip :estado="props.row.status" /></q-td>
          </template>
          <template #body-cell-acciones="props">
            <q-td :props="props" class="text-right car-acciones">
              <q-btn
                v-if="puede('portfolio.receivable.adjust')"
                flat
                dense
                no-caps
                size="sm"
                icon="tune"
                label="Ajustar"
                @click="abrirAjuste(props.row)"
              />
              <q-btn
                v-if="puede('portfolio.receivable.writeoff') && props.row.status !== 'WRITTEN_OFF'"
                flat
                dense
                no-caps
                size="sm"
                color="negative"
                icon="money_off"
                label="Castigar"
                @click="confirmarCastigo(props.row)"
              />
            </q-td>
          </template>
        </q-table>
      </q-tab-panel>

      <!-- ============ CxP ============ -->
      <q-tab-panel name="cxp" class="q-pa-none">
        <q-table
          class="app-table"
          :rows="cxp"
          :columns="columnasObligacion()"
          row-key="id"
          flat
          :loading="cargando"
          :pagination="{ rowsPerPage: 25 }"
          no-data-label="No hay cuentas por pagar."
        >
          <template #body-cell-parte="props">
            <q-td :props="props">{{ nombreParte(props.row.party) }}</q-td>
          </template>
          <template #body-cell-saldo="props">
            <q-td :props="props" class="text-weight-bold">{{ formatMoney(props.row.outstanding_amount) }}</q-td>
          </template>
          <template #body-cell-vence="props">
            <q-td :props="props" :class="props.row.is_overdue ? 'text-negative' : ''">
              {{ formatDate(props.row.due_date) }}
            </q-td>
          </template>
          <template #body-cell-aging="props">
            <q-td :props="props">{{ AGING_BUCKET_LABELS[props.row.aging_bucket] ?? props.row.aging_bucket }}</q-td>
          </template>
          <template #body-cell-estado="props">
            <q-td :props="props"><EstadoChip :estado="props.row.status" /></q-td>
          </template>
          <template #body-cell-acciones="props">
            <q-td :props="props" />
          </template>
        </q-table>
      </q-tab-panel>

      <!-- ============ Aplicaciones ============ -->
      <q-tab-panel name="aplicaciones" class="q-pa-none">
        <div class="text-caption text-muted q-mb-sm">
          Pagos aplicados a obligaciones (los generan caja, comisariato y planilla).
        </div>
        <q-table
          class="app-table"
          :rows="aplicaciones"
          :columns="columnasAplicacion"
          row-key="id"
          flat
          :loading="cargando"
          :pagination="{ rowsPerPage: 25 }"
          no-data-label="Sin aplicaciones de pago."
        >
          <template #body-cell-monto="props">
            <q-td :props="props">{{ formatMoney(props.row.allocated_amount) }}</q-td>
          </template>
          <template #body-cell-fecha="props">
            <q-td :props="props">{{ formatDate(props.row.allocation_date) }}</q-td>
          </template>
        </q-table>
      </q-tab-panel>
    </q-tab-panels>

    <!-- Diálogo: ajustar CxC -->
    <q-dialog v-model="dlgAjuste">
      <q-card class="app-dialog">
        <q-card-section class="text-h6">Ajustar cuenta por cobrar</q-card-section>
        <q-card-section class="app-form">
          <div class="text-caption text-muted">
            {{ objetivo ? `${nombreParte(objetivo.party)} · saldo ${formatMoney(objetivo.outstanding_amount)}` : '' }}
          </div>
          <q-input
            v-model="formAjuste.monto"
            outlined
            dense
            type="number"
            label="Monto del ajuste C$ * (negativo = rebaja)"
          />
          <q-input v-model="formAjuste.motivo" outlined dense label="Motivo *" />
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat no-caps label="Cancelar" v-close-popup />
          <q-btn
            unelevated
            no-caps
            color="primary"
            label="Aplicar ajuste"
            :loading="accionando"
            :disable="!formAjuste.monto || !formAjuste.motivo.trim()"
            @click="aplicarAjuste"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>
  </q-page>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue';
import { useQuasar, type QTableColumn } from 'quasar';
import PageHeader from 'src/components/PageHeader.vue';
import EstadoChip from 'src/components/EstadoChip.vue';
import { apiErrorMessage } from 'src/core/api';
import { formatDate, formatMoney } from 'src/core/format';
import { listParties } from 'src/features/parties/parties.api';
import {
  adjustReceivable,
  AGING_BUCKET_LABELS,
  listAllocations,
  listPayables,
  listReceivables,
  writeoffReceivable,
  type AllocationRow,
  type Payable,
  type Receivable,
} from 'src/features/portfolio/portfolio.api';
import { useAclStore } from 'src/stores/acl.store';
import { useContextStore } from 'src/stores/context.store';

const $q = useQuasar();
const acl = useAclStore();
const ctx = useContextStore();

const tab = ref('cxc');
const cargando = ref(false);
const accionando = ref(false);

const cxc = ref<Receivable[]>([]);
const cxp = ref<Payable[]>([]);
const aplicaciones = ref<AllocationRow[]>([]);
const nombresParte = ref(new Map<number, string>());

function puede(code: string): boolean {
  const companyId = ctx.activeCompanyId;
  return companyId ? acl.hasPermission(companyId, code) : false;
}

function nombreParte(partyId: number): string {
  return nombresParte.value.get(partyId) ?? `Tercero #${partyId}`;
}

function columnasObligacion(): QTableColumn<Receivable | Payable>[] {
  return [
    { name: 'parte', label: 'Tercero', field: 'party', align: 'left' },
    { name: 'referencia', label: 'Referencia', field: 'reference_type', align: 'left' },
    { name: 'total', label: 'Total', field: (r) => formatMoney(r.total_amount), align: 'right' },
    { name: 'saldo', label: 'Saldo', field: 'outstanding_amount', align: 'right' },
    { name: 'vence', label: 'Vence', field: 'due_date', align: 'left' },
    { name: 'aging', label: 'Antigüedad', field: 'aging_bucket', align: 'left' },
    { name: 'estado', label: 'Estado', field: 'status', align: 'left' },
    { name: 'acciones', label: '', field: 'id', align: 'right' },
  ];
}

const columnasAplicacion: QTableColumn<AllocationRow>[] = [
  { name: 'allocation_id', label: 'Aplicación', field: 'allocation_id', align: 'left' },
  { name: 'monto', label: 'Monto', field: 'allocated_amount', align: 'right' },
  { name: 'fecha', label: 'Fecha', field: 'allocation_date', align: 'left' },
  { name: 'status', label: 'Estado', field: 'status', align: 'left' },
];

async function recargar() {
  cargando.value = true;
  try {
    const tareas: Promise<void>[] = [
      listReceivables().then((r) => {
        cxc.value = r;
      }),
      listParties().then((ps) => {
        nombresParte.value = new Map(ps.map((p) => [p.id, p.display_name]));
      }),
    ];
    if (puede('portfolio.payable.read')) {
      tareas.push(
        listPayables().then((r) => {
          cxp.value = r;
        }),
      );
    }
    if (puede('portfolio.payment.allocation.read')) {
      tareas.push(
        listAllocations().then((r) => {
          aplicaciones.value = r;
        }),
      );
    }
    await Promise.all(tareas);
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo cargar la cartera.') });
  } finally {
    cargando.value = false;
  }
}

// --- Ajuste / castigo ---
const dlgAjuste = ref(false);
const objetivo = ref<Receivable | null>(null);
const formAjuste = reactive({ monto: '', motivo: '' });

function abrirAjuste(r: Receivable) {
  objetivo.value = r;
  Object.assign(formAjuste, { monto: '', motivo: '' });
  dlgAjuste.value = true;
}

async function aplicarAjuste() {
  if (!objetivo.value) return;
  accionando.value = true;
  try {
    await adjustReceivable(objetivo.value.id, {
      adjustment_amount: Number(formAjuste.monto).toFixed(2),
      reason: formAjuste.motivo.trim(),
    });
    dlgAjuste.value = false;
    $q.notify({ type: 'positive', message: 'Ajuste aplicado.' });
    await recargar();
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo ajustar.') });
  } finally {
    accionando.value = false;
  }
}

function confirmarCastigo(r: Receivable) {
  $q.dialog({
    title: 'Castigar cuenta',
    message: `Castigar la deuda de ${nombreParte(r.party)} por ${formatMoney(
      r.outstanding_amount,
    )} la saca de cobranza (irreversible). Motivo:`,
    prompt: { model: '', type: 'text', isValid: (v: string) => v.trim().length >= 5 },
    cancel: { flat: true, noCaps: true, label: 'Cancelar' },
    ok: { unelevated: true, noCaps: true, color: 'negative', label: 'Castigar' },
    persistent: true,
  }).onOk((motivo: string) => {
    void (async () => {
      try {
        await writeoffReceivable(r.id, motivo.trim());
        $q.notify({ type: 'positive', message: 'Cuenta castigada.' });
        await recargar();
      } catch (e) {
        $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo castigar.') });
      }
    })();
  });
}

onMounted(recargar);
</script>

<style scoped>
.car-tabs {
  color: var(--app-text-muted);
}

.car-panels {
  background: transparent;
}

.car-acciones {
  white-space: nowrap;
}
</style>
