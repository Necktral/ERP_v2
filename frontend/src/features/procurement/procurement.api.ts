/**
 * Compras (procurement) — documentos de proveedor con ciclo
 * BORRADOR → POSTEADO → ANULADO. El posteo asigna número y crea la CxP.
 */
import { api } from 'src/boot/axios';
import { PAGE, type Paginated } from 'src/core/api';

export type PurchaseDocType =
  | 'GOODS_RECEIPT'
  | 'SUPPLIER_INVOICE'
  | 'SUPPLIER_CREDIT_NOTE'
  | 'SUPPLIER_PAYMENT'
  | 'ADJUSTMENT';

export type PurchaseDocStatus = 'DRAFT' | 'POSTED' | 'VOIDED';

export const PURCHASE_DOC_TYPE_LABELS: Record<PurchaseDocType, string> = {
  GOODS_RECEIPT: 'Recepción de bienes',
  SUPPLIER_INVOICE: 'Factura de proveedor',
  SUPPLIER_CREDIT_NOTE: 'Nota de crédito de proveedor',
  SUPPLIER_PAYMENT: 'Pago a proveedor',
  ADJUSTMENT: 'Ajuste',
};

export interface PurchaseDocRow {
  id: number;
  doc_type: PurchaseDocType;
  status: PurchaseDocStatus;
  series: string;
  number: number;
  currency: string;
  supplier_name: string;
  supplier_party_id: number | null;
  supplier_party_display_name: string;
  subtotal: string;
  tax_total: string;
  total: string;
  created_at: string;
  posted_at: string | null;
  voided_at: string | null;
}

export interface PurchaseDoc extends PurchaseDocRow {
  supplier_ref: string;
  external_ref: string;
  void_reason: string;
  notes: string;
}

export interface PurchaseDocFilters {
  status?: PurchaseDocStatus | '';
  doc_type?: PurchaseDocType | '';
  q?: string;
  date_from?: string;
  date_to?: string;
}

export async function listPurchaseDocs(filters: PurchaseDocFilters = {}): Promise<PurchaseDocRow[]> {
  const params: Record<string, string | number> = { ...PAGE };
  for (const [k, v] of Object.entries(filters)) {
    if (v) params[k] = v;
  }
  const { data } = await api.get<Paginated<PurchaseDocRow>>('/procurement/docs/', { params });
  return data.results;
}

export async function getPurchaseDoc(docId: number): Promise<PurchaseDoc> {
  const { data } = await api.get<PurchaseDoc>(`/procurement/docs/${docId}/`);
  return data;
}

export async function createPurchaseDoc(input: {
  doc_type: PurchaseDocType;
  supplier_party_id?: number;
  supplier_name?: string;
  supplier_ref?: string;
  external_ref?: string;
  subtotal: string;
  tax_total: string;
  total: string;
  notes?: string;
}): Promise<number> {
  const { data } = await api.post<{ id: number }>('/procurement/docs/', {
    ...input,
    idempotency_key: crypto.randomUUID(),
  });
  return data.id;
}

export async function postPurchaseDoc(docId: number): Promise<{ status: string; number: number }> {
  const { data } = await api.post<{ status: string; number: number }>(
    `/procurement/docs/${docId}/post/`,
    {},
  );
  return data;
}

export async function voidPurchaseDoc(docId: number, reason: string): Promise<{ status: string }> {
  const { data } = await api.post<{ status: string }>(`/procurement/docs/${docId}/void/`, { reason });
  return data;
}
