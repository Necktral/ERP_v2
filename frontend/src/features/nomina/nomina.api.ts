/**
 * Nómina (planilla) — capa de datos tipada del kernel `nomina`.
 *
 * Flujo del planillero: config del año (una vez) → período → planilla(s) →
 * entradas (aplicar asistencia de campo o agregar manual) → calcular →
 * enviar/aprobar → exportar XLSX/PDF legal.
 */
import { api } from 'src/boot/axios';
import { PAGE, type Paginated } from 'src/core/api';

// --- Configuración (tasas + IR) ---------------------------------------------
export interface NominaConfig {
  id: number;
  fiscal_year: number;
  effective_from: string;
  is_active: boolean;
  inss_laboral_rate: string;
  inss_patronal_rate_small: string;
  inss_patronal_rate_large: string;
  inatec_rate: string;
  vacation_rate: string;
  thirteenth_month_rate: string;
  min_wage_agro: string;
  ir_brackets: { id: number; order: number; min_income: string; max_income: string | null; base_tax: string; rate: string }[];
}

export async function listConfigs(): Promise<NominaConfig[]> {
  const { data } = await api.get<Paginated<NominaConfig>>('/nomina/config/', { params: PAGE });
  return data.results;
}

export async function createDefaultConfig(fiscalYear?: number): Promise<NominaConfig> {
  const { data } = await api.post<NominaConfig>('/nomina/config/', fiscalYear ? { fiscal_year: fiscalYear } : {});
  return data;
}

// --- Períodos -----------------------------------------------------------------
export type PeriodType = 'FIRST_HALF' | 'SECOND_HALF' | 'CATORCENA' | 'MONTHLY';
export type PeriodStatus = 'DRAFT' | 'IN_REVIEW' | 'APPROVED' | 'PAID' | 'CLOSED';

export interface PayrollPeriod {
  id: number;
  year: number;
  month: number;
  period_type: PeriodType;
  start_date: string;
  end_date: string;
  working_days: number;
  exchange_rate_usd: string;
  status: PeriodStatus;
  total_gross: string;
  total_deductions: string;
  total_net: string;
  total_patronal: string;
  total_payroll_cost: string;
  notes: string;
}

export async function listPeriods(params: { year?: number; status?: string } = {}): Promise<PayrollPeriod[]> {
  const { data } = await api.get<Paginated<PayrollPeriod>>('/nomina/periods/', {
    params: { ...PAGE, ...params },
  });
  return data.results;
}

export async function createPeriod(input: {
  year: number;
  month: number;
  period_type: PeriodType;
  start_date: string;
  end_date: string;
  working_days?: number;
  exchange_rate_usd?: string | null;
  notes?: string;
}): Promise<PayrollPeriod> {
  const { data } = await api.post<PayrollPeriod>('/nomina/periods/', input);
  return data;
}

// --- Planillas (sheets) --------------------------------------------------------
export type SheetStatus = 'DRAFT' | 'SUBMITTED' | 'REVIEWED' | 'APPROVED' | 'REJECTED';

export interface PayrollSheet {
  id: number;
  sheet_name: string;
  has_inss: boolean;
  status: SheetStatus;
  entry_count: number;
  notes: string;
  submitted_at: string | null;
  approved_at: string | null;
}

export async function listSheets(periodId: number): Promise<PayrollSheet[]> {
  const { data } = await api.get<Paginated<PayrollSheet>>(`/nomina/periods/${periodId}/sheets/`, {
    params: PAGE,
  });
  return data.results;
}

export async function createSheet(
  periodId: number,
  input: { sheet_name: string; has_inss: boolean; branch_id?: number | null; notes?: string },
): Promise<PayrollSheet> {
  const { data } = await api.post<PayrollSheet>(`/nomina/periods/${periodId}/sheets/`, input);
  return data;
}

export async function sheetAction(
  periodId: number,
  sheetId: number,
  action: 'submit' | 'approve' | 'compute',
): Promise<{ computed?: number }> {
  const { data } = await api.post<{ computed?: number }>(
    `/nomina/periods/${periodId}/sheets/${sheetId}/${action}/`,
    {},
  );
  return data;
}

