/**
 * CEC (cierre contable orquestado) — corridas CREADA→RECOLECTADA→VALIDADA→
 * EMPAQUETADA→ENTREGADA (o reabierta por excepción) y excepciones con resolución.
 */
import { api } from 'src/boot/axios';
import { PAGE, type Paginated } from 'src/core/api';

export const CLOSE_RUN_STATUS_LABELS: Record<string, string> = {
  CREATED: 'Creada',
  GATHERED: 'Recolectada',
  VALIDATED: 'Validada',
  PACKAGED: 'Empaquetada',
  DELIVERED: 'Entregada',
  REOPENED_EXCEPTION: 'Reabierta (excepción)',
};

export const CEC_STATUS_ORDER = ['CREATED', 'GATHERED', 'VALIDATED', 'PACKAGED', 'DELIVERED'];

export const CEC_SEVERITY_LABELS: Record<string, string> = {
  LOW: 'Baja',
  MEDIUM: 'Media',
  HIGH: 'Alta',
  CRITICAL: 'Crítica',
};

export interface CloseRunRow {
  run_id: string;
  run_type: string;
  status: string;
  created_at?: string;
  [k: string]: unknown;
}

export interface CecException {
  id: number;
  source_module: string;
  code: string;
  severity: string;
  status: string;
  resolution_note?: string;
  [k: string]: unknown;
}

export async function listCloseRuns(): Promise<CloseRunRow[]> {
  const { data } = await api.get<Paginated<CloseRunRow>>('/cec/close-runs/', { params: PAGE });
  return data.results;
}

export async function createCloseRun(runType: 'DAILY' | 'PERIODIC'): Promise<CloseRunRow> {
  const { data } = await api.post<CloseRunRow>('/cec/close-runs/', { run_type: runType });
  return data;
}

export async function advanceCloseRun(runId: string, status: string): Promise<CloseRunRow> {
  const { data } = await api.post<CloseRunRow>(`/cec/close-runs/${runId}/advance/`, { status });
  return data;
}

export async function executeCloseRun(
  runId: string,
  windowStart: string,
  windowEnd: string,
): Promise<Record<string, unknown>> {
  const { data } = await api.post<Record<string, unknown>>(`/cec/close-runs/${runId}/execute/`, {
    window_start: windowStart,
    window_end: windowEnd,
  });
  return data;
}

export async function getCloseRunSummary(runId: string): Promise<Record<string, unknown>> {
  const { data } = await api.get<Record<string, unknown>>(`/cec/close-runs/${runId}/summary/`);
  return data;
}

export async function explainCloseRun(runId: string): Promise<Record<string, unknown>> {
  const { data } = await api.get<Record<string, unknown>>(`/cec/close-runs/${runId}/explain/`);
  return data;
}

export async function listCecExceptions(): Promise<CecException[]> {
  const { data } = await api.get<Paginated<CecException>>('/cec/exceptions/', { params: PAGE });
  return data.results;
}

export async function resolveCecException(excId: number, note: string): Promise<void> {
  await api.post(`/cec/exceptions/${excId}/resolve/`, { resolution_note: note });
}
