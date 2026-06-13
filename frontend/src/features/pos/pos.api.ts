/**
 * Punto de venta (retail_pos) — TPV de la estación: sesión POS → ticket sobre
 * el turno de combustible → checkout (crea venta fuel + intento de pago +
 * movimiento de caja). Compensación automática si algo falla a medio camino.
 */
import { api } from 'src/boot/axios';
import { PAGE, type Paginated } from 'src/core/api';

export const POS_TICKET_STATUS_LABELS: Record<string, string> = {
  CART_OPEN: 'Carrito abierto',
  CHECKOUT_PENDING: 'Cobro pendiente',
  PAID: 'Pagado',
  CLOSED: 'Cerrado',
  VOIDED: 'Anulado',
};

export interface PosSession {
  id: number;
  status: 'OPEN' | 'CLOSED';
  opening_amount: string;
  counted_amount: string | null;
  difference_amount: string | null;
  opened_at?: string;
  closed_at?: string | null;
}

export interface PosTicketLine {
  product: string;
  volume: string;
  volume_uom: string;
  unit_price_entered: string;
  unit_price_uom: string;
  amount_estimated?: string;
}

export interface PosTicket {
  id: number;
  status: string;
  sale_type: string;
  payment_method: string;
  customer_name: string;
  shift: number;
  sale: number | null;
  compensation_pending?: boolean;
  created_at?: string;
  lines?: PosTicketLine[];
  total_estimated?: string;
}

export async function getCurrentPosSession(): Promise<PosSession | null> {
  const { data } = await api.get<PosSession | Record<string, never>>('/retail/pos/sessions/current/');
  return data && 'id' in data ? (data as PosSession) : null;
}

export async function openPosSession(opening_amount = '0.00'): Promise<PosSession> {
  const { data } = await api.post<PosSession>('/retail/pos/sessions/open/', { opening_amount });
  return data;
}

export async function closePosSession(sessionId: number, counted_amount: string): Promise<PosSession> {
  const { data } = await api.post<PosSession>(`/retail/pos/sessions/${sessionId}/close/`, {
    counted_amount,
  });
  return data;
}

export async function listPosTickets(): Promise<PosTicket[]> {
  const { data } = await api.get<Paginated<PosTicket>>('/retail/pos/tickets/', { params: PAGE });
  return data.results;
}

export async function openPosTicket(input: {
  shift_id: number;
  sale_type?: string;
  payment_method?: string;
  customer_name?: string;
  customer_party_id?: number | null;
}): Promise<PosTicket> {
  const { data } = await api.post<PosTicket>('/retail/pos/tickets/', {
    ...input,
    idempotency_key: crypto.randomUUID(),
  });
  return data;
}

export async function checkoutPosTicket(ticketId: number, line: PosTicketLine): Promise<PosTicket> {
  const { data } = await api.post<PosTicket>(`/retail/pos/tickets/${ticketId}/checkout/`, { line });
  return data;
}

export async function retryPosCompensation(ticketId: number): Promise<void> {
  await api.post(`/retail/pos/tickets/${ticketId}/compensate/retry/`, {});
}

export async function getPosCockpit(): Promise<Record<string, unknown>> {
  const { data } = await api.get<Record<string, unknown>>('/retail/pos/cockpit/');
  return data;
}
