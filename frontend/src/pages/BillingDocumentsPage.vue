<template>
  <AppContainer fluid>
    <AppPageHeader
      :title="`${labels.billing} · Documentos`"
      subtitle="API: GET/POST /billing/docs/ · POST /billing/docs/{id}/issue/ · POST /billing/docs/{id}/void/"
    >
      <template #badges>
        <q-badge outline color="primary">Empresa activa: {{ companyLabel }}</q-badge>
        <q-badge outline>Permiso lectura: billing.doc.read</q-badge>
        <q-badge outline v-if="canCreate">Permiso creación: billing.doc.create</q-badge>
        <q-badge outline>Total: {{ totalRows }}</q-badge>
      </template>

      <template #actions>
        <q-btn flat label="Recargar" :disable="loadingList" @click="reload" />
        <q-btn color="primary" label="Nuevo documento" :disable="!canCreate" @click="openCreateDialog" />
      </template>
    </AppPageHeader>

    <div class="q-mt-md">
      <q-card class="app-card q-mb-md">
        <q-card-section>
          <div class="row q-col-gutter-md items-end">
            <div class="col-12 col-md-3">
              <q-input v-model="filters.q" dense outlined label="Buscar" placeholder="Cliente, ref, serie o número" />
            </div>
            <div class="col-12 col-md-2">
              <q-select
                v-model="filters.status"
                dense
                outlined
                emit-value
                map-options
                :options="statusOptions"
                label="Estado"
                clearable
              />
            </div>
            <div class="col-12 col-md-2">
              <q-select
                v-model="filters.doc_type"
                dense
                outlined
                emit-value
                map-options
                :options="docTypeOptions"
                label="Tipo"
                clearable
              />
            </div>
            <div class="col-12 col-md-2">
              <q-input v-model="filters.date_from" dense outlined type="date" label="Fecha desde" />
            </div>
            <div class="col-12 col-md-2">
              <q-input v-model="filters.date_to" dense outlined type="date" label="Fecha hasta" />
            </div>
            <div class="col-12 col-md-1">
              <q-select
                v-model="filters.ordering"
                dense
                outlined
                emit-value
                map-options
                :options="orderingOptions"
                label="Orden"
              />
            </div>
            <div class="col-12 row q-gutter-sm">
              <q-btn color="primary" label="Aplicar filtros" :loading="loadingList" @click="applyFilters" />
              <q-btn flat label="Limpiar" :disable="loadingList" @click="clearFilters" />
            </div>
          </div>
        </q-card-section>
      </q-card>

      <AppDataTable
        title="Listado de documentos"
        caption="Vista operativa con filtros avanzados, detalle y acciones transaccionales controladas por permiso y estado."
        :rows="rows"
        :columns="columns"
        row-key="id"
        :loading="loadingList"
        :rows-per-page-options="[10, 20, 50, 0]"
        :pagination="pagination"
        @request="onRequest"
      >
        <template #body-cell-status="props">
          <q-td :props="props">
            <q-badge :color="statusColor(props.row.status)" outline>{{ props.row.status }}</q-badge>
          </q-td>
        </template>

        <template #body-cell-created_at="props">
          <q-td :props="props">{{ formatDate(props.row.created_at) }}</q-td>
        </template>

        <template #body-cell-total="props">
          <q-td :props="props">{{ money(props.row.total, props.row.currency) }}</q-td>
        </template>

        <template #body-cell-actions="props">
          <q-td :props="props" class="text-right">
            <q-btn dense flat icon="visibility" title="Ver detalle" @click="openDetail(props.row.id)" />
            <q-btn
              dense
              flat
              icon="send"
              color="primary"
              title="Emitir"
              :disable="!canIssue(props.row)"
              :loading="isActionLoading(props.row.id, 'issue')"
              @click="openIssueDialog(props.row)"
            />
            <q-btn
              dense
              flat
              icon="cancel"
              color="negative"
              title="Anular"
              :disable="!canVoid(props.row)"
              :loading="isActionLoading(props.row.id, 'void')"
              @click="openVoidDialog(props.row)"
            />
          </q-td>
        </template>
      </AppDataTable>

      <q-banner v-if="listError" class="q-mt-md bg-red-1 text-red-10" rounded>
        {{ listError }}
      </q-banner>

      <q-banner
        v-if="!loadingList && rows.length === 0 && !listError"
        class="q-mt-md bg-grey-2 text-grey-9"
        rounded
      >
        No hay documentos para los filtros aplicados.
      </q-banner>

      <q-card v-if="selectedDetail" class="app-card q-mt-md">
        <q-card-section class="row items-center justify-between">
          <div>
            <div class="text-subtitle1">Detalle del documento #{{ selectedDetail.id }}</div>
            <div class="text-caption text-grey-7">
              {{ selectedDetail.doc_type }} · {{ selectedDetail.status }} · {{ formatDate(selectedDetail.created_at) }}
            </div>
          </div>
          <q-btn flat label="Cerrar" @click="selectedDetail = null" />
        </q-card-section>
        <q-separator />
        <q-card-section>
          <div class="row q-col-gutter-md">
            <div class="col-12 col-md-6">
              <q-list dense bordered>
                <q-item><q-item-section>Cliente: {{ selectedDetail.customer_name || '—' }}</q-item-section></q-item>
                <q-item><q-item-section>Referencia: {{ selectedDetail.customer_ref || '—' }}</q-item-section></q-item>
                <q-item><q-item-section>Serie/Número: {{ selectedDetail.series }}-{{ selectedDetail.number }}</q-item-section></q-item>
                <q-item><q-item-section>Moneda: {{ selectedDetail.currency }}</q-item-section></q-item>
                <q-item><q-item-section>Total: {{ money(selectedDetail.total, selectedDetail.currency) }}</q-item-section></q-item>
              </q-list>
            </div>
            <div class="col-12 col-md-6">
              <q-list dense bordered>
                <q-item><q-item-section>Fiscal estado: {{ selectedDetail.fiscal?.status || '—' }}</q-item-section></q-item>
                <q-item><q-item-section>Fiscal referencia: {{ selectedDetail.fiscal?.reference || '—' }}</q-item-section></q-item>
                <q-item><q-item-section>Accounting status: {{ selectedDetail.accounting?.status || '—' }}</q-item-section></q-item>
                <q-item><q-item-section>Issued: {{ formatDate(selectedDetail.issued_at) }}</q-item-section></q-item>
                <q-item><q-item-section>Voided: {{ formatDate(selectedDetail.voided_at) }}</q-item-section></q-item>
              </q-list>
            </div>
          </div>

          <q-markup-table dense flat class="q-mt-md">
            <thead>
              <tr>
                <th class="text-left">Descripción</th>
                <th class="text-right">Cantidad</th>
                <th class="text-right">Precio</th>
                <th class="text-right">Impuesto</th>
                <th class="text-right">Total línea</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="line in selectedDetail.lines" :key="line.id">
                <td>{{ line.description }}</td>
                <td class="text-right">{{ line.quantity }}</td>
                <td class="text-right">{{ line.unit_price }}</td>
                <td class="text-right">{{ line.tax_rate }}</td>
                <td class="text-right">{{ line.line_total }}</td>
              </tr>
            </tbody>
          </q-markup-table>
        </q-card-section>
      </q-card>
    </div>

    <q-dialog v-model="createDialog">
      <q-card style="width: 980px; max-width: 98vw" class="app-card">
        <q-card-section class="row items-center justify-between">
          <div class="text-h6">Nuevo documento de facturación</div>
          <q-btn flat icon="close" v-close-popup />
        </q-card-section>
        <q-separator />
        <q-card-section>
          <q-form @submit.prevent="createDocument">
            <div class="row q-col-gutter-md">
              <div class="col-12 col-md-3">
                <q-select
                  v-model="createForm.doc_type"
                  dense
                  outlined
                  emit-value
                  map-options
                  :options="docTypeOptions"
                  label="Tipo documento"
                />
              </div>
              <div class="col-12 col-md-2">
                <q-input v-model="createForm.series" dense outlined label="Serie" />
              </div>
              <div class="col-12 col-md-2">
                <q-input v-model="createForm.currency" dense outlined label="Moneda" />
              </div>
              <div class="col-12 col-md-3">
                <q-input v-model="createForm.customer_name" dense outlined label="Cliente" />
              </div>
              <div class="col-12 col-md-2">
                <q-input v-model="createForm.customer_ref" dense outlined label="Referencia" />
              </div>
              <div class="col-12">
                <q-toggle v-model="createForm.is_fiscal" label="Documento fiscal" />
              </div>
            </div>

            <div class="row items-center justify-between q-mt-md q-mb-sm">
              <div class="text-subtitle2">Líneas</div>
              <q-btn flat icon="add" label="Agregar línea" @click="appendLine" />
            </div>

            <q-markup-table dense flat bordered>
              <thead>
                <tr>
                  <th class="text-left">Descripción</th>
                  <th class="text-right">Cantidad</th>
                  <th class="text-right">Precio unitario</th>
                  <th class="text-right">Impuesto</th>
                  <th class="text-right">Acción</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(line, idx) in createForm.lines" :key="line.key">
                  <td>
                    <q-input v-model="line.description" dense outlined placeholder="Descripción" />
                  </td>
                  <td>
                    <q-input v-model="line.quantity" dense outlined type="number" min="0.0001" step="0.0001" />
                  </td>
                  <td>
                    <q-input
                      v-model="line.unit_price"
                      dense
                      outlined
                      type="number"
                      min="0"
                      step="0.000001"
                    />
                  </td>
                  <td>
                    <q-input
                      v-model="line.tax_rate"
                      dense
                      outlined
                      type="number"
                      min="0"
                      step="0.0001"
                    />
                  </td>
                  <td class="text-right">
                    <q-btn flat dense color="negative" icon="delete" :disable="createForm.lines.length <= 1" @click="removeLine(idx)" />
                  </td>
                </tr>
              </tbody>
            </q-markup-table>

            <q-banner v-if="createError" class="q-mt-md bg-red-1 text-red-10" rounded>
              {{ createError }}
            </q-banner>

            <div class="q-mt-md row q-gutter-sm">
              <q-btn color="primary" type="submit" :loading="creating">Crear documento</q-btn>
              <q-btn flat label="Cancelar" v-close-popup />
            </div>
          </q-form>
        </q-card-section>
      </q-card>
    </q-dialog>

    <q-dialog v-model="issueDialog.open">
      <q-card style="width: 520px; max-width: 95vw" class="app-card">
        <q-card-section class="text-h6">Emitir documento #{{ issueDialog.doc?.id }}</q-card-section>
        <q-separator />
        <q-card-section>
          <q-toggle v-model="issueDialog.print_after_issue" label="Solicitar impresión después de emitir" />
          <q-banner class="q-mt-md bg-blue-1 text-blue-10" rounded>
            `apply_inventory` se envía en `false` por política de bounded context en este slice.
          </q-banner>
          <q-banner v-if="actionError" class="q-mt-md bg-red-1 text-red-10" rounded>
            {{ actionError }}
          </q-banner>
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat label="Cancelar" v-close-popup />
          <q-btn color="primary" label="Emitir" :loading="isActionLoading(issueDialog.doc?.id, 'issue')" @click="confirmIssue" />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <q-dialog v-model="voidDialog.open">
      <q-card style="width: 520px; max-width: 95vw" class="app-card">
        <q-card-section class="text-h6">Anular documento #{{ voidDialog.doc?.id }}</q-card-section>
        <q-separator />
        <q-card-section>
          <q-input v-model="voidDialog.reason" dense outlined label="Razón de anulación" maxlength="255" />
          <q-banner v-if="actionError" class="q-mt-md bg-red-1 text-red-10" rounded>
            {{ actionError }}
          </q-banner>
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat label="Cancelar" v-close-popup />
          <q-btn color="negative" label="Anular" :loading="isActionLoading(voidDialog.doc?.id, 'void')" @click="confirmVoid" />
        </q-card-actions>
      </q-card>
    </q-dialog>
  </AppContainer>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import type { QTableColumn } from 'quasar';
