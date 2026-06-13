/**
 * Cartera (kernel portfolio) — CxC (lo que te deben), CxP (lo que debés),
 * créditos y aplicaciones de pago. Aging automático por buckets.
 *
 * OJO: este kernel es un router DRF sin envelope de paginación: los listados
 * devuelven ARRAY plano (no {count, results}).
 */
import { api } from 'src/boot/axios';

export type ObligationStatus =
  | 'PENDING'
  | 'PARTIAL'
  | 'PAID'
  | 'OVERDUE'
  | 'WRITTEN_OFF'
  | 'DISPUTED'
  | 'RESTRUCTURED'
  | 'CANCELLED';

export const AGING_BUCKET_LABELS: Record<string, string> = {
  CURRENT: 'Al día',
  'DAYS_1_30': '1–30 días',
  'DAYS_31_60': '31–60 días',
  'DAYS_61_90': '61–90 días',
  'DAYS_91_120': '91–120 días',
  'DAYS_120_PLUS': '+120 días',
};

interface ObligationBase {
  id: number;
  obligation_id: string;
  company: number;
  branch: number | null;
  party: number;
  reference_type: string;
  reference_id: number;
  status: ObligationStatus;
  currency: string;
  principal_amount: string;
  interest_amount: string;
  fee_amount: string;
  penalty_amount: string;
  allocated_amount: string;
  total_amount: string;
  outstanding_amount: string;
  issue_date: string;
  due_date: string;
  days_overdue: number;
  aging_bucket: string;
  is_overdue: boolean;
  notes: string;
}

export interface Receivable extends ObligationBase {
  invoice_number: string;
  invoice_date: string | null;
  risk_rating: string;
  collection_priority: string;
}

export interface Payable extends ObligationBase {
  supplier_invoice_number: string;
  supplier_invoice_date: string | null;
  payment_priority: string;
}

export interface Credit {
  id: number;
  obligation_id: string;
  company: number;
  party: number;
  status: ObligationStatus;
  credit_type: string;
  credit_status: string;
  contract_number: string;
  currency: string;
  principal_amount: string;
  total_amount: string;
  outstanding_amount: string;
  interest_rate: string;
  term_months: number | null;
  approval_date: string | null;
  disbursement_date: string | null;
  maturity_date: string | null;
}

export interface AllocationRow {
  id: number;
  allocation_id: string;
  status: string;
  allocated_amount: string;
  currency: string;
  allocation_date: string;
  obligation_content_type: number;
  obligation_object_id: number;
  reversed_at: string | null;
  reversal_reason: string;
}

export const CREDIT_STATUS_LABELS: Record<string, string> = {
  PENDING: 'Pendiente',
  APPROVED: 'Aprobado',
  ACTIVE: 'Activo',
  MATURED: 'Vencido (plazo)',
  DEFAULTED: 'En mora',
  FULLY_PAID: 'Pagado',
  CANCELLED: 'Cancelado',
};

export async function listReceivables(filters: { status?: string; party?: number } = {}): Promise<Receivable[]> {
  const params: Record<string, string | number> = {};
  if (filters.status) params.status = filters.status;
  if (filters.party) params.party = filters.party;
  const { data } = await api.get<Receivable[]>('/portfolio/receivables/', { params });
  return data;
}

export async function adjustReceivable(
  id: number,
  input: { adjustment_amount: string; reason: string },
): Promise<Receivable> {
  const { data } = await api.post<Receivable>(`/portfolio/receivables/${id}/adjust/`, input);
  return data;
}

export async function writeoffReceivable(id: number, reason: string): Promise<Receivable> {
  const { data } = await api.post<Receivable>(`/portfolio/receivables/${id}/writeoff/`, { reason });
  return data;
}

export async function listPayables(filters: { status?: string; party?: number } = {}): Promise<Payable[]> {
  const params: Record<string, string | number> = {};
  if (filters.status) params.status = filters.status;
  if (filters.party) params.party = filters.party;
  const { data } = await api.get<Payable[]>('/portfolio/payables/', { params });
  return data;
}

export async function listCredits(): Promise<Credit[]> {
  const { data } = await api.get<Credit[]>('/portfolio/credits/');
  return data;
}

export async function disburseCredit(
  id: number,
  input: { disbursed_amount: string; disbursement_date: string },
): Promise<Credit> {
  const { data } = await api.post<Credit>(`/portfolio/credits/${id}/disburse/`, input);
  return data;
}

export async function listAllocations(): Promise<AllocationRow[]> {
  const { data } = await api.get<AllocationRow[]>('/portfolio/allocations/');
  return data;
}
