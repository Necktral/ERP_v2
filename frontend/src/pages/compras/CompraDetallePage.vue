<template>
  <q-page class="app-page">
    <PageHeader
      :title="titulo"
      :subtitle="doc ? PURCHASE_DOC_TYPE_LABELS[doc.doc_type] : ''"
      :loading="loading"
      @refresh="cargar"
    >
      <template #actions>
        <q-btn flat round dense icon="arrow_back" aria-label="Volver" to="/compras" />
        <q-btn
          v-if="doc?.status === 'DRAFT' && puede('procurement.doc.post')"
          unelevated
          no-caps
          color="primary"
          icon="task_alt"
          label="Postear"
          :loading="accionando"
          @click="confirmarPostear"
        />
        <q-btn
          v-if="doc?.status === 'POSTED' && puede('procurement.doc.void')"
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

    <div v-if="doc" class="cmpd-grid">
      <div class="cmpd-card">
        <div class="cmpd-card__title">
          Documento
          <EstadoChip :estado="doc.status" />
        </div>
        <dl class="cmpd-dl">
          <dt>Número</dt>
          <dd>{{ doc.number > 0 ? `${doc.series}-${doc.number}` : 'Sin número (borrador)' }}</dd>
          <dt>Tipo</dt>
          <dd>{{ PURCHASE_DOC_TYPE_LABELS[doc.doc_type] }}</dd>
          <dt>Moneda</dt>
          <dd>{{ doc.currency }}</dd>
          <dt>Posteado</dt>
          <dd>{{ formatDateTime(doc.posted_at) }}</dd>
          <dt v-if="doc.voided_at">Anulado</dt>
          <dd v-if="doc.voided_at">{{ formatDateTime(doc.voided_at) }} — {{ doc.void_reason }}</dd>
        </dl>
      </div>

      <div class="cmpd-card">
        <div class="cmpd-card__title">Proveedor</div>
        <dl class="cmpd-dl">
          <dt>Nombre</dt>
          <dd>{{ doc.supplier_party_display_name || doc.supplier_name || '—' }}</dd>
          <dt>Referencia</dt>
          <dd>{{ doc.supplier_ref || '—' }}</dd>
          <dt>Ref. externa</dt>
          <dd>{{ doc.external_ref || '—' }}</dd>
        </dl>
      </div>

      <div class="cmpd-card">
        <div class="cmpd-card__title">Montos</div>
        <dl class="cmpd-dl">
          <dt>Subtotal</dt>
          <dd>{{ formatMoney(doc.subtotal) }}</dd>
          <dt>Impuesto</dt>
          <dd>{{ formatMoney(doc.tax_total) }}</dd>
          <dt class="cmpd-total">Total</dt>
          <dd class="cmpd-total">{{ formatMoney(doc.total) }}</dd>
        </dl>
      </div>

      <div v-if="doc.notes" class="cmpd-card cmpd-card--ancho">
        <div class="cmpd-card__title">Notas</div>
        <p class="text-muted">{{ doc.notes }}</p>
      </div>
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useRoute } from 'vue-router';
import { useQuasar } from 'quasar';
import PageHeader from 'src/components/PageHeader.vue';
import EstadoChip from 'src/components/EstadoChip.vue';
import { apiErrorMessage } from 'src/core/api';
import { formatDateTime, formatMoney } from 'src/core/format';
import {
  getPurchaseDoc,
  postPurchaseDoc,
  PURCHASE_DOC_TYPE_LABELS,
  voidPurchaseDoc,
  type PurchaseDoc,
} from 'src/features/procurement/procurement.api';
import { useAclStore } from 'src/stores/acl.store';
import { useContextStore } from 'src/stores/context.store';

const $q = useQuasar();
const route = useRoute();
const acl = useAclStore();
const ctx = useContextStore();

const docId = Number(route.params.id);
const doc = ref<PurchaseDoc | null>(null);
const loading = ref(false);
const accionando = ref(false);

const titulo = computed(() =>
  doc.value
    ? doc.value.number > 0
      ? `Compra ${doc.value.series}-${doc.value.number}`
      : `Compra (borrador #${doc.value.id})`
    : 'Compra',
);

function puede(code: string): boolean {
  const companyId = ctx.activeCompanyId;
  return companyId ? acl.hasPermission(companyId, code) : false;
}

async function cargar() {
  loading.value = true;
  try {
    doc.value = await getPurchaseDoc(docId);
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo cargar el documento.') });
  } finally {
    loading.value = false;
  }
}

function confirmarPostear() {
  $q.dialog({
    title: 'Postear documento',
    message:
      'Al postear, el documento toma número y queda en firme (alimenta la cuenta por pagar). ¿Continuar?',
    cancel: { flat: true, noCaps: true, label: 'Cancelar' },
    ok: { unelevated: true, noCaps: true, color: 'primary', label: 'Postear' },
  }).onOk(() => {
    void ejecutarPostear();
  });
}

async function ejecutarPostear() {
  accionando.value = true;
  try {
    const r = await postPurchaseDoc(docId);
    $q.notify({ type: 'positive', message: `Documento posteado con número ${r.number}.` });
    await cargar();
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo postear.') });
  } finally {
    accionando.value = false;
  }
}

function confirmarAnular() {
  $q.dialog({
    title: 'Anular documento',
    message: 'Motivo de la anulación:',
    prompt: { model: '', type: 'text', isValid: (v: string) => v.trim().length >= 3 },
    cancel: { flat: true, noCaps: true, label: 'Cancelar' },
    ok: { unelevated: true, noCaps: true, color: 'negative', label: 'Anular' },
    persistent: true,
  }).onOk((motivo: string) => {
    void ejecutarAnular(motivo.trim());
  });
}

async function ejecutarAnular(motivo: string) {
  accionando.value = true;
  try {
    await voidPurchaseDoc(docId, motivo);
    $q.notify({ type: 'positive', message: 'Documento anulado.' });
    await cargar();
  } catch (e) {
    $q.notify({ type: 'negative', message: apiErrorMessage(e, 'No se pudo anular.') });
  } finally {
    accionando.value = false;
  }
}

onMounted(cargar);
</script>

<style scoped>
.cmpd-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: var(--app-space-4);
}

.cmpd-card {
  padding: var(--app-space-4);
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-lg);
  background: var(--app-surface);
}

.cmpd-card--ancho {
  grid-column: 1 / -1;
}

.cmpd-card__title {
  display: flex;
  align-items: center;
  gap: var(--app-space-2);
  font-weight: 800;
  color: var(--app-text);
  margin-bottom: var(--app-space-3);
}

.cmpd-dl {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: var(--app-space-1) var(--app-space-4);
  margin: 0;
}

.cmpd-dl dt {
  color: var(--app-text-muted);
  font-size: 0.82rem;
}

.cmpd-dl dd {
  margin: 0;
  color: var(--app-text);
  font-size: 0.88rem;
}

.cmpd-total {
  font-weight: 800;
}
</style>