import { useQuasar } from 'quasar';

import AppContainer from 'src/ui/AppContainer.vue';
import AppDataTable from 'src/ui/AppDataTable.vue';
import AppPageHeader from 'src/ui/AppPageHeader.vue';
import { extractApiError, extractErrorMessage } from 'src/core/http/errors';
import {
  createBillingDoc,
  getBillingDocDetail,
  issueBillingDoc,
  listBillingDocs,
  type BillingDocDetail,
  type BillingDocListParams,
  type BillingDocRow,
  type BillingDocStatus,
  type BillingDocType,
  voidBillingDoc,
} from 'src/services/billing.service';
import { useAclStore } from 'src/stores/acl.store';
import { useContextStore } from 'src/stores/context.store';
import { BUSINESS_LABELS } from 'src/shared/ui/business-terms';

const $q = useQuasar();
const acl = useAclStore();
const ctx = useContextStore();
const labels = BUSINESS_LABELS;

const companyLabel = computed(() => acl.companyName(ctx.activeCompanyId) ?? ctx.activeCompanyId ?? '—');

function hasCompanyPermission(permission: string): boolean {
  const companyId = ctx.activeCompanyId;
  if (!companyId) return false;
  return acl.hasPermission(companyId, permission);
}

const canCreate = computed(() => hasCompanyPermission('billing.doc.create'));
const canIssuePermission = computed(() => hasCompanyPermission('billing.doc.issue'));
const canVoidPermission = computed(() => hasCompanyPermission('billing.doc.void'));

