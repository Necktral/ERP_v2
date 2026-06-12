/**
 * Terceros (parties) — directorio de clientes/proveedores/productores de la
 * empresa activa. Lo consumen compras, facturación, cartera y comisariato.
 */
import { api } from 'src/boot/axios';
import { PAGE, type Paginated } from 'src/core/api';

export type PartyType = 'NATURAL' | 'JURIDICAL' | 'INTERNAL';
export type PartyStatus = 'ACTIVE' | 'INACTIVE' | 'BLOCKED';
export type PartyRoleCode =
  | 'CUSTOMER'
  | 'SUPPLIER'
  | 'EMPLOYEE'
  | 'PRODUCER'
  | 'DECLARANT'
  | 'EXTERNAL_BUYER';

export interface Party {
  id: number;
  party_type: PartyType;
  display_name: string;
  legal_name: string;
  tax_id: string;
  national_id: string;
  email: string;
  phone: string;
  status: PartyStatus;
  roles: PartyRoleCode[];
  created_at: string;
}

export interface PartyInput {
  party_type: PartyType;
  display_name: string;
  legal_name?: string;
  tax_id?: string;
  national_id?: string;
  email?: string;
  phone?: string;
}

/** Etiquetas en español para chips/selects (única fuente). */
export const PARTY_ROLE_LABELS: Record<PartyRoleCode, string> = {
  CUSTOMER: 'Cliente',
  SUPPLIER: 'Proveedor',
  EMPLOYEE: 'Empleado',
  PRODUCER: 'Productor',
  DECLARANT: 'Declarante',
  EXTERNAL_BUYER: 'Comprador externo',
};

export const PARTY_TYPE_LABELS: Record<PartyType, string> = {
  NATURAL: 'Persona natural',
  JURIDICAL: 'Persona jurídica',
  INTERNAL: 'Interna del grupo',
};

export const PARTY_STATUS_LABELS: Record<PartyStatus, string> = {
  ACTIVE: 'Activo',
  INACTIVE: 'Inactivo',
  BLOCKED: 'Bloqueado',
};

export interface PartyFilters {
  q?: string;
  role?: PartyRoleCode | '';
  status?: PartyStatus | '';
  party_type?: PartyType | '';
}

export async function listParties(filters: PartyFilters = {}): Promise<Party[]> {
  const params: Record<string, string | number> = { ...PAGE };
  if (filters.q) params.q = filters.q;
  if (filters.role) params.role = filters.role;
  if (filters.status) params.status = filters.status;
  if (filters.party_type) params.party_type = filters.party_type;
  const { data } = await api.get<Paginated<Party>>('/parties/', { params });
  return data.results;
}

export async function createParty(input: PartyInput & { roles?: PartyRoleCode[] }): Promise<Party> {
  const { data } = await api.post<Party>('/parties/', input);
  return data;
}

export async function updateParty(
  partyId: number,
  patch: Partial<PartyInput> & { status?: PartyStatus },
): Promise<Party> {
  const { data } = await api.patch<Party>(`/parties/${partyId}/`, patch);
  return data;
}

export async function assignPartyRole(partyId: number, role: PartyRoleCode): Promise<Party> {
  const { data } = await api.post<Party>(`/parties/${partyId}/roles/`, { role });
  return data;
}

export async function revokePartyRole(partyId: number, role: PartyRoleCode): Promise<Party> {
  const { data } = await api.post<Party>(`/parties/${partyId}/roles/revoke/`, { role });
  return data;
}
