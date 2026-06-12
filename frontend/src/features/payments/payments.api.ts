/**
 * Caja y Pagos (kernel payments) — sesiones de caja (abrir → movimientos →
 * arqueo por denominación → cerrar) e intenciones de pago. Reembolso y
 * reapertura son SoD: una persona solicita, OTRA aprueba.
 */
import { api } from 'src/boot/axios';
import { PAGE, type Paginated } from 'src/core/api';

// --- Sesiones de caja --------------------------------------------------------
export const CASH_SESSION_STATUS_LABELS: Record<string, string> = {
  OPEN: 'Abierta',
  COUNT_PENDING: 'Pendiente de conteo',
  REVIEW_PENDING: 'Pendiente de revisión',
  CLOSED: 'Cerrada',
  REOPENED_FOR_INVESTIGATION: 'Reabierta (investigación)',
};

export const CASH_MOVEMENT_TYPE_LABELS: Record<string, string> = {
  INCOME: 'Ingreso',
  EXPENSE: 'Egreso',
  ADJUSTMENT: 'Ajuste',
  REFUND: 'Reembolso',
};

export interface CashSessionRow {
  id: number;
  status: string;
  opening_amount: string;
  expected_amount: string;
  counted_amount: string | null;
  difference_amount: string | null;
  opened_at: string;
  closed_at: string | null;
}

export interface CashSession extends CashSessionRow {
  opened_by_id: number | null;
  closed_by_id: number | null;
  notes: string;
  register_id: string;
}

export interface CashMovementRow {
  id: number;
  movement_type: string;
  amount: string;
  reference: string;
  created_at: string;
}

export interface Denomination {
  denomination_type: 'BILL' | 'COIN';
  denomination_value: string;
  quantity: number;
}

export async function listCashSessions(): Promise<CashSessionRow[]> {
  const { data } = await api.get<Paginated<CashSessionRow>>('/payments/cash-sessions/', {
    params: PAGE,
  });
  return data.results;
}

export async function openCashSession(input: {
  opening_amount?: string;
  notes?: string;
}): Promise<{ id: number; status: string }> {
  const { data } = await api.post<{ id: number; status: string }>(
    '/payments/cash-sessions/open/',
    input,
  );
  return data;
}

export async function getCashSession(sessionId: number): Promise<CashSession> {
  const { data } = await api.get<CashSession>(`/payments/cash-sessions/${sessionId}/`);
  return data;
}

export async function closeCashSession(
  sessionId: number,
  input: { counted_amount: string; notes?: string },
): Promise<{ id: number; status: string; expected_amount: string; counted_amount: string; difference_amount: string }> {
  const { data } = await api.post(`/payments/cash-sessions/${sessionId}/close/`, input);
  return data as {
    id: number;
    status: string;
    expected_amount: string;
    counted_amount: string;
    difference_amount: string;
  };
}

export async function submitDenominations(
  sessionId: number,
  denominations: Denomination[],
): Promise<{ counted_total: string }> {
  const { data } = await api.post(`/payments/cash-sessions/${sessionId}/denomination/`, {
    denominations,
  });
  return data as { counted_total: string };
}

export async function listCashMovements(sessionId: number): Promise<CashMovementRow[]> {
  const { data } = await api.get<Paginated<CashMovementRow>>(
    `/payments/cash-sessions/${sessionId}/movements/`,
    { params: PAGE },
  );
  return data.results;
}

export async function createCashMovement(
  sessionId: number,
  input: { movement_type: string; amount: string; reference?: string; reason?: string },
): Promise<{ id: number }> {
  const { data } = await api.post<{ id: number }>(
    `/payments/cash-sessions/${sessionId}/movements/`,
    { ...input, idempotency_key: crypto.randomUUID() },
  );
  return data;
}

/** SoD maker: solicita reabrir una sesión cerrada; la aprueba otra persona. */
export async function requestReopenCashSession(
  sessionId: number,
  reason: string,
): Promise<{ approval_request_id: string }> {
  const { data } = await api.post<{ approval_request_id: string }>(
    `/payments/cash-sessions/${sessionId}/reopen/`,
    { reason },
  );
  return data;
}

/** SoD checker: aprueba y ejecuta la reapertura. */
export async function approveReopen(approvalRequestId: string): Promise<void> {
  await api.post(`/payments/approvals/${approvalRequestId}/reopen/approve/`, {});
}

// --- Intenciones de pago --------------------------------------------------------
export const INTENT_STATUS_LABELS: Record<string, string> = {
  INTENDED: 'Creada',
  AUTHORIZED: 'Autorizada',
  CAPTURED: 'Cobrada',
  PARTIALLY_CAPTURED: 'Cobro parcial',
  REFUNDED: 'Reembolsada',
  PARTIALLY_REFUNDED: 'Reembolso parcial',
  FAILED: 'Fallida',
  CANCELLED: 'Cancelada',
};

export interface PaymentIntentRow {
  payment_id: string;
  amount: string;
  currency: string;
  status: string;
  external_ref: string;
  payment_method: string;
  created_at: string;
}

export interface PaymentIntent extends PaymentIntentRow {
  amount_authorized: string;
  amount_captured: string;
  amount_refunded: string;
  failure_reason: string;
  cancellation_reason: string;
  authorized_at: string | null;
  captured_at: string | null;
  refunded_at: string | null;
}

export async function listPaymentIntents(): Promise<PaymentIntentRow[]> {
  const { data } = await api.get<Paginated<PaymentIntentRow>>('/payments/intents/', {
    params: PAGE,
  });
  return data.results;
}

export async function createPaymentIntent(input: {
  amount: string;
  payment_method?: string;
  external_ref?: string;
}): Promise<{ payment_id: string; status: string }> {
  const { data } = await api.post<{ payment_id: string; status: string }>('/payments/intents/', {
    ...input,
    idempotency_key: crypto.randomUUID(),
  });
  return data;
}

export async function getPaymentIntent(paymentId: string): Promise<PaymentIntent> {
  const { data } = await api.get<PaymentIntent>(`/payments/intents/${paymentId}/`);
  return data;
}

export async function authorizeIntent(paymentId: string): Promise<void> {
  await api.post(`/payments/intents/${paymentId}/authorize/`, {});
}

export async function captureIntent(paymentId: string): Promise<void> {
  await api.post(`/payments/intents/${paymentId}/capture/`, {});
}

/** SoD maker: el reembolso queda pendiente de aprobación de otra persona. */
export async function requestRefund(
  paymentId: string,
  input: { amount: string; reason?: string },
): Promise<Record<string, unknown>> {
  const { data } = await api.post<Record<string, unknown>>(
    `/payments/intents/${paymentId}/refund/`,
    { ...input, idempotency_key: crypto.randomUUID() },
  );
  return data;
}

export async function approveRefund(approvalRequestId: string): Promise<void> {
  await api.post(`/payments/approvals/${approvalRequestId}/refund/approve/`, {});
}

export async function cancelIntent(paymentId: string, reason = ''): Promise<void> {
  await api.post(`/payments/intents/${paymentId}/cancel/`, { reason });
}
