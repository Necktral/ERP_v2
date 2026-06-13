/**
 * Auditoría — bitácora inmutable con cadena criptográfica. Solo lectura;
 * paginación por cursor del backend.
 */
import { api } from 'src/boot/axios';

export interface AuditEventRow {
  event_id: string;
  module: string;
  event_type: string;
  reason_code: string;
  timestamp_server: string;
  actor_user: number | null;
  device_id: string;
  ip_server_seen: string;
  offline_mode: boolean;
  path: string;
  [k: string]: unknown;
}

export interface BitacoraFilters {
  event_type?: string;
  module?: string;
  actor_user_id?: string;
  subject_type?: string;
  subject_id?: string;
  device_id?: string;
  ip?: string;
  path_contains?: string;
  after?: string;
  before?: string;
}

export interface BitacoraPage {
  next: string | null;
  previous: string | null;
  results: AuditEventRow[];
}

export async function listBitacora(
  filters: BitacoraFilters = {},
  cursor?: string,
): Promise<BitacoraPage> {
  const params: Record<string, string | number> = { page_size: 100 };
  for (const [k, v] of Object.entries(filters)) {
    if (v) params[k] = v;
  }
  if (cursor) params.cursor = cursor;
  const { data } = await api.get<BitacoraPage>('/audit/bitacora/', { params });
  return data;
}

export async function getAuditEvent(eventId: string): Promise<Record<string, unknown>> {
  const { data } = await api.get<Record<string, unknown>>(`/audit/events/${eventId}/`);
  return data;
}
