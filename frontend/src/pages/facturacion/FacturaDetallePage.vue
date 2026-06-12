<template>
  <q-page class="app-page">
    <PageHeader :title="titulo" :subtitle="subtitulo" :loading="loading" @refresh="cargar">
      <template #actions>
        <q-btn flat round dense icon="arrow_back" aria-label="Volver" to="/facturacion" />
        <q-btn
          v-if="doc?.status === 'DRAFT' && puede('billing.doc.issue')"
          unelevated
          no-caps
          color="primary"
          icon="task_alt"
          label="Emitir"
          :loading="accionando"
          @click="abrirEmitir"
        />
        <q-btn
          v-if="doc?.status === 'ISSUED' && doc.is_fiscal && puede('billing.doc.print')"
          outline
          no-caps
          color="primary"
          icon="print"
          label="Imprimir"
          :loading="accionando"
          @click="imprimir"
        />
        <q-btn
          v-if="doc?.status === 'ISSUED' && puede('billing.doc.void')"
          outline
          no-caps
          color="negative"
          icon="block"
          label="Anular"
          :loading="accionando"
          @click="confirmarAnular"
        />
      </template>
    </PageHeader>

    <div v-if="doc" class="facd-grid">
      <div class="facd-card">
        <div class="facd-card__title">
          Documento
          <EstadoChip :estado="doc.status" />
        </div>
        <dl class="facd-dl">
          <dt>Número</dt>
          <dd>{{ doc.number > 0 ? `${doc.series}-${doc.number}` : 'Sin número (borrador)' }}</dd>
          <dt>Tipo</dt>
          <dd>{{ BILLING_DOC_TYPE_LABELS[doc.doc_type] }}</dd>
          <dt>Método de pago</dt>
          <dd>{{ PAYMENT_METHOD_LABELS[doc.payment_method] ?? doc.payment_method ?? '—' }}</dd>
          <dt>Emitido</dt>
          <dd>{{ formatDateTime(doc.issued_at) }}</dd>
          <dt v-if="doc.voided_at">Anulado</dt>
          <dd v-if="doc.voided_at">{{ formatDateTime(doc.voided_at) }} — {{ doc.void_reason }}</dd>
        </dl>
      </div>

      <div class="facd-card">
        <div class="facd-card__title">Cliente</div>
        <dl class="facd-dl">
          <dt>Nombre</dt>
          <dd>{{ doc.customer_party_display_name || doc.customer_name || '—' }}</dd>
          <dt>Referencia</dt>
          <dd>{{ doc.customer_ref || '—' }}</dd>
        </dl>
      </div>

      <div v-if="doc.is_fiscal" class="facd-card">
        <div class="facd-card__title">
          Fiscal
          <EstadoChip v-if="doc.fiscal?.status" :estado="doc.fiscal.status" :map="MAPA_FISCAL" />
        </div>
        <dl class="facd-dl">
          <dt>Referencia</dt>
          <dd>{{ doc.fiscal?.reference || '—' }}</dd>
          <dt>Impreso</dt>
          <dd>{{ formatDateTime(doc.fiscal?.printed_at) }}</dd>
          <dt>Intentos</dt>
          <dd>{{ doc.fiscal?.attempts ?? 0 }}</dd>
          <dt v-if="doc.fiscal?.last_error">Último error</dt>
          <dd v-if="doc.fiscal?.last_error" class="text-negative">{{ doc.fiscal.last_error }}</dd>
          <dt v-if="doc.fiscal?.contingency_reason">Contingencia</dt>
          <dd v-if="doc.fiscal?.contingency_reason">{{ doc.fiscal.contingency_reason }}</dd>
        </dl>
        <div class="q-mt-sm" v-if="doc.status === 'ISSUED'">
          <q-btn
            v-if="doc.fiscal?.status !== 'CONTINGENCY' && puede('billing.doc.contingency')"
            flat
            dense
            no-caps
            size="sm"
            icon="warning"
            color="warning"
            label="Marcar contingencia"
            @click="marcarContingencia"
          />
          <template v-if="doc.fiscal?.status === 'CONTINGENCY' && puede('billing.doc.contingency.resolve')">
            <q-btn
              flat
              dense
              no-caps
              size="sm"
              icon="refresh"
              color="primary"
              label="Reintentar impresión"
              @click="resolverContingencia('RETRY_PRINT')"
            />
            <q-btn
              flat
              dense
              no-caps
              size="sm"
              icon="block"
              color="negative"
              label="Anular por contingencia"
              @click="resolverContingencia('VOID')"
            />
          </template>
        </div>
      </div>

      <div class="facd-card facd-card--ancho">
        <div class="facd-card__title">Líneas</div>
        <q-markup-table flat dense class="facd-lineas">
          <thead>
            <tr>
              <th class="text-left">Descripción</th>
              <th class="text-right">Cantidad</th>
              <th class="text-right">Precio</th>
              <th class="text-right">IVA</th>
              <th class="text-right">Total</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="l in doc.lines" :key="l.id">
              <td class="text-left">{{ l.description }}</td>
              <td class="text-right">{{ formatQty(l.quantity) }}</td>
              <td class="text-right">{{ formatMoney(l.unit_price) }}</td>
              <td class="text-right">{{ formatMoney(l.line_tax) }}</td>
              <td class="text-right">{{ formatMoney(l.line_total) }}</td>
            </tr>
          </tbody>
          <tfoot>
            <tr>
              <td colspan="3"></td>
              <td class="text-right text-muted">Subtotal</td>
              <td class="text-right">{{ formatMoney(doc.subtotal) }}</td>
            </tr>
            <tr>
              <td colspan="3"></td>
              <td class="text-right text-muted">IVA</td>
              <td class="text-right">{{ formatMoney(doc.tax_total) }}</td>
            </tr>
            <tr>
              <td colspan="3"></td>
              <td class="text-right text-weight-bold">Total</td>
              <td class="text-right text-weight-bold">{{ formatMoney(doc.total) }}</td>
            </tr>
          </tfoot>
        </q-markup-table>
      </div>
    </div>

    <!-- Diálogo: emitir -->
    <q-dialog v-model="dlgEmitir">
      <q-card class="app-dialog">
        <q-card-section class="text-h6">Emitir documento</q-card-section>
        <q-card-section class="app-form">
          <div class="text-caption text-muted">
            Al emitir, el documento toma número{{ doc?.is_fiscal ? ' fiscal' : '' }} y queda en firme.
          </div>
          <q-toggle
            v-model="emitirForm.apply_inventory"
            label="Bajar inventario (líneas con artículo)"
            color="primary"
          />
          <q-select
            v-if="emitirForm.apply_inventory"
            v-model="emitirForm.warehouse_id"
            :options="opcionesBodega"
            label="Bodega de despacho *"
            outlined
            dense
            emit-value
            map-options
          />
          <q-toggle
            v-if="doc?.is_fiscal"
            v-model="emitirForm.print_after_issue"
            label="Imprimir al emitir"
            color="primary"
          />
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat no-caps label="Cancelar" v-close-popup />
          <q-btn
            unelevated
            no-caps
            color="primary"
            label="Emitir"
            :loading="accionando"
            :disable="emitirForm.apply_inventory && emitirForm.warehouse_id == null"
            @click="emitir"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>
  </q-page>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import { useRoute } from 'vue-router';
