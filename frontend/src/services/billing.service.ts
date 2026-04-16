import { api } from 'src/boot/axios';

export type BillingDocStatus = 'DRAFT' | 'ISSUED' | 'VOIDED';
export type BillingDocType = 'INVOICE' | 'CREDIT_NOTE';

export type BillingDocRow = {
  id: number;
  doc_type: BillingDocType;
  status: BillingDocStatus;
  series: string;
  number: number;
  currency: string;
  customer_name: string;
  customer_ref: string;
  subtotal: string;
  tax_total: string;
  total: string;
  is_fiscal: boolean;
  fiscal_status: string;
  created_at: string;
  issued_at: string | null;
  voided_at: string | null;
};

export type BillingDocLineIn = {
  description: string;
  quantity: string;
  unit_price: string;
  tax_rate?: string;
  inventory_item_id?: number | null;
};

export type BillingDocListParams = {
  limit?: number;
  offset?: number;
  status?: BillingDocStatus | undefined;
  doc_type?: BillingDocType | undefined;
  q?: string;
  date_from?: string;
  date_to?: string;
  ordering?: '-created_at' | 'created_at' | '-id' | 'id' | '-total' | 'total';
};

export type BillingDocListResponse = {
  count: number;
  limit: number;
  offset: number;
  results: BillingDocRow[];
};

export type CreateBillingDocPayload = {
  doc_type: BillingDocType;
  series?: string;
  currency?: string;
  customer_name?: string;
  customer_ref?: string;
  is_fiscal?: boolean;
  idempotency_key?: string;
  lines: BillingDocLineIn[];
};

export type CreateBillingDocResponse = {
  id: number;
};

export type BillingDocDetail = BillingDocRow & {
  void_reason: string;
  accounting: {
    status: string;
    error: string;
    economic_event_id: string | null;
    journal_draft_id: string | null;
    journal_entry_id: string | null;
  };
  fiscal: {
    mode: string;
    status: string;
    reference: string;
    evidence_id: string;
    printed_at: string | null;
    attempts: number;
    last_error: string;
    contingency_reason: string;
    contingency_at: string | null;
    metadata: Record<string, unknown>;
  };
  lines: Array<{
    id: number;
    description: string;
    quantity: string;
    unit_price: string;
    tax_rate: string;
    line_subtotal: string;
    line_tax: string;
    line_total: string;
    inventory_item_id: number | null;
  }>;
};

export type IssueBillingDocPayload = {
  apply_inventory?: boolean;
  print_after_issue?: boolean;
  idempotency_key?: string;
};

export type VoidBillingDocPayload = {
  reason: string;
};

export type BillingActionResponse = {
  ok?: boolean;
  already_issued?: boolean;
  status?: string;
  [key: string]: unknown;
};

function buildListParams(filters: BillingDocListParams): Record<string, string | number> {
  const out: Record<string, string | number> = {};
  if (typeof filters.limit === 'number') out.limit = filters.limit;
  if (typeof filters.offset === 'number') out.offset = filters.offset;
  if (filters.status) out.status = filters.status;
  if (filters.doc_type) out.doc_type = filters.doc_type;
  if (filters.q && String(filters.q).trim()) out.q = String(filters.q).trim();
  if (filters.date_from) out.date_from = filters.date_from;
  if (filters.date_to) out.date_to = filters.date_to;
  if (filters.ordering) out.ordering = filters.ordering;
  return out;
}

export async function listBillingDocs(filters: BillingDocListParams = {}) {
  const params = buildListParams(filters);
  const { data } = await api.get<BillingDocListResponse>('/billing/docs/', { params });
  return data;
}

export async function getBillingDocDetail(docId: number) {
  const { data } = await api.get<BillingDocDetail>(`/billing/docs/${docId}/`);
  return data;
}

export async function createBillingDoc(payload: CreateBillingDocPayload) {
  const { data } = await api.post<CreateBillingDocResponse>('/billing/docs/', payload);
  return data;
}

export async function issueBillingDoc(docId: number, payload: IssueBillingDocPayload) {
  const { data } = await api.post<BillingActionResponse>(`/billing/docs/${docId}/issue/`, payload);
  return data;
}

export async function voidBillingDoc(docId: number, payload: VoidBillingDocPayload) {
  const { data } = await api.post<BillingActionResponse>(`/billing/docs/${docId}/void/`, payload);
  return data;
}
