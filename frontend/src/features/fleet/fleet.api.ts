/**
 * Flota (fleet) — vehículos y maquinaria: lecturas de odómetro/horómetro,
 * documentos con vencimiento (seguro, circulación…) y planes de mantenimiento
 * con alertas. Los listados devuelven array plano.
 */
import { api } from 'src/boot/axios';

export const ASSET_TYPE_LABELS: Record<string, string> = {
  VEHICLE: 'Vehículo',
  MACHINERY: 'Maquinaria',
  STATIONARY: 'Estacionario',
};

export const ASSET_STATUS_LABELS: Record<string, string> = {
  ACTIVE: 'Activo',
  IN_SERVICE: 'En servicio',
  MAINTENANCE_DUE: 'Mantenimiento vencido',
  IN_MAINTENANCE: 'En mantenimiento',
  OUT_OF_SERVICE: 'Fuera de servicio',
  RETIRED: 'Retirado',
};

export const FLEET_DOC_TYPE_LABELS: Record<string, string> = {
  INSURANCE: 'Seguro',
  CIRCULATION: 'Circulación',
  LICENSE: 'Licencia',
  TECH_REVIEW: 'Revisión técnica',
  OTHER: 'Otro',
};

export const FLEET_DOC_STATUS_LABELS: Record<string, string> = {
  VALID: 'Vigente',
  EXPIRING: 'Por vencer',
  EXPIRED: 'Vencido',
};

export interface FleetAsset {
  id: number;
  code: string;
  name: string;
  asset_type: string;
  status: string;
  plate: string;
  make: string;
  model: string;
  year: number | null;
  current_odometer_km: string;
  current_hourmeter: string;
  branch_id: number | null;
}

export interface FleetDriver {
  id: number;
  full_name: string;
  national_id: string;
  license_number: string;
  license_category: string;
  license_expiry: string | null;
  status: string;
  employee_id: number | null;
}

export interface FleetDocument {
  id: number;
  doc_type: string;
  status: string;
  expiry_date: string | null;
  asset_id: number | null;
  driver_id: number | null;
}

export interface MaintenanceTypeRow {
  id: number;
  code: string;
  name: string;
  kind: string;
  trigger_basis: string;
}

export interface MaintenancePlanRow {
  id: number;
  name: string;
  asset_class: string;
  is_active: boolean;
}

// --- Activos ---
export async function listAssets(): Promise<FleetAsset[]> {
  const { data } = await api.get<FleetAsset[]>('/fleet/assets/');
  return data;
}

export async function upsertAsset(input: {
  code: string;
  name: string;
  asset_type: string;
  plate?: string;
  make?: string;
  model?: string;
  year?: number | null;
  fuel_type?: string;
  meter_basis?: string;
}): Promise<FleetAsset> {
  const { data } = await api.post<FleetAsset>('/fleet/assets/', input);
  return data;
}

export async function recordMeterReading(input: {
  asset_id: number;
  odometer_km?: string;
  hourmeter?: string;
}): Promise<Record<string, unknown>> {
  const { data } = await api.post<Record<string, unknown>>('/fleet/meter-readings/', input);
  return data;
}

// --- Conductores ---
export async function listDrivers(): Promise<FleetDriver[]> {
  const { data } = await api.get<FleetDriver[]>('/fleet/drivers/');
  return data;
}

export async function upsertDriver(input: {
  full_name: string;
  national_id?: string;
  license_number?: string;
  license_category?: string;
  license_expiry?: string | null;
  employee_id?: number | null;
}): Promise<{ id: number }> {
  const { data } = await api.post<{ id: number }>('/fleet/drivers/', input);
  return data;
}

export async function assignDriver(assetId: number, driverId: number): Promise<void> {
  await api.post('/fleet/driver-assignments/', { asset_id: assetId, driver_id: driverId });
}

// --- Documentos ---
export async function listFleetDocuments(status?: string): Promise<FleetDocument[]> {
  const { data } = await api.get<FleetDocument[]>('/fleet/documents/', {
    params: status ? { status } : {},
  });
  return data;
}

export async function registerFleetDocument(input: {
  doc_type: string;
  asset_id?: number | null;
  driver_id?: number | null;
  number?: string;
  issuer?: string;
  issue_date?: string;
  expiry_date?: string;
}): Promise<void> {
  await api.post('/fleet/documents/', input);
}

// --- Mantenimiento ---
export async function listMaintenanceTypes(): Promise<MaintenanceTypeRow[]> {
  const { data } = await api.get<MaintenanceTypeRow[]>('/fleet/maintenance/types/');
  return data;
}

export async function createMaintenanceType(input: {
  code: string;
  name: string;
  kind?: string;
  trigger_basis?: string;
}): Promise<void> {
  await api.post('/fleet/maintenance/types/', input);
}

export async function listMaintenancePlans(): Promise<MaintenancePlanRow[]> {
  const { data } = await api.get<MaintenancePlanRow[]>('/fleet/maintenance/plans/');
  return data;
}

export async function createMaintenancePlan(input: { name: string; asset_class?: string }): Promise<void> {
  await api.post('/fleet/maintenance/plans/', input);
}

export async function addMaintenanceRule(input: {
  plan_id: number;
  maintenance_type_id: number;
  trigger_basis: string;
  interval_km?: number | null;
  interval_hours?: number | null;
  interval_days?: number | null;
}): Promise<void> {
  await api.post('/fleet/maintenance/rules/', input);
}

export async function applyMaintenancePlan(assetId: number, planId: number): Promise<void> {
  await api.post('/fleet/maintenance/apply-plan/', { asset_id: assetId, plan_id: planId });
}

export async function runFleetAlerts(horizonDays = 30): Promise<Record<string, unknown>> {
  const { data } = await api.post<Record<string, unknown>>('/fleet/alerts/run/', {
    horizon_days: horizonDays,
  });
  return data;
}
