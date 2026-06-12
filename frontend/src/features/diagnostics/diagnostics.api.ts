/**
 * Diagnóstico — supervisión técnica: errores de runtime (C1/C2/C3), diagnóstico
 * determinista + análisis IA opcional, hallazgos de seguridad y kill switch IA.
 */
import { api } from 'src/boot/axios';
import { PAGE } from 'src/core/api';

export const RISK_LABELS: Record<string, string> = {
  C1: 'C1 (crítico)',
  C2: 'C2 (alto)',
  C3: 'C3 (normal)',
};

export const ERROR_STATUS_LABELS: Record<string, string> = {
  open: 'Abierto',
  triaged: 'En triage',
  confirmed: 'Confirmado',
  fixed: 'Corregido',
  regressed: 'Regresó',
  accepted_risk: 'Riesgo aceptado',
  false_positive: 'Falso positivo',
};

export interface ErrorEventRow {
  id: number;
  risk_class: string;
  status: string;
  domain: string;
  exception_type?: string;
  message?: string;
  occurrences?: number;
  last_seen_at?: string;
  [k: string]: unknown;
}

export interface SecurityFindingRow {
  id: number;
  status: string;
  severity?: string;
  title?: string;
  source?: string;
  [k: string]: unknown;
}

export async function listErrors(filters: { risk_class?: string; status?: string } = {}): Promise<
  ErrorEventRow[]
> {
  const params: Record<string, string | number> = { ...PAGE };
  if (filters.risk_class) params.risk_class = filters.risk_class;
  if (filters.status) params.status = filters.status;
  const { data } = await api.get<{ results: ErrorEventRow[] }>('/diagnostics/errors/', { params });
  return data.results;
}

export async function diagnoseError(errorId: number): Promise<Record<string, unknown>> {
  const { data } = await api.post<Record<string, unknown>>(`/diagnostics/errors/${errorId}/diagnose/`, {});
  return data;
}

export async function triageError(errorId: number, status: string): Promise<void> {
  await api.post(`/diagnostics/errors/${errorId}/triage/`, { status });
}

export async function listSecurityFindings(): Promise<SecurityFindingRow[]> {
  const { data } = await api.get<{ results: SecurityFindingRow[] }>('/diagnostics/findings/', {
    params: PAGE,
  });
  return data.results;
}

export async function triageSecurityFinding(findingId: number, status: string): Promise<void> {
  await api.post(`/diagnostics/findings/${findingId}/triage/`, { status });
}

export async function getReleaseReadiness(): Promise<Record<string, unknown>> {
  const { data } = await api.get<Record<string, unknown>>('/diagnostics/release-readiness/');
  return data;
}

export async function getSupervision(): Promise<Record<string, unknown>> {
  const { data } = await api.get<Record<string, unknown>>('/diagnostics/supervision/');
  return data;
}

export async function getAiControl(): Promise<{ enabled: boolean }> {
  const { data } = await api.get<{ ai_enabled: boolean }>('/diagnostics/ai-control/');
  return { enabled: Boolean(data.ai_enabled) };
}

export async function setAiControl(enabled: boolean, reason = ''): Promise<void> {
  await api.post('/diagnostics/ai-control/', { enabled, reason });
}
