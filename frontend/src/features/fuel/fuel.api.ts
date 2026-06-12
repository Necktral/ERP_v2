/**
 * Estación de servicio (fuel) — turno del día: abrir → despachos por surtidor →
 * ventas (interna/empleado/público) → cierre con reporte. Litros o galones según
 * preferencia.
 */
import { api } from 'src/boot/axios';
import { PAGE, type Paginated } from 'src/core/api';

export const FUEL_PRODUCT_LABELS: Record<string, string> = {
  DIESEL: 'Diésel',
  GASOLINE: 'Gasolina',
};

export const FUEL_SALE_TYPE_LABELS: Record<string, string> = {
  INTERNAL: 'Consumo interno',
  EMPLOYEE: 'Empleado',
  PUBLIC: 'Público',
};

export const FUEL_PAYMENT_LABELS: Record<string, string> = {
  CASH: 'Efectivo',
  TRANSFER: 'Transferencia',
  CREDIT: 'Crédito',
};

export const FUEL_SALE_STATUS_LABELS: Record<string, string> = {
  ACTIVE: 'Activa',
  COMPENSATING: 'Compensando',
  CANCELLED: 'Cancelada',
  COMPENSATION_FAILED: 'Compensación fallida',
};

export const VOLUME_UOM_LABELS: Record<string, string> = {
  LITER: 'Litros',
  GALLON: 'Galones',
  GALLON_US: 'Galones US',
};

export interface FuelShift {
  id: number;
  status: 'OPEN' | 'CLOSED';
  opened_at: string;
  closed_at: string | null;
  opened_by_id: number | null;
  closed_by_id: number | null;
  note?: string;
}

export interface FuelDispense {
  id: number;
  shift: number;
  product: string;
  liters: string;
  volume_entered?: string;
  uom_entered?: string;
  unit_price: string;
  amount: string;
  vehicle_plate: string;
  driver_name: string;
  pump_code: string;
  occurred_at: string;
}

export interface FuelSale {
  id: number;
  shift: number;
  dispense: number;
  sale_type: string;
  payment_method: string;
  customer_name: string;
  customer_party: number | null;
  total_amount: string;
  status: string;
  created_at: string;
}

// --- Turnos ---
export async function listShifts(): Promise<FuelShift[]> {
  const { data } = await api.get<Paginated<FuelShift>>('/fuel/shifts/', { params: PAGE });
  return data.results;
}

export async function openShift(note = ''): Promise<FuelShift> {
  const { data } = await api.post<FuelShift>('/fuel/shifts/open/', note ? { note } : {});
  return data;
}

export async function closeShift(shiftId: number, note = ''): Promise<FuelShift> {
  const { data } = await api.post<FuelShift>(`/fuel/shifts/${shiftId}/close/`, note ? { note } : {});
  return data;
}

// --- Despachos ---
export async function listDispenses(shiftId?: number): Promise<FuelDispense[]> {
  const params: Record<string, string | number> = { ...PAGE };
  if (shiftId) params.shift_id = shiftId;
  const { data } = await api.get<Paginated<FuelDispense>>('/fuel/dispenses/', { params });
  return data.results;
}

export async function createDispense(input: {
  shift_id: number;
  product: string;
  volume: string;
  volume_uom: string;
  unit_price: string;
  unit_price_uom: string;
  vehicle_plate?: string;
  driver_name?: string;
  pump_code?: string;
  note?: string;
}): Promise<FuelDispense> {
  const { data } = await api.post<FuelDispense>('/fuel/dispenses/', input);
  return data;
}

// --- Ventas ---
export async function listSales(shiftId?: number): Promise<FuelSale[]> {
  const params: Record<string, string | number> = { ...PAGE };
  if (shiftId) params.shift_id = shiftId;
  const { data } = await api.get<Paginated<FuelSale>>('/fuel/sales/', { params });
  return data.results;
}

export async function createSale(input: {
  shift_id: number;
  dispense_id: number;
  sale_type: string;
  payment_method: string;
  customer_name?: string;
  customer_party_id?: number;
}): Promise<FuelSale> {
  const { data } = await api.post<FuelSale>('/fuel/sales/', {
    ...input,
    idempotency_key: crypto.randomUUID(),
  });
  return data;
}

export async function cancelSale(saleId: number, reason: string): Promise<void> {
  await api.post(`/fuel/sales/${saleId}/cancel/`, { reason });
}

export async function retrySaleCompensation(saleId: number): Promise<void> {
  await api.post(`/fuel/sales/${saleId}/compensate/retry/`, {});
}

// --- Reportes ---
export async function getShiftCloseReport(shiftId: number): Promise<Record<string, unknown>> {
  const { data } = await api.get<Record<string, unknown>>(`/fuel/reports/shift-close/${shiftId}/`);
  return data;
}

export async function getDailyCloseReport(date?: string): Promise<Record<string, unknown>> {
  const { data } = await api.get<Record<string, unknown>>('/fuel/reports/daily-close/', {
    params: date ? { date } : {},
  });
  return data;
}

// --- Preferencias UoM (por usuario y sucursal) ---
export interface UomPreferences {
  gasoline_volume_uom: string;
  diesel_volume_uom: string;
}

export async function getUomPreferences(): Promise<UomPreferences> {
  const { data } = await api.get<UomPreferences>('/fuel/uom-preferences/');
  return data;
}

export async function updateUomPreferences(prefs: Partial<UomPreferences>): Promise<UomPreferences> {
  const { data } = await api.put<UomPreferences>('/fuel/uom-preferences/', prefs);
  return data;
}