const loadingList = ref(false);
const listError = ref<string | null>(null);
const actionError = ref<string | null>(null);
const rows = ref<BillingDocRow[]>([]);
const selectedDetail = ref<BillingDocDetail | null>(null);

const filters = reactive<BillingDocListParams>({
  q: '',
  status: undefined,
  doc_type: undefined,
  date_from: '',
  date_to: '',
  ordering: '-created_at',
});

const pagination = ref({
  page: 1,
  rowsPerPage: 20,
  rowsNumber: 0,
});

const totalRows = computed(() => pagination.value.rowsNumber || rows.value.length);

const statusOptions: Array<{ label: string; value: BillingDocStatus }> = [
  { label: 'DRAFT', value: 'DRAFT' },
  { label: 'ISSUED', value: 'ISSUED' },
  { label: 'VOIDED', value: 'VOIDED' },
];

const docTypeOptions: Array<{ label: string; value: BillingDocType }> = [
  { label: 'INVOICE', value: 'INVOICE' },
  { label: 'CREDIT_NOTE', value: 'CREDIT_NOTE' },
];

const orderingOptions = [
  { label: 'Recientes', value: '-created_at' },
  { label: 'Antiguos', value: 'created_at' },
  { label: 'ID desc', value: '-id' },
  { label: 'ID asc', value: 'id' },
  { label: 'Total desc', value: '-total' },
  { label: 'Total asc', value: 'total' },
];

