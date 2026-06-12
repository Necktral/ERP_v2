/**
 * Comisariato — tienda a crédito. Cuentas por tercero con límite (C-01:
 * null = sin tope, 0 = sin crédito, >0 = tope). La venta orquesta factura +
 * baja de inventario + CxC; el cobro a empleados se aplica en planilla.
 */
import { api } from 'src/boot/axios';
import { PAGE, type Paginated } from 'src/core/api';

export type CustomerSegment = 'EMPLOYEE' | 'PRODUCER' | 'PUBLIC';

export const SEGMENT_LABELS: Record<CustomerSegment, string> = {
  EMPLOYEE: 'Empleado (descuento en planilla)',
  PRODUCER: 'Productor',
  PUBLIC: 'Público',
};

export interface CreditAccount {
  id: number;
  company_id: number;
  party_id: number;
  party_display_name: string;
  segment: CustomerSegment;
  credit_limit: string | null;
  outstanding: string;
  available: string | null;
  collecting_company_id: number | null;
  is_active: boolean;
  notes: string;
}

export async function listAccounts(filters: { q?: string; segment?: CustomerSegment | '' } = {}): Promise<
  CreditAccount[]
> {
  const params: Record<string, string | number> = { ...PAGE };
  if (filters.q) params.q = filters.q;
  if (filters.segment) params.segment = filters.segment;
  const { data } = await api.get<Paginated<CreditAccount>>('/comisariato/accounts/', { params });
  return data.results;
}

export async function upsertAccount(input: {
  party_id: number;
  segment: CustomerSegment;
  credit_limit?: string | null;
  collecting_company_id?: number | null;
  is_active?: boolean;
  notes?: string;
}): Promise<CreditAccount> {
  const { data } = await api.post<CreditAccount>('/comisariato/accounts/', input);
  return data;
}

export interface SaleLineInput {
  description: string;
  quantity: string;
  unit_price: string;
  tax_rate?: string;
  inventory_item_id: number;
}

export async function createCreditSale(input: {
  account_id: number;
  warehouse_id: number;
  reference_code: string;
  is_fiscal?: boolean;
  lines: SaleLineInput[];
}): Promise<Record<string, unknown>> {
  const { data } = await api.post<Record<string, unknown>>('/comisariato/sales/', input);
  return data;
}

export async function applyStoreCredit(
  sheetId: number,
  input: { comisariato_company_id: number; per_period_cap?: string },
): Promise<Record<string, unknown>> {
  const { data } = await api.post<Record<string, unknown>>(
    `/comisariato/payroll/${sheetId}/apply-store-credit/`,
    input,
  );
  return data;
}