import { useQuasar } from 'quasar';
import PageHeader from 'src/components/PageHeader.vue';
import EstadoChip, { type EstadoEstilo } from 'src/components/EstadoChip.vue';
import { apiErrorMessage } from 'src/core/api';
import { formatDateTime, formatMoney, formatQty } from 'src/core/format';
import {
  BILLING_DOC_TYPE_LABELS,
  FISCAL_STATUS_LABELS,
  getBillingDoc,
  issueBillingDoc,
  PAYMENT_METHOD_LABELS,
  printBillingDoc,
  resolveBillingContingency,
  setBillingContingency,
  voidBillingDoc,
  type BillingDoc,
} from 'src/features/billing/billing.api';
import { listWarehouses, type Warehouse } from 'src/features/inventory/inventory.api';
import { useAclStore } from 'src/stores/acl.store';
import { useContextStore } from 'src/stores/context.store';

const $q = useQuasar();
const route = useRoute();
const acl = useAclStore();
const ctx = useContextStore();

const MAPA_FISCAL: Record<string, EstadoEstilo> = Object.fromEntries(
  Object.entries(FISCAL_STATUS_LABELS).map(([code, label]) => [
    code,
    {
      label,
      color: code === 'PRINTED' || code === 'ISSUED' ? 'secondary' : code === 'NUMBER_RESERVED' ? 'grey-7' : 'warning',
      outline: true,
    },
  ]),
);

const docId = Number(route.params.id);
const doc = ref<BillingDoc | null>(null);
const loading = ref(false);
const accionando = ref(false);
const bodegas = ref<Warehouse[]>([]);

const titulo = computed(() =>
  doc.value
    ? doc.value.number > 0
      ? `${BILLING_DOC_TYPE_LABELS[doc.value.doc_type]} ${doc.value.series}-${doc.value.number}`
      : `${BILLING_DOC_TYPE_LABELS[doc.value.doc_type]} (borrador #${doc.value.id})`
    : 'Documento',
);
const subtitulo = computed(() =>
  doc.value ? `${doc.value.customer_party_display_name || doc.value.customer_name || 'Sin cliente'} · ${formatMoney(doc.value.total)}` : '',
);

