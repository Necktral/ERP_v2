/**
 * Contabilidad (kernel accounting) — plan de cuentas, períodos fiscales,
 * diario (borradores con SoD aprobar→postear, asientos con reversa), reportes,
 * tipo de cambio/revaluación e intercompany.
 */
import { api } from 'src/boot/axios';
import { PAGE, type Paginated } from 'src/core/api';

export const ACCOUNT_TYPE_LABELS: Record<string, string> = {
  ASSET: 'Activo',
  LIABILITY: 'Pasivo',
  EQUITY: 'Patrimonio',
  REVENUE: 'Ingreso',
  EXPENSE: 'Gasto',
};

export const DRAFT_STATE_LABELS: Record<string, string> = {
  GENERATED: 'Generado',
  VALIDATED: 'Validado',
  EXCEPTION: 'Excepción',
  APPROVED_FOR_POSTING: 'Aprobado',
  POSTED: 'Posteado',
  SUPERSEDED: 'Sustituido',
};

export const IC_STATUS_LABELS: Record<string, string> = {
  CREATED: 'Creada',
  CONFIRMED: 'Confirmada',
  RECONCILED: 'Conciliada',
  DISPUTED: 'En disputa',
  SETTLED: 'Liquidada',
  CLOSED: 'Cerrada',
};

// --- Plan de cuentas ---
export interface CoARow {
  id: number;
  code: string;
  name: string;
  account_type: string;
  parent_code: string;
  is_postable: boolean;
  is_active: boolean;
  is_revaluable: boolean;
}

export interface CoAResponse extends Paginated<CoARow> {
  config: {
    functional_currency: string;
    fx_gain_account_code: string;
    fx_loss_account_code: string;
    retained_earnings_account_code: string;
  };
}

export async function getChartOfAccounts(): Promise<CoAResponse> {
  const { data } = await api.get<CoAResponse>('/accounting/chart-of-accounts/', { params: PAGE });
  return data;
}

export async function upsertChartOfAccounts(rows: {
  code: string;
  name: string;
  account_type: string;
  parent_code?: string;
  is_postable?: boolean;
  is_active?: boolean;
  is_revaluable?: boolean;
}[]): Promise<void> {
  await api.put('/accounting/chart-of-accounts/', { rows });
}

// --- Períodos ---
export interface FiscalPeriodRow {
  id: number;
  year: number;
  month: number;
  status: 'OPEN' | 'CLOSED';
  opened_at: string | null;
  closed_at: string | null;
}

export async function listPeriods(): Promise<FiscalPeriodRow[]> {
  const { data } = await api.get<Paginated<FiscalPeriodRow>>('/accounting/periods/', { params: PAGE });
  return data.results;
}

export async function closePeriod(year: number, month: number): Promise<void> {
  await api.post('/accounting/periods/close/', { year, month });
}

export async function reopenPeriod(year: number, month: number, reason: string): Promise<void> {
  await api.post('/accounting/periods/reopen/', { year, month, reason });
}

// --- Diario: borradores ---
export interface JournalDraftRow {
  id: number;
  state: string;
  close_run_id: string;
  economic_event_id: number;
  total_debit: string;
  total_credit: string;
  generated_at: string;
  validated_at: string | null;
  approved_at: string | null;
  posted_at: string | null;
  validation_passed: boolean | null;
}

export async function listJournalDrafts(state?: string): Promise<JournalDraftRow[]> {
  const params: Record<string, string | number> = { ...PAGE };
  if (state) params.state = state;
  const { data } = await api.get<Paginated<JournalDraftRow>>('/accounting/journal-drafts/', { params });
  return data.results;
}

export async function approveDrafts(limit = 200): Promise<{ attempted: number; approved: number; skipped: number }> {
  const { data } = await api.post('/accounting/journal-drafts/approve/', { limit });
  return data as { attempted: number; approved: number; skipped: number };
}

export async function postDrafts(limit = 200): Promise<Record<string, unknown>> {
  const { data } = await api.post<Record<string, unknown>>('/accounting/journal-drafts/post/', { limit });
  return data;
}

// --- Diario: asientos ---
export interface JournalEntryRow {
  id: number;
  draft_id: number;
  year: number;
  month: number;
  entry_date: string;
  description: string;
  debit_total: string;
  credit_total: string;
  status?: string;
}

export async function listJournalEntries(filters: { year?: number; month?: number } = {}): Promise<
  JournalEntryRow[]
> {
  const params: Record<string, string | number> = { ...PAGE };
  if (filters.year) params.year = filters.year;
  if (filters.month) params.month = filters.month;
  const { data } = await api.get<Paginated<JournalEntryRow>>('/accounting/journal-entries/', { params });
  return data.results;
}

export async function reverseJournalEntry(entryId: number, reason: string): Promise<void> {
  await api.post(`/accounting/journal-entries/${entryId}/reverse/`, { reason });
}

// --- Reportes (filas dinámicas) ---
export type ReportKey = 'trial-balance' | 'general-ledger' | 'pnl' | 'balance-sheet';

export interface ReportResponse {
  count: number;
  results: Record<string, unknown>[];
  filters?: Record<string, string>;
}

export async function getAccountingReport(
  report: ReportKey,
  params: { year?: number; month?: number; date_from?: string; date_to?: string; as_of?: string; account_code?: string },
): Promise<ReportResponse> {
  const q: Record<string, string | number> = { ...PAGE };
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== '' && v !== null) q[k] = v;
  }
  const { data } = await api.get<ReportResponse>(`/accounting/reports/${report}/`, { params: q });
  return data;
}

// --- FX / revaluación ---
export interface FxRateRow {
  id?: number;
  rate_date: string;
  from_currency: string;
  to_currency: string;
  rate_type: string;
  rate: string;
}

export async function listFxRates(): Promise<FxRateRow[]> {
  const { data } = await api.get<Paginated<FxRateRow> | FxRateRow[]>('/accounting/fx-rates/', {
    params: PAGE,
  });
  return Array.isArray(data) ? data : data.results;
}

export async function upsertFxRate(input: FxRateRow): Promise<void> {
  await api.post('/accounting/fx-rates/', input);
}

export async function runRevaluation(input: { year: number; month: number }): Promise<Record<string, unknown>> {
  const { data } = await api.post<Record<string, unknown>>('/accounting/revaluation/run/', input);
  return data;
}

// --- Intercompany ---
export interface IntercompanyTx {
  id: number;
  status: string;
  amount: string;
  currency: string;
  description?: string;
  reference_code?: string;
  source_company_id?: number;
  target_company_id?: number;
  [k: string]: unknown;
}

export async function listIntercompanyTxs(): Promise<IntercompanyTx[]> {
  const { data } = await api.get<Paginated<IntercompanyTx> | IntercompanyTx[]>(
    '/accounting/intercompany/transactions/',
    { params: PAGE },
  );
  return Array.isArray(data) ? data : data.results;
}

export async function createIntercompanyTx(input: {
  target_company_id: number;
  amount: string;
  source_account_code: string;
  target_account_code: string;
  description?: string;
}): Promise<void> {
  await api.post('/accounting/intercompany/transactions/', input);
}

export async function intercompanyAction(
  txId: number,
  action: 'confirm' | 'reconcile' | 'settle' | 'close',
): Promise<void> {
  await api.post(`/accounting/intercompany/transactions/${txId}/${action}/`, {});
}

export async function disputeIntercompanyTx(txId: number, reason: string): Promise<void> {
  await api.post(`/accounting/intercompany/transactions/${txId}/dispute/`, { reason });
}
