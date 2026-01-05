import { isAxiosError } from 'axios';

type HasDetail = { detail?: unknown };

function tryDetail(data: unknown): string | null {
  if (!data || typeof data !== 'object') return null;
  const d = (data as HasDetail).detail;
  return typeof d === 'string' ? d : null;
}

export function extractErrorMessage(e: unknown): string {
  if (isAxiosError(e)) {
    const data = e.response?.data;
    if (typeof data === 'string') return data;
    const detail = tryDetail(data);
    if (detail) return detail;
    return e.message || 'Request failed';
  }
  if (e instanceof Error) return e.message;
  return String(e);
}