function puede(code: string): boolean {
  const companyId = ctx.activeCompanyId;
  return companyId ? acl.hasPermission(companyId, code) : false;
}

const opcionesBodega = computed(() => bodegas.value.map((w) => ({ value: w.id, label: w.name })));

async function cargar() {
  loading.value = true;
  try {
    doc.value = await getBillingDoc(docId);
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo cargar el documento.') });
  } finally {
    loading.value = false;
  }
}

// --- Emitir ---
const dlgEmitir = ref(false);
const emitirForm = reactive<{
  apply_inventory: boolean;
  warehouse_id: number | null;
  print_after_issue: boolean;
}>({ apply_inventory: false, warehouse_id: null, print_after_issue: false });

async function abrirEmitir() {
  if (bodegas.value.length === 0) {
    try {
      bodegas.value = await listWarehouses();
    } catch {
      /* sin bodegas: emitir sin inventario */
    }
  }
  Object.assign(emitirForm, { apply_inventory: false, warehouse_id: null, print_after_issue: false });
  dlgEmitir.value = true;
}

async function emitir() {
  accionando.value = true;
  try {
    const r = await issueBillingDoc(docId, {
      apply_inventory: emitirForm.apply_inventory,
      ...(emitirForm.warehouse_id != null ? { warehouse_id: emitirForm.warehouse_id } : {}),
      print_after_issue: emitirForm.print_after_issue,
    });
    dlgEmitir.value = false;
    $q.notify({ type: 'positive', message: `Documento emitido${r.number ? ` con número ${r.number}` : ''}.` });
    await cargar();
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo emitir.') });
  } finally {
    accionando.value = false;
  }
}

async function imprimir() {
  accionando.value = true;
  try {
    await printBillingDoc(docId);
    $q.notify({ type: 'positive', message: 'Impresión encolada.' });
    await cargar();
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo imprimir.') });
  } finally {
    accionando.value = false;
  }
}

function confirmarAnular() {
  $q.dialog({
    title: 'Anular documento',
    message:
      'La anulación es un control sensible (puede requerir aprobación de otra persona). Motivo:',
    prompt: { model: '', type: 'text', isValid: (v: string) => v.trim().length >= 3 },
    cancel: { flat: true, noCaps: true, label: 'Cancelar' },
    ok: { unelevated: true, noCaps: true, color: 'negative', label: 'Anular' },
    persistent: true,
  }).onOk((motivo: string) => {
    void anular(motivo.trim());
  });
}

async function anular(motivo: string) {
  accionando.value = true;
  try {
    await voidBillingDoc(docId, motivo);
    $q.notify({ type: 'positive', message: 'Anulación registrada.' });
    await cargar();
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo anular.') });
  } finally {
    accionando.value = false;
  }
}

function marcarContingencia() {
  $q.dialog({
    title: 'Marcar contingencia',
    message: 'Motivo (ej. impresora fiscal sin papel / sin energía):',
    prompt: { model: '', type: 'text', isValid: (v: string) => v.trim().length >= 3 },
    cancel: { flat: true, noCaps: true, label: 'Cancelar' },
    ok: { unelevated: true, noCaps: true, color: 'warning', label: 'Marcar' },
  }).onOk((motivo: string) => {
    void (async () => {
      try {
        await setBillingContingency(docId, motivo.trim());
        $q.notify({ type: 'warning', message: 'Documento en contingencia.' });
        await cargar();
      } catch (e) {
        $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo marcar.') });
      }
    })();
  });
}

async function resolverContingencia(action: 'RETRY_PRINT' | 'VOID') {
  accionando.value = true;
  try {
    await resolveBillingContingency(docId, action);
    $q.notify({ type: 'positive', message: action === 'RETRY_PRINT' ? 'Reintento encolado.' : 'Anulado por contingencia.' });
    await cargar();
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo resolver la contingencia.') });
  } finally {
    accionando.value = false;
  }
}

onMounted(cargar);
</script>

<style scoped>
.facd-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: var(--app-space-4);
}

.facd-card {
  padding: var(--app-space-4);
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-lg);
  background: var(--app-surface);
}

.facd-card--ancho {
  grid-column: 1 / -1;
}

.facd-card__title {
  display: flex;
  align-items: center;
  gap: var(--app-space-2);
  font-weight: 800;
  color: var(--app-text);
  margin-bottom: var(--app-space-3);
}

.facd-dl {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: var(--app-space-1) var(--app-space-4);
  margin: 0;
}

.facd-dl dt {
  color: var(--app-text-muted);
  font-size: 0.82rem;
}

.facd-dl dd {
  margin: 0;
  color: var(--app-text);
  font-size: 0.88rem;
}

.facd-lineas {
  background: transparent;
}
</style>
