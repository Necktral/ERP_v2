/**
 * Finca (manejo agrícola) — fincas (sucursales con perfil agrícola), lotes de
 * cultivo, catálogo de labores y órdenes de trabajo con insumos. El costeo
 * real por lote/finca se puede contabilizar a GL.
 */
import { api } from 'src/boot/axios';
import { PAGE, type Paginated } from 'src/core/api';

export const LABOR_CATEGORY_LABELS: Record<string, string> = {
  ESTABLECIMIENTO: 'Establecimiento',
  MANTENIMIENTO: 'Mantenimiento',
  SANIDAD: 'Sanidad',
  COSECHA: 'Cosecha',
  BENEFICIADO: 'Beneficiado',
  INFRAESTRUCTURA: 'Infraestructura',
};

export const LABOR_UNIT_LABELS: Record<string, string> = {
  JORNAL: 'Jornal',
  MANZANA: 'Manzana',
  LATA: 'Lata',
  QUINTAL: 'Quintal',
  HORA: 'Hora',
};

export const WORK_ORDER_STATUS_LABELS: Record<string, string> = {
  PLANNED: 'Planificada',
  IN_PROGRESS: 'En ejecución',
  DONE: 'Terminada',
  CANCELLED: 'Cancelada',
};

export interface FincaRow {
  finca_id: number;
  name?: string;
  department?: string;
  municipio?: string;
  zona?: string;
  area_manzanas?: string;
  is_headquarters?: boolean;
  [k: string]: unknown;
}

export interface Plot {
  id: number;
  finca: number;
  code: string;
  name: string;
  area_manzanas: string;
  crop: string;
  variety: string;
  planting_year: number | null;
  is_active: boolean;
}

export interface Labor {
  id: number;
  code: string;
  name: string;
  category: string;
  unit: string;
  is_piecework: boolean;
  default_rate: string | null;
  is_active: boolean;
  is_global: boolean;
}

export interface WorkOrder {
  id: number;
  finca: number;
  plot: number;
  labor: number;
  season_label: string;
  planned_date: string | null;
  done_date: string | null;
  status: string;
  target_quantity: string | null;
  actual_quantity: string | null;
  jornales: string;
  notes: string;
}

export async function listFincas(): Promise<FincaRow[]> {
  const { data } = await api.get<{ results: FincaRow[] }>('/finca/fincas/');
  return data.results ?? [];
}

export async function getFincaProfile(fincaId: number): Promise<FincaRow> {
  const { data } = await api.get<FincaRow>(`/finca/fincas/${fincaId}/profile/`);
  return data;
}

export async function updateFincaProfile(fincaId: number, input: Partial<FincaRow>): Promise<FincaRow> {
  const { data } = await api.put<FincaRow>(`/finca/fincas/${fincaId}/profile/`, input);
  return data;
}

// --- Lotes ---
export async function listPlots(fincaId?: number): Promise<Plot[]> {
  const params: Record<string, string | number> = { ...PAGE };
  if (fincaId) params.finca_id = fincaId;
  const { data } = await api.get<Paginated<Plot>>('/finca/plots/', { params });
  return data.results;
}

export async function createPlot(input: {
  finca_id: number;
  code: string;
  name?: string;
  area_manzanas?: string;
  crop?: string;
  variety?: string;
  planting_year?: number | null;
}): Promise<Plot> {
  const { data } = await api.post<Plot>('/finca/plots/', input);
  return data;
}

export async function updatePlot(plotId: number, patch: Partial<Plot>): Promise<Plot> {
  const { data } = await api.patch<Plot>(`/finca/plots/${plotId}/`, patch);
  return data;
}

// --- Labores ---
export async function listLabors(): Promise<Labor[]> {
  const { data } = await api.get<Paginated<Labor>>('/finca/labors/', { params: PAGE });
  return data.results;
}

export async function createLabor(input: {
  code: string;
  name: string;
  category: string;
  unit: string;
  is_piecework?: boolean;
  default_rate?: string | null;
}): Promise<Labor> {
  const { data } = await api.post<Labor>('/finca/labors/', input);
  return data;
}

// --- Órdenes de trabajo ---
export async function listWorkOrders(filters: {
  finca_id?: number;
  plot_id?: number;
  status?: string;
} = {}): Promise<WorkOrder[]> {
  const params: Record<string, string | number> = { ...PAGE };
  for (const [k, v] of Object.entries(filters)) {
    if (v) params[k] = v;
  }
  const { data } = await api.get<Paginated<WorkOrder>>('/finca/work-orders/', { params });
  return data.results;
}

export async function createWorkOrder(input: {
  plot_id: number;
  labor_id: number;
  season_label?: string;
  planned_date?: string | null;
  target_quantity?: string | null;
  notes?: string;
}): Promise<WorkOrder> {
  const { data } = await api.post<WorkOrder>('/finca/work-orders/', input);
  return data;
}