const columns: QTableColumn<BillingDocRow>[] = [
  { name: 'id', label: 'ID', field: 'id', align: 'left', sortable: true },
  { name: 'created_at', label: 'Creado', field: 'created_at', align: 'left', sortable: true },
  { name: 'doc_type', label: 'Tipo', field: 'doc_type', align: 'left', sortable: true },
  { name: 'status', label: 'Estado', field: 'status', align: 'left', sortable: true },
  { name: 'customer_name', label: 'Cliente', field: 'customer_name', align: 'left' },
  { name: 'series', label: 'Serie', field: 'series', align: 'left' },
  { name: 'number', label: 'Número', field: 'number', align: 'left', sortable: true },
  { name: 'total', label: 'Total', field: 'total', align: 'right', sortable: true },
  { name: 'actions', label: 'Acciones', field: (row) => row.id, align: 'right' },
];

type ActionKind = 'issue' | 'void';
const actionLoading = ref<{ docId: number | null; kind: ActionKind | null }>({ docId: null, kind: null });

function isActionLoading(docId: number | undefined, kind: ActionKind): boolean {
  if (!docId) return false;
  return actionLoading.value.docId === docId && actionLoading.value.kind === kind;
}

function statusColor(status: BillingDocStatus): string {
  if (status === 'ISSUED') return 'positive';
  if (status === 'VOIDED') return 'negative';
  return 'warning';
}

