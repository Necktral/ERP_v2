import { api } from 'src/boot/axios';

export type PosSessionSummary = {
  id: number;
  status: 'OPEN' | 'CLOSED';
  cash_session_id: number | null;
  opened_at: string;
  opened_by: number;
  opening_amount: string;
  note?: string;
};

export type PosTicketLinePayload = {
  product: 'DIESEL' | 'GASOLINE';
  volume: string;
  volume_uom?: 'LITER' | 'GALLON' | 'GALLON_US';
  unit_price_entered: string;
  unit_price_uom?: 'PER_LITER' | 'PER_GALLON' | 'PER_GALLON_US';
  metadata?: Record<string, unknown>;
};

export type PosTicket = {
  id: number;
  status: 'CART_OPEN' | 'CHECKOUT_PENDING' | 'PAID' | 'CLOSED' | 'VOIDED';
  session_id: number;
  shift_id: number;
  external_ref: string;
  correlation_id: string;
  sale_type: string;
  payment_method: string;
  total_amount: string;
  customer_name: string;
  customer_ref: string;
  sale_id: number | null;
  payment_intent_id: string;
  cash_movement_id: number | null;
  created_at: string;
  updated_at: string;
  checkout_started_at: string | null;
  paid_at: string | null;
  closed_at: string | null;
  voided_at: string | null;
  void_reason: string;
  last_error: string;
  compensation_pending: boolean;
  compensation_attempts: number;
  compensation_last_error: string;
  compensation_next_retry_at: string | null;
  last_compensation_at: string | null;
  lines: Array<{
    id: number;
    line_no: number;
    line_type: string;
    product: string;
    volume: string;
    volume_uom: string;
    unit_price_entered: string;
    unit_price_uom: string;
    amount_estimated: string;
    metadata: Record<string, unknown>;
  }>;
  idempotency_status?: 'DUPLICATE_PROCESSED';
};

export type PosTicketList = {
  count: number;
  limit: number;
  offset: number;
  results: PosTicket[];
};

export type PosPeripheralRow = {
  id: number;
  connector_id: string;
  connector_version: string;
  device_key: string;
  device_kind: string;
  capability_level: string;
  status: string;
  last_seen_at: string;
  edge_session_id?: number | null;
  metadata: Record<string, unknown>;
};

export type PosCockpit = {
  session: {
    id: number | null;
    status: string;
    cash_session_id: number | null;
    opened_at: string | null;
    opened_by: number | null;
    opening_amount: string;
  };
  tickets: {
    pending: number;
    closed: number;
    voided: number;
  };
  compensation: {
    pending: number;
    overdue: number;
    max_pending_age_min: number;
  };
  peripherals: {
    total: number;
    online: number;
    degraded: number;
    offline: number;
  };
};

export type OpenPosTicketPayload = {
  shift_id: number;
  idempotency_key?: string;
  external_ref?: string;
  customer_name?: string;
  customer_ref?: string;
  sale_type?: 'PUBLIC' | 'INTERNAL' | 'EMPLOYEE';
  payment_method?: 'CASH' | 'TRANSFER' | 'CREDIT';
};

export type CheckoutPosTicketPayload = { line?: PosTicketLinePayload };

export async function getPosCurrentSession(): Promise<PosSessionSummary | null> {
  const { data } = await api.get<{ session: PosSessionSummary | null }>('/retail/pos/sessions/current/');
  return data.session ?? null;
}

export async function openPosSession(payload: {
  opening_amount?: string;
  note?: string;
}): Promise<PosSessionSummary> {
  const { data } = await api.post<PosSessionSummary>('/retail/pos/sessions/open/', payload);
  return data;
}

export async function closePosSession(sessionId: number, payload: { counted_amount: string; note?: string }) {
  const { data } = await api.post<{
    id: number;
    status: string;
    counted_amount: string;
    difference_amount: string;
    closed_at: string | null;
  }>(`/retail/pos/sessions/${sessionId}/close/`, payload);
  return data;
}

export async function listPosTickets(params?: { limit?: number; offset?: number }) {
  const { data } = await api.get<PosTicketList>('/retail/pos/tickets/', { params });
  return data;
}

export async function openPosTicket(payload: OpenPosTicketPayload) {
  const { data } = await api.post<PosTicket>('/retail/pos/tickets/', payload);
  return data;
}

export async function checkoutPosTicket(ticketId: number, payload?: CheckoutPosTicketPayload) {
  const { data } = await api.post<PosTicket>(`/retail/pos/tickets/${ticketId}/checkout/`, payload ?? {});
  return data;
}

export async function voidPosTicket(ticketId: number, payload?: { reason?: string }) {
  const { data } = await api.post<PosTicket>(`/retail/pos/voids/${ticketId}/`, payload ?? {});
  return data;
}

export async function retryPosTicketCompensation(ticketId: number, payload?: { reason?: string }) {
  const { data } = await api.post<PosTicket>(`/retail/pos/tickets/${ticketId}/compensate/retry/`, payload ?? {});
  return data;
}

export async function getPosCockpit() {
  const { data } = await api.get<PosCockpit>('/retail/pos/cockpit/');
  return data;
}

export async function listPosPeripherals() {
  const { data } = await api.get<{ count: number; results: PosPeripheralRow[] }>('/retail/pos/peripherals/status/');
  return data;
}

export async function upsertPosPeripheral(payload: {
  connector_id: string;
  connector_version?: string;
  device_key: string;
  device_kind: 'THERMAL_PRINTER' | 'SCANNER' | 'DRAWER' | 'SCALE' | 'PAYMENT_TERMINAL';
  capability_level?: 'supported' | 'experimental' | 'unsupported';
  status?: 'ONLINE' | 'OFFLINE' | 'DEGRADED';
  metadata?: Record<string, unknown>;
}) {
  const { data } = await api.post<{
    id: number;
    device_key: string;
    device_kind: string;
    status: string;
    capability_level: string;
    last_seen_at: string;
  }>('/retail/pos/peripherals/status/', payload);
  return data;
}
