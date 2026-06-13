/**
 * Controles anti-fraude — reglas SoD (qué pares de permisos no pueden convivir),
 * violaciones vivas por concesión y hallazgos materializados con triage.
 */
import { api } from 'src/boot/axios';
import { PAGE, type Paginated } from 'src/core/api';

export const FINDING_STATUS_LABELS: Record<string, string> = {
  OPEN: 'Abierto',
  ACKNOWLEDGED: 'Reconocido',
  RESOLVED: 'Resuelto',
  DISMISSED: 'Descartado',
};

export const SEVERITY_LABELS: Record<string, string> = {
  LOW: 'Baja',
  MEDIUM: 'Media',
  HIGH: 'Alta',
  CRITICAL: 'Crítica',
};

export interface SodRule {
  id: number;
  code: string;
  permission_a: string;
  permission_b: string;
  severity: string;
  description?: string;
  [k: string]: unknown;
}

export interface SodViolation {
  user_id: number;
  username: string;
  rule_code: string;
  permission_a: string;
  permission_b: string;
  severity: string;
}

export interface ControlFinding {
  id: number;
  control_code: string;
  status: string;
  severity: string;
  detected_at?: string;
  [k: string]: unknown;
}

export async function listSodRules(): Promise<SodRule[]> {
  const { data } = await api.get<{ results: SodRule[] }>('/controls/sod/rules/');
  return data.results;
}

export async function listSodViolations(): Promise<SodViolation[]> {
  const { data } = await api.get<{ results: SodViolation[] }>('/controls/sod/violations/');
  return data.results;
}

export async function runControlScan(windowDays = 90): Promise<{ created: number }> {
  const { data } = await api.post<{ created: number }>('/controls/scan/', {
    window_days: windowDays,
  });
  return data;
}

export async function listFindings(status?: string): Promise<ControlFinding[]> {
  const params: Record<string, string | number> = { ...PAGE };
  if (status) params.status = status;
  const { data } = await api.get<Paginated<ControlFinding>>('/controls/findings/', { params });
  return data.results;
}

export async function resolveFinding(
  findingId: number,
  status: 'ACKNOWLEDGED' | 'RESOLVED' | 'DISMISSED',
  note = '',
): Promise<void> {
  await api.post(`/controls/findings/${findingId}/resolve/`, { status, note });
}
