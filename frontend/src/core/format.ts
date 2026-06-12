/**
 * Formato compartido de números y fechas (es-NI). Toda página formatea con esto;
 * nada de toFixed sueltos por el código.
 */

const moneyFmt = new Intl.NumberFormat('es-NI', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const qtyFmt = new Intl.NumberFormat('es-NI', { minimumFractionDigits: 0, maximumFractionDigits: 4 });

/** "12345.5" → "C$ 12,345.50" (el backend manda decimales como string). */
export function formatMoney(value: string | number | null | undefined, symbol = 'C$'): string {
  const n = Number(value ?? 0);
  if (!Number.isFinite(n)) return `${symbol} 0.00`;
  return `${symbol} ${moneyFmt.format(n)}`;
}

/** Cantidades: hasta 4 decimales, sin ceros de relleno. */
export function formatQty(value: string | number | null | undefined): string {
  const n = Number(value ?? 0);
  if (!Number.isFinite(n)) return '0';
  return qtyFmt.format(n);
}

/** "2026-06-11" o ISO completo → "11/06/2026". */
export function formatDate(value: string | null | undefined): string {
  if (!value) return '—';
  const d = new Date(value.length === 10 ? `${value}T00:00:00` : value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString('es-NI', { day: '2-digit', month: '2-digit', year: 'numeric' });
}

/** ISO → "11/06/2026 14:30". */
export function formatDateTime(value: string | null | undefined): string {
  if (!value) return '—';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString('es-NI', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });
}