export async function updateWorkOrder(
  woId: number,
  patch: {
    status?: string;
    done_date?: string | null;
    actual_quantity?: string | null;
    jornales?: string;
    notes?: string;
  },
): Promise<WorkOrder> {
  const { data } = await api.patch<WorkOrder>(`/finca/work-orders/${woId}/`, patch);
  return data;
}

export async function addInsumoManual(
  woId: number,
  input: { item_name: string; quantity: string; unit?: string; unit_cost?: string | null },
): Promise<void> {
  await api.post(`/finca/work-orders/${woId}/insumos/`, input);
}

export async function issueInsumoFromStock(
  woId: number,
  input: { warehouse_id: number; item_id: number; quantity: string; note?: string },
): Promise<void> {
  await api.post(`/finca/work-orders/${woId}/issue-insumo/`, {
    ...input,
    idempotency_key: crypto.randomUUID(),
  });
}

// --- Costeo ---
export async function getFincaCostReport(params: {
  finca_id?: number;
  date_from?: string;
  date_to?: string;
} = {}): Promise<Record<string, unknown>> {
  const q: Record<string, string | number> = {};
  for (const [k, v] of Object.entries(params)) {
    if (v) q[k] = v;
  }
  const { data } = await api.get<Record<string, unknown>>('/finca/reports/finca-cost/', { params: q });
  return data;
}

export async function postFincaCostToGL(input: {
  finca_id: number;
  season?: string;
  date_from?: string;
  date_to?: string;
}): Promise<Record<string, unknown>> {
  const { data } = await api.post<Record<string, unknown>>('/finca/reports/finca-cost/post/', input);
  return data;
}

// --- Presupuesto agrícola (Ola G) -------------------------------------------
export interface FincaBudgetRow {
  id: number;
  finca_id: number;
  finca_name: string;
  season_label: string;
  name: string;
  status: 'DRAFT' | 'APPROVED' | 'ARCHIVED';
  status_label: string;
  created_at: string;
  approved_at: string | null;
}

export interface FincaBudgetLineRow {
  id: number;
  labor_id: number;
  labor_name: string;
  plot_id: number;
  plot_code: string;
  planned_jornales: string;
  planned_rate: string;
  planned_insumos_amount: string;
  planned_total: string;
}

export interface FincaBudgetVsActualRow {
  labor_id: number;
  labor_name: string;
  plot_id: number;
  plot_code: string;
  planned_jornales: string;
  planned_total: string;
  actual_jornales: string;
  actual_labor: string;
  actual_insumos: string;
  actual_total: string;
  variance: string;
  variance_pct: string | null;
}

export interface FincaBudgetVsActual {
  budget_id: number;
  season_label: string;
  status: string;
  rows: FincaBudgetVsActualRow[];
  total_planned: string;
  total_actual: string;
  total_variance: string;
}

export async function listFincaBudgets(fincaId?: number): Promise<FincaBudgetRow[]> {
  const qs = fincaId ? `?finca_id=${fincaId}` : '';
  const { data } = await api.get<{ results: FincaBudgetRow[] }>(`/finca/budgets/${qs}`);
  return data.results;
}

export async function getFincaBudget(budgetId: number): Promise<FincaBudgetRow & { lines: FincaBudgetLineRow[] }> {
  const { data } = await api.get<FincaBudgetRow & { lines: FincaBudgetLineRow[] }>(`/finca/budgets/${budgetId}/`);
  return data;
}

export async function createFincaBudget(input: {
  finca_id: number;
  season_label: string;
  name: string;
}): Promise<FincaBudgetRow> {
  const { data } = await api.post<FincaBudgetRow>('/finca/budgets/', input);
  return data;
}

export async function setFincaBudgetLines(
  budgetId: number,
  lines: Array<{
    labor_id: number;
    plot_id: number;
    planned_jornales?: string;
    planned_rate?: string;
    planned_insumos_amount?: string;
  }>,
): Promise<FincaBudgetRow & { lines: FincaBudgetLineRow[] }> {
  const { data } = await api.put<FincaBudgetRow & { lines: FincaBudgetLineRow[] }>(
    `/finca/budgets/${budgetId}/lines/`,
    { lines },
  );
  return data;
}

export async function approveFincaBudget(budgetId: number): Promise<FincaBudgetRow> {
  const { data } = await api.post<FincaBudgetRow>(`/finca/budgets/${budgetId}/approve/`, {});
  return data;
}

export async function getFincaBudgetVsActual(budgetId: number): Promise<FincaBudgetVsActual> {
  const { data } = await api.get<FincaBudgetVsActual>(`/finca/budgets/${budgetId}/vs-actual/`);
  return data;
}