function formatDate(value: string | null): string {
  if (!value) return '—';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return String(value);
  return d.toLocaleString();
}

function money(value: string, currency: string): string {
  const numeric = Number(value);
  if (Number.isNaN(numeric)) return `${value} ${currency}`;
  return new Intl.NumberFormat('es-NI', {
    style: 'currency',
    currency: currency || 'NIO',
    maximumFractionDigits: 2,
  }).format(numeric);
}

function canIssue(row: BillingDocRow): boolean {
  return canIssuePermission.value && row.status === 'DRAFT';
}

function canVoid(row: BillingDocRow): boolean {
  return canVoidPermission.value && row.status === 'ISSUED';
}

function computeLimit(rowsPerPage: number) {
  return rowsPerPage === 0 ? 200 : rowsPerPage;
}

function currentFilters() {
  return {
    status: filters.status,
    doc_type: filters.doc_type,
    q: filters.q,
    date_from: filters.date_from,
    date_to: filters.date_to,
    ordering: filters.ordering,
  } as BillingDocListParams;
}

async function loadList(page = pagination.value.page, rowsPerPage = pagination.value.rowsPerPage) {
  loadingList.value = true;
  listError.value = null;
  try {
    const limit = computeLimit(rowsPerPage);
    const offset = (page - 1) * limit;
    const payload = await listBillingDocs({
      limit,
      offset,
      ...currentFilters(),
    });
    rows.value = payload.results;
    pagination.value = {
      ...pagination.value,
      page,
      rowsPerPage,
      rowsNumber: payload.count,
    };
  } catch (e: unknown) {
    listError.value = extractErrorMessage(e);
  } finally {
    loadingList.value = false;
  }
}

function onRequest(props: { pagination: { page: number; rowsPerPage: number } }) {
  const { page, rowsPerPage } = props.pagination;
  void loadList(page, rowsPerPage);
}

function applyFilters() {
  pagination.value.page = 1;
  void loadList(1, pagination.value.rowsPerPage);
}

function clearFilters() {
  filters.q = '';
  filters.status = undefined;
  filters.doc_type = undefined;
  filters.date_from = '';
  filters.date_to = '';
  filters.ordering = '-created_at';
  applyFilters();
}

function reload() {
  void loadList();
}

async function openDetail(docId: number) {
  listError.value = null;
  try {
    selectedDetail.value = await getBillingDocDetail(docId);
  } catch (e: unknown) {
    listError.value = extractErrorMessage(e);
  }
}

const createDialog = ref(false);
const creating = ref(false);
const createError = ref<string | null>(null);

const createForm = reactive({
  doc_type: 'INVOICE' as BillingDocType,
  series: 'A',
  currency: 'NIO',
  customer_name: '',
  customer_ref: '',
  is_fiscal: false,
  lines: [
    {
      key: 1,
      description: '',
      quantity: '1.0000',
      unit_price: '0.000000',
      tax_rate: '0.1500',
    },
  ],
});

let lineKeyCounter = 2;

function resetCreateForm() {
  createForm.doc_type = 'INVOICE';
  createForm.series = 'A';
  createForm.currency = 'NIO';
  createForm.customer_name = '';
  createForm.customer_ref = '';
  createForm.is_fiscal = false;
  createForm.lines = [
    {
      key: 1,
      description: '',
      quantity: '1.0000',
      unit_price: '0.000000',
      tax_rate: '0.1500',
    },
  ];
  lineKeyCounter = 2;
}

function openCreateDialog() {
  if (!canCreate.value) {
    $q.notify({ type: 'negative', message: 'No tienes permiso: billing.doc.create' });
    return;
  }
  createError.value = null;
  resetCreateForm();
  createDialog.value = true;
}

function appendLine() {
  createForm.lines.push({
    key: lineKeyCounter,
    description: '',
    quantity: '1.0000',
    unit_price: '0.000000',
    tax_rate: '0.1500',
  });
  lineKeyCounter += 1;
}

