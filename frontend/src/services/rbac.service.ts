import { api } from 'src/boot/axios';

export type RoleRow = {
  id: number;
  name: string;
  description: string;
  is_active: boolean;
};

type PaginatedResponse<T> = {
  count: number;
  limit: number;
  offset: number;
  results: T[];
};

type ListParams = {
  includeInactive?: boolean;
  limit?: number;
  offset?: number;
};

function buildListQuery(params?: ListParams): string {
  if (!params) return '';
  const qs = new URLSearchParams();
  if (params.includeInactive) qs.set('include_inactive', '1');
  if (typeof params.limit === 'number') qs.set('limit', String(params.limit));
  if (typeof params.offset === 'number') qs.set('offset', String(params.offset));
  const out = qs.toString();
  return out ? `?${out}` : '';
}

export async function listRoles(params?: ListParams) {
  const qs = buildListQuery(params);
  const { data } = await api.get<PaginatedResponse<RoleRow>>(`/rbac/roles/${qs}`);
  return data;
}
