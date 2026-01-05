import { api } from 'src/boot/axios';

export type RoleRow = {
  id: number;
  name: string;
  description: string;
  is_active: boolean;
};

export async function listRoles(includeInactive = false) {
  const qs = includeInactive ? '?include_inactive=1' : '';
  const { data } = await api.get<{ count: number; results: RoleRow[] }>(`/rbac/roles/${qs}`);
  return data.results;
}