function removeLine(index: number) {
  if (createForm.lines.length <= 1) return;
  createForm.lines.splice(index, 1);
}

async function createDocument() {
  creating.value = true;
  createError.value = null;
  try {
    const lines = createForm.lines
      .map((line) => ({
        description: String(line.description || '').trim(),
        quantity: String(line.quantity || '').trim(),
        unit_price: String(line.unit_price || '').trim(),
        tax_rate: String(line.tax_rate || '').trim() || '0.0000',
      }))
      .filter((line) => line.description && line.quantity && line.unit_price);

    if (lines.length === 0) {
      createError.value = 'Debes registrar al menos una línea válida.';
      return;
    }

    const created = await createBillingDoc({
      doc_type: createForm.doc_type,
      series: String(createForm.series || 'A').trim() || 'A',
      currency: String(createForm.currency || 'NIO').trim() || 'NIO',
      customer_name: String(createForm.customer_name || '').trim(),
      customer_ref: String(createForm.customer_ref || '').trim(),
      is_fiscal: Boolean(createForm.is_fiscal),
      idempotency_key: `web-billing-create-${Date.now()}`,
      lines,
    });

    createDialog.value = false;
    $q.notify({ type: 'positive', message: `Documento creado (id=${created.id})` });
    await loadList();
    await openDetail(created.id);
  } catch (e: unknown) {
    createError.value = extractErrorMessage(e);
  } finally {
    creating.value = false;
  }
}

const issueDialog = reactive<{
  open: boolean;
  doc: BillingDocRow | null;
  print_after_issue: boolean;
}>({
  open: false,
  doc: null,
  print_after_issue: false,
});

function openIssueDialog(row: BillingDocRow) {
  actionError.value = null;
  issueDialog.doc = row;
  issueDialog.print_after_issue = false;
  issueDialog.open = true;
}

async function confirmIssue() {
  if (!issueDialog.doc) return;
  const docId = issueDialog.doc.id;
  actionLoading.value = { docId, kind: 'issue' };
  actionError.value = null;
  try {
    const payload = {
      apply_inventory: false,
      print_after_issue: Boolean(issueDialog.print_after_issue),
      idempotency_key: `web-billing-issue-${docId}-${Date.now()}`,
    };
    const result = await issueBillingDoc(docId, payload);
    issueDialog.open = false;
    await loadList();
    await openDetail(docId);
    if (result.already_issued) {
      $q.notify({ type: 'info', message: `Documento #${docId} ya estaba emitido.` });
    } else {
      $q.notify({ type: 'positive', message: `Documento #${docId} emitido.` });
    }
  } catch (e: unknown) {
    const apiError = extractApiError(e);
    if (apiError.status === 409) {
      actionError.value = `Conflicto de estado: ${apiError.message}`;
    } else {
      actionError.value = apiError.message;
    }
  } finally {
    actionLoading.value = { docId: null, kind: null };
  }
}

const voidDialog = reactive<{
  open: boolean;
  doc: BillingDocRow | null;
  reason: string;
}>({
  open: false,
  doc: null,
  reason: '',
});

function openVoidDialog(row: BillingDocRow) {
  actionError.value = null;
  voidDialog.doc = row;
  voidDialog.reason = '';
  voidDialog.open = true;
}

async function confirmVoid() {
  if (!voidDialog.doc) return;
  const reason = String(voidDialog.reason || '').trim();
  if (!reason) {
    actionError.value = 'La razón de anulación es obligatoria.';
    return;
  }

  const docId = voidDialog.doc.id;
  actionLoading.value = { docId, kind: 'void' };
  actionError.value = null;
  try {
    await voidBillingDoc(docId, { reason });
    voidDialog.open = false;
    await loadList();
    await openDetail(docId);
    $q.notify({ type: 'positive', message: `Documento #${docId} anulado.` });
  } catch (e: unknown) {
    const apiError = extractApiError(e);
    if (apiError.status === 409) {
      actionError.value = `Conflicto de estado: ${apiError.message}`;
    } else {
      actionError.value = apiError.message;
    }
  } finally {
    actionLoading.value = { docId: null, kind: null };
  }
}

onMounted(() => {
  void loadList();
});
</script>