export async function applyFieldAttendance(sheetId: number): Promise<Record<string, unknown>> {
  const { data } = await api.post<Record<string, unknown>>(
    `/nomina/field/sheets/${sheetId}/apply-field-attendance/`,
    {},
  );
  return data;
}

// --- Entradas (líneas de planilla) ----------------------------------------------
/** Línea de planilla — MISMAS casillas que la planilla legal en Excel (carpeta excel/). */
export interface PayrollEntry {
  id: number;
  inss_number: string;
  cedula: string;
  full_name: string;
  gender: string;
  cargo: string;
  has_inss: boolean;
  salary_type: 'MONTHLY' | 'DAILY' | 'HOURLY';
  daily_rate_nio: string; // Salario Diario
  base_salary_nio: string; // Salario Mensual
  // INGRESOS
  quincenal_salary: string; // Salario del Período
  days_in_period: number;
  days_worked: string; // Días Laborados
  seventh_day_days: string; // Séptimo Día
  seventh_day_amount: string;
  holiday_amount: string;
  days_subsidy: string; // Días Subsidio
  subsidy_amount: string; // Subsidio
  vacation_provision: string; // Vacaciones (ingreso)
  thirteenth_month_provision: string; // 13vo Mes (ingreso)
  total_income: string; // Total Ingresos
  // RETENCIONES
  inss_laboral: string; // INSS
  ir_amount: string; // IR
  loan_payment: string; // Abono Préstamos
  total_deductions: string; // Total Retención
  // OTRAS DEDUCCIONES
  food_deduction: string; // Alimentación
  advance_deduction: string; // Adelanto Finca
  store_credit_deduction: string; // Crédito Comisariato
  // Totales
  total_devengado: string; // Salario Devengado
  net_to_pay: string; // Neto a Pagar
  // COSTOS PATRONALES
  inss_patronal: string;
  vacation_cost: string;
  thirteenth_month_cost: string;
  inatec: string; // INATEC 2%
  total_employer_cost: string;
  total_payroll_cost: string; // Total Gastos Nómina
  notes: string;
}

export async function listEntries(
  periodId: number,
  sheetId: number,
  search = '',
): Promise<PayrollEntry[]> {
  const { data } = await api.get<Paginated<PayrollEntry>>(
    `/nomina/periods/${periodId}/sheets/${sheetId}/entries/`,
    { params: { ...PAGE, ...(search ? { search } : {}) } },
  );
  return data.results;
}

export interface EntryInput {
  /** Con employee_id el backend autollena del expediente HR (cédula, INSS, género, cargo, salario). */
  employee_id?: number | null;
  /** Obligatorio solo para entradas manuales (sin expediente). */
  full_name?: string;
  cedula?: string;
  inss_number?: string;
  cargo?: string;
  has_inss?: boolean;
  salary_type?: 'MONTHLY' | 'DAILY' | 'HOURLY';
  payment_frequency: PeriodType;
  /** Mensuales: salario del mes. */
  base_salary_nio?: string;
  /** Jornaleros (DAILY): el jornal del día tal cual; el backend lo lleva a base mensual. */
  daily_rate_nio?: string;
  days_in_period: number;
  days_worked: string;
  notes?: string;
}

export async function createEntry(
  periodId: number,
  sheetId: number,
  input: EntryInput,
): Promise<PayrollEntry> {
  const { data } = await api.post<PayrollEntry>(
    `/nomina/periods/${periodId}/sheets/${sheetId}/entries/`,
    input,
  );
  return data;
}

// --- Export legal (XLSX / PDF) — vía blob para mantener cookies + contexto ------
export async function downloadPlanilla(
  periodId: number,
  sheetId: number,
  format: 'xlsx' | 'pdf',
): Promise<void> {
  const url = `/nomina/periods/${periodId}/sheets/${sheetId}/planilla.${format}`;
  const { data } = await api.get<Blob>(url, { responseType: 'blob' });
  const objectUrl = URL.createObjectURL(data);
  const a = document.createElement('a');
  a.href = objectUrl;
  a.download = `planilla_${periodId}_${sheetId}.${format}`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(objectUrl);
}
