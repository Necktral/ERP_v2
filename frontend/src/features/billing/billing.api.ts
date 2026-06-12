/**
 * Facturación (kernel facturacion) — documentos de venta con numeración fiscal:
 * BORRADOR → EMITIDO (toma número, opcionalmente baja inventario e imprime) → ANULADO (SoD).
 * Contingencia: si la impresora fiscal falla, el doc queda en CONTINGENCY y se resuelve
 * con reintento o anulación.
 */
import { api } from 'src/boot/axios';
import { PAGE, type Paginated } from 'src/core/api';

export type BillingDocType = 'INVOICE' | 'CREDIT_NOTE' | 'QUOTE' | 'ORDER';
export type BillingDocStatus = 'DRAFT' | 'ISSUED' | 'VOIDED';

export const BILLING_DOC_TYPE_LABELS: Record<BillingDocType, string> = {
  INVOICE: 'Factura',
  CREDIT_NOTE: 'Nota de crédito',
  QUOTE: 'Cotización',
  ORDER: 'Pedido',
};

export const FISCAL_STATUS_LABELS: Record<string, string> = {
  NUMBER_RESERVED: 'Número reservado',
  ISSUED: 'Emitido',
  PRINTED: 'Impreso',
  FAILED_PRINT: 'Falla de impresión',
  CONTINGENCY: 'Contingencia',
  VOIDED: 'Anulado',
};

export const PAYMENT_METHOD_LABELS: Record<string, string> = {
  CASH: 'Efectivo',
  TRANSFER: 'Transferencia',
  CREDIT: 'Crédito',
  CARD: 'Tarjeta',
  CHECK: 'Cheque',
  PAYROLL_DEDUCTION: 'Deducción de planilla',
  PRODUCER_CREDIT: 'Crédito de productor',
  INTERNAL_TRANSFER: 'Traslado interno',
  COFFEE_QUOTA: 'Cuota de café',
  MIXED: 'Mixto',
};

export interface BillingLineInput {
  description: string;
  quantity: string;
  unit_price: string;
  tax_rate?: string;
  inventory_item_id?: number | null;
}

export interface BillingDocRow {
  id: number;
  doc_type: BillingDocType;
  status: BillingDocStatus;
  series: string;
  number: number;
  currency: string;
  customer_name: string;
  customer_ref: string;
  customer_party_id: number | null;
  customer_party_display_name: string;
  subtotal: string;
  tax_total: string;
  total: string;
  payment_method: string;
  is_fiscal: boolean;
  fiscal_status: string;
  created_at: string;
  issued_at: string | null;
  voided_at: string | null;
}

export interface BillingLine {
  id: number;
  description: string;
  quantity: string;
  unit_price: string;
  tax_rate: string;
  line_subtotal: string;
  line_tax: string;
  line_total: string;
  inventory_item_id: number | null;
}

export interface BillingDoc extends BillingDocRow {
  void_reason: string;
  fiscal: {
    mode: string;
    status: string;
    reference: string;
    printed_at: string | null;
    attempts: number;
    last_error: string;
    contingency_reason: string;
    contingency_at: string | null;
  };
  accounting: {
    status: string;
    error: string;
    journal_draft_id: number | null;
    journal_entry_id: number | null;
  };
  lines: BillingLine[];
}

export interface BillingFilters {
  status?: BillingDocStatus | '';
  doc_type?: BillingDocType | '';
  q?: string;
  date_from?: string;
  date_to?: string;
}

export async function listBillingDocs(filters: BillingFilters = {}): Promise<BillingDocRow[]> {
  const params: Record<string, string | number> = { ...PAGE };
  for (const [k, v] of Object.entries(filters)) {
    if (v) params[k] = v;
  }
  const { data } = await api.get<Paginated<BillingDocRow>>('/billing/docs/', { params });
  return data.results;
}

export async function getBillingDoc(docId: number): Promise<BillingDoc> {
  const { data } = await api.get<BillingDoc>(`/billing/docs/${docId}/`);
  return data;
}

export async function createBillingDoc(input: {
  doc_type: BillingDocType;
  customer_party_id?: number;
  customer_name?: string;
  customer_ref?: string;
  is_fiscal?: boolean;
  payment_method?: string;
  lines: BillingLineInput[];
}): Promise<number> {
  const { data } = await api.post<{ id: number }>('/billing/docs/', {
    ...input,
    idempotency_key: crypto.randomUUID(),
  });
  return data.id;
}

export async function issueBillingDoc(
  docId: number,
  opts: { apply_inventory?: boolean; warehouse_id?: number; print_after_issue?: boolean } = {},
): Promise<{ status: string; number?: number; fiscal_status?: string }> {
  const { data } = await api.post<{ status: string; number?: number; fiscal_status?: string }>(
    `/billing/docs/${docId}/issue/`,
    { ...opts, idempotency_key: crypto.randomUUID() },
  );
  return data;
}

export async function printBillingDoc(docId: number): Promise<void> {
  await api.post(`/billing/docs/${docId}/print/`, { idempotency_key: crypto.randomUUID() });
}

export async function voidBillingDoc(docId: number, reason: string): Promise<Record<string, unknown>> {
  const { data } = await api.post<Record<string, unknown>>(`/billing/docs/${docId}/void/`, { reason });
  return data;
}

export async function setBillingContingency(docId: number, reason: string): Promise<void> {
  await api.post(`/billing/docs/${docId}/contingency/`, { reason });
}

export async function resolveBillingContingency(
  docId: number,
  action: 'RETRY_PRINT' | 'VOID',
  reason = '',
): Promise<void> {
  await api.post(`/billing/docs/${docId}/contingency/resolve/`, {
    action,
    reason,
    idempotency_key: crypto.randomUUID(),
  });
}

// --- Configuración fiscal de la sucursal ---
export interface FiscalConfig {
  fiscal_mode: string;
  adapter_code: string;
  print_required: boolean;
  strict_integrity: boolean;
  contingency_max_attempts: number;
  is_active: boolean;
}

export async function getFiscalConfig(): Promise<FiscalConfig> {
  const { data } = await api.get<FiscalConfig>('/billing/fiscal/branch-config/');
  return data;
}

export async function updateFiscalConfig(input: Partial<FiscalConfig>): Promise<FiscalConfig> {
  const { data } = await api.put<FiscalConfig>('/billing/fiscal/branch-config/', input);
  return data;
}
