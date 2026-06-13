/**
 * Utilidades compartidas de la capa de datos (todas las features/*.api.ts
 * importan de aquí; ninguna define las suyas propias).
 */

/** Envelope de paginación estándar del backend ({count, limit, offset, results}). */
export interface Paginated<T> {
  count: number;
  limit: number;
  offset: number;
  results: T[];
}

/** Página por defecto para listados de catálogo (trae todo de una vez). */
export const PAGE = { limit: 200, offset: 0 } as const;

/**
 * Extrae un mensaje legible del envelope de error de DRF:
 * `detail` si existe; si no, el primer error de campo como "campo: mensaje".
 */
export function apiErrorMessage(e: unknown, fallback = ''): string {
  const err = e as { response?: { data?: Record<string, unknown> } };
  const data = err.response?.data;
  if (data && typeof data === 'object') {
    if (typeof data.detail === 'string') return data.detail;
    for (const k of Object.keys(data)) {
      const v = data[k];
      if (Array.isArray(v) && v.length) return `${k}: ${String(v[0])}`;
      if (typeof v === 'string') return `${k}: ${v}`;
    }
  }
  return fallback;
}
